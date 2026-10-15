//! Client for the TransJakarta app backend: guest session tokens and the bus position feed.

use std::fmt;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::header::{ACCEPT, HeaderMap, HeaderName, HeaderValue};
use serde::Serialize;
use serde_json::{Value, json};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::config::Settings;

/// Renew the access token this many seconds before it expires.
const TOKEN_MARGIN: f64 = 300.0;
/// Skip a refresh token that expires within this many seconds.
const REFRESH_MARGIN: f64 = 60.0;
// TODO: fixed 3 rounds with a linear backoff; turn these into settings if upstream outages need longer retries.
/// How many rounds of refresh and guest login to try before giving up.
const MAX_ATTEMPTS: u32 = 3;
/// Wait this long times the attempt number between rounds.
const RETRY_STEP: Duration = Duration::from_millis(200);

/// A failed call to the upstream. The message names the method and path, never the full URL.
#[derive(Debug)]
pub struct UpstreamError {
    status: Option<u16>,
    message: String,
}

impl UpstreamError {
    /// Builds an error that has no HTTP status, such as a network failure.
    fn new(message: impl Into<String>) -> Self {
        Self {
            status: None,
            message: message.into(),
        }
    }
}

impl fmt::Display for UpstreamError {
    /// Prints the message.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for UpstreamError {}

/// Login state as reported by GET /health. It never holds the tokens themselves.
#[derive(Serialize)]
pub struct TokenInfo {
    mode: &'static str,
    logged_in_as: Option<&'static str>,
    // Account login does not exist yet, so this is always null. Kept for parity with the Python API.
    email: Option<String>,
    has_token: bool,
    valid_until: Option<u64>,
    last_error: Option<String>,
}

/// Current session tokens. Times are unix seconds, the format the upstream uses.
#[derive(Default)]
struct Tokens {
    token: String,
    valid_until: f64,
    refresh: String,
    refresh_valid_until: f64,
    logged_in_as: Option<&'static str>,
    last_error: Option<String>,
}

impl Tokens {
    /// Takes the token fields from a login or refresh response. They sit either at
    /// the top level or inside a data object.
    fn store(&mut self, body: &Value) -> Result<(), UpstreamError> {
        let d = body.get("data").filter(|d| d.is_object()).unwrap_or(body);
        let token = d
            .get("token")
            .and_then(Value::as_str)
            .filter(|t| !t.is_empty())
            .ok_or_else(|| UpstreamError::new("auth response has no token"))?;
        self.token = token.to_owned();
        self.valid_until = d
            .get("token_valid_until")
            .and_then(Value::as_f64)
            .unwrap_or_else(|| now() + 3600.0);
        // A refresh response may leave out the refresh token; the old one stays usable then.
        if let Some(r) = d
            .get("refresh_token")
            .and_then(Value::as_str)
            .filter(|r| !r.is_empty())
        {
            self.refresh = r.to_owned();
        }
        self.refresh_valid_until = d
            .get("refresh_token_valid_until")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        Ok(())
    }
}

/// Talks to the upstream with the device headers the Android app sends.
pub struct TjClient {
    http: reqwest::Client,
    base_url: String,
    // Held for the whole renewal, network calls included, so concurrent requests
    // wait for one login instead of each starting their own.
    tokens: Mutex<Tokens>,
}

impl TjClient {
    /// Builds the HTTP client with the device headers and timeout from settings.
    pub fn new(settings: Settings) -> Result<Self, Box<dyn std::error::Error>> {
        let mut headers = HeaderMap::new();
        for (name, value) in [
            ("x-app-version", &settings.app_version),
            ("x-device-id", &settings.device_id),
            ("x-lang", &settings.lang),
            ("x-fcm-token", &settings.fcm_token),
            ("x-app-os", &settings.app_os),
            ("x-app-os-version", &settings.app_os_version),
            ("x-app-platform", &settings.app_platform),
            ("x-device-model", &settings.device_model),
        ] {
            headers.insert(HeaderName::from_static(name), HeaderValue::try_from(value)?);
        }
        headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
        let http = reqwest::Client::builder()
            .default_headers(headers)
            .timeout(settings.timeout)
            .build()?;
        Ok(Self {
            http,
            base_url: settings.base_url.trim_end_matches('/').to_owned(),
            tokens: Mutex::default(),
        })
    }

    /// Returns an access token that stays valid for at least TOKEN_MARGIN seconds.
    ///
    /// A missing or expiring token is renewed: the refresh token first, then a new
    /// guest session if the refresh fails. Up to MAX_ATTEMPTS rounds run before the
    /// last error is returned. With force set, the current token is renewed even if
    /// it looks valid, which is what a 401 from the upstream calls for.
    pub async fn ensure_token(&self, force: bool) -> Result<String, UpstreamError> {
        let mut t = self.tokens.lock().await;
        if !force && !t.token.is_empty() && now() < t.valid_until - TOKEN_MARGIN {
            return Ok(t.token.clone());
        }
        let mut attempt = 1;
        loop {
            match self.renew(&mut t).await {
                Ok(()) => {
                    t.last_error = None;
                    return Ok(t.token.clone());
                }
                Err(e) => {
                    t.last_error = Some(e.to_string());
                    if attempt == MAX_ATTEMPTS {
                        error!("could not get an upstream token after {attempt} attempts: {e}");
                        return Err(e);
                    }
                    warn!("token attempt {attempt} failed: {e}");
                }
            }
            tokio::time::sleep(RETRY_STEP * attempt).await;
            attempt += 1;
        }
    }

    /// Fetches every bus within radius_km of a point from POST /v1/bus/offline.
    /// A 401 gets one retry with a fresh token, in case the upstream revoked the old one early.
    pub async fn offline_buses(
        &self,
        lat: f64,
        lon: f64,
        radius_km: f64,
    ) -> Result<Vec<Value>, UpstreamError> {
        const PATH: &str = "/v1/bus/offline";
        let body = json!({
            "latitude": lat,
            "longitude": lon,
            "radius": radius_km,
            "event": "change_loc",
        });
        let token = self.ensure_token(false).await?;
        let mut resp = match self.post(PATH, body.clone(), Some(&token)).await {
            Err(e) if e.status == Some(401) => {
                warn!("{e}; renewing the token and retrying once");
                let token = self.ensure_token(true).await?;
                self.post(PATH, body, Some(&token)).await?
            }
            other => other?,
        };
        Ok(match resp.get_mut("data").map(Value::take) {
            Some(Value::Array(buses)) => buses,
            _ => Vec::new(),
        })
    }

    /// Reports the login state without exposing any token.
    pub async fn token_info(&self) -> TokenInfo {
        let t = self.tokens.lock().await;
        TokenInfo {
            mode: "guest",
            logged_in_as: t.logged_in_as,
            email: None,
            has_token: !t.token.is_empty(),
            valid_until: (t.valid_until > 0.0).then_some(t.valid_until as u64),
            last_error: t.last_error.clone(),
        }
    }

    /// Runs one renewal round: use the refresh token while it is still valid, and
    /// start a new guest session when there is none or the refresh fails.
    async fn renew(&self, t: &mut Tokens) -> Result<(), UpstreamError> {
        if !t.refresh.is_empty() && now() < t.refresh_valid_until - REFRESH_MARGIN {
            let body = json!({ "refresh_token": t.refresh });
            match self.post("/v1/auth/token/refresh", body, None).await {
                Ok(b) if t.store(&b).is_ok() => {
                    info!("upstream token refreshed");
                    return Ok(());
                }
                Ok(_) => warn!("token refresh response had no token; starting a guest session"),
                Err(e) => warn!("token refresh failed ({e}); starting a guest session"),
            }
        }
        let body = self.post("/v1/auth/login/guest", json!({}), None).await?;
        t.store(&body)?;
        t.logged_in_as = Some("guest");
        info!(
            "logged in as guest, token valid until {}",
            t.valid_until as u64
        );
        Ok(())
    }

    /// Sends a JSON POST, with a bearer token when one is given. Network failures,
    /// HTTP errors and non-JSON bodies all become an UpstreamError.
    async fn post(
        &self,
        path: &str,
        body: Value,
        token: Option<&str>,
    ) -> Result<Value, UpstreamError> {
        let err = |detail: String| UpstreamError::new(format!("POST {path}: {detail}"));
        let mut req = self
            .http
            .post(format!("{}{path}", self.base_url))
            .json(&body);
        if let Some(token) = token {
            req = req.bearer_auth(token);
        }
        // without_url keeps the upstream host out of error messages and logs.
        let resp = req
            .send()
            .await
            .map_err(|e| err(e.without_url().to_string()))?;
        let status = resp.status();
        let text = resp
            .text()
            .await
            .map_err(|e| err(e.without_url().to_string()))?;
        if status.is_client_error() || status.is_server_error() {
            let snippet: String = text.chars().take(200).collect();
            return Err(UpstreamError {
                status: Some(status.as_u16()),
                ..err(format!("HTTP {} {snippet}", status.as_u16()))
            });
        }
        serde_json::from_str(&text).map_err(|_| err("response is not JSON".into()))
    }
}

/// Current unix time in seconds.
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0.0, |d| d.as_secs_f64())
}

/// Fake upstream for tests: an axum server on a random local port.
#[cfg(test)]
pub mod fake {
    use std::sync::{Arc, Mutex};

    use axum::{
        Json, Router,
        extract::State,
        http::{HeaderMap, StatusCode, Uri},
        routing::post,
    };
    use serde_json::{Value, json};

    /// What the fake has seen, and knobs that make it misbehave.
    pub struct FakeState {
        /// Path, JSON body and headers of every request, in order.
        pub calls: Vec<(String, Value, HeaderMap)>,
        /// Lifetime in seconds of the access tokens it hands out.
        pub ttl: f64,
        /// Answer this many guest logins with HTTP 500 before succeeding.
        pub fail_logins: u32,
        /// Answer every refresh with HTTP 401.
        pub fail_refresh: bool,
        /// Answer the next bus poll with HTTP 401, as if the token was revoked.
        pub revoke_token: bool,
        /// What POST /v1/bus/offline returns in data.
        pub buses: Vec<Value>,
        issued: u32,
    }

    pub type Fake = Arc<Mutex<FakeState>>;

    /// Creates a well-behaved fake whose tokens last a day.
    pub fn fake() -> Fake {
        Arc::new(Mutex::new(FakeState {
            calls: Vec::new(),
            ttl: 86400.0,
            fail_logins: 0,
            fail_refresh: false,
            revoke_token: false,
            buses: Vec::new(),
            issued: 0,
        }))
    }

    /// Counts the requests made to one path.
    pub fn count(fake: &Fake, path: &str) -> usize {
        paths(fake).iter().filter(|p| *p == path).count()
    }

    /// Lists the paths requested so far.
    pub fn paths(fake: &Fake) -> Vec<String> {
        fake.lock()
            .unwrap()
            .calls
            .iter()
            .map(|c| c.0.clone())
            .collect()
    }

    /// Starts the fake and returns its base URL.
    pub async fn start(fake: &Fake) -> String {
        let app = Router::new()
            .route("/{*path}", post(handle))
            .with_state(fake.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        url
    }

    /// Records the request, then answers login and refresh with numbered tokens
    /// (tok1, ref1, ...) and bus polls with the configured buses.
    async fn handle(
        State(fake): State<Fake>,
        uri: Uri,
        headers: HeaderMap,
        Json(body): Json<Value>,
    ) -> (StatusCode, Json<Value>) {
        let mut s = fake.lock().unwrap();
        s.calls.push((uri.path().to_owned(), body, headers));
        match uri.path() {
            "/v1/auth/login/guest" if s.fail_logins > 0 => {
                s.fail_logins -= 1;
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({"message": "down"})),
                )
            }
            "/v1/auth/token/refresh" if s.fail_refresh => (
                StatusCode::UNAUTHORIZED,
                Json(json!({"message": "invalid refresh token"})),
            ),
            "/v1/auth/login/guest" | "/v1/auth/token/refresh" => {
                s.issued += 1;
                let now = super::now();
                (
                    StatusCode::OK,
                    Json(json!({
                        "token": format!("tok{}", s.issued),
                        "token_valid_until": now + s.ttl,
                        "refresh_token": format!("ref{}", s.issued),
                        "refresh_token_valid_until": now + s.ttl + 3600.0,
                    })),
                )
            }
            "/v1/bus/offline" if s.revoke_token => {
                s.revoke_token = false;
                (
                    StatusCode::UNAUTHORIZED,
                    Json(json!({"message": "Unauthorized, token is required"})),
                )
            }
            "/v1/bus/offline" => (StatusCode::OK, Json(json!({"data": s.buses}))),
            _ => (StatusCode::NOT_FOUND, Json(json!({}))),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::fake::{Fake, fake, paths, start};
    use super::*;

    /// Builds a client that talks to the given fake.
    async fn client(fake: &Fake) -> TjClient {
        let mut settings = Settings::new(start(fake).await);
        settings.device_id = "test-device".into();
        TjClient::new(settings).unwrap()
    }

    /// Token fields are read from the top level or from data, and a body without a token is an error.
    #[test]
    fn store_reads_both_response_shapes() {
        let mut t = Tokens::default();
        t.store(&json!({"token": "a", "token_valid_until": 100, "refresh_token": "r"}))
            .unwrap();
        assert_eq!(
            (t.token.as_str(), t.valid_until, t.refresh.as_str()),
            ("a", 100.0, "r")
        );

        t.store(&json!({"data": {"token": "b", "token_valid_until": 200}}))
            .unwrap();
        assert_eq!((t.token.as_str(), t.valid_until), ("b", 200.0));
        assert_eq!(t.refresh, "r", "missing refresh_token keeps the old one");

        assert!(t.store(&json!({"data": {}})).is_err());
    }

    /// The first call logs in as guest and later calls reuse that token.
    #[tokio::test]
    async fn guest_login_then_reuse() {
        let f = fake();
        let c = client(&f).await;
        assert_eq!(c.ensure_token(false).await.unwrap(), "tok1");
        assert_eq!(c.ensure_token(false).await.unwrap(), "tok1");
        assert_eq!(paths(&f), ["/v1/auth/login/guest"]);
    }

    /// Login sends the device headers and no Authorization header.
    #[tokio::test]
    async fn guest_login_sends_device_headers() {
        let f = fake();
        client(&f).await.ensure_token(false).await.unwrap();
        let s = f.lock().unwrap();
        let (_, body, headers) = &s.calls[0];
        assert_eq!(body, &json!({}));
        assert!(headers.get("authorization").is_none());
        assert_eq!(headers["x-app-version"], "3.0.4");
        assert_eq!(headers["x-device-id"], "test-device");
        assert_eq!(headers["x-device-model"], "Google|Pixel 8");
    }

    /// A token inside the renewal margin is renewed with the refresh token, not a new guest login.
    #[tokio::test]
    async fn expiring_token_is_refreshed() {
        let f = fake();
        f.lock().unwrap().ttl = 10.0;
        let c = client(&f).await;
        c.ensure_token(false).await.unwrap();
        assert_eq!(c.ensure_token(false).await.unwrap(), "tok2");
        assert_eq!(
            paths(&f),
            ["/v1/auth/login/guest", "/v1/auth/token/refresh"]
        );
        assert_eq!(
            f.lock().unwrap().calls[1].1,
            json!({"refresh_token": "ref1"})
        );
    }

    /// When the refresh is rejected, a new guest session replaces it.
    #[tokio::test]
    async fn failed_refresh_falls_back_to_guest_login() {
        let f = fake();
        {
            let mut s = f.lock().unwrap();
            s.ttl = 10.0;
            s.fail_refresh = true;
        }
        let c = client(&f).await;
        c.ensure_token(false).await.unwrap();
        assert_eq!(c.ensure_token(false).await.unwrap(), "tok2");
        assert_eq!(
            paths(&f),
            [
                "/v1/auth/login/guest",
                "/v1/auth/token/refresh",
                "/v1/auth/login/guest"
            ]
        );
    }

    /// One failed login is retried and the second attempt succeeds.
    #[tokio::test]
    async fn failed_login_is_retried() {
        let f = fake();
        f.lock().unwrap().fail_logins = 1;
        let c = client(&f).await;
        assert_eq!(c.ensure_token(false).await.unwrap(), "tok1");
        assert_eq!(paths(&f).len(), 2);
        assert!(c.token_info().await.last_error.is_none());
    }

    /// A bus poll sends the bearer token and the area payload, and returns data.
    #[tokio::test]
    async fn offline_buses_sends_token_and_area() {
        let f = fake();
        f.lock().unwrap().buses = vec![json!({"bus_body_no": "TJ-1"})];
        let c = client(&f).await;
        let buses = c.offline_buses(-6.1754, 106.8272, 60.0).await.unwrap();
        assert_eq!(buses, [json!({"bus_body_no": "TJ-1"})]);
        let s = f.lock().unwrap();
        let (path, body, headers) = &s.calls[1];
        assert_eq!(path, "/v1/bus/offline");
        assert_eq!(headers["authorization"], "Bearer tok1");
        assert_eq!(
            body,
            &json!({"latitude": -6.1754, "longitude": 106.8272, "radius": 60.0, "event": "change_loc"})
        );
    }

    /// A 401 on a bus poll renews the token and retries once with the new one.
    #[tokio::test]
    async fn offline_buses_retries_once_after_401() {
        let f = fake();
        let c = client(&f).await;
        c.ensure_token(false).await.unwrap();
        f.lock().unwrap().revoke_token = true;
        c.offline_buses(-6.1754, 106.8272, 1.0).await.unwrap();
        assert_eq!(
            paths(&f),
            [
                "/v1/auth/login/guest",
                "/v1/bus/offline",
                "/v1/auth/token/refresh",
                "/v1/bus/offline"
            ]
        );
        assert_eq!(f.lock().unwrap().calls[3].2["authorization"], "Bearer tok2");
    }

    /// After MAX_ATTEMPTS failed logins the error comes back and is kept in last_error.
    #[tokio::test]
    async fn gives_up_after_max_attempts() {
        let f = fake();
        f.lock().unwrap().fail_logins = 99;
        let c = client(&f).await;
        let e = c.ensure_token(false).await.unwrap_err();
        assert!(
            e.to_string()
                .starts_with("POST /v1/auth/login/guest: HTTP 500")
        );
        assert_eq!(paths(&f).len(), MAX_ATTEMPTS as usize);
        let info = c.token_info().await;
        assert!(!info.has_token);
        assert!(info.last_error.unwrap().contains("HTTP 500"));
    }
}
