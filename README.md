# TJ Live Tracking API

Backend kecil (FastAPI) yang menyediakan posisi bus TransJakarta secara live untuk client lain lewat HTTP dan WebSocket.

**Dokumentasi lengkap ada di [docs/](docs/README.md)**: [backend](docs/README.md#backend) (instalasi, konfigurasi, referensi API dengan contoh request/response, alur end to end, autentikasi, struktur kode, UI, testing, troubleshooting) dan [source](docs/source/README.md) (analisis lengkap APK TransJakarta 3.0.4: manifest, kode native, library, bundle Hermes, katalog 152 endpoint, live tracking, temuan keamanan).

Alurnya meniru app Android TransJakarta v3.0.4 (hasil analisis bundle Hermes, sudah dicek ke server asli):

1. Login: `POST /v1/auth/login {email, password}` kalau akun diisi di `.env`, kalau tidak `POST /v1/auth/login/guest`. Token (berlaku ±24 jam) dikirim sebagai `Authorization: Bearer …` dan diperbarui otomatis lewat `POST /v1/auth/token/refresh`.
2. `GET /v1/settings/api/config/mqtt_url` → alamat broker MQTT (saat ini `wss://mqtt.tj.co.id:8084/mqtt`).
3. `POST /v1/bus {latitude, longitude, radius, event:"change_loc"}` → `data.topics` (mis. `/mobile_armada/0014-0020/#`), lalu subscribe topik itu di broker; tiap pesan adalah JSON satu bus.
4. Kalau broker MQTT tidak terjangkau, posisi bus diambil dengan polling `POST /v1/bus/offline` (default tiap 10 detik) untuk area yang sedang dipantau. Hasilnya dikirim lewat API dan WebSocket yang sama.

> `tijeapi.transjakarta.co.id` bukan API publik resmi. Formatnya bisa berubah sewaktu-waktu, dan pemakaian di luar app mungkin melanggar ketentuan layanan TransJakarta. Backend ini meng-cache lookup topik, hanya membuka satu koneksi MQTT, dan hanya mem-polling area yang sedang diminta client, agar beban ke server mereka kecil.

## Login akun TransJakarta (opsional)

Peta, bus, dan halte cukup dengan login guest (otomatis). Untuk endpoint yang butuh akun, isi `.env`:

```
TJ_LOGIN_EMAIL=you@example.com
TJ_LOGIN_PASSWORD=your-password
```

- Password tidak pernah ditulis ke log atau dikembalikan oleh API.
- Kalau login akun gagal (password salah, dll.), backend tetap jalan sebagai guest; alasannya terlihat di `GET /account` dan `/health` (`last_error`).
- Endpoint akun yang tersedia: `GET /account/trips` (riwayat perjalanan, `GET /v1/user/trips`). Endpoint akun lain bisa ditambah di `app/main.py` dengan `client.request("GET", "/v1/…")`. Sengaja hanya endpoint baca; endpoint yang mengubah akun (edit/hapus profil, pembayaran) tidak dibuka.

## Setup

```powershell
cd python
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # opsional
```

## Menjalankan

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- UI peta: http://localhost:8000/ (redirect ke `/ui/`)
- Dokumentasi interaktif: http://localhost:8000/docs

## UI template

`app/static/index.html` adalah satu file HTML tanpa build step (Leaflet + OpenStreetMap) yang memanggil API ini:

- klik peta atau tombol **Lokasi saya** untuk memilih titik pantau, lalu pilih radius;
- bus tampil live lewat `WS /ws` (marker berwarna sesuai rute, panah menunjukkan arah), daftar di samping diurutkan dari yang terdekat; klik item untuk membuka marker-nya;
- tombol **Tampilkan halte** memanggil `GET /stops`;
- koneksi WebSocket otomatis tersambung ulang kalau putus.

Halaman ini memanggil API di origin yang sama. Untuk memakai file HTML-nya dari tempat lain, tambahkan `?api=http://host:8000`, misalnya `index.html?api=http://192.168.1.10:8000`.

## Endpoint

| Method | Path | Keterangan |
|---|---|---|
| GET | `/health` | Status server, login upstream, dan koneksi MQTT |
| GET | `/account` | Identitas upstream yang dipakai (guest/akun, tanpa token/password) |
| GET | `/account/trips?page=&limit=` | Riwayat perjalanan akun (butuh `TJ_LOGIN_EMAIL`/`TJ_LOGIN_PASSWORD`, 403 kalau guest) |
| GET | `/buses?lat=&lon=&radius_km=&wait=` | Bus live di sekitar titik, urut dari yang terdekat. `wait` (0–10 detik) menunggu posisi pertama kalau cache masih kosong |
| GET | `/buses/{bus_body_no}` | Status terakhir satu bus (areanya harus sudah pernah diminta lewat `/buses` atau `/ws`) |
| GET | `/buses/offline?lat=&lon=&radius_km=` | Diteruskan apa adanya dari `POST /v1/bus/offline` |
| GET | `/stops?lat=&lon=&radius_km=` | Halte/bus stop di sekitar, diteruskan dari `GET /v2/bus-stop` |
| WS | `/ws?lat=&lon=&radius_km=` | Pesan `snapshot` sekali, lalu `update` setiap ada bus bergerak di dalam radius |

`radius_km` default 1, maksimal 20. `routes=4,4D` menyaring jalur (di `/buses` dan `/ws`). Koordinat dibatasi ke sekitar Jakarta.

Contoh:

```powershell
curl "http://localhost:8000/buses?lat=-6.1754&lon=106.8272&radius_km=1&wait=5"
```

```json
{
  "count": 1,
  "radius_km": 1.0,
  "topics": ["..."],
  "mqtt_connected": false,
  "buses": [{
    "bus_body_no": "MYS-17084", "route_code": "1", "route_name": "Blok M", "trip_headsign": "Blok M", "type": "BRT",
    "latitude": -6.19544, "longitude": 106.8233, "bearing": 227, "speed": 0,
    "next_stops": "H00251P-Tosari", "next_stop_name": "Tosari", "prev_stop_name": "Bundaran HI Astra",
    "estimated_distance_next_stops": 168, "estimated_time_next_stops": 0,
    "topic": "rest:/v1/bus/offline", "distance_km": 0.012, "age_seconds": 3.1
  }]
}
```

Contoh client WebSocket (JavaScript):

```js
const ws = new WebSocket("ws://localhost:8000/ws?lat=-6.1754&lon=106.8272&radius_km=1");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## Konfigurasi

Semua lewat environment variable berawalan `TJ_` atau file `.env`; lihat `.env.example`.
Header yang dikirim ke upstream (`X-App-Version`, `X-Device-ID`, `X-App-OS`, …) sama dengan yang dikirim app.

## Test

```powershell
.\.venv\Scripts\python -m pytest -q
```

Test memakai upstream palsu (`httpx.MockTransport`) dan pesan MQTT simulasi, jadi tidak menghubungi server TransJakarta.

## Catatan

- Sudah dicek ke server asli: login guest, `POST /v1/bus`, `POST /v1/bus/offline`, `GET /v2/bus-stop`, dan URL broker.
- Broker MQTT `mqtt.tj.co.id` (103.145.125.134) tidak bisa dihubungi dari jaringan tempat backend ini dites (semua port timeout), sementara `tijeapi` bisa. Kemungkinan broker dibatasi per jaringan/IP. Selama itu terjadi, backend otomatis memakai polling REST; kalau broker bisa dihubungi, `/health` menunjukkan `"connected": true` dan update datang realtime.
- `estimated_time_next_stops` sering bernilai `0` dari upstream; UI menampilkan jarak ke halte berikutnya (`estimated_distance_next_stops`, meter).
- Login dengan akun (`/v1/auth/login`) dibuat dari analisis bundle dan sudah dites dengan upstream palsu; belum dicoba dengan akun asli.
