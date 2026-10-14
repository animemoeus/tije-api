"""Cache of live bus positions, filled by polling POST /v1/bus/offline.

Each bus is a JSON object as the app receives it:
  bus_body_no, latitude, longitude, snap_latitude, snap_longitude, bearing, timestamp,
  route_code, route_color, route_text_color, next_stops, estimated_time_next_stops, type
"""

import logging
import math
import threading
import time
from typing import Any

log = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bus_position(bus: dict[str, Any]) -> tuple[float, float] | None:
    """Prefer the route-snapped position, like the app does."""
    lat = bus.get("snap_latitude") or bus.get("latitude")
    lon = bus.get("snap_longitude") or bus.get("longitude")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def stop_name(raw: Any) -> str | None:
    """'H00251P-Tosari' -> 'Tosari' (upstream prefixes halte names with their stop code)."""
    if not raw:
        return None
    s = str(raw)
    code, sep, name = s.partition("-")
    return name if sep and code[:1].isalpha() and code[1:2].isdigit() else s


def parse_routes(raw: str | None) -> set[str] | None:
    """'4, 4d ,JAK.10' -> {'4', '4D', 'JAK.10'}; empty -> None (no filter). Matching is exact, case-insensitive."""
    codes = {c.strip().upper() for c in (raw or "").split(",") if c.strip()}
    return codes or None


def route_matches(bus: dict[str, Any], routes: set[str] | None) -> bool:
    return routes is None or str(bus.get("route_code") or "").upper() in routes


def bus_type(raw: Any) -> str:
    t = str(raw or "").upper()
    return "BRT" if t == "BRT" else "Mikrotrans" if t == "MIKROTRANS" else "Non-BRT"


# A position change bigger than this is a jump (bus reappeared elsewhere), not movement: no glide.
SNAP_KM = 0.5


class Tracker:
    def __init__(self, bus_expiry_seconds: float, max_glide_seconds: float = 5.0):
        self.bus_expiry_seconds = bus_expiry_seconds
        self.max_glide_seconds = max_glide_seconds
        self._lock = threading.Lock()
        # bus_body_no -> {"data", "source", "received_at", "received_wall", "glide"}
        # glide: {"from", "to", "start", "dur"}, the shown position moves from "from" to "to" over dur seconds.
        self._buses: dict[str, dict[str, Any]] = {}

    def prune(self) -> None:
        """Drop buses with no update for bus_expiry_seconds."""
        now = time.monotonic()
        with self._lock:
            for no in [
                n
                for n, b in self._buses.items()
                if now - b["received_at"] > self.bus_expiry_seconds
            ]:
                del self._buses[no]

    def ingest(self, items: list[Any], source: str) -> None:
        """Store bus dicts from an upstream response."""
        now = time.monotonic()
        with self._lock:
            for bus in items:
                if not isinstance(bus, dict) or not bus.get("bus_body_no"):
                    continue
                no = str(bus["bus_body_no"])
                prev = self._buses.get(no)
                # Same rule as the app: ignore out-of-order updates.
                if prev and _num(prev["data"].get("timestamp")) > _num(
                    bus.get("timestamp")
                ):
                    continue
                glide = _next_glide(
                    prev["glide"] if prev else None,
                    bus_position(bus),
                    now,
                    self.max_glide_seconds,
                )
                self._buses[no] = {
                    "data": bus,
                    "source": source,
                    "received_at": now,
                    # Wall clock of the last *different* data, so an unchanged bus keeps the same
                    # received_at (mode=delta only sends what changed).
                    "received_wall": prev["received_wall"]
                    if prev and prev["data"] == bus
                    else time.time(),
                    "glide": glide,
                }

    # ---- Queries ---------------------------------------------------------

    def to_public(self, bus_body_no: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._buses.get(bus_body_no)
            if not entry:
                return None
            bus, source, received_at, received_wall, glide = (
                entry["data"],
                entry["source"],
                entry["received_at"],
                entry["received_wall"],
                entry["glide"],
            )
        pos = glide_position(glide, time.monotonic()) if glide else None
        return {
            "bus_body_no": bus_body_no,
            "route_code": bus.get("route_code"),
            "route_name": bus.get("route_name"),
            "trip_headsign": bus.get("trip_headsign"),
            "trip_id": bus.get("trip_id"),
            "route_color": bus.get("route_color"),
            "route_text_color": bus.get("route_text_color"),
            "type": bus_type(bus.get("type")),
            "latitude": pos[0] if pos else None,
            "longitude": pos[1] if pos else None,
            "raw_latitude": bus.get("latitude"),
            "raw_longitude": bus.get("longitude"),
            "bearing": bus.get("bearing"),
            "speed": bus.get("speed"),
            "timestamp": bus.get("timestamp"),
            "next_stops": bus.get("next_stops"),
            "next_stop_name": stop_name(bus.get("next_stops")),
            "prev_stop_name": stop_name(bus.get("prev_stops")),
            "estimated_time_next_stops": bus.get("estimated_time_next_stops"),
            "estimated_distance_next_stops": bus.get("estimated_distance_next_stops"),
            "source": source,
            "age_seconds": round(time.monotonic() - received_at, 1),
            "received_at": round(received_wall, 1),
        }

    def buses_near(
        self, lat: float, lon: float, radius_km: float, routes: set[str] | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            nos = list(self._buses)
        out = []
        for no in nos:
            item = self.to_public(no)
            if not item or item["latitude"] is None or not route_matches(item, routes):
                continue
            d = haversine_km(lat, lon, item["latitude"], item["longitude"])
            if d <= radius_km:
                out.append({**item, "distance_km": round(d, 3)})
        return sorted(out, key=lambda b: b["distance_km"])

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"buses": len(self._buses)}


def glide_position(glide: dict[str, Any], now: float) -> tuple[float, float]:
    """Where the bus is shown at `now`: linear between the previous and the newest upstream position."""
    (lat0, lon0), (lat1, lon1) = glide["from"], glide["to"]
    f = min(1.0, (now - glide["start"]) / glide["dur"]) if glide["dur"] > 0 else 1.0
    return lat0 + (lat1 - lat0) * f, lon0 + (lon1 - lon0) * f


def _next_glide(
    prev: dict[str, Any] | None,
    pos: tuple[float, float] | None,
    now: float,
    max_glide: float,
) -> dict[str, Any] | None:
    """Start a new glide when upstream reports a new position; keep the running one otherwise."""
    if pos is None:
        return None
    if prev is None:
        return {"from": pos, "to": pos, "start": now, "dur": 0.0}
    if pos == prev["to"]:
        return prev
    shown = glide_position(prev, now)
    if haversine_km(*shown, *pos) > SNAP_KM:
        return {"from": pos, "to": pos, "start": now, "dur": 0.0}
    # Glide over the time the last position took to arrive, so the bus keeps moving until the next one.
    return {
        "from": shown,
        "to": pos,
        "start": now,
        "dur": min(now - prev["start"], max_glide),
    }


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
