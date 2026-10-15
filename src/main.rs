mod config;
mod upstream;

use std::sync::Arc;

use axum::{Json, Router, extract::State, http::StatusCode, response::IntoResponse, routing::get};
use serde_json::json;

use config::Settings;
use upstream::TjClient;

/// State shared by every handler.
#[derive(Clone)]
struct AppState {
    client: Arc<TjClient>,
}

/// Builds the router with every route. Tests call this directly, without a socket.
fn app(state: AppState) -> Router {
    Router::new()
        .route("/", get(hello))
        .route("/health", get(health))
        .with_state(state)
}

/// Placeholder endpoint for GET / that confirms the server is up.
async fn hello() -> &'static str {
    "Hello, World!"
}

/// Reports the upstream login state. It gets or renews the guest token first,
/// so a 503 here means the upstream could not be reached.
async fn health(State(state): State<AppState>) -> impl IntoResponse {
    let (code, status) = match state.client.ensure_token().await {
        Ok(_) => (StatusCode::OK, "ok"),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, "degraded"),
    };
    let auth = state.client.token_info().await;
    (code, Json(json!({ "status": status, "auth": auth })))
}

/// Loads .env and settings, then starts the HTTP server on port 8000.
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // The .env file is optional, but a broken one should stop the server.
    if let Err(e) = dotenvy::dotenv()
        && !e.not_found()
    {
        return Err(e.into());
    }
    tracing_subscriber::fmt::init();
    let state = AppState {
        client: Arc::new(TjClient::new(Settings::from_env()?)?),
    };
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
        app(AppState {
            client: Arc::new(client),
        })
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
