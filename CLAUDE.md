# tije-api

Rust port of the TJ Live Tracking API, built on axum. It logs in to the TransJakarta app backend (host set by `TJ_BASE_URL`), polls bus positions, and serves them to other clients over HTTP and WebSocket.

## Working rules

- Use the `ponytail` skill for all coding work. Write the smallest change that works, reach for std and existing crates before adding new ones, and skip abstractions nobody asked for. Where ponytail would leave a `ponytail:` comment on a deliberate shortcut, write `TODO:` instead.
- Every change ships with a test that covers it, and `cargo test` must pass before the work counts as done. This applies to small changes too, which overrides ponytail's "trivial code needs no test".
- Every function, test functions included, starts with a `///` doc comment saying what it does. Logic that takes more than a quick read to follow (math, state machines, concurrency, upstream quirks) also gets a `//` comment explaining why it works that way. Write comments as plain sentences with no backticks or other markdown, and run them through the humanizer like any other prose.
- Follow idiomatic Rust and axum conventions. Ponytail decides how much code to write, and these conventions decide how it looks:
  - Errors go through `Result` and `?`. `unwrap`/`expect` belong in tests or on invariants that can't fail, with the reason in the `expect` message.
  - Handlers are named `async fn`s that take extractors (`Query`, `Path`, `State`, `Json`) and return `impl IntoResponse` or `Result<_, AppError>`, where `AppError` implements `IntoResponse`.
  - Shared state goes in one `AppState` passed with `Router::with_state`. Use `Arc` and `tokio::sync` locks only where data really is shared.
  - Use `serde` derives for request/response types, `tracing` for logs (never `println!`), and keep code clean under `cargo clippy -- -D warnings`.
- Write plans in Bahasa Indonesia (plan mode, task breakdowns, proposals). Code, comments, docs and commit messages stay in English.

## Reference implementation

The original FastAPI backend lives at `/home/arter/Documents/Projects/transjakarta/transjakarta-api`. Treat it as the spec: same endpoints, query parameters, response shapes, `TJ_*` environment variables and upstream headers. Read the relevant part before porting a feature.

- `README.md`: endpoint table and request/response examples.
- `docs/backend/`: API reference (`04`), end-to-end flow (`05`), upstream auth (`06`), code structure (`07`), testing (`09`). Written in Indonesian.
- `docs/source/07-katalog-api-upstream.md`: upstream endpoint catalog from the APK analysis.
- `tests/test_api.py`: expected behaviour. Port these cases when porting a feature.

Module mapping:

| Python | Rust | Role |
|---|---|---|
| `app/config.py` | `src/config.rs` | Settings from `TJ_*` env vars and `.env` |
| `app/upstream.py` | `src/upstream.rs` | Upstream client: guest/account login, token refresh, retry once on 401 |
| `app/tracker.py` | `src/tracker.rs` | Bus position cache, radius/route filter, glide interpolation |
| `app/routes.py` | `src/routes.rs` | Polyline decoding, route normalization |
| `app/main.py` | `src/main.rs` | Router, area polling, WebSocket broadcast, background tasks |

Dependencies go one way: `main` uses everything, `upstream` uses `config`. `tracker` knows nothing about HTTP or upstream, and `upstream` knows nothing about areas or the tracker.

## Commands

```sh
cargo run                       # server on 0.0.0.0:8000
cargo test
cargo clippy -- -D warnings
cargo fmt
git config core.hooksPath .githooks   # once per clone: pre-commit hook formats staged .rs files
```

## Conventions

- Add a crate only once code uses it. The expected set is `axum` (with `ws`), `tokio`, `reqwest` (rustls, json), `serde`/`serde_json`, `tracing`/`tracing-subscriber`, and `dotenvy` for `.env`.
- Test endpoints in-process: build the router with `app()` and call it with `tower::ServiceExt::oneshot`, no open port needed.
- Tests never call the real upstream. Start a small axum router on `127.0.0.1:0` as a fake upstream and point `TJ_BASE_URL` at it, the same way the Python tests use `httpx.MockTransport`. Tests must ignore `.env`.
- Never log or return tokens and passwords. Account endpoints are read-only; don't expose anything that edits a profile or makes a payment.
- Keep the upstream host out of the repo: code, docs, tests and logs. It only lives in `.env` as `TJ_BASE_URL`. Error messages name the method and path, never the full URL.
- The upstream is not a public API. Clients watching the same area share one poll, so don't add per-client upstream requests.
