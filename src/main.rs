use axum::{Router, routing::get};

/// Builds the router with every route. Tests call this directly, without a socket.
fn app() -> Router {
    Router::new().route("/", get(hello))
}

/// Placeholder endpoint for GET / that confirms the server is up.
async fn hello() -> &'static str {
    "Hello, World!"
}

/// Starts the HTTP server on port 8000.
#[tokio::main]
async fn main() -> std::io::Result<()> {
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8000").await?;
    axum::serve(listener, app()).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Request};
    use tower::ServiceExt;

    /// GET / answers 200 with the hello world text.
    #[tokio::test]
    async fn hello_world() {
        let res = app()
            .oneshot(Request::get("/").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(res.status(), 200);
        let body = axum::body::to_bytes(res.into_body(), usize::MAX)
            .await
            .unwrap();
        assert_eq!(body, "Hello, World!");
    }
}
