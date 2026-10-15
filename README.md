# tije-api

A Rust port of the TJ Live Tracking API, built on [axum](https://github.com/tokio-rs/axum).

It asks the TransJakarta app backend where every bus is and hands the answer to you over HTTP, WebSocket and server-sent events. In other words, it is a very fast middleman. The buses do not get there any sooner.

## Running it locally

You need Rust 1.88 or newer. Edition 2024 and let chains are not optional, so an older toolchain will just produce a long and educational error.

Copy the example config:

```sh
cp .env.example .env
```

Then set `TJ_BASE_URL`. It is required, it has no default, and it never goes in the repo, so ask the team for it instead of grepping the git history hoping someone slipped. The other `TJ_*` settings are optional and default to whatever the Android app sends. `.env.example` lists them, including `TJ_POLL_SECONDS` (default 0.5), which sets how often the bus feed is polled while someone is watching.

Start the server:

```sh
cargo run
```

It listens on `0.0.0.0:8000`. Check that it's alive:

```sh
curl http://localhost:8000/health
```

If the server can't reach the upstream, it will tell you, with a 503 and a fair amount of passive aggression. See `/health` below.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Says hello. That's it |
| GET | `/health` | Upstream connection state and live feed counters |
| GET | `/route-types` | Every route type and how many routes it has |
| GET | `/routes?type=` | Path and stops of every route of one or more types |
| WS | `/ws?routes=` | Live bus positions: one snapshot, then deltas |
| GET | `/buses/{bus_body_no}` | Event stream that follows one bus |

CORS allows every origin (`Access-Control-Allow-Origin: *`), so your frontend on some other domain can call it without a week of debugging preflight requests.

Errors come back as JSON with a `detail` field: 400 when you sent something wrong, 502 when the upstream did. Upstream errors name the method and path and never the host, so don't bother fishing for it there either.

```json
{"detail": "unknown route type \"Ojek\", expected some of [\"BRT\", \"Angkutan Umum Integrasi\", ...]"}
```

### GET /

```sh
curl http://localhost:8000/
```

```
Hello, World!
```

Every project needs one endpoint that can't fail. This is it.

### GET /health

Checks the upstream connection first, then reports how things are going.

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

`live.buses` is how many buses the last poll saw. `live.clients` counts every open `/ws` connection and `/buses/{bus_body_no}` stream. If no token could be obtained, you get a 503 with `"status": "degraded"` and the reason in `auth.last_error`. Tokens themselves never show up here or in the logs, however nicely you ask.

### GET /route-types

```sh
curl http://localhost:8000/route-types
```

```json
{
  "types": [
    {"type": "BRT", "routes": 30},
    {"type": "Angkutan Umum Integrasi", "routes": 64},
    {"type": "Mikrotrans", "routes": 98},
    {"type": "Transjabodetabek", "routes": 18},
    {"type": "Royaltrans", "routes": 10},
    {"type": "Rusun", "routes": 14},
    {"type": "Bus Wisata", "routes": 3}
  ]
}
```

Seven types, always in this order. These are the values the upstream puts in `route_desc`, so you can't invent new ones.

### GET /routes?type=

```sh
curl "http://localhost:8000/routes?type=BRT,Mikrotrans"
```

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

The rules:

- `type` takes one or more types from `/route-types`, comma-separated, in any case. `brt,%20MIKROTRANS` works too, if you insist.
- Leave `type` out to get every route.
- An unknown type returns 400.
- Routes come back in natural order (1, 1A, 2, 4D, 10, JAK.10), because sorting "10" before "2" is a crime.
- `path` points are `[lat, lon]`, decoded from the upstream polyline. Note the order before you hand it to a map library that wants `[lon, lat]`.
- A direction without a polyline falls back to straight lines between its stops. Buses don't drive through buildings, but the drawing does.
- A route the upstream doesn't know, or one with no path, is left out quietly.
- The route list and each route detail are cached for an hour. The first call after a restart takes about 2 seconds for BRT and Mikrotrans together (128 routes). Every call after that is fast.

### WS /ws?routes=

The live bus feed. `routes` is the only parameter: comma-separated route codes like `1,4D,JAK.10`, in any case. Leave it out to get every bus in the city, all ~3,900 of them. Other parameters (`lat`, `lon`, `radius_km`, `mode`) are accepted and ignored.

One background poller fetches every bus within 60 km of Monas, which reaches as far as Bogor. It runs every `TJ_POLL_SECONDS` while at least one `/ws` client or `/buses/{bus_body_no}` stream is open, and stops when the last one leaves. A poll never starts before the previous one finishes, so the upstream gets one request at a time no matter how many tabs you open. A full poll takes 1.5 to 2 seconds (about 2 MB), so that's how often updates really arrive, whatever `TJ_POLL_SECONDS` says.

The first message holds every matching bus:

```json
{"type": "snapshot", "buses": [{"bus_body_no": "BMP-220253", "route_code": "1", "type": "BRT", "latitude": -6.181174, "longitude": 106.823, "raw_latitude": -6.181174, "raw_longitude": 106.823, "next_stop_name": "Monumen Nasional", "...": "..."}]}
```

After that the server sends only what changed, and nothing at all when nothing did. Silence means the buses are stuck, which is Jakarta, so it's plausible.

```json
{"type": "delta", "upsert": [{"bus_body_no": "BMP-220253", "latitude": -6.18102, "raw_latitude": -6.18102}], "remove": ["TJ-001"]}
```

`upsert` carries new buses whole and known buses as `bus_body_no` plus the fields that changed. `remove` lists buses that dropped out of the upstream data. Each bus has the upstream fields plus a few derived ones:

| Field | Meaning |
|---|---|
| `latitude`, `longitude` | Route-snapped position (`snap_latitude`/`snap_longitude`) when the upstream has one, otherwise the reported position |
| `raw_latitude`, `raw_longitude` | Position as the bus reported it. Changes only when the bus sends a new GPS fix |
| `type` | `BRT`, `Mikrotrans` or `Non-BRT` |
| `next_stop_name`, `prev_stop_name` | `next_stops`/`prev_stops` without the stop code, so `H00251P-Tosari` becomes `Tosari` |

The upstream also sends `speed`, `timestamp` and `estimated_time_next_stops`, often as 0. Don't build an ETA feature on them.

The client keeps its own map and merges deltas into it:

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

A server-sent event stream (`text/event-stream`) for one bus, for when you only care about the one you're waiting for. It reads from the same shared feed, so it never calls the upstream itself, and it keeps the poller running while it's open.

Two events:

- `bus`: the whole bus, with the fields above. Sent as soon as there is data and again every time the bus changes.
- `gone`: the bus isn't in the latest poll. The data is `{"bus_body_no": "..."}` and the stream ends after it.

A comment line goes out every 15 seconds so proxies don't decide the connection is dead.

```sh
curl -N http://localhost:8000/buses/BMP-220253
```

```
event: bus
data: {"bus_body_no":"BMP-220253","route_code":"1","type":"BRT","latitude":-6.181174,"longitude":106.823,"next_stop_name":"Monumen Nasional",...}

event: gone
data: {"bus_body_no":"BMP-220253"}
```

In the browser:

```js
const es = new EventSource("http://localhost:8000/buses/BMP-220253");
es.addEventListener("bus", (e) => show(JSON.parse(e.data)));
es.addEventListener("gone", () => es.close());
```

Close the stream after `gone`. If you don't, `EventSource` reconnects on its own, forever, waiting for a bus that has gone home.
