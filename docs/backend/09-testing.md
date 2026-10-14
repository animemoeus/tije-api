# Testing

Ada dua jenis pengujian: test otomatis yang tidak butuh internet, dan uji live ke server TransJakarta dengan browser sungguhan.

## Test otomatis

```powershell
.\.venv\Scripts\python -m pytest -q
```

```
.................                                                        [100%]
21 passed, 1 warning in 0.65s
```

Peringatan `StarletteDeprecationWarning` tentang `httpx2` berasal dari `TestClient` Starlette dan tidak memengaruhi hasil.

### Cara kerjanya

Semua test ada di `tests/test_api.py`.

- **`FakeTJ`** meniru `tijeapi` lewat `httpx.MockTransport`. Ia menerbitkan token (`tok1`, `tok2`, …), menolak request tanpa token valid dengan 401 seperti server asli, dan menyediakan `/v1/auth/login/guest`, `/v1/auth/login` (hanya menerima `me@example.com` / `s3cret`), `/v1/auth/token/refresh`, `/v1/bus`, `/v1/bus/offline`, `/v2/bus-stop`, `/v1/settings/api/config/mqtt_url`, dan `/v1/user/trips`. Semua request yang diterima dicatat di `fake.calls`.
- **MQTT** tidak dijalankan (`start_mqtt=False`). Pesan dari broker disimulasikan dengan memanggil `tracker.handle_message(topic, payload)` langsung.
- **`client`** (fixture) membuat aplikasi lengkap lewat `create_app` dan membungkusnya dengan `fastapi.testclient.TestClient`, jadi lifespan, routing, validasi, dan WebSocket ikut dites.

### Daftar test

| Test | Yang dipastikan |
|---|---|
| `test_buses_subscribes_area_and_returns_nearby` | Urutan request upstream (login guest → `/v1/bus` → `/v1/bus/offline`), body `/v1/bus`, header identitas, Bearer token, hanya bus dalam radius yang dikembalikan, jenis `brt` menjadi `BRT` |
| `test_topics_and_token_are_reused` | Tiga `/buses` berturut-turut hanya memicu satu `/v1/bus`, dan token dipakai ulang untuk `/stops` |
| `test_relogin_after_401` | Token dicabut server → backend login ulang sekali dan request berhasil dengan `tok2` |
| `test_expired_token_is_refreshed` | Token yang hampir habis diperbarui lewat `/v1/auth/token/refresh` dengan `refresh_token` yang benar |
| `test_static_bearer_token_skips_guest_login` | `TJ_BEARER_TOKEN` dipakai langsung tanpa login |
| `test_rest_buses_seed_tracker` | `data.buses` dari `/v1/bus` langsung masuk ke daftar bus |
| `test_snapped_position_and_out_of_order_updates` | Posisi `snap_*` diutamakan; update dengan timestamp lebih lama diabaikan |
| `test_bus_not_found_and_bad_payload` | Pesan MQTT bukan JSON diabaikan; bus tak dikenal → 404 |
| `test_validation_and_upstream_errors` | Koordinat London → 422; upstream 500 → 502 |
| `test_radius_capped_at_max` | Radius 50 dipotong ke 20, dan topik area dipakai ulang dari cache |
| `test_route_filter` | `routes= 4, 4d ` hanya mengembalikan jalur 4 dan 4D; `routes_available` urut alami dengan jumlah benar |
| `test_unchanged_bus_is_not_rebroadcast` | Data bus yang sama persis tidak dikirim ulang lewat WebSocket, tapi umurnya tetap diperbarui |
| `test_websocket_route_filter` | WebSocket dengan `routes=4D,4` hanya mengirim jalur itu, tidak peka huruf besar-kecil |
| `test_stops_passthrough` | `/stops` meneruskan `data` dari `/v2/bus-stop` |
| `test_rest_poll_fills_buses_when_mqtt_down` | Tanpa MQTT, `/buses` berisi data `/v1/bus/offline`; `next_stop_name`, `prev_stop_name`, `trip_headsign` benar |
| `test_account_login_used_and_trips_available` | Login akun dipakai, `/account/trips` 200, `/account` menunjukkan `user`, password tidak muncul di `/health` |
| `test_wrong_password_falls_back_to_guest` | Password salah → guest, `last_error` terisi, `/account/trips` 403, password tidak bocor |
| `test_trips_need_account` | Mode guest → `/account/trips` 403 |
| `test_websocket_snapshot_then_updates` | WebSocket mengirim `snapshot`, lalu `update` hanya untuk bus di dalam radius |
| `test_ui_is_served` | `/` mengarah ke UI dan halaman memuat kode WebSocket |
| `test_health` | `/health` berisi status, auth guest, MQTT belum terhubung |

### Menjalankan sebagian

```powershell
.\.venv\Scripts\python -m pytest -q -k account        # hanya test yang namanya mengandung "account"
.\.venv\Scripts\python -m pytest -q -x                # berhenti di kegagalan pertama
.\.venv\Scripts\python -m pytest -vv tests/test_api.py::test_relogin_after_401
```

## Uji live dengan Playwright

Uji ini membuka UI di Microsoft Edge tanpa jendela, membiarkan backend bicara dengan server TransJakarta asli, lalu memeriksa hasilnya. Uji ini mengirim request sungguhan ke upstream, jadi jalankan seperlunya.

### Persiapan

Playwright tidak dipasang di venv proyek. Uji yang dipakai selama pengembangan memanfaatkan `playwright-core` yang sudah ikut terpasang bersama paket npm global `rea-agents`, dan Microsoft Edge yang ada di Windows (`channel: "msedge"`, jadi tidak perlu mengunduh browser Playwright).

Cara yang paling mudah diulang adalah memasang `playwright-core` di folder terpisah. Paket npm global tidak bisa di-`import` dari modul ES, jadi pasang secara lokal:

```powershell
mkdir $env:TEMP\tj-e2e; cd $env:TEMP\tj-e2e
npm init -y
npm install playwright-core@1.58.2
```

### Skrip

Simpan sebagai `live_e2e.mjs` di folder `tj-e2e` tadi:

```js
import { chromium } from "playwright-core";

const base = "http://127.0.0.1:8770";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

const errors = [];
const frames = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("websocket", (ws) => ws.on("framereceived", (f) => frames.push(String(f.payload))));

await page.goto(base + "/", { waitUntil: "networkidle" });
await page.mouse.click(780, 330);                       // pilih titik di dekat koridor 1
await page.waitForSelector(".bus", { timeout: 60000 }); // tunggu bus pertama
await page.waitForTimeout(25000);                       // beri waktu untuk beberapa polling

console.log("status :", await page.textContent("#status"));
console.log("sumber :", await page.textContent("#source"));
console.log("daftar :", await page.locator(".bus").count(), "bus");
console.log("marker :", await page.locator(".bus-icon").count());
console.log("frame WS:", frames.length);
console.log("error  :", errors);

await page.click("#stopsBtn");
await page.waitForTimeout(3000);
console.log("halte  :", await page.textContent("#stopsBtn"));
await page.screenshot({ path: "live.png" });

const health = await (await fetch(base + "/health")).json();
console.log("health :", health.auth.logged_in_as, health.mqtt);
await browser.close();
```

### Menjalankan

Terminal pertama, server di port terpisah supaya tidak bentrok dengan server yang sedang dipakai:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --port 8770
```

Terminal kedua:

```powershell
node live_e2e.mjs
```

### Hasil yang didapat saat pengembangan

```
status : Live · 48 bus
sumber : Sumber: polling REST (MQTT tidak terjangkau) · guest
daftar : 48 bus
marker : 48
frame WS: 79
error  : []
halte  : Sembunyikan halte (20)
health : guest { connected: false, broker_url: 'wss://mqtt.tj.co.id:8084/mqtt', buses: 52, topics: 9, subscribed: 0, listeners: 1 }
```

Request ke upstream selama uji (dari log server):

```
1 POST /v1/auth/login/guest
1 GET  /v1/settings/api/config/mqtt_url
2 POST /v1/bus
6 POST /v1/bus/offline
1 GET  /v2/bus-stop
```

![Hasil uji live](../images/ui-live.png)

## Uji tampilan tanpa upstream

Untuk mengubah UI tanpa menyentuh server TransJakarta, jalankan aplikasi dengan upstream palsu dan bus simulasi. Contoh skrip demo:

```python
"""Demo: aplikasi asli + upstream palsu + tiga bus berputar di sekitar Monas."""
import json, math, threading, time
import httpx, uvicorn
from app.config import Settings
from app.main import create_app
from app.tracker import Tracker
from app.upstream import TJClient

def upstream(req):
    if req.url.path == "/v1/auth/login/guest":
        return httpx.Response(200, json={"token": "demo", "token_valid_until": time.time() + 86400})
    if req.url.path == "/v1/bus":
        return httpx.Response(200, json={"data": {"topics": ["demo/area"], "buses": []}})
    if req.url.path == "/v1/bus/offline":
        return httpx.Response(200, json={"data": []})
    if req.url.path == "/v2/bus-stop":
        return httpx.Response(200, json={"data": [
            {"stop_id": "1", "stop_name": "Monas", "stop_lat": -6.1767, "stop_lon": 106.8230, "bus_stop_type": "halte"}]})
    return httpx.Response(404)

s = Settings(bearer_token="")
tracker = Tracker(s.bus_expiry_seconds, s.topic_idle_seconds)
app = create_app(s, client=TJClient(s, transport=httpx.MockTransport(upstream)), tracker=tracker, start_mqtt=False)

def simulate():
    t = 0
    while True:
        for i, (no, route, color) in enumerate([("TJ-0101", "1", "D32F2F"), ("TJ-0205", "2", "1565C0"), ("MK-1001", "JAK.10", "F9A825")]):
            a = t / 20 + i * 2
            tracker.handle_message("demo/area", json.dumps({
                "bus_body_no": no, "route_code": route, "route_color": color, "route_text_color": "FFFFFF",
                "latitude": -6.1754 + 0.004 * math.sin(a), "longitude": 106.8272 + 0.005 * math.cos(a),
                "bearing": (math.degrees(-a) + 360) % 360, "timestamp": t, "type": "brt", "next_stops": "H00001P-Monas",
            }).encode())
        t += 1
        time.sleep(1)

threading.Thread(target=simulate, daemon=True).start()
uvicorn.run(app, host="127.0.0.1", port=8766)
```

Simpan sebagai `demo_server.py` **di dalam folder `python`** (sejajar dengan folder `app`), karena Python mencari paket `app` relatif terhadap lokasi skrip. Lalu:

```powershell
.\.venv\Scripts\python demo_server.py
```

Buka http://127.0.0.1:8766/. `GET /buses?lat=-6.1754&lon=106.8272` akan berisi tiga bus simulasi (`TJ-0101`, `TJ-0205`, `MK-1001`). Kalau skrip disimpan di tempat lain, jalankan dengan `$env:PYTHONPATH = "<path ke folder python>"` lebih dulu.
