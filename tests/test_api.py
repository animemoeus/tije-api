"""Offline tests: fake tijeapi via httpx.MockTransport, fake MQTT via Tracker.handle_message."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tracker import Tracker
from app.upstream import TJClient

MONAS = (-6.1754, 106.8272)
TOPIC = "/mobile_armada/0014-0020/#"


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

    def _tokens(self):
        self.issued += 1
        tok = f"tok{self.issued}"
        self.valid.add(tok)
        now = int(time.time())
        return {"token": tok, "token_valid_until": now + self.ttl, "refresh_token": f"ref{self.issued}",
                "refresh_token_valid_until": now + self.ttl + 3600, "user": {"is_guest": True}, "moter": None}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        path = req.url.path
        if path == "/v1/auth/login/guest":
            return httpx.Response(200, json=self._tokens())
        if path == "/v1/auth/login":
            body = json.loads(req.content)
            if body != {"email": "me@example.com", "password": "s3cret"}:
                return httpx.Response(400, json={"code": 400, "message": "Email atau password salah"})
            t = self._tokens()
            self.user_tokens.add(t["token"])
            return httpx.Response(200, json=t)
        if path == "/v1/auth/token/refresh":
            return httpx.Response(200, json={"data": self._tokens()})
        auth = req.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ") not in self.valid:
            return httpx.Response(401, json={"code": 401, "message": "Unauthorized, token is required"})
        if path == "/v1/bus":
            return httpx.Response(200, json={"code": 200, "data": {"topics": [TOPIC], "buses": [], "stops": []}})
        if path == "/v2/bus-stop":
            return httpx.Response(200, json={"data": [{"stop_id": "S1", "stop_name": "Monas"}]})
        if path == "/v1/bus/offline":
            if self.offline_status != 200:
                return httpx.Response(self.offline_status, text="boom")
            return httpx.Response(200, json={"code": 200, "data": self.offline_buses})
        if path == "/v1/user/trips":
            if auth.removeprefix("Bearer ") not in self.user_tokens:
                return httpx.Response(403, json={"code": 403, "message": "guest"})
            return httpx.Response(200, json={"code": 200, "data": [{"trip_id": "T1"}]})
        if path == "/v1/settings/api/config/mqtt_url":
            return httpx.Response(200, json={"data": {"properties": {"url": "wss://mqtt.example:8084/mqtt"}}})
        return httpx.Response(404)

    def paths(self):
        return [c.url.path for c in self.calls]


def bus_msg(no="TJ-001", lat=-6.1760, lon=106.8280, ts=1000, **extra):
    return json.dumps({
        "bus_body_no": no, "latitude": lat, "longitude": lon, "bearing": 90, "timestamp": ts,
        "route_code": "1", "route_color": "D32F2F", "route_text_color": "FFFFFF", "type": "brt",
        "next_stops": "Monas", "estimated_time_next_stops": "2 menit", **extra,
    }).encode()


@pytest.fixture
def fake():
    return FakeTJ()


@pytest.fixture
def client(fake):
    settings = Settings(device_id="test-device", bearer_token="")
    tj = TJClient(settings, transport=httpx.MockTransport(fake))
    tracker = Tracker(settings.bus_expiry_seconds, settings.topic_idle_seconds)
    app = create_app(settings, client=tj, tracker=tracker, start_mqtt=False)
    with TestClient(app) as c:
        c.tracker = tracker
        yield c


def test_buses_subscribes_area_and_returns_nearby(client, fake):
    client.tracker.handle_message(TOPIC, bus_msg())
    client.tracker.handle_message(TOPIC, bus_msg(no="FAR", lat=-6.30, lon=106.90))

    r = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["topics"] == [TOPIC]
    assert [b["bus_body_no"] for b in body["buses"]] == ["TJ-001"]
    assert body["buses"][0]["type"] == "BRT"
    assert TOPIC in client.tracker._topics

    # MQTT is not running in tests, so the first request also polls /v1/bus/offline.
    assert fake.paths() == ["/v1/auth/login/guest", "/v1/bus", "/v1/bus/offline"]
    login, req, _ = fake.calls
    assert "Authorization" not in login.headers
    assert req.method == "POST" and req.headers["Authorization"] == "Bearer tok1"
    assert json.loads(req.content) == {"latitude": MONAS[0], "longitude": MONAS[1], "radius": 1.0, "event": "change_loc"}
    assert req.headers["X-App-OS"] == "android" and req.headers["X-Device-ID"] == "test-device"


def test_topics_and_token_are_reused(client, fake):
    for _ in range(3):
        client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]})
    client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert fake.paths() == ["/v1/auth/login/guest", "/v1/bus", "/v1/bus/offline", "/v2/bus-stop"]


def test_relogin_after_401(client, fake):
    client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    fake.valid.clear()  # server revokes the token
    r = client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert r.status_code == 200
    assert fake.paths().count("/v2/bus-stop") == 3
    assert fake.calls[-1].headers["Authorization"] == "Bearer tok2"


def test_expired_token_is_refreshed():
    fake = FakeTJ(ttl=10)  # inside the renewal margin, so the next call renews it
    tj = TJClient(Settings(bearer_token=""), transport=httpx.MockTransport(fake))

    async def run():
        await tj.get_bus_stops(*MONAS, 1)
        await tj.get_bus_stops(*MONAS, 1)
        await tj.aclose()

    asyncio.run(run())
    assert fake.paths() == ["/v1/auth/login/guest", "/v2/bus-stop", "/v1/auth/token/refresh", "/v2/bus-stop"]
    assert json.loads(fake.calls[2].content) == {"refresh_token": "ref1"}


def test_static_bearer_token_skips_guest_login():
    fake = FakeTJ()
    fake.valid.add("mine")
    tj = TJClient(Settings(bearer_token="mine"), transport=httpx.MockTransport(fake))

    async def run():
        assert await tj.get_mqtt_url() == "wss://mqtt.example:8084/mqtt"
        await tj.aclose()

    asyncio.run(run())
    assert fake.paths() == ["/v1/settings/api/config/mqtt_url"]


def test_rest_buses_seed_tracker(client, fake):
    orig = fake.__call__

    def with_buses(req):
        if req.url.path == "/v1/bus":
            fake.calls.append(req)
            return httpx.Response(200, json={"data": {"topics": [TOPIC], "buses": [json.loads(bus_msg(no="REST-1"))]}})
        return orig(req)

    client.app.state.client._http._transport = httpx.MockTransport(with_buses)
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).json()
    assert [b["bus_body_no"] for b in body["buses"]] == ["REST-1"]


def test_snapped_position_and_out_of_order_updates(client):
    t = client.tracker
    t.handle_message(TOPIC, bus_msg(ts=2000, snap_latitude=-6.1755, snap_longitude=106.8273))
    t.handle_message(TOPIC, bus_msg(ts=1500, lat=-6.0, lon=106.0))  # older, ignored
    b = client.get("/buses/TJ-001").json()
    assert (b["latitude"], b["longitude"], b["timestamp"]) == (-6.1755, 106.8273, 2000)


def test_bus_not_found_and_bad_payload(client):
    client.tracker.handle_message(TOPIC, b"not json")
    assert client.get("/buses/NOPE").status_code == 404


def test_validation_and_upstream_errors(client, fake):
    fake.offline_status = 500
    assert client.get("/buses", params={"lat": 51.5, "lon": 0.1}).status_code == 422
    r = client.get("/buses/offline", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert r.status_code == 502


def test_radius_capped_at_max(client, fake):
    assert client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 20}).json()["radius_km"] == 20
    assert client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1], "radius_km": 50}).json()["radius_km"] == 20
    sent = [json.loads(c.content)["radius"] for c in fake.calls if c.url.path == "/v1/bus"]
    assert sent == [20.0]  # second request hits the (lat, lon, 20) topic cache


def test_route_filter(client):
    for no, route in [("A", "4"), ("B", "4D"), ("C", "10"), ("D", "4"), ("E", "JAK.10")]:
        client.tracker.handle_message(TOPIC, bus_msg(no=no, route_code=route))
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1], "routes": " 4, 4d "}).json()
    assert sorted(b["bus_body_no"] for b in body["buses"]) == ["A", "B", "D"]
    assert body["routes"] == ["4", "4D"] and body["count"] == 3
    assert [(r["route_code"], r["count"]) for r in body["routes_available"]] == [("4", 2), ("4D", 1), ("10", 1), ("JAK.10", 1)]
    # no filter -> everything, routes is null
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).json()
    assert body["count"] == 5 and body["routes"] is None


def test_unchanged_bus_is_not_rebroadcast(client):
    with client.websocket_connect(f"/ws?lat={MONAS[0]}&lon={MONAS[1]}") as ws:
        ws.receive_json()  # snapshot
        client.tracker.handle_message(TOPIC, bus_msg(no="A"))
        client.tracker.handle_message(TOPIC, bus_msg(no="A"))           # identical: refreshes age only
        client.tracker.handle_message(TOPIC, bus_msg(no="A", lat=-6.1761))  # moved
        assert ws.receive_json()["bus"]["latitude"] == -6.176
        assert ws.receive_json()["bus"]["latitude"] == -6.1761
    assert client.get("/buses/A").json()["age_seconds"] < 5


def test_websocket_route_filter(client):
    client.tracker.handle_message(TOPIC, bus_msg(no="A", route_code="4"))
    client.tracker.handle_message(TOPIC, bus_msg(no="B", route_code="1"))
    with client.websocket_connect(f"/ws?lat={MONAS[0]}&lon={MONAS[1]}&routes=4D,4") as ws:
        assert [b["bus_body_no"] for b in ws.receive_json()["buses"]] == ["A"]
        client.tracker.handle_message(TOPIC, bus_msg(no="B", route_code="1", ts=1001))   # filtered out
        client.tracker.handle_message(TOPIC, bus_msg(no="C", route_code="4d", ts=1001))  # case-insensitive
        assert ws.receive_json()["bus"]["bus_body_no"] == "C"


def test_stops_passthrough(client):
    r = client.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]})
    assert r.json() == [{"stop_id": "S1", "stop_name": "Monas"}]


def test_websocket_snapshot_then_updates(client):
    client.tracker.handle_message(TOPIC, bus_msg(no="A"))
    with client.websocket_connect(f"/ws?lat={MONAS[0]}&lon={MONAS[1]}&radius_km=1") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and [b["bus_body_no"] for b in snap["buses"]] == ["A"]
        client.tracker.handle_message(TOPIC, bus_msg(no="FAR", lat=-6.30, lon=106.90))  # filtered out
        client.tracker.handle_message(TOPIC, bus_msg(no="B", ts=1001))
        upd = ws.receive_json()
        assert upd["type"] == "update" and upd["bus"]["bus_body_no"] == "B"


def make_client(fake, **settings_kw):
    settings = Settings(device_id="test-device", bearer_token="", **settings_kw)
    tj = TJClient(settings, transport=httpx.MockTransport(fake))
    app = create_app(settings, client=tj, tracker=Tracker(300, 600), start_mqtt=False)
    return TestClient(app)


def test_rest_poll_fills_buses_when_mqtt_down(client, fake):
    fake.offline_buses = [json.loads(bus_msg(no="MYS-17084", ts="0", next_stops="H00251P-Tosari",
                                              prev_stops="H00022P-Bundaran HI Astra", estimated_distance_next_stops=168,
                                              trip_headsign="Blok M", route_name="Blok M"))]
    body = client.get("/buses", params={"lat": MONAS[0], "lon": MONAS[1]}).json()
    b = body["buses"][0]
    assert b["bus_body_no"] == "MYS-17084" and b["topic"] == "rest:/v1/bus/offline"
    assert (b["next_stop_name"], b["prev_stop_name"], b["trip_headsign"]) == ("Tosari", "Bundaran HI Astra", "Blok M")


def test_account_login_used_and_trips_available(fake):
    with make_client(fake, login_email="me@example.com", login_password="s3cret") as c:
        r = c.get("/account/trips")
        assert r.status_code == 200 and r.json() == {"code": 200, "data": [{"trip_id": "T1"}]}
        info = c.get("/account").json()
        assert info["mode"] == "user" and info["logged_in_as"] == "user" and info["email"] == "me@example.com"
        assert "s3cret" not in c.get("/health").text
    assert fake.paths()[0] == "/v1/auth/login"
    assert "Authorization" not in fake.calls[0].headers


def test_wrong_password_falls_back_to_guest(fake):
    with make_client(fake, login_email="me@example.com", login_password="wrong") as c:
        assert c.get("/stops", params={"lat": MONAS[0], "lon": MONAS[1]}).status_code == 200
        info = c.get("/account").json()
        assert info["logged_in_as"] == "guest" and "account login failed" in info["last_error"]
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
    assert body["status"] == "ok" and body["mqtt"]["connected"] is False
    assert body["auth"]["mode"] == "guest"
