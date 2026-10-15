# tije-api

Rust port of the TJ Live Tracking API, built on [axum](https://github.com/tokio-rs/axum). When finished, it will serve live TransJakarta bus positions over HTTP and WebSocket. The original FastAPI version lives in `../transjakarta-api`.

So far the server logs in to the TransJakarta app backend as a guest and reports that session on `/health`.

## Requirements

Rust 1.88 or newer (edition 2024 with let chains).

## Configuration

Settings come from `TJ_*` environment variables or a `.env` file:

```sh
cp .env.example .env
```

`TJ_BASE_URL` is required and has no default. Set it to the upstream base URL, which stays out of the repo. The other settings are optional and default to the values the Android app sends; `.env.example` lists them.

## Running

```sh
cargo run
```

The server listens on `0.0.0.0:8000`.

```sh
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "auth": {
    "mode": "guest",
    "logged_in_as": "guest",
    "email": null,
    "has_token": true,
    "valid_until": 1791987415,
    "last_error": null
  }
}
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Returns `Hello, World!` |
| GET | `/health` | Upstream login state. Gets or renews the guest token first. Returns 503 with `"status": "degraded"` and `last_error` when no token could be obtained |

## Upstream token

The server keeps one guest session for every request.

1. A token with more than 5 minutes left is reused.
2. Otherwise the refresh token is tried first, while it is still valid.
3. If there is no refresh token or the refresh fails, the server starts a new guest session.
4. Steps 2 and 3 run up to 3 times, 200 ms and then 400 ms apart, before the request fails.

Tokens never appear in responses or logs.

## Development

Enable the pre-commit hook once per clone. It runs `rustfmt` on staged `.rs` files and re-stages them:

```sh
git config core.hooksPath .githooks
```

```sh
cargo test
cargo clippy --all-targets -- -D warnings
cargo fmt
```

Tests run against a fake upstream on a local port and never touch the real one.
