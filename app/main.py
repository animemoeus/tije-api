"""HTTP + WebSocket API for TransJakarta live bus positions.

Run:  .venv\\Scripts\\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""

import asyncio
import contextlib
import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, settings as default_settings
from .tracker import Tracker, haversine_km, parse_routes, route_matches
from .upstream import TJClient, UpstreamError

log = logging.getLogger("tj")

# Jakarta-ish bounds, to reject obviously wrong coordinates early.
LAT = dict(ge=-7.5, le=-5.5)
LON = dict(ge=106.0, le=107.5)


def create_app(
    settings: Settings = default_settings,
    client: TJClient | None = None,
    tracker: Tracker | None = None,
    start_mqtt: bool = True,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = client or TJClient(settings)
        app.state.tracker = tracker or Tracker(settings.bus_expiry_seconds, settings.topic_idle_seconds)
        app.state.tracker.attach_loop(asyncio.get_running_loop())
        app.state.areas = {}  # (lat, lon, r) rounded -> {"lat", "lon", "r", "last", "polled"}
        tasks = [asyncio.create_task(_prune_loop(app.state.tracker))]
        if settings.rest_poll != "off":
            tasks.append(asyncio.create_task(_rest_poll_loop(app, settings)))
        if start_mqtt:
            tasks.append(asyncio.create_task(_connect_mqtt(app, settings)))
        yield
        for t in tasks:
            t.cancel()
        app.state.tracker.stop()
        await app.state.client.aclose()

    app = FastAPI(title="TJ Live Tracking API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    def radius_param(radius_km: float | None) -> float:
        r = radius_km or settings.default_radius_km
        return min(r, settings.max_radius_km)

    async def track_area(request_app: FastAPI, lat: float, lon: float, radius_km: float) -> list[str]:
        try:
            area = await request_app.state.client.get_area(lat, lon, radius_km)
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e
        request_app.state.tracker.ingest(area.buses, "rest:/v1/bus")
        request_app.state.tracker.want_topics(area.topics)
        key = (round(lat, 3), round(lon, 3), radius_km)
        entry = request_app.state.areas.setdefault(key, {"lat": lat, "lon": lon, "r": radius_km, "polled": 0.0})
        entry["last"] = time.monotonic()
        # First request for an area while MQTT is down: fetch positions now so the reply is not empty.
        if _should_poll(request_app, settings) and time.monotonic() - entry["polled"] > settings.rest_poll_seconds:
            await _poll_area(request_app, entry)
        return area.topics

    app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/ui/")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        return {"status": "ok", "auth": request.app.state.client.token_info(), "mqtt": request.app.state.tracker.stats()}

    @app.get("/buses")
    async def buses(
        request: Request,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
        wait: float = Query(0, ge=0, le=10, description="Seconds to wait for first positions if none are cached yet"),
        routes: str | None = Query(None, description="Comma-separated route codes to keep, e.g. 4,4D (exact, case-insensitive)"),
    ) -> dict[str, Any]:
        """Live buses near a point, nearest first. `routes_available` lists every route in the area, before filtering."""
        r = radius_param(radius_km)
        wanted = parse_routes(routes)
        topics = await track_area(request.app, lat, lon, r)
        tracker: Tracker = request.app.state.tracker
        everything = tracker.buses_near(lat, lon, r)
        deadline = asyncio.get_running_loop().time() + wait
        while not everything and topics and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
            everything = tracker.buses_near(lat, lon, r)
        items = [b for b in everything if route_matches(b, wanted)]
        return {
            "count": len(items),
            "radius_km": r,
            "routes": sorted(wanted) if wanted else None,
            "routes_available": route_summary(everything),
            "topics": topics,
            "mqtt_connected": tracker.connected,
            "buses": items,
        }

    @app.get("/buses/offline")
    async def buses_offline(
        request: Request,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
    ) -> Any:
        """Upstream POST /v1/bus/offline, passed through as-is."""
        try:
            return await request.app.state.client.get_offline_buses(lat, lon, radius_param(radius_km))
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    @app.get("/buses/{bus_body_no}")
    async def bus_detail(request: Request, bus_body_no: str) -> dict[str, Any]:
        """Latest known state of one bus (must be inside an area some client is tracking)."""
        item = request.app.state.tracker.to_public(bus_body_no)
        if not item:
            raise HTTPException(404, "bus not seen recently; query /buses for its area first")
        return item

    @app.get("/stops")
    async def stops(
        request: Request,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
    ) -> Any:
        """Upstream GET /v2/bus-stop (halte and bus stops near a point), passed through as-is."""
        try:
            return await request.app.state.client.get_bus_stops(lat, lon, radius_param(radius_km))
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    @app.get("/account")
    async def account(request: Request) -> dict[str, Any]:
        """Which upstream identity this backend uses (no secrets)."""
        return request.app.state.client.token_info()

    @app.get("/account/trips")
    async def account_trips(request: Request, page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50)) -> Any:
        """Trip history of the configured TransJakarta account (GET /v1/user/trips). Needs TJ_LOGIN_EMAIL/PASSWORD."""
        client: TJClient = request.app.state.client
        try:
            await client._ensure_token()
            if not client.is_user_session:
                raise HTTPException(403, "needs a TransJakarta account: set TJ_LOGIN_EMAIL and TJ_LOGIN_PASSWORD in .env")
            return await client.request("GET", "/v1/user/trips", params={"page": page, "limit": limit})
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    @app.websocket("/ws")
    async def ws(
        websocket: WebSocket,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
        routes: str | None = Query(None),
    ) -> None:
        """Snapshot of buses near a point, then one JSON message per position update. `routes=4,4D` filters by route."""
        r = radius_param(radius_km)
        wanted = parse_routes(routes)
        await websocket.accept()
        tracker: Tracker = websocket.app.state.tracker
        try:
            await track_area(websocket.app, lat, lon, r)
        except HTTPException as e:
            await websocket.send_json({"type": "error", "detail": e.detail})
            await websocket.close(code=1011)
            return
        # One REST poll of a 20 km area yields ~2,300 updates at once; keep room for a few polls.
        q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        tracker.add_listener(q)
        refresh = asyncio.create_task(_refresh_area(websocket.app, lat, lon, r, settings.topics_cache_seconds))
        try:
            await websocket.send_json({"type": "snapshot", "buses": tracker.buses_near(lat, lon, r, wanted)})
            while True:
                bus = await q.get()
                if bus["latitude"] is None or not route_matches(bus, wanted):
                    continue
                d = haversine_km(lat, lon, bus["latitude"], bus["longitude"])
                if d <= r:
                    await websocket.send_json({"type": "update", "bus": {**bus, "distance_km": round(d, 3)}})
        except WebSocketDisconnect:
            pass
        finally:
            refresh.cancel()
            tracker.remove_listener(q)

    return app


async def _connect_mqtt(app: FastAPI, settings: Settings) -> None:
    """Resolve the broker URL (retrying on failure) and start the MQTT client."""
    delay = 5
    while True:
        try:
            url = settings.mqtt_url or await app.state.client.get_mqtt_url()
            app.state.tracker.start(url, asyncio.get_running_loop())
            log.info("MQTT broker: %s", url)
            return
        except UpstreamError as e:
            log.warning("cannot get MQTT url (%s); retry in %ss", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)


def route_summary(buses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Routes present in a bus list with their colours and bus counts, in natural order (1, 1A, 2, 4, 4D, 10, JAK.10)."""
    acc: dict[str, dict[str, Any]] = {}
    for b in buses:
        code = str(b.get("route_code") or "").strip()
        if not code:
            continue
        e = acc.setdefault(code, {"route_code": code, "route_color": b.get("route_color"),
                                  "route_text_color": b.get("route_text_color"), "count": 0})
        e["count"] += 1
    return sorted(acc.values(), key=lambda e: _natural_key(e["route_code"]))


def _natural_key(code: str) -> list[Any]:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.upper()) for p in re.findall(r"\d+|\D+", code)]


def _should_poll(app: FastAPI, settings: Settings) -> bool:
    if settings.rest_poll == "always":
        return True
    return settings.rest_poll == "auto" and not app.state.tracker.connected


async def _poll_area(app: FastAPI, entry: dict[str, Any]) -> None:
    entry["polled"] = time.monotonic()
    try:
        buses = await app.state.client.get_offline_buses(entry["lat"], entry["lon"], entry["r"])
    except UpstreamError as e:
        log.warning("REST poll failed: %s", e)
        return
    if isinstance(buses, list):
        app.state.tracker.ingest(buses, "rest:/v1/bus/offline")


async def _rest_poll_loop(app: FastAPI, settings: Settings) -> None:
    """Positions via POST /v1/bus/offline for areas clients asked about recently (fallback when MQTT is down)."""
    while True:
        await asyncio.sleep(settings.rest_poll_seconds)
        if not _should_poll(app, settings):
            continue
        now = time.monotonic()
        for key, entry in list(app.state.areas.items()):
            if now - entry["last"] > settings.topic_idle_seconds:
                del app.state.areas[key]
            elif now - entry["polled"] >= settings.rest_poll_seconds - 0.5:
                await _poll_area(app, entry)


async def _prune_loop(tracker: Tracker) -> None:
    while True:
        await asyncio.sleep(30)
        tracker.prune()


async def _refresh_area(app: FastAPI, lat: float, lon: float, r: float, every: float) -> None:
    """Keep a WebSocket client's area subscribed while it is connected."""
    while True:
        await asyncio.sleep(every)
        with contextlib.suppress(UpstreamError):
            area = await app.state.client.get_area(lat, lon, r)
            app.state.tracker.ingest(area.buses, "rest:/v1/bus")
            app.state.tracker.want_topics(area.topics)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
