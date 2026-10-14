"""Route geometry from GET /v2/route/{route_code}.

Upstream `data` holds `route` (name, colours) and up to three directions, `inbound`, `outbound` and `loop`
(null when absent). Each direction: trip_id (same format as a bus's trip_id, e.g. 1-R07), headsign,
stops (in travel order, with stop_id/stop_name/stop_lat/stop_lon) and `polyline`, a Google encoded polyline
with 5 decimal places.
"""

from typing import Any

DIRECTIONS = ("outbound", "inbound", "loop")


def decode_polyline(encoded: str, precision: int = 5) -> list[list[float]]:
    """Google encoded polyline -> [[lat, lon], ...]."""
    out: list[list[float]] = []
    i = lat = lon = 0
    factor = 10**precision
    try:
        while i < len(encoded):
            delta = []
            for _ in range(2):
                shift = result = 0
                while True:
                    b = ord(encoded[i]) - 63
                    i += 1
                    result |= (b & 0x1F) << shift
                    shift += 5
                    if b < 0x20:
                        break
                delta.append(~(result >> 1) if result & 1 else result >> 1)
            lat += delta[0]
            lon += delta[1]
            out.append([round(lat / factor, 6), round(lon / factor, 6)])
    except IndexError:
        pass  # Truncated input: keep the points decoded so far.
    return out


def normalize_route(route_code: str, data: Any) -> dict[str, Any]:
    """Upstream route detail -> {route_code, route_name, colours, directions: [{trip_id, headsign, path, stops}]}."""
    data = data if isinstance(data, dict) else {}
    route = data.get("route") if isinstance(data.get("route"), dict) else {}
    directions = []
    for name in DIRECTIONS:
        d = data.get(name)
        if not isinstance(d, dict):
            continue
        stops = [
            {
                "stop_id": s.get("stop_id"),
                "name": s.get("stop_name"),
                "lat": s.get("stop_lat"),
                "lon": s.get("stop_lon"),
                "type": s.get("bus_stop_type"),
            }
            for s in d.get("stops") or []
            if isinstance(s, dict)
            and s.get("stop_lat") is not None
            and s.get("stop_lon") is not None
        ]
        poly = d.get("polyline")
        path = decode_polyline(poly) if isinstance(poly, str) else []
        # No geometry upstream: fall back to straight lines between stops.
        if len(path) < 2:
            path = [[s["lat"], s["lon"]] for s in stops]
        directions.append(
            {
                "direction": name,
                "trip_id": d.get("trip_id"),
                "headsign": d.get("headsign"),
                "path": path,
                "stops": stops,
            }
        )
    return {
        "route_code": route.get("route_short_name")
        or route.get("route_id")
        or route_code,
        "route_name": route.get("route_long_name"),
        "route_type": route.get("route_desc"),
        "route_color": route.get("route_color"),
        "route_text_color": route.get("route_text_color"),
        "directions": directions,
    }
