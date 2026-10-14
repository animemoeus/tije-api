# TJ Live Tracking API

Backend kecil (FastAPI) yang menyediakan posisi bus TransJakarta secara live untuk client lain lewat HTTP dan WebSocket.

**Dokumentasi lengkap ada di [docs/](docs/README.md)**: [backend](docs/README.md#backend) (instalasi, konfigurasi, referensi API dengan contoh request/response, alur end to end, autentikasi, struktur kode, UI, testing, troubleshooting) dan [source](docs/source/README.md) (analisis lengkap APK TransJakarta 3.0.4: manifest, kode native, library, bundle Hermes, katalog 152 endpoint, live tracking, temuan keamanan).

Alurnya meniru app Android TransJakarta v3.0.4 (hasil analisis bundle Hermes, sudah dicek ke server asli):

1. Login: `POST /v1/auth/login {email, password}` kalau akun diisi di `.env`, kalau tidak `POST /v1/auth/login/guest`. Token (berlaku ±24 jam) dikirim sebagai `Authorization: Bearer …` dan diperbarui otomatis lewat `POST /v1/auth/token/refresh`.
2. Posisi bus diambil dengan polling `POST /v1/bus/offline {latitude, longitude, radius, event:"change_loc"}`, default tiap 1 detik, hanya untuk area yang sedang dipantau client WebSocket. `GET /buses` mem-poll area-nya saat diminta.
3. `WS /ws` mengirim snapshot semua bus di radius setiap 1 detik.

Backend ini tidak memakai MQTT. App aslinya memakai broker MQTT (`wss://mqtt.tj.co.id:8084/mqtt`), tetapi broker itu tidak bisa dihubungi dari luar jaringan mereka.

> `tijeapi.transjakarta.co.id` bukan API publik resmi. Formatnya bisa berubah sewaktu-waktu, dan pemakaian di luar app mungkin melanggar ketentuan layanan TransJakarta. Tiap area yang punya client WebSocket aktif = 1 request per detik ke server mereka; client di area yang sama berbagi satu poll. Naikkan `TJ_POLL_SECONDS` kalau perlu mengurangi beban.

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
- bus tampil live lewat `WS /ws`, diperbarui tiap detik (marker berwarna sesuai rute, panah menunjukkan arah; bus yang keluar radius hilang), daftar di samping diurutkan dari yang terdekat; klik item untuk membuka marker-nya;
- tombol **Tampilkan halte** memanggil `GET /stops`;
- koneksi WebSocket otomatis tersambung ulang kalau putus.

Halaman ini memanggil API di origin yang sama. Untuk memakai file HTML-nya dari tempat lain, tambahkan `?api=http://host:8000`, misalnya `index.html?api=http://192.168.1.10:8000`.

## Endpoint

| Method | Path | Keterangan |
|---|---|---|
| GET | `/health` | Status server, login upstream, jumlah bus/area/client WebSocket |
| GET | `/account` | Identitas upstream yang dipakai (guest/akun, tanpa token/password) |
| GET | `/account/trips?page=&limit=` | Riwayat perjalanan akun (butuh `TJ_LOGIN_EMAIL`/`TJ_LOGIN_PASSWORD`, 403 kalau guest) |
| GET | `/buses?lat=&lon=&radius_km=` | Bus live di sekitar titik, urut dari yang terdekat |
| GET | `/buses/{bus_body_no}` | Status terakhir satu bus (areanya harus sudah pernah diminta lewat `/buses` atau `/ws`) |
| GET | `/buses/offline?lat=&lon=&radius_km=` | Diteruskan apa adanya dari `POST /v1/bus/offline` |
| GET | `/stops?lat=&lon=&radius_km=` | Halte/bus stop di sekitar, diteruskan dari `GET /v2/bus-stop` |
| WS | `/ws?lat=&lon=&radius_km=` | Pesan `{"type":"snapshot","buses":[…]}` tiap 1 detik (`TJ_POLL_SECONDS`), berisi semua bus di dalam radius |

`radius_km` default 1, maksimal 20. `routes=4,4D` menyaring jalur (di `/buses` dan `/ws`). Koordinat dibatasi ke sekitar Jakarta.

Contoh:

```powershell
curl "http://localhost:8000/buses?lat=-6.1754&lon=106.8272&radius_km=1"
```

```json
{
  "count": 1,
  "radius_km": 1.0,
  "routes": null,
  "routes_available": [{"route_code": "1", "route_color": "D62126", "route_text_color": "FFFFFF", "count": 1}],
  "buses": [{
    "bus_body_no": "MYS-17084", "route_code": "1", "route_name": "Blok M", "trip_headsign": "Blok M", "type": "BRT",
    "latitude": -6.19544, "longitude": 106.8233, "bearing": 227, "speed": 0,
    "next_stops": "H00251P-Tosari", "next_stop_name": "Tosari", "prev_stop_name": "Bundaran HI Astra",
    "estimated_distance_next_stops": 168, "estimated_time_next_stops": 0,
    "source": "rest:/v1/bus/offline", "distance_km": 0.012, "age_seconds": 0.4
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

Test memakai upstream palsu (`httpx.MockTransport`) dan mengabaikan `.env`, jadi tidak menghubungi server TransJakarta.

## Lint & format

Pakai [ruff](https://docs.astral.sh/ruff/). Pasang hook pre-commit sekali setelah install dependency:

```powershell
.\.venv\Scripts\pre-commit install
```

Setelah itu `ruff check --fix` dan `ruff format` jalan otomatis tiap commit. Untuk menjalankan manual ke semua file:

```powershell
.\.venv\Scripts\pre-commit run --all-files
```

## Catatan

- Sudah dicek ke server asli: login guest, `POST /v1/bus/offline`, `GET /v2/bus-stop`, dan `WS /ws` (snapshot tiap ±1,00 detik).
- Snapshot radius besar cukup berat: radius 20 km ≈ 2.300 bus ≈ 1–2 MB per detik per client.
- `estimated_time_next_stops` sering bernilai `0` dari upstream; UI menampilkan jarak ke halte berikutnya (`estimated_distance_next_stops`, meter).
- Login dengan akun (`/v1/auth/login`) dibuat dari analisis bundle dan sudah dites dengan upstream palsu; belum dicoba dengan akun asli.
