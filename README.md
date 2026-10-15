# tije-api

Rust port of the TJ Live Tracking API, built on [axum](https://github.com/tokio-rs/axum). When finished, it will serve live TransJakarta bus positions over HTTP and WebSocket. The original FastAPI version lives in `../transjakarta-api`.

The server logs in to the TransJakarta app backend as a guest. It serves route types and route geometry, streams live bus positions over `WS /ws`, follows one bus over an event stream, and reports its state on `/health`.

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
  "live": { "buses": 3914, "clients": 2 }
}
```

`live.clients` counts every open `/ws` connection and `/buses/{bus_body_no}` stream.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Returns `Hello, World!` |
| GET | `/health` | Upstream login state and live feed counters. Gets or renews the guest token first. Returns 503 with `"status": "degraded"` and `last_error` when no token could be obtained |
| GET | `/route-types` | Every route type with how many routes the upstream has of it |
| GET | `/routes?type=` | Path and stops of every route of one or more types |
| WS | `/ws?routes=` | Live bus positions: one snapshot, then deltas |
| GET | `/buses/{bus_body_no}` | Event stream that follows one bus |

CORS allows every origin (`Access-Control-Allow-Origin: *`), so a frontend on another domain can call the API.

Errors come back as JSON with a `detail` field: 400 for a bad request, 502 when the upstream fails. Upstream errors name the method and path, never the host.

## Routes

`GET /route-types` lists the seven route types the upstream uses in `route_desc`, in a fixed order:

```json
{"types": [{"type": "BRT", "routes": 30}, {"type": "Angkutan Umum Integrasi", "routes": 64}, {"type": "Mikrotrans", "routes": 98}, {"type": "Transjabodetabek", "routes": 18}, {"type": "Royaltrans", "routes": 10}, {"type": "Rusun", "routes": 14}, {"type": "Bus Wisata", "routes": 3}]}
```

`GET /routes?type=BRT,Mikrotrans` takes one or more of those types, comma-separated and in any case. Leave `type` out for every route. An unknown type returns 400. Routes come back in natural order (1, 1A, 2, 4D, 10, JAK.10):

```json
{
  "types": ["BRT", "Mikrotrans"],
  "routes": [{
    "route_code": "1", "route_name": "Blok M - Kota", "route_type": "BRT",
    "route_color": "D62126", "route_text_color": "FFFFFF",
    "directions": [{
      "direction": "outbound", "trip_id": "1-R07", "headsign": "Kota",
      "path": [[-6.24382, 106.80071], [-6.24301, 106.80078]],
      "stops": [{"stop_id": "H00093P", "name": "Kali Besar", "lat": -6.135355, "lon": 106.81143, "type": "halte"}]
    }]
  }]
}
```

`path` points are `[lat, lon]`, decoded from the upstream polyline. A direction without a polyline falls back to straight lines between its stops. A route the upstream doesn't know, or one with no path, is left out. The route list and each route detail are cached for an hour, so only the first call after a restart is slow (about 2 seconds for BRT and Mikrotrans together, 128 routes).

## Live bus feed

One background poller fetches every bus from `POST /v1/bus/offline`: a 60 km radius around Monas, which reaches the farthest buses near Bogor (about 48 km out). It polls every `TJ_POLL_SECONDS` (default 0.5) while at least one `/ws` client or `/buses/{bus_body_no}` stream is open, and stops when the last one leaves. A poll never starts before the previous one finishes, so the upstream gets one request at a time no matter how many clients there are. A full poll takes 1.5 to 2 seconds (roughly 3,900 buses, 2 MB), so in practice updates arrive that often.

### Bus fields

Every bus carries the upstream fields plus a few derived ones, the same ones the Python API adds:

| Field | Meaning |
|---|---|
| `latitude`, `longitude` | Route-snapped position (`snap_latitude`/`snap_longitude`) when the upstream has one, otherwise the reported position |
| `raw_latitude`, `raw_longitude` | Position as the bus reported it. These change only when the bus sends a new GPS fix |
| `type` | `BRT`, `Mikrotrans` or `Non-BRT` |
| `next_stop_name`, `prev_stop_name` | `next_stops`/`prev_stops` without the stop code, so `H00251P-Tosari` becomes `Tosari` |

The upstream sends `speed`, `timestamp` and `estimated_time_next_stops` but often as 0.

### WS /ws

`routes` is the only parameter: comma-separated route codes such as `1,4D,JAK.10`, in any case. Leave it out for every bus. Other parameters (such as `lat`, `lon`, `radius_km` or `mode`) are ignored.

The first message holds every matching bus:

```json
{"type": "snapshot", "buses": [{"bus_body_no": "BMP-220253", "route_code": "1", "type": "BRT", "latitude": -6.181174, "raw_latitude": -6.181174, "next_stop_name": "Monumen Nasional", "...": "..."}]}
```

After that, the server only sends what changed, and nothing at all when nothing did:

```json
{"type": "delta", "upsert": [{"bus_body_no": "BMP-220253", "latitude": -6.18102, "raw_latitude": -6.18102}], "remove": ["TJ-001"]}
```

`upsert` carries new buses whole, and known buses with only `bus_body_no` and the fields that changed. `remove` lists buses that left the upstream data. A client keeps its own map:

```js
const buses = new Map();
const ws = new WebSocket("ws://localhost:8000/ws?routes=1,4D");
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

### GET /buses/{bus_body_no}

A server-sent event stream (`text/event-stream`) for one bus. It reads from the same feed, so it never calls the upstream itself, and it keeps the poller running while it is open.

- `bus`: the whole bus, with the fields above. It is sent as soon as there is data and again each time the bus changes.
- `gone`: the bus is not in the latest poll, with data `{"bus_body_no": "..."}`. The stream ends after it.

A comment line goes out every 15 seconds so proxies keep the connection open.

```js
const es = new EventSource("http://localhost:8000/buses/BMP-220253");
es.addEventListener("bus", (e) => show(JSON.parse(e.data)));
es.addEventListener("gone", () => es.close());
```

Close the stream after `gone`. Otherwise `EventSource` reconnects on its own.

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
