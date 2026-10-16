mod config;
mod live;
mod routes;
mod upstream;

use std::sync::Arc;

use axum::{
    Json, Router,
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
};
use serde_json::json;
use tokio::sync::watch;
use tower_http::cors::CorsLayer;

use config::Settings;
use live::Feed;
use routes::RouteCache;
use upstream::{TjClient, UpstreamError};

/// State shared by every handler.
#[derive(Clone)]
struct AppState {
    client: Arc<TjClient>,
    feed: Feed,
    routes: Arc<RouteCache>,
}

impl AppState {
    /// Wraps the upstream client with an empty bus feed and an empty route cache.
    fn new(client: TjClient) -> Self {
        Self {
            client: Arc::new(client),
            feed: Arc::new(watch::Sender::new(None)),
            routes: Arc::default(),
        }
    }
}

/// Errors a handler can answer with. Each becomes a JSON body with a detail field.
enum AppError {
    /// The request itself is wrong: 400.
    BadRequest(String),
    /// The upstream failed: 502.
    Upstream(UpstreamError),
}

impl From<UpstreamError> for AppError {
    /// Lets handlers use the question mark on upstream calls.
    fn from(e: UpstreamError) -> Self {
        Self::Upstream(e)
    }
}

impl IntoResponse for AppError {
    /// Answers with the status and a detail message. Upstream errors name the
    /// method and path only, never the host.
    fn into_response(self) -> Response {
        let (status, detail) = match self {
            Self::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            Self::Upstream(e) => (StatusCode::BAD_GATEWAY, format!("upstream error: {e}")),
        };
        (status, Json(json!({ "detail": detail }))).into_response()
    }
}

/// Builds the router with every route. Tests call this directly, without a socket.
/// CORS is open to every origin, like the Python API, so the frontend can live elsewhere.
fn app(state: AppState) -> Router {
    Router::new()
        .route("/", get(hello))
        .route("/health", get(health))
        .route("/ws", get(live::ws))
        .route("/buses/{bus_body_no}", get(live::bus_events))
        .route("/route-types", get(routes::route_types))
        .route("/routes", get(routes::routes))
        .route("/stops", get(routes::stops))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

/// Placeholder endpoint for GET / that confirms the server is up.
async fn hello() -> &'static str {
    "Hello, World!"
}

/// Reports the upstream login state. It gets or renews the guest token first,
/// so a 503 here means the upstream could not be reached.
async fn health(State(state): State<AppState>) -> impl IntoResponse {
    let (code, status) = match state.client.ensure_token(false).await {
        Ok(_) => (StatusCode::OK, "ok"),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, "degraded"),
    };
    let auth = state.client.token_info().await;
    let buses = state.feed.borrow().as_ref().map_or(0, |b| b.len());
    // Every WebSocket client and bus event stream counts as one listener of the feed.
    let live = json!({ "buses": buses, "clients": state.feed.receiver_count() });
    (
        code,
        Json(json!({ "status": status, "auth": auth, "live": live })),
    )
}

/// Loads .env and settings, starts the bus poller, then serves HTTP on port 8000.
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // The .env file is optional, but a broken one should stop the server.
    if let Err(e) = dotenvy::dotenv()
        && !e.not_found()
    {
        return Err(e.into());
    }
    tracing_subscriber::fmt::init();
    let settings = Settings::from_env()?;
    let poll = settings.poll;
    let state = AppState::new(TjClient::new(settings)?);
    tokio::spawn(live::poller(state.client.clone(), state.feed.clone(), poll));
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8000").await?;
    axum::serve(listener, app(state)).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::upstream::fake::{Fake, fake, start};
    use axum::{body::Body, http::Request};
    use serde_json::Value;
    use tower::ServiceExt;

    /// Builds the app with its upstream pointed at the given fake.
    async fn test_app(fake: &Fake) -> Router {
        let client = TjClient::new(Settings::new(start(fake).await)).unwrap();
        app(AppState::new(client))
    }

    /// Sends GET to the path and returns the status and raw body.
    async fn get(app: Router, path: &str) -> (StatusCode, String) {
        let res = app
            .oneshot(Request::get(path).body(Body::empty()).unwrap())
            .await
            .unwrap();
        let status = res.status();
        let body = axum::body::to_bytes(res.into_body(), usize::MAX)
            .await
            .unwrap();
        (status, String::from_utf8(body.to_vec()).unwrap())
    }

    /// GET / answers 200 with the hello world text.
    #[tokio::test]
    async fn hello_world() {
        let (status, body) = get(test_app(&fake()).await, "/").await;
        assert_eq!(status, 200);
        assert_eq!(body, "Hello, World!");
    }

    /// GET /health logs in as guest and reports it without leaking the token.
    #[tokio::test]
    async fn health_ok() {
        let (status, body) = get(test_app(&fake()).await, "/health").await;
        assert_eq!(status, 200);
        assert!(!body.contains("tok1"), "token leaked: {body}");
        let v: Value = serde_json::from_str(&body).unwrap();
        assert_eq!(v["status"], "ok");
        assert_eq!(v["auth"]["has_token"], true);
        assert_eq!(v["auth"]["logged_in_as"], "guest");
        assert_eq!(v["auth"]["last_error"], Value::Null);
        assert_eq!(v["live"], json!({"buses": 0, "clients": 0}));
    }

    /// Any origin may call the API, which the frontend on its own domain needs.
    #[tokio::test]
    async fn cors_allows_any_origin() {
        let req = Request::get("/")
            .header("origin", "https://tije.info")
            .body(Body::empty())
            .unwrap();
        let res = test_app(&fake()).await.oneshot(req).await.unwrap();
        assert_eq!(res.headers()["access-control-allow-origin"], "*");
    }

    /// GET /health answers 503 with the last error when every login attempt fails.
    #[tokio::test]
    async fn health_degraded_when_upstream_fails() {
        let f = fake();
        f.lock().unwrap().fail_logins = 99;
        let (status, body) = get(test_app(&f).await, "/health").await;
        assert_eq!(status, 503);
        let v: Value = serde_json::from_str(&body).unwrap();
        assert_eq!(v["status"], "degraded");
        assert_eq!(v["auth"]["has_token"], false);
        assert!(
            v["auth"]["last_error"]
                .as_str()
                .unwrap()
                .contains("HTTP 500")
        );
    }
}
