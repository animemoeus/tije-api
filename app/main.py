"""HTTP + WebSocket API for TransJakarta live bus positions.

Run:  .venv\\Scripts\\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .config import settings as default_settings
from .routes import normalize_route
from .tracker import Tracker, parse_routes, route_matches
from .upstream import TJClient, UpstreamError


class RouteType(StrEnum):
    """Route types as upstream names them in `route_desc`. Matched case-insensitively."""

    BRT = "BRT"
    ANGKUTAN_UMUM_INTEGRASI = "Angkutan Umum Integrasi"
    MIKROTRANS = "Mikrotrans"
    TRANSJABODETABEK = "Transjabodetabek"
    ROYALTRANS = "Royaltrans"
    RUSUN = "Rusun"
    BUS_WISATA = "Bus Wisata"

    @classmethod
    def _missing_(cls, value: object) -> "RouteType | None":
        text = str(value).strip().lower()
        return next((m for m in cls if m.value.lower() == text), None)


log = logging.getLogger("tj")

# WebSocket snapshots go out on ticks of ws_base_seconds / WS_TICKS; `hz` must divide it.
WS_TICKS = 4
# A mode=delta client with more unsent frames than this is behind: its queue becomes one fresh snapshot.
DELTA_BACKLOG = 8

# Jakarta-ish bounds, to reject obviously wrong coordinates early.
LAT = {"ge": -7.5, "le": -5.5}
LON = {"ge": 106.0, "le": 107.5}


def create_app(
    settings: Settings = default_settings,
    client: TJClient | None = None,
    tracker: Tracker | None = None,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = client or TJClient(settings)
        app.state.tracker = tracker or Tracker(settings.bus_expiry_seconds)
        # (lat, lon, r) rounded -> {"lat", "lon", "r", "last", "polled", "clients", "groups", "busy"}
        app.state.areas = {}
        app.state.routes = {}  # route code -> (fetched_at, normalized route)
        tasks = [
            asyncio.create_task(_prune_loop(app.state.tracker)),
            asyncio.create_task(_poll_loop(app, settings)),
            asyncio.create_task(_broadcast_loop(app, settings)),
        ]
        yield
        for t in tasks:
            t.cancel()
        await app.state.client.aclose()

    app = FastAPI(title="TJ Live Tracking API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    def radius_param(radius_km: float | None) -> float:
        r = radius_km or settings.default_radius_km
        return min(r, settings.max_radius_km)

    async def track_area(
        request_app: FastAPI, lat: float, lon: float, radius_km: float
    ) -> dict[str, Any]:
        """Register an area and poll it now unless a recent poll already covers it."""
        key = (round(lat, 3), round(lon, 3), radius_km)
        entry = request_app.state.areas.setdefault(
            key,
            {
                "lat": lat,
                "lon": lon,
                "r": radius_km,
                "polled": 0.0,
                "clients": [],
                # mode=delta clients, grouped so each group's diff is computed once:
                # (routes, every) -> {"routes", "every", "state", "clients"}
                "groups": {},
                "busy": False,
            },
        )
        entry["last"] = time.monotonic()
        if time.monotonic() - entry["polled"] >= settings.poll_seconds:
            first = entry["polled"] == 0.0
            try:
                await _poll_area(request_app, entry)
            except UpstreamError as e:
                if first:
                    raise HTTPException(502, f"upstream error: {e}") from e
                log.warning("poll failed: %s", e)
        return entry

    if settings.serve_ui:
        app.mount(
            "/ui",
            StaticFiles(directory=Path(__file__).parent / "static", html=True),
            name="ui",
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/ui/" if settings.serve_ui else "/docs")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        areas = request.app.state.areas.values()
        return {
            "status": "ok",
            "auth": request.app.state.client.token_info(),
            "tracker": {
                **request.app.state.tracker.stats(),
                "areas": len(areas),
                "ws_clients": sum(_ws_count(a) for a in areas),
                "poll_seconds": settings.poll_seconds,
                "ws_base_seconds": settings.ws_base_seconds,
            },
        }

    @app.get("/buses")
    async def buses(
        request: Request,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
        routes: str | None = Query(
            None,
            description="Comma-separated route codes to keep, e.g. 4,4D (exact, case-insensitive)",
        ),
    ) -> dict[str, Any]:
        """Live buses near a point, nearest first. `routes_available` lists every route in the area, before filtering."""
        r = radius_param(radius_km)
        wanted = parse_routes(routes)
        await track_area(request.app, lat, lon, r)
        everything = request.app.state.tracker.buses_near(lat, lon, r)
        items = [b for b in everything if route_matches(b, wanted)]
        return {
            "count": len(items),
            "radius_km": r,
            "routes": sorted(wanted) if wanted else None,
            "routes_available": route_summary(everything),
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
            return await request.app.state.client.get_offline_buses(
                lat, lon, radius_param(radius_km)
            )
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    @app.get("/buses/{bus_body_no}")
    async def bus_detail(request: Request, bus_body_no: str) -> dict[str, Any]:
        """Latest known state of one bus (must be inside an area some client is tracking)."""
        item = request.app.state.tracker.to_public(bus_body_no)
        if not item:
            raise HTTPException(
                404, "bus not seen recently; query /buses for its area first"
            )
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
            return await request.app.state.client.get_bus_stops(
                lat, lon, radius_param(radius_km)
            )
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    async def cached(request_app: FastAPI, key: str, fetch: Any) -> Any:
        """`await fetch()`, kept in app.state.routes for route_cache_seconds."""
        cache: dict[str, tuple[float, Any]] = request_app.state.routes
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < settings.route_cache_seconds:
            return hit[1]
        value = await fetch()
        cache[key] = (time.monotonic(), value)
        return value

    async def get_route(request_app: FastAPI, route_code: str) -> dict[str, Any]:
        """Normalized route, cached. HTTPException 404 for unknown codes or routes without a path, 502 upstream errors."""
        code = route_code.strip().upper()

        async def fetch() -> dict[str, Any]:
            try:
                data = await request_app.state.client.get_route(code)
            except UpstreamError as e:
                if e.status == 404:
                    raise HTTPException(404, f"route {code} not found") from e
                raise HTTPException(502, f"upstream error: {e}") from e
            route = normalize_route(code, data)
            if not route["directions"]:
                raise HTTPException(404, f"route {code} has no path")
            return route

        return await cached(request_app, code, fetch)

    async def route_list(request_app: FastAPI) -> list[Any]:
        """Every route upstream knows (GET /v2/route, no geometry), cached. HTTPException 502 on upstream errors."""

        async def fetch() -> list[Any]:
            try:
                return await request_app.state.client.list_routes()
            except UpstreamError as e:
                raise HTTPException(502, f"upstream error: {e}") from e

        return await cached(request_app, "__list__", fetch)

    @app.get("/route-types")
    async def route_types(request: Request) -> dict[str, Any]:
        """Values accepted by `GET /routes?type=`, with how many routes upstream has of each."""
        listing = await route_list(request.app)
        counts = Counter(
            str(r.get("route_desc") or "").strip().lower()
            for r in listing
            if isinstance(r, dict)
        )
        return {
            "types": [
                {"type": t.value, "routes": counts[t.value.lower()]} for t in RouteType
            ]
        }

    TYPE_QUERY = Query(
        description="Route type as upstream names it in route_desc. Empty = every route"
    )

    async def routes_of(
        request_app: FastAPI, type: RouteType | None
    ) -> list[dict[str, Any]]:
        """Normalized routes of one type (every route when None), sorted by code. Routes whose detail fails are left out."""
        listing = await route_list(request_app)
        wanted = type.value.lower() if type else None
        codes = [
            str(r.get("route_short_name") or r.get("route_id"))
            for r in listing
            if isinstance(r, dict)
            and (
                wanted is None
                or str(r.get("route_desc") or "").strip().lower() == wanted
            )
            and (r.get("route_short_name") or r.get("route_id"))
        ]
        limit = asyncio.Semaphore(5)

        async def one(code: str) -> dict[str, Any] | None:
            async with limit:
                try:
                    return await get_route(request_app, code)
                except HTTPException as e:
                    log.warning("route %s skipped: %s", code, e.detail)
                    return None

        found = [r for r in await asyncio.gather(*map(one, codes)) if r]
        return sorted(found, key=lambda r: _natural_key(str(r["route_code"])))

    @app.get("/routes")
    async def routes_by_type(
        request: Request,
        type: Annotated[RouteType | None, TYPE_QUERY] = None,
    ) -> dict[str, Any]:
        """Path and stops of every route of one type (e.g. all BRT corridors), or of every route when `type` is empty.

        Routes whose detail fails are left out."""
        return {
            "type": type.value if type else None,
            "routes": await routes_of(request.app, type),
        }

    @app.get("/stops/all")
    async def all_stops(
        request: Request,
        type: Annotated[RouteType | None, TYPE_QUERY] = None,
    ) -> dict[str, Any]:
        """Every stop served by routes of one type (every route when `type` is empty), one entry per `stop_id`.

        Built from route details, since upstream has no "all stops" endpoint. `routes` lists the codes stopping there."""
        stops: dict[str, dict[str, Any]] = {}
        for route in await routes_of(request.app, type):
            for d in route["directions"]:
                for st in d["stops"]:
                    key = str(st.get("stop_id") or f"{st['lat']},{st['lon']}")
                    entry = stops.setdefault(key, {**st, "routes": []})
                    if route["route_code"] not in entry["routes"]:
                        entry["routes"].append(route["route_code"])
        return {
            "type": type.value if type else None,
            "stops": sorted(stops.values(), key=lambda s: str(s.get("name") or "")),
        }

    @app.get("/routes/{route_code}")
    async def route_detail(request: Request, route_code: str) -> dict[str, Any]:
        """Route path and stops per direction (upstream GET /v2/route/{code}), for drawing a route on the map.

        Match a bus to a direction by its `trip_id`. Cached for `route_cache_seconds`."""
        return await get_route(request.app, route_code)

    @app.get("/account")
    async def account(request: Request) -> dict[str, Any]:
        """Which upstream identity this backend uses (no secrets)."""
        return request.app.state.client.token_info()

    @app.get("/account/trips")
    async def account_trips(
        request: Request,
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=50),
    ) -> Any:
        """Trip history of the configured TransJakarta account (GET /v1/user/trips). Needs TJ_LOGIN_EMAIL/PASSWORD."""
        client: TJClient = request.app.state.client
        try:
            await client._ensure_token()
            if not client.is_user_session:
                raise HTTPException(
                    403,
                    "needs a TransJakarta account: set TJ_LOGIN_EMAIL and TJ_LOGIN_PASSWORD in .env",
                )
            return await client.request(
                "GET", "/v1/user/trips", params={"page": page, "limit": limit}
            )
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e

    @app.websocket("/ws")
    async def ws(
        websocket: WebSocket,
        lat: float = Query(..., **LAT),
        lon: float = Query(..., **LON),
        radius_km: float | None = Query(None, gt=0),
        routes: str | None = Query(None),
        hz: int = Query(
            2, ge=1, le=WS_TICKS, description="Snapshots per second: 1, 2 or 4"
        ),
        mode: Literal["snapshot", "delta"] = Query(
            "snapshot",
            description="snapshot: every bus every time. delta: one snapshot, then only what changed",
        ),
    ) -> None:
        """`hz` snapshots per second (default 2): all buses near a point, nearest first. `routes=4,4D` filters by route."""
        if WS_TICKS % hz:
            await websocket.close(code=1008)
            return
        r = radius_param(radius_km)
        wanted = parse_routes(routes)
        await websocket.accept()
        tracker: Tracker = websocket.app.state.tracker
        try:
            entry = await track_area(websocket.app, lat, lon, r)
        except HTTPException as e:
            await websocket.send_json({"type": "error", "detail": e.detail})
            await websocket.close(code=1011)
            return
        every = WS_TICKS // hz
        if mode == "delta":
            # Start from the state the group's next delta is computed against, so this client is in sync.
            key = (frozenset(wanted) if wanted else None, every)
            group = entry["groups"].get(key)
            if group is None:
                state = {
                    b["bus_body_no"]: _delta_view(b)
                    for b in tracker.buses_near(
                        entry["lat"], entry["lon"], entry["r"], wanted
                    )
                }
                group = entry["groups"][key] = {
                    "routes": wanted,
                    "every": every,
                    "state": state,
                    "clients": [],
                }
            # _broadcast_loop appends to "queue"; delta frames cannot be skipped.
            me = {
                "queue": [_snapshot(list(group["state"].values()))],
                "ready": asyncio.Event(),
            }
            group["clients"].append(me)
        else:
            # _broadcast_loop fills "frame"; only the newest frame is kept,
            # so a slow client skips frames instead of holding up the others.
            me = {
                "routes": wanted,
                "every": every,
                "frame": _snapshot(tracker.buses_near(lat, lon, r, wanted)),
                "ready": asyncio.Event(),
            }
            entry["clients"].append(me)
        me["ready"].set()

        async def read() -> None:
            # Nothing is expected from the client; this only notices when it goes away.
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass

        async def send() -> None:
            while True:
                await me["ready"].wait()
                me["ready"].clear()
                if mode == "delta":
                    frames, me["queue"] = me["queue"], []
                    for frame in frames:
                        await websocket.send_text(frame)
                else:
                    await websocket.send_text(me["frame"])

        tasks = [asyncio.create_task(read()), asyncio.create_task(send())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            if mode == "delta":
                group["clients"].remove(me)
                if not group["clients"]:
                    del entry["groups"][key]
            else:
                entry["clients"].remove(me)

    return app


def route_summary(buses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Routes present in a bus list with their colours and bus counts, in natural order (1, 1A, 2, 4, 4D, 10, JAK.10)."""
    acc: dict[str, dict[str, Any]] = {}
    for b in buses:
        code = str(b.get("route_code") or "").strip()
        if not code:
            continue
        e = acc.setdefault(
            code,
            {
                "route_code": code,
                "route_color": b.get("route_color"),
                "route_text_color": b.get("route_text_color"),
                "count": 0,
            },
        )
        e["count"] += 1
    return sorted(acc.values(), key=lambda e: _natural_key(e["route_code"]))


def _natural_key(code: str) -> list[Any]:
    return [
        (0, int(p), "") if p.isdigit() else (1, 0, p.upper())
        for p in re.findall(r"\d+|\D+", code)
    ]


async def _poll_area(app: FastAPI, entry: dict[str, Any]) -> None:
    """POST /v1/bus/offline for one area. Skipped while a poll of the same area is still running."""
    if entry["busy"]:
        return
    entry["busy"] = True
    try:
        buses = await app.state.client.get_offline_buses(
            entry["lat"], entry["lon"], entry["r"]
        )
        entry["polled"] = time.monotonic()
    finally:
        entry["busy"] = False
    if isinstance(buses, list):
        app.state.tracker.ingest(buses, "rest:/v1/bus/offline")


async def _poll_quietly(app: FastAPI, entry: dict[str, Any]) -> None:
    try:
        await _poll_area(app, entry)
    except UpstreamError as e:
        log.warning("poll failed: %s", e)


async def _poll_loop(app: FastAPI, settings: Settings) -> None:
    """Keep areas with WebSocket clients fresh; drop areas nobody asked for recently."""
    running: set[asyncio.Task] = set()
    while True:
        await asyncio.sleep(settings.poll_seconds)
        now = time.monotonic()
        due = []
        for key, entry in list(app.state.areas.items()):
            if _ws_count(entry):
                if now - entry["polled"] >= settings.poll_seconds * 0.9:
                    due.append(entry)
            elif now - entry["last"] > settings.area_idle_seconds:
                del app.state.areas[key]
        # Polls run in the background so one slow area does not delay the others or the next tick.
        for entry in due:
            if not entry["busy"]:
                task = asyncio.create_task(_poll_quietly(app, entry))
                running.add(task)
                task.add_done_callback(running.discard)


def _snapshot(buses: list[dict[str, Any]]) -> str:
    return json.dumps({"type": "snapshot", "buses": buses})


def _ws_count(entry: dict[str, Any]) -> int:
    return len(entry["clients"]) + sum(
        len(g["clients"]) for g in entry["groups"].values()
    )


def _delta_view(bus: dict[str, Any]) -> dict[str, Any]:
    """A bus as mode=delta sends it: no age_seconds (changes every frame; received_at replaces it),
    and lat/lon rounded to ~0.1 m so interpolation float noise is not a change."""
    out = {k: v for k, v in bus.items() if k != "age_seconds"}
    for k in ("latitude", "longitude"):
        if out.get(k) is not None:
            out[k] = round(out[k], 6)
    return out


def _diff(
    prev: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]
) -> dict[str, list[Any]]:
    """Per-field changes from prev to new (both bus_body_no -> bus). New buses are sent whole."""
    upsert = []
    for no, bus in new.items():
        old = prev.get(no)
        if old is None:
            upsert.append(bus)
            continue
        changed = {k: v for k, v in bus.items() if old.get(k) != v}
        if changed:
            upsert.append({"bus_body_no": no, **changed})
    return {"upsert": upsert, "remove": [no for no in prev if no not in new]}


def _push(client: dict[str, Any], frame: str, resync: Any) -> None:
    """Queue a delta frame; a client too far behind gets one snapshot (from resync()) instead."""
    if len(client["queue"]) >= DELTA_BACKLOG:
        client["queue"] = [resync()]
    else:
        client["queue"].append(frame)
    client["ready"].set()


async def _broadcast_loop(app: FastAPI, settings: Settings) -> None:
    """Push frames to every WebSocket client.

    Work is done once per area (buses_near), once per route filter (snapshot JSON) and once
    per delta group (diff + JSON), then the same string goes to every client that wants it,
    so clients add almost no load.
    """
    loop = asyncio.get_running_loop()
    tick_seconds = settings.ws_base_seconds / WS_TICKS
    next_at = loop.time()
    tick = 0
    while True:
        # Fixed schedule: time spent encoding does not shift the interval.
        next_at += tick_seconds
        await asyncio.sleep(max(0.0, next_at - loop.time()))
        tick += 1
        for entry in list(app.state.areas.values()):
            due = [c for c in entry["clients"] if tick % c["every"] == 0]
            groups = [g for g in entry["groups"].values() if tick % g["every"] == 0]
            if not due and not groups:
                continue
            entry["last"] = time.monotonic()
            everything = app.state.tracker.buses_near(
                entry["lat"], entry["lon"], entry["r"]
            )
            frames: dict[frozenset[str] | None, str] = {}
            for c in due:
                key = frozenset(c["routes"]) if c["routes"] else None
                if key not in frames:
                    frames[key] = _snapshot(
                        [b for b in everything if route_matches(b, c["routes"])]
                    )
                c["frame"] = frames[key]
                c["ready"].set()
            for g in groups:
                new = {
                    b["bus_body_no"]: _delta_view(b)
                    for b in everything
                    if route_matches(b, g["routes"])
                }
                d = _diff(g["state"], new)
                g["state"] = new
                if not d["upsert"] and not d["remove"]:
                    continue  # nothing changed: send nothing
                frame = json.dumps({"type": "delta", **d})
                snap: list[
                    str
                ] = []  # built at most once, only if some client needs a resync

                def resync(new=new, snap=snap) -> str:
                    if not snap:
                        snap.append(_snapshot(list(new.values())))
                    return snap[0]

                for c in g["clients"]:
                    _push(c, frame, resync)


async def _prune_loop(tracker: Tracker) -> None:
    while True:
        await asyncio.sleep(30)
        tracker.prune()


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
# httpx logs every request with the full upstream URL at INFO; keep it out of the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
app = create_app()
