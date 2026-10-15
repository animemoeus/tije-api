# tije-api

Rust port of the TJ Live Tracking API, built on [axum](https://github.com/tokio-rs/axum). When finished, it will serve live TransJakarta bus positions over HTTP and WebSocket. The original FastAPI version lives in `../transjakarta-api`.

Right now the server has a single hello-world endpoint.

## Requirements

Rust 1.85 or newer (the crate uses edition 2024).

## Running

```sh
cargo run
```

The server listens on `0.0.0.0:8000`.

```sh
curl http://localhost:8000/
# Hello, World!
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Returns `Hello, World!` |

## Development

Enable the pre-commit hook once per clone. It runs `rustfmt` on staged `.rs` files and re-stages them:

```sh
git config core.hooksPath .githooks
```

```sh
cargo test
cargo clippy -- -D warnings
cargo fmt
```
