# tije-api

Rust port of the TJ Live Tracking API, built on [axum](https://github.com/tokio-rs/axum). When finished, it will serve live TransJakarta bus positions over HTTP and WebSocket. The original FastAPI version lives in `../transjakarta-api`.

So far the server logs in to the TransJakarta app backend as a guest, streams live bus positions over `WS /ws`, and reports its state on `/health`.

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
  },
  "live": { "buses": 3931, "ws_clients": 2 }
}
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Returns `Hello, World!` |
| GET | `/health` | Upstream login state and live feed counters. Gets or renews the guest token first. Returns 503 with `"status": "degraded"` and `last_error` when no token could be obtained |
| WS | `/ws?lat=&lon=&radius_km=&routes=` | Live bus positions: one snapshot, then deltas |

## Live bus feed

One background poller fetches every bus from `POST /v1/bus/offline`: a 60 km radius around Monas, which reaches the farthest buses near Bogor (about 48 km out). It polls every `TJ_POLL_SECONDS` (default 0.5) while at least one WebSocket client is connected, and stops polling when the last one leaves. A poll never starts before the previous one finishes, so the upstream gets one request at a time no matter how many clients there are. A full poll currently takes about 2 seconds (roughly 3,900 buses, 2 MB), so in practice updates arrive about every 2 seconds.

Every parameter of `WS /ws` is optional:

| Parameter | Meaning |
|---|---|
| `lat`, `lon` | Only buses within `radius_km` of this point. Must be given together, inside lat -7.5..-5.5 and lon 106.0..107.5 |
| `radius_km` | Radius around `lat`/`lon`, default 1, at most 60 |
| `routes` | Comma-separated route codes, such as `4,4D`. Case does not matter |

Without parameters the client gets every bus. Bad parameters get HTTP 400 instead of a WebSocket. A bus's position is its `snap_latitude`/`snap_longitude` when the upstream sends them, otherwise `latitude`/`longitude`.

The first message holds every matching bus, exactly as the upstream sent it:

```json
{"type": "snapshot", "buses": [{"bus_body_no": "MYS-17084", "route_code": "1", "latitude": -6.19544, "longitude": 106.8233, "...": "..."}]}
```

After that, the server only sends what changed, and nothing at all when nothing did:

```json
{"type": "delta", "upsert": [{"bus_body_no": "MYS-17084", "latitude": -6.19561}], "remove": ["TJ-001"]}
```

`upsert` carries new buses whole, and known buses with only `bus_body_no` and the fields that changed. `remove` lists buses that left the upstream data or the client's filter. A client keeps its own map:

```js
const buses = new Map();
const ws = new WebSocket("ws://localhost:8000/ws?lat=-6.1754&lon=106.8272&radius_km=2");
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.type === "snapshot") {
    buses.clear();
    for (const b of m.buses) buses.set(b.bus_body_no, b);
  } else {
    for (const b of m.upsert) buses.set(b.bus_body_no, { ...buses.get(b.bus_body_no), ...b });
    for (const no of m.remove) buses.delete(no);
  }
};
```

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
