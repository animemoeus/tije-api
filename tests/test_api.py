"""Offline tests: fake tijeapi via httpx.MockTransport."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routes import decode_polyline
from app.tracker import Tracker
from app.upstream import TJClient

MONAS = (-6.1754, 106.8272)
SOURCE = "rest:/v1/bus/offline"

# Trimmed GET /v2/route/1 response (real shape; polyline is the first points of the real one).
ROUTE_1 = {
    "route": {
        "route_id": "1",
        "route_short_name": "1",
        "route_long_name": "Blok M - Kota",
        "route_desc": "BRT",
        "route_color": "D62126",
        "route_text_color": "FFFFFF",
    },
    "inbound": {
        "trip_id": "1-R08",
        "headsign": "Blok M",
        "polyline": "bimd@yq|jS@?oEr@",
        "stops": [
            {
                "stop_id": "H00093P",
                "stop_name": "Kali Besar",
                "stop_lat": -6.135355,
                "stop_lon": 106.81143,
                "bus_stop_type": "halte",
            }
        ],
    },
    "outbound": {
        "trip_id": "1-R07",
        "headsign": "Kali Besar Barat",
        "polyline": "",
        "stops": [
            {
                "stop_id": "H00014P",
                "stop_name": "Blok M",
                "stop_lat": -6.243312,
                "stop_lon": 106.80175,
            },
            {
                "stop_id": "H00278P",
                "stop_name": "Harmoni",
                "stop_lat": -6.1655,
                "stop_lon": 106.8205,
            },
        ],
    },
    "loop": None,
}
ROUTE_LIST = [
    {"route_id": "10", "route_short_name": "10", "route_desc": "BRT"},
    {"route_id": "1", "route_short_name": "1", "route_desc": "BRT"},
    {"route_id": "2", "route_short_name": "2", "route_desc": "BRT"},
    {"route_id": "JAK.10", "route_short_name": "JAK.10", "route_desc": "Mikrotrans"},
]


class FakeTJ:
    """Mimics tijeapi auth: everything but login/refresh needs a valid Bearer token."""

    def __init__(self, ttl=86400):
        self.ttl = ttl
        self.issued = 0
        self.valid: set[str] = set()
        self.calls: list[httpx.Request] = []
        self.offline_status = 200
        self.offline_buses: list[dict] = []
        self.user_tokens: set[str] = set()
        self.route_status = 200
        self.missing_routes: set[str] = set()

    def _tokens(self):
        self.issued += 1
        tok = f"tok{self.issued}"
        self.valid.add(tok)
        now = int(time.time())
        return {
            "token": tok,
            "token_valid_until": now + self.ttl,
            "refresh_token": f"ref{self.issued}",
            "refresh_token_valid_until": now + self.ttl + 3600,
            "user": {"is_guest": True},
            "moter": None,
        }

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        path = req.url.path
        if path == "/v1/auth/login/guest":
            return httpx.Response(200, json=self._tokens())
        if path == "/v1/auth/login":
            body = json.loads(req.content)
            if body != {"email": "me@example.com", "password": "s3cret"}:
                return httpx.Response(
                    400, json={"code": 400, "message": "Email atau password salah"}
                )
            t = self._tokens()
            self.user_tokens.add(t["token"])
            return httpx.Response(200, json=t)
        if path == "/v1/auth/token/refresh":
            return httpx.Response(200, json={"data": self._tokens()})
        auth = req.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ") not in self.valid:
            return httpx.Response(
                401, json={"code": 401, "message": "Unauthorized, token is required"}
            )
        if path == "/v2/bus-stop":
            return httpx.Response(
                200, json={"data": [{"stop_id": "S1", "stop_name": "Monas"}]}
            )
        if path == "/v1/bus/offline":
            if self.offline_status != 200:
                return httpx.Response(self.offline_status, text="boom")
            return httpx.Response(200, json={"code": 200, "data": self.offline_buses})
        if path == "/v2/route":
            return httpx.Response(
                200, json={"code": 200, "data": {"routes": ROUTE_LIST}}
            )
        if path.startswith("/v2/route/"):
            if path in self.missing_routes:
                return httpx.Response(
                    404, json={"code": 404, "message": "Rute tidak ditemukan"}
                )
            if self.route_status != 200:
                return httpx.Response(
                    self.route_status,
                    json={"code": self.route_status, "message": "Rute tidak ditemukan"},
                )
            return httpx.Response(200, json={"code": 200, "data": ROUTE_1})
        if path == "/v1/user/trips":
            if auth.removeprefix("Bearer ") not in self.user_tokens:
                return httpx.Response(403, json={"code": 403, "message": "guest"})
            return httpx.Response(200, json={"code": 200, "data": [{"trip_id": "T1"}]})
        return httpx.Response(404)

    def paths(self):
        return [c.url.path for c in self.calls]


def bus_msg(no="TJ-001", lat=-6.1760, lon=106.8280, ts=1000, **extra):
    return {
        "bus_body_no": no,
        "latitude": lat,
        "longitude": lon,
        "bearing": 90,
        "timestamp": ts,
        "route_code": "1",
        "route_color": "D32F2F",
        "route_text_color": "FFFFFF",
        "type": "brt",
        "next_stops": "Monas",
        "estimated_time_next_stops": "2 menit",
        **extra,
    }


@pytest.fixture
def fake():
    return FakeTJ()


@pytest.fixture
def client(fake):
    settings = Settings(
        _env_file=None, device_id="test-device", bearer_token="", poll_seconds=0.05
    )
    tj = TJClient(settings, transport=httpx.MockTransport(fake))
    tracker = Tracker(settings.bus_expiry_seconds)
    app = create_app(settings, client=tj, tracker=tracker)
    with TestClient(app) as c:
        c.tracker = tracker
        yield c


def make_client(fake, **settings_kw):
    settings = Settings(
        _env_file=None, device_id="test-device", bearer_token="", **settings_kw
    )
    tj = TJClient(settings, transport=httpx.MockTransport(fake))
    app = create_app(settings, client=tj, tracker=Tracker(300))
    return TestClient(app)


def nos(msg):
    return sorted(b["bus_body_no"] for b in msg["buses"])


def wait_for(ws, cond, limit=100):
    """Read snapshots until one matches; returns its bus numbers."""
    for _ in range(limit):
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        if cond(msg):
            return nos(msg)
    raise AssertionError("no matching snapshot")


def test_buses_polls_area_and_returns_nearby(client, fake):
    fake.offline_buses = [bus_msg(), bus_msg(no="FAR", lat=-6.30, lon=106.90)]

    r = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 1})
    assert r.status_code == 200
    body = r.json()
    assert [b["bus_body_no"] for b in body["buses"]] == ["TJ-001"]
    assert body["buses"][0]["type"] == "BRT" and body["buses"][0]["source"] == SOURCE

    assert fake.paths() == ["/v1/auth/login/guest", "/v1/bus/offline"]
    login, req = fake.calls
    assert "Authorization" not in login.headers
    assert req.method == "POST" and req.headers["Authorization"] == "Bearer tok1"
    assert json.loads(req.content) == {
        "latitude": MONAS[0],
        "longitude": MONAS[1],
        "radius": 1.0,
        "event": "change_loc",
    }
    assert (
        req.headers["X-App-OS"] == "android"
        and req.headers["X-Device-ID"] == "test-device"
    )


def test_buses_reuses_recent_poll(fake):
    with make_client(fake, poll_seconds=60) as c:
        for _ in range(3):
            c.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert fake.paths() == ["/v1/auth/login/guest", "/v1/bus/offline"]


def test_token_is_reused(client, fake):
    for _ in range(3):
        client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert fake.paths() == ["/v1/auth/login/guest"] + ["/v2/bus-stop"] * 3


def test_relogin_after_401(client, fake):
    client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    fake.valid.clear()  # server revokes the token
    r = client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert r.status_code == 200
    assert fake.paths().count("/v2/bus-stop") == 3
    assert fake.calls[-1].headers["Authorization"] == "Bearer tok2"


def test_expired_token_is_refreshed():
    fake = FakeTJ(ttl=10)  # inside the renewal margin, so the next call renews it
    tj = TJClient(
        Settings(_env_file=None, bearer_token=""), transport=httpx.MockTransport(fake)
    )

    async def run():
        await tj.get_bus_stops(*MONAS, 1)
        await tj.get_bus_stops(*MONAS, 1)
        await tj.aclose()

    asyncio.run(run())
    assert fake.paths() == [
        "/v1/auth/login/guest",
        "/v2/bus-stop",
        "/v1/auth/token/refresh",
        "/v2/bus-stop",
    ]
    assert json.loads(fake.calls[2].content) == {"refresh_token": "ref1"}


def test_static_bearer_token_skips_guest_login():
    fake = FakeTJ()
    fake.valid.add("mine")
    tj = TJClient(
        Settings(_env_file=None, bearer_token="mine"),
        transport=httpx.MockTransport(fake),
    )

    async def run():
        assert await tj.get_bus_stops(*MONAS, 1) == [
            {"stop_id": "S1", "stop_name": "Monas"}
        ]
        await tj.aclose()

    asyncio.run(run())
    assert fake.paths() == ["/v2/bus-stop"]


def test_snapped_position_and_out_of_order_updates(client):
    t = client.tracker
    t.ingest([bus_msg(ts=2000, snap_latitude=-6.1755, snap_longitude=106.8273)], SOURCE)
    t.ingest([bus_msg(ts=1500, lat=-6.0, lon=106.0)], SOURCE)  # older, ignored
    b = client.get("/buses/TJ-001").json()
    assert (b["latitude"], b["longitude"], b["timestamp"]) == (-6.1755, 106.8273, 2000)


def test_bus_not_found_and_bad_payload(client):
    client.tracker.ingest(["not a bus", {"no_body_no": 1}], SOURCE)
    assert client.get("/buses/NOPE").status_code == 404


def test_validation_and_upstream_errors(client, fake):
    fake.offline_status = 500
    assert client.get("/buses", params={"lat": 51.5, "lon": 0.1}).status_code == 422
    assert (
        client.get(
            "/buses/offline", params={"lat": MONAS[0], "lon": MONAS[1]}
        ).status_code
        == 502
    )
    assert (
        client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).status_code
        == 502
    )
    with client.websocket_connect(f"/ws?lat={MONAS[0]}&lon={MONAS[1]}") as ws:
        assert ws.receive_json()["type"] == "error"


def test_radius_capped_at_max(client, fake):
    assert (
        client.get(
            "/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 20}
        ).json()["radius_km"]
        == 20
    )
    assert (
        client.get(
            "/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 50}
        ).json()["radius_km"]
        == 20
    )
    sent = {
        json.loads(c.content)["radius"]
        for c in fake.calls
        if c.url.path == "/v1/bus/offline"
    }
    assert sent == {20.0}


def test_route_filter(client, fake):
    fake.offline_buses = [
        bus_msg(no=no, route_code=route)
        for no, route in [
            ("A", "4"),
            ("B", "4D"),
            ("C", "10"),
            ("D", "4"),
            ("E", "JAK.10"),
        ]
    ]
    body = client.get(
        "/buses", params={"lat": MONAS[0], "lon": MONAS[1], "routes": " 4, 4d "}
    ).json()
    assert sorted(b["bus_body_no"] for b in body["buses"]) == ["A", "B", "D"]
    assert body["routes"] == ["4", "4D"] and body["count"] == 3
    assert [(r["route_code"], r["count"]) for r in body["routes_available"]] == [
        ("4", 2),
        ("4D", 1),
        ("10", 1),
        ("JAK.10", 1),
    ]
    # no filter -> everything, routes is null
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).json()
    assert body["count"] == 5 and body["routes"] is None


def test_websocket_route_filter(client, fake):
    fake.offline_buses = [
        bus_msg(no="A", route_code="4"),
        bus_msg(no="B", route_code="1"),
    ]
    with client.websocket_connect(
        f"/ws?lat={MONAS[0]}&lon={MONAS[1]}&routes=4D,4"
    ) as ws:
        assert nos(ws.receive_json()) == ["A"]
        fake.offline_buses = [
            bus_msg(no="B", route_code="1", ts=1001),
            bus_msg(no="C", route_code="4d", ts=1001),
        ]
        assert wait_for(ws, lambda m: "C" in nos(m)) == [
            "A",
            "C",
        ]  # 4d matches case-insensitively, B never shows


def test_websocket_sends_snapshot_every_interval(client, fake):
    fake.offline_buses = [bus_msg(no="A"), bus_msg(no="FAR", lat=-6.30, lon=106.90)]
    with client.websocket_connect(
        f"/ws?lat={MONAS[0]}&lon={MONAS[1]}&radius_km=1"
    ) as ws:
        start = time.monotonic()
        snaps = [ws.receive_json() for _ in range(4)]
        assert all(m["type"] == "snapshot" and nos(m) == ["A"] for m in snaps)
        assert (
            time.monotonic() - start >= 3 * 0.05 * 0.8
        )  # paced by poll_seconds, not sent back to back
        assert snaps[0]["buses"][0]["distance_km"] < 1

        # Upstream moves A and adds B: later snapshots follow.
        fake.offline_buses = [
            bus_msg(no="A", lat=-6.1761, ts=1001),
            bus_msg(no="B", ts=1001),
        ]
        wait_for(
            ws,
            lambda m: (
                nos(m) == ["A", "B"]
                and -6.1761 in [b["raw_latitude"] for b in m["buses"]]
            ),
        )
        # B drives out of the radius.
        fake.offline_buses = [bus_msg(no="B", lat=-6.30, lon=106.90, ts=1002)]
        assert wait_for(ws, lambda m: "B" not in nos(m)) == ["A"]
    for _ in range(50):  # the server notices the disconnect asynchronously
        if client.get("/health").json()["tracker"]["ws_clients"] == 0:
            break
        time.sleep(0.02)
    assert client.get("/health").json()["tracker"]["ws_clients"] == 0


def test_stops_passthrough(client):
    r = client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert r.json() == [{"stop_id": "S1", "stop_name": "Monas"}]


def test_decode_polyline():
    # Example from Google's polyline algorithm docs.
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        [38.5, -120.2],
        [40.7, -120.95],
        [43.252, -126.453],
    ]
    assert decode_polyline("") == []


def test_route_detail_normalized_and_cached(client, fake):
    r = client.get("/routes/1")
    assert r.status_code == 200
    body = r.json()
    assert (body["route_code"], body["route_name"], body["route_color"]) == (
        "1",
        "Blok M - Kota",
        "D62126",
    )
    outbound, inbound = body["directions"]
    assert outbound["direction"] == "outbound" and outbound["trip_id"] == "1-R07"
    # Empty polyline: straight lines between stops.
    assert outbound["path"] == [[-6.243312, 106.80175], [-6.1655, 106.8205]]
    assert [s["name"] for s in outbound["stops"]] == ["Blok M", "Harmoni"]
    assert inbound["path"][0] == [-6.13538, 106.81133] and len(inbound["path"]) == 3
    client.get("/routes/1")
    assert fake.paths().count("/v2/route/1") == 1


def test_route_detail_errors(client, fake):
    fake.route_status = 404
    assert client.get("/routes/XYZ").status_code == 404
    fake.route_status = 500
    assert client.get("/routes/ABC").status_code == 502


def test_routes_by_type(client, fake):
    fake.missing_routes = {"/v2/route/2"}
    body = client.get("/routes", params={"type": "brt"}).json()
    # Only BRT, failed detail left out. FakeTJ answers every code with route 1, so check the codes requested.
    assert len(body["routes"]) == 2
    asked = sorted(p for p in fake.paths() if p.startswith("/v2/route/"))
    assert asked == ["/v2/route/1", "/v2/route/10", "/v2/route/2"]
    n = len(fake.calls)
    client.get("/routes", params={"type": "BRT"})
    # List and details come from the cache; only the missing route is asked again.
    assert fake.paths()[n:] == ["/v2/route/2"]
    # No type: every route, Mikrotrans included.
    every = client.get("/routes").json()
    assert every["type"] is None
    assert "/v2/route/JAK.10" in fake.paths()


def test_poll_fields(client, fake):
    fake.offline_buses = [
        bus_msg(
            no="MYS-17084",
            ts="0",
            next_stops="H00251P-Tosari",
            prev_stops="H00022P-Bundaran HI Astra",
            estimated_distance_next_stops=168,
            trip_headsign="Blok M",
            route_name="Blok M",
        )
    ]
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).json()
    b = body["buses"][0]
    assert b["bus_body_no"] == "MYS-17084" and b["source"] == SOURCE
    assert (b["next_stop_name"], b["prev_stop_name"], b["trip_headsign"]) == (
        "Tosari",
        "Bundaran HI Astra",
        "Blok M",
    )


def test_account_login_used_and_trips_available(fake):
    with make_client(fake, login_email="me@example.com", login_password="s3cret") as c:
        r = c.get("/account/trips")
        assert r.status_code == 200 and r.json() == {
            "code": 200,
            "data": [{"trip_id": "T1"}],
        }
        info = c.get("/account").json()
        assert (
            info["mode"] == "user"
            and info["logged_in_as"] == "user"
            and info["email"] == "me@example.com"
        )
        assert "s3cret" not in c.get("/health").text
    assert fake.paths()[0] == "/v1/auth/login"
    assert "Authorization" not in fake.calls[0].headers


def test_wrong_password_falls_back_to_guest(fake):
    with make_client(fake, login_email="me@example.com", login_password="wrong") as c:
        assert (
            c.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]}).status_code
            == 200
        )
        info = c.get("/account").json()
        assert (
            info["logged_in_as"] == "guest"
            and "account login failed" in info["last_error"]
        )
        assert c.get("/account/trips").status_code == 403
        assert "wrong" not in c.get("/health").text
    assert fake.paths()[:2] == ["/v1/auth/login", "/v1/auth/login/guest"]


def test_trips_need_account(client):
    assert client.get("/account/trips").status_code == 403


def test_ui_is_served(client):
    r = client.get("/", follow_redirects=True)
    assert r.status_code == 200 and "TJ Live Tracking" in r.text
    assert 'new URL("/ws", API)' in r.text


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["tracker"] == {
        "buses": 0,
        "areas": 0,
        "ws_clients": 0,
        "poll_seconds": 0.05,
    }
    assert body["auth"]["mode"] == "guest"


def test_routes_type_values(client):
    assert (
        client.get("/routes", params={"type": "angkutan umum integrasi"}).json()["type"]
        == "Angkutan Umum Integrasi"
    )
    assert (
        client.get("/routes", params={"type": "Bus Wisata"}).json()["type"]
        == "Bus Wisata"
    )
    assert client.get("/routes", params={"type": "Kereta"}).status_code == 422


def test_route_types(client):
    types = {t["type"]: t["routes"] for t in client.get("/route-types").json()["types"]}
    assert types["BRT"] == 3 and types["Mikrotrans"] == 1 and types["Royaltrans"] == 0
    assert len(types) == 7


def test_all_stops(client):
    body = client.get("/stops/all", params={"type": "BRT"}).json()
    assert body["type"] == "BRT"
    ids = [s["stop_id"] for s in body["stops"]]
    # FakeTJ answers every code with route 1, so the stops are shared and merged once each.
    assert ids and len(ids) == len(set(ids))
    assert all(
        s["routes"] and {"lat", "lon", "name"} <= s.keys() for s in body["stops"]
    )
    assert client.get("/stops/all", params={"type": "Kereta"}).status_code == 422
