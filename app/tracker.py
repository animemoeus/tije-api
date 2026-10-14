"""Live bus state fed by the TransJakarta MQTT broker.

The app's map WebView does `mqtt.connect(mqtt_url, 'id_' + random)` with no credentials,
subscribes to the topics returned by POST /v1/bus, and treats every message as one bus JSON:
  bus_body_no, latitude, longitude, snap_latitude, snap_longitude, bearing, timestamp,
  route_code, route_color, route_text_color, next_stops, estimated_time_next_stops, type
"""

import asyncio
import json
import logging
import math
import random
import ssl
import threading
import time
from typing import Any
from urllib.parse import urlparse

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


class Tracker:
    def __init__(self, bus_expiry_seconds: float, topic_idle_seconds: float):
        self.bus_expiry_seconds = bus_expiry_seconds
        self.topic_idle_seconds = topic_idle_seconds
        self._lock = threading.Lock()
        self._buses: dict[str, dict[str, Any]] = {}  # bus_body_no -> {"data", "topic", "received_at"}
        self._topics: dict[str, float] = {}  # topic -> last time a client asked for it
        self._subscribed: set[str] = set()
        self._listeners: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self.connected = False
        self.broker_url = ""

    # ---- MQTT connection -------------------------------------------------

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Event loop that WebSocket listeners run on; MQTT callbacks hand updates to it."""
        self._loop = loop

    def start(self, broker_url: str, loop: asyncio.AbstractEventLoop) -> None:
        import paho.mqtt.client as mqtt

        self._loop = loop
        self.broker_url = broker_url
        u = urlparse(broker_url)
        scheme = (u.scheme or "wss").lower()
        websockets = scheme in ("ws", "wss")
        secure = scheme in ("wss", "mqtts", "ssl")
        port = u.port or {"ws": 80, "wss": 443, "mqtt": 1883, "tcp": 1883, "mqtts": 8883, "ssl": 8883}.get(scheme, 443)

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"id_{random.randint(0, 99999)}",
            transport="websockets" if websockets else "tcp",
        )
        if websockets:
            client.ws_set_options(path=(u.path or "/mqtt") + (f"?{u.query}" if u.query else ""))
        if secure:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = lambda _c, _u, msg: self.handle_message(msg.topic, msg.payload)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(u.hostname, port, keepalive=60)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self.connected = False

    def _on_connect(self, client, _userdata, _flags, reason_code, _props) -> None:
        self.connected = not reason_code.is_failure
        log.info("MQTT connect %s: %s", self.broker_url, reason_code)
        if self.connected:
            with self._lock:
                topics = list(self._topics)
                self._subscribed.clear()
            self._subscribe(topics)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _props) -> None:
        self.connected = False
        log.warning("MQTT disconnected: %s", reason_code)

    def _subscribe(self, topics: list[str]) -> None:
        if not self._client or not self.connected:
            return
        with self._lock:
            new = [t for t in topics if t not in self._subscribed]
            self._subscribed.update(new)
        for t in new:
            self._client.subscribe(t, qos=0)

    # ---- Topics ----------------------------------------------------------

    def want_topics(self, topics: list[str]) -> None:
        """Mark topics as needed now and subscribe to any new ones."""
        now = time.monotonic()
        with self._lock:
            for t in topics:
                self._topics[t] = now
        self._subscribe(topics)

    def prune(self) -> None:
        """Drop expired buses and unsubscribe from topics nobody asked for recently."""
        now = time.monotonic()
        with self._lock:
            for no in [n for n, b in self._buses.items() if now - b["received_at"] > self.bus_expiry_seconds]:
                del self._buses[no]
            idle = [t for t, ts in self._topics.items() if now - ts > self.topic_idle_seconds]
            for t in idle:
                del self._topics[t]
                self._subscribed.discard(t)
        if idle and self._client and self.connected:
            for t in idle:
                self._client.unsubscribe(t)

    # ---- Messages --------------------------------------------------------

    def handle_message(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            log.debug("non-JSON message on %s", topic)
            return
        self.ingest(data if isinstance(data, list) else [data], topic)

    def ingest(self, items: list[Any], topic: str) -> None:
        """Store bus dicts from MQTT or from the REST POST /v1/bus response."""
        for bus in items:
            if not isinstance(bus, dict) or not bus.get("bus_body_no"):
                continue
            no = str(bus["bus_body_no"])
            with self._lock:
                prev = self._buses.get(no)
                # Same rule as the app: ignore out-of-order updates.
                if prev and _num(prev["data"].get("timestamp")) > _num(bus.get("timestamp")):
                    continue
                # REST polls repeat every bus each time; only a real change is worth sending to clients.
                changed = prev is None or prev["data"] != bus
                self._buses[no] = {"data": bus, "topic": topic, "received_at": time.monotonic()}
            if changed:
                self._broadcast(self.to_public(no))

    def _broadcast(self, item: dict[str, Any] | None) -> None:
        if not item or not self._loop:
            return
        for q in list(self._listeners):
            self._loop.call_soon_threadsafe(_put_nowait_drop_oldest, q, item)

    def add_listener(self, q: asyncio.Queue) -> None:
        self._listeners.add(q)

    def remove_listener(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)

    # ---- Queries ---------------------------------------------------------

    def to_public(self, bus_body_no: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._buses.get(bus_body_no)
            if not entry:
                return None
            bus, topic, received_at = entry["data"], entry["topic"], entry["received_at"]
        pos = bus_position(bus)
        return {
            "bus_body_no": bus_body_no,
            "route_code": bus.get("route_code"),
            "route_name": bus.get("route_name"),
            "trip_headsign": bus.get("trip_headsign"),
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
            "topic": topic,
            "age_seconds": round(time.monotonic() - received_at, 1),
        }

    def buses_near(self, lat: float, lon: float, radius_km: float, routes: set[str] | None = None) -> list[dict[str, Any]]:
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
            return {
                "connected": self.connected,
                "broker_url": self.broker_url,
                "buses": len(self._buses),
                "topics": len(self._topics),
                "subscribed": len(self._subscribed),
                "listeners": len(self._listeners),
            }


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _put_nowait_drop_oldest(q: asyncio.Queue, item: Any) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(item)
