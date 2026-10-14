# Referensi API

Semua contoh di halaman ini memakai server lokal di `http://localhost:8000`. Response diambil dari server yang terhubung ke TransJakarta asli, dengan titik di sekitar Bundaran HI (`-6.1950, 106.8231`). Daftar panjang dipotong; baris `"... (N item total)"` menandai jumlah aslinya.

Dokumentasi interaktif yang dibuat otomatis oleh FastAPI ada di `/docs` (Swagger) dan `/redoc`. Skema OpenAPI mentah ada di `/openapi.json`.

## Aturan umum

| Hal | Aturan |
|---|---|
| Format | Semua response berupa JSON (`Content-Type: application/json`), kecuali `/ui` |
| Autentikasi client | Tidak ada. Siapa pun yang bisa menjangkau server bisa memanggil API. Lihat [11-pengembangan-lanjut.md](11-pengembangan-lanjut.md) kalau server dibuka ke internet |
| CORS | Semua origin diizinkan untuk method `GET` |
| Koordinat | `lat` harus di antara -7.5 dan -5.5, `lon` di antara 106.0 dan 107.5 |
| Radius | `radius_km` harus lebih dari 0. Kosong berarti 1 km. Nilai di atas 20 (`TJ_MAX_RADIUS_KM`) dipotong menjadi 20 |
| Filter jalur | `routes` berisi kode jalur dipisah koma, misalnya `4,4D,JAK.10`. Cocok persis, tidak peka huruf besar-kecil (`4d` = `4D`). `4` tidak ikut mencocokkan `4D` |
| Waktu | `age_seconds` dalam detik. `valid_until` berupa unix timestamp (detik) |

### Format error

Error dari backend sendiri:

```json
{ "detail": "pesan error" }
```

Error validasi parameter (HTTP 422) memakai format bawaan FastAPI, berisi daftar field yang salah:

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["query", "lat"],
      "msg": "Input should be less than or equal to -5.5",
      "input": "51.5",
      "ctx": { "le": -5.5 }
    }
  ]
}
```

### Kode status

| Kode | Arti |
|---|---|
| 200 | Berhasil |
| 307 | Redirect (hanya `GET /`) |
| 403 | Endpoint butuh akun TransJakarta, tapi backend sedang login sebagai guest |
| 404 | Data tidak ditemukan, misalnya bus yang belum pernah terlihat |
| 422 | Parameter salah atau di luar batas |
| 502 | Server TransJakarta menolak atau gagal menjawab. Pesan aslinya ada di `detail` |

## Objek Bus

Endpoint `/buses`, `/buses/{bus_body_no}`, dan `/ws` mengembalikan objek bus dengan bentuk yang sama.

```json
{
  "bus_body_no": "MYS-17022",
  "route_code": "1",
  "route_name": "Kota",
  "trip_headsign": "Kota",
  "route_color": "D62126",
  "route_text_color": "FFFFFF",
  "type": "BRT",
  "latitude": -6.19545,
  "longitude": 106.823278,
  "raw_latitude": -6.19545,
  "raw_longitude": 106.823278,
  "bearing": 217,
  "speed": 0,
  "timestamp": "0",
  "next_stops": "H00278P-Harmoni",
  "next_stop_name": "Harmoni",
  "prev_stop_name": "Monumen Nasional",
  "estimated_time_next_stops": 0,
  "estimated_distance_next_stops": 1626,
  "topic": "rest:/v1/bus/offline",
  "age_seconds": 0.0,
  "distance_km": 0.054
}
```

| Field | Tipe | Asal | Keterangan |
|---|---|---|---|
| `bus_body_no` | string | upstream | Nomor badan bus, unik per kendaraan. Dipakai sebagai ID |
| `route_code` | string | upstream | Kode rute/koridor, misalnya `1`, `4C`, `JAK.10` |
| `route_name` | string \| null | upstream | Nama rute. Dari MQTT bisa tidak ada |
| `trip_headsign` | string \| null | upstream | Tujuan akhir perjalanan saat ini |
| `route_color` | string | upstream | Warna rute dalam hex tanpa `#` |
| `route_text_color` | string | upstream | Warna teks di atas warna rute |
| `type` | string | turunan | `BRT`, `Mikrotrans`, atau `Non-BRT`. Nilai upstream selain BRT dan Mikrotrans (misalnya `Angkutan Umum Integrasi`, `Royaltrans`) menjadi `Non-BRT`, sama seperti di app |
| `latitude`, `longitude` | number | turunan | Posisi yang dipakai. Kalau upstream mengirim posisi yang sudah ditempelkan ke jalur (`snap_latitude`/`snap_longitude`), nilai itu yang dipakai |
| `raw_latitude`, `raw_longitude` | number | upstream | Posisi GPS mentah |
| `bearing` | number | upstream | Arah hadap dalam derajat (0 = utara, searah jarum jam) |
| `speed` | number \| null | upstream | Kecepatan. Dari REST sering bernilai 0 |
| `timestamp` | string \| number | upstream | Waktu data dari upstream. Dari REST bernilai `"0"` |
| `next_stops` | string \| null | upstream | Kode dan nama halte berikutnya, misalnya `H00278P-Harmoni` |
| `next_stop_name` | string \| null | turunan | `next_stops` tanpa kode halte |
| `prev_stop_name` | string \| null | turunan | Nama halte sebelumnya, dari `prev_stops` |
| `estimated_time_next_stops` | number \| string | upstream | Perkiraan waktu ke halte berikutnya. Sering bernilai 0, artinya tidak diketahui |
| `estimated_distance_next_stops` | number \| null | upstream | Jarak ke halte berikutnya dalam meter |
| `topic` | string | backend | Asal data: nama topik MQTT, `rest:/v1/bus/offline`, atau `rest:/v1/bus` |
| `age_seconds` | number | backend | Sudah berapa detik sejak backend menerima data bus ini |
| `distance_km` | number | backend | Jarak dari titik yang diminta. Tidak ada di `GET /buses/{bus_body_no}` |

Kode halte berawalan `H` untuk halte BRT dan `B` untuk bus stop biasa, contohnya `H00278P` dan `B00790P`.

---

## `GET /health`

Status server, login upstream, dan koneksi MQTT. Cocok untuk monitoring.

**Request**

```powershell
curl http://localhost:8000/health
```

**Response 200**

```json
{
  "status": "ok",
  "auth": {
    "mode": "guest",
    "logged_in_as": "guest",
    "email": null,
    "has_token": true,
    "valid_until": 1791987415,
    "last_error": null
  },
  "mqtt": {
    "connected": false,
    "broker_url": "wss://mqtt.tj.co.id:8084/mqtt",
    "buses": 3,
    "topics": 4,
    "subscribed": 0,
    "listeners": 1
  }
}
```

| Field | Keterangan |
|---|---|
| `auth` | Sama dengan `GET /account` |
| `mqtt.connected` | `true` kalau broker MQTT terhubung |
| `mqtt.broker_url` | Alamat broker yang dipakai. Kosong kalau backend belum berhasil mendapatkannya |
| `mqtt.buses` | Jumlah bus yang sedang disimpan di memori (dari semua area) |
| `mqtt.topics` | Jumlah topik yang sedang diminati client |
| `mqtt.subscribed` | Jumlah topik yang benar-benar sudah di-subscribe ke broker |
| `mqtt.listeners` | Jumlah client WebSocket yang tersambung |

---

## `GET /buses`

Daftar bus di sekitar sebuah titik, diurutkan dari yang terdekat.

Panggilan pertama untuk sebuah area membuat backend mulai memantau area itu: mengambil topik dari upstream, subscribe ke MQTT, dan (kalau MQTT tidak tersedia) langsung mengambil posisi lewat REST. Panggilan berikutnya dalam 60 detik memakai cache.

**Parameter query**

| Nama | Wajib | Tipe | Bawaan | Keterangan |
|---|---|---|---|---|
| `lat` | ya | number | | Lintang titik pusat |
| `lon` | ya | number | | Bujur titik pusat |
| `radius_km` | tidak | number | 1 | Radius pencarian, maksimal 20 |
| `routes` | tidak | string | | Hanya jalur ini, dipisah koma, misalnya `4,4D` |
| `wait` | tidak | number | 0 | Kalau belum ada bus di cache, tunggu sampai sekian detik (0–10) untuk posisi pertama |

**Request**

```powershell
curl "http://localhost:8000/buses?lat=-6.1950&lon=106.8231&radius_km=0.5"
```

**Response 200**

```json
{
  "count": 3,
  "radius_km": 0.5,
  "routes": null,
  "routes_available": [
    { "route_code": "1", "route_color": "D62126", "route_text_color": "FFFFFF", "count": 1 },
    { "route_code": "4C", "route_color": "553C62", "route_text_color": "FFFFFF", "count": 1 },
    "... (3 item total)"
  ],
  "topics": [
    "/mobile_armada/0017-0020/#",
    "/mobile_armada/0017-0021/#",
    "... (4 item total)"
  ],
  "mqtt_connected": false,
  "buses": [
    {
      "bus_body_no": "MYS-17022",
      "route_code": "1",
      "route_name": "Kota",
      "trip_headsign": "Kota",
      "route_color": "D62126",
      "route_text_color": "FFFFFF",
      "type": "BRT",
      "latitude": -6.19545,
      "longitude": 106.823278,
      "raw_latitude": -6.19545,
      "raw_longitude": 106.823278,
      "bearing": 217,
      "speed": 0,
      "timestamp": "0",
      "next_stops": "H00278P-Harmoni",
      "next_stop_name": "Harmoni",
      "prev_stop_name": "Monumen Nasional",
      "estimated_time_next_stops": 0,
      "estimated_distance_next_stops": 1626,
      "topic": "rest:/v1/bus/offline",
      "age_seconds": 0.0,
      "distance_km": 0.054
    },
    {
      "bus_body_no": "DMR-230106",
      "route_code": "4C",
      "route_name": "JIEP",
      "trip_headsign": "JIEP",
      "route_color": "553C62",
      "route_text_color": "FFFFFF",
      "type": "Non-BRT",
      "latitude": -6.19448,
      "longitude": 106.8232,
      "raw_latitude": -6.19448,
      "raw_longitude": 106.8232,
      "bearing": 116,
      "speed": 0,
      "timestamp": "0",
      "next_stops": "B00790P-Imam Bonjol",
      "next_stop_name": "Imam Bonjol",
      "prev_stop_name": "Tosari 2",
      "estimated_time_next_stops": 0,
      "estimated_distance_next_stops": 230,
      "topic": "rest:/v1/bus/offline",
      "age_seconds": 0.0,
      "distance_km": 0.059
    }
  ]
}
```

| Field | Keterangan |
|---|---|
| `count` | Jumlah bus dalam `buses` (setelah filter jalur) |
| `radius_km` | Radius yang benar-benar dipakai (setelah dipotong ke batas maksimal) |
| `routes` | Filter jalur yang dipakai, dalam huruf besar dan terurut, atau `null` kalau tanpa filter |
| `routes_available` | Semua jalur yang ada di radius ini **sebelum** filter, dengan warna dan jumlah bus, urut alami (1, 1A, 2, 4, 4D, 10, JAK.10). Berguna untuk membuat pilihan filter |
| `topics` | Topik MQTT untuk area ini menurut upstream |
| `mqtt_connected` | Status broker saat request diproses |
| `buses` | Daftar [objek bus](#objek-bus) |

### Menyaring jalur

```powershell
curl "http://localhost:8000/buses?lat=-6.1950&lon=106.8231&radius_km=20&routes=4,4d"
```

```json
{
  "count": 23,
  "radius_km": 20.0,
  "routes": ["4", "4D"],
  "routes_available": [
    { "route_code": "1", "route_color": "D62126", "route_text_color": "FFFFFF", "count": 40 },
    "... (212 item total)"
  ],
  "topics": ["... (1332 item total)"],
  "mqtt_connected": false,
  "buses": ["... 23 objek bus jalur 4 dan 4D, urut jarak"]
}
```

Angka di atas dari uji live 13 Oktober 2026 (radius 20 km di sekitar Bundaran HI: 2.118 bus, 212 jalur, 23 bus jalur 4/4D, 40 bus jalur 1). `routes=4` hanya mengembalikan jalur `4`, bukan `4D` atau `4C`.

**Error**

| Kode | Kapan |
|---|---|
| 422 | `lat`/`lon` tidak ada, bukan angka, atau di luar batas; `radius_km` ≤ 0; `wait` di luar 0–10 |
| 502 | Upstream menolak `POST /v1/bus`, misalnya `{"detail": "upstream error: POST /v1/bus: HTTP 401 ..."}` |

Contoh 422 untuk koordinat London:

```powershell
curl "http://localhost:8000/buses?lat=51.5&lon=0.1"
```

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["query", "lat"],
      "msg": "Input should be less than or equal to -5.5",
      "input": "51.5",
      "ctx": { "le": -5.5 }
    },
    {
      "type": "greater_than_equal",
      "loc": ["query", "lon"],
      "msg": "Input should be greater than or equal to 106",
      "input": "0.1",
      "ctx": { "ge": 106.0 }
    }
  ]
}
```

---

## `GET /buses/{bus_body_no}`

Status terakhir satu bus. Bus hanya dikenal kalau areanya sedang dipantau (pernah diminta lewat `/buses` atau `/ws` dalam 5 menit terakhir).

**Request**

```powershell
curl http://localhost:8000/buses/MYS-17022
```

**Response 200**

```json
{
  "bus_body_no": "MYS-17022",
  "route_code": "1",
  "route_name": "Kota",
  "trip_headsign": "Kota",
  "route_color": "D62126",
  "route_text_color": "FFFFFF",
  "type": "BRT",
  "latitude": -6.19545,
  "longitude": 106.823278,
  "raw_latitude": -6.19545,
  "raw_longitude": 106.823278,
  "bearing": 217,
  "speed": 0,
  "timestamp": "0",
  "next_stops": "H00278P-Harmoni",
  "next_stop_name": "Harmoni",
  "prev_stop_name": "Monumen Nasional",
  "estimated_time_next_stops": 0,
  "estimated_distance_next_stops": 1626,
  "topic": "rest:/v1/bus/offline",
  "age_seconds": 0.1
}
```

**Response 404**

```powershell
curl http://localhost:8000/buses/NOPE-1
```

```json
{ "detail": "bus not seen recently; query /buses for its area first" }
```

---

## `GET /buses/offline`

Meneruskan `POST /v1/bus/offline` dari upstream apa adanya (isi field `data`). Berguna untuk melihat data mentah, termasuk field yang tidak dipakai backend seperti `trip_id`, `livery`, dan `curr_stops`. Endpoint ini tidak memengaruhi cache atau pemantauan area.

**Parameter query**: `lat`, `lon`, `radius_km`, aturannya sama dengan `/buses`.

**Request**

```powershell
curl "http://localhost:8000/buses/offline?lat=-6.1950&lon=106.8231&radius_km=0.5"
```

**Response 200**

```json
[
  {
    "bus_body_no": "MYS-17022",
    "route_code": "1",
    "route_name": "Kota",
    "route_color": "D62126",
    "latitude": -6.19545,
    "longitude": 106.823278,
    "speed": 0,
    "bearing": 217,
    "timestamp": "0",
    "trip_id": "1-R07",
    "direction": "",
    "distance": 0,
    "route_text_color": "FFFFFF",
    "type": "BRT",
    "stops": [],
    "trip_headsign": "Kota",
    "estimated_time_next_stops": 0,
    "estimated_distance_next_stops": 1626,
    "curr_stops": "",
    "next_stops": "H00278P-Harmoni",
    "prev_stops": "H00131P-Monumen Nasional",
    "livery": null
  },
  "... (19 item total)"
]
```

Upstream menyaring sesuai radius (bus terjauh selalu berada dalam radius yang diminta). Endpoint ini tidak menghitung `distance_km` dan tidak mengurutkan hasilnya; gunakan `/buses` untuk itu.

**Error**: 422 untuk parameter, 502 kalau upstream gagal.

---

## `GET /stops`

Halte dan bus stop di sekitar titik. Meneruskan `GET /v2/bus-stop` dari upstream (isi field `data`).

**Parameter query**: `lat`, `lon`, `radius_km`.

**Request**

```powershell
curl "http://localhost:8000/stops?lat=-6.1950&lon=106.8231&radius_km=0.5"
```

**Response 200**

```json
[
  {
    "stop_id": "B02863P",
    "platform_code": "",
    "stop_name": "Plaza Indonesia",
    "stop_lat": -6.193733,
    "stop_lon": 106.8228,
    "facilities": [],
    "routes": [
      {
        "route_id": "1P",
        "route_short_name": "1P",
        "route_long_name": "Senen - Blok M",
        "route_color": "D65E62",
        "route_text_color": "000000",
        "route_desc": "Angkutan Umum Integrasi"
      },
      {
        "route_id": "1T",
        "route_short_name": "1T",
        "route_long_name": "Cibubur - Balai Kota",
        "route_color": "9C4782",
        "route_text_color": "FFFFFF",
        "route_desc": "Royaltrans"
      },
      "... (3 item total)"
    ],
    "distance": 0.14,
    "bus_stop_type": "bus_stop",
    "v2_facilities": [],
    "stop_gates": {},
    "header_detail_color": ""
  },
  "... (20 item total)"
]
```

| Field | Keterangan |
|---|---|
| `stop_id` | Kode halte (`H…` halte BRT, `B…` bus stop) |
| `stop_name` | Nama halte |
| `stop_lat`, `stop_lon` | Posisi |
| `routes` | Rute yang berhenti di halte ini |
| `distance` | Jarak dari titik yang diminta, dalam km |
| `bus_stop_type` | `halte` atau `bus_stop` |
| `facilities`, `v2_facilities` | Fasilitas halte (sering kosong) |
| `stop_gates` | Data pintu halte (sering kosong) |

Upstream membatasi hasil 20 halte per permintaan (`meta.limit = 20`).

---

## `GET /account`

Identitas yang dipakai backend saat bicara dengan upstream. Tidak pernah berisi token atau password.

**Request**

```powershell
curl http://localhost:8000/account
```

**Response 200, mode guest**

```json
{
  "mode": "guest",
  "logged_in_as": "guest",
  "email": null,
  "has_token": true,
  "valid_until": 1791987415,
  "last_error": null
}
```

**Response 200, akun berhasil login**

```json
{
  "mode": "user",
  "logged_in_as": "user",
  "email": "nama@contoh.com",
  "has_token": true,
  "valid_until": 1791990000,
  "last_error": null
}
```

**Response 200, password salah sehingga jatuh ke guest**

```json
{
  "mode": "user",
  "logged_in_as": "guest",
  "email": "nama@contoh.com",
  "has_token": true,
  "valid_until": 1791987415,
  "last_error": "account login failed: POST /v1/auth/login: HTTP 400 {\"code\":400,\"message\":\"...\"}"
}
```

| Field | Keterangan |
|---|---|
| `mode` | Mode yang diminta konfigurasi: `guest`, `user`, atau `static` |
| `logged_in_as` | Identitas yang benar-benar dipakai sekarang: `guest`, `user`, `static`, atau `null` kalau belum login |
| `email` | Email dari `TJ_LOGIN_EMAIL`, atau `null` |
| `has_token` | Apakah backend sudah memegang token |
| `valid_until` | Kapan token berakhir (unix detik). `null` untuk mode `static` |
| `last_error` | Pesan error login akun terakhir, atau `null` |

Login terjadi saat request pertama yang butuh upstream. Sebelum itu `has_token` bernilai `false` dan `logged_in_as` bernilai `null`.

---

## `GET /account/trips`

Riwayat perjalanan akun TransJakarta yang dikonfigurasi. Meneruskan `GET /v1/user/trips` dari upstream. Hanya bisa dipakai kalau backend login dengan akun (`TJ_LOGIN_EMAIL` dan `TJ_LOGIN_PASSWORD`, atau `TJ_BEARER_TOKEN`).

**Parameter query**

| Nama | Wajib | Bawaan | Keterangan |
|---|---|---|---|
| `page` | tidak | 1 | Halaman, mulai dari 1 |
| `limit` | tidak | 10 | Jumlah per halaman, 1–50 |

**Request**

```powershell
curl "http://localhost:8000/account/trips?page=1&limit=10"
```

**Response 200**

Isinya response asli upstream. Bentuk persisnya tergantung akun dan belum dicatat dari akun asli. Di test, bentuk yang dipakai adalah:

```json
{ "code": 200, "data": [ { "trip_id": "T1" } ] }
```

**Response 403, backend login sebagai guest**

```json
{ "detail": "needs a TransJakarta account: set TJ_LOGIN_EMAIL and TJ_LOGIN_PASSWORD in .env" }
```

**Error lain**: 502 kalau upstream menolak.

---

## `WS /ws`

Aliran posisi bus untuk satu area. Client menerima satu pesan `snapshot` berisi semua bus yang sudah diketahui, lalu satu pesan `update` setiap ada bus di dalam radius yang posisinya berubah.

**Parameter query**: `lat`, `lon`, `radius_km`, dan `routes`, aturannya sama dengan `/buses`. Dengan `routes`, `snapshot` dan `update` hanya berisi jalur itu.

**URL**

```
ws://localhost:8000/ws?lat=-6.1950&lon=106.8231&radius_km=0.5
```

Selama koneksi terbuka, backend memperbarui topik area itu setiap 60 detik dan (kalau MQTT tidak tersedia) mem-polling posisinya setiap 10 detik.

### Pesan dari server

**`snapshot`**, dikirim sekali setelah koneksi diterima:

```json
{
  "type": "snapshot",
  "buses": [
    {
      "bus_body_no": "MYS-17022",
      "route_code": "1",
      "route_name": "Kota",
      "trip_headsign": "Kota",
      "route_color": "D62126",
      "route_text_color": "FFFFFF",
      "type": "BRT",
      "latitude": -6.19545,
      "longitude": 106.823278,
      "raw_latitude": -6.19545,
      "raw_longitude": 106.823278,
      "bearing": 217,
      "speed": 0,
      "timestamp": "0",
      "next_stops": "H00278P-Harmoni",
      "next_stop_name": "Harmoni",
      "prev_stop_name": "Monumen Nasional",
      "estimated_time_next_stops": 0,
      "estimated_distance_next_stops": 1626,
      "topic": "rest:/v1/bus/offline",
      "age_seconds": 0.2,
      "distance_km": 0.054
    },
    "... (3 item total)"
  ]
}
```

**`update`**, satu bus berubah posisi:

```json
{
  "type": "update",
  "bus": {
    "bus_body_no": "DMR-230106",
    "route_code": "4C",
    "route_name": "JIEP",
    "trip_headsign": "JIEP",
    "route_color": "553C62",
    "route_text_color": "FFFFFF",
    "type": "Non-BRT",
    "latitude": -6.194908,
    "longitude": 106.823551,
    "raw_latitude": -6.194908,
    "raw_longitude": 106.823551,
    "bearing": 162,
    "speed": 0,
    "timestamp": "0",
    "next_stops": "B00790P-Imam Bonjol",
    "next_stop_name": "Imam Bonjol",
    "prev_stop_name": "Tosari 2",
    "estimated_time_next_stops": 0,
    "estimated_distance_next_stops": 165,
    "topic": "rest:/v1/bus/offline",
    "age_seconds": 0.0,
    "distance_km": 0.051
  }
}
```

**`error`**, dikirim kalau backend gagal mendaftarkan area (misalnya upstream menolak). Setelah pesan ini server menutup koneksi dengan kode 1011.

```json
{
  "type": "error",
  "detail": "upstream error: POST /v1/bus: HTTP 401 {\"code\":401,\"message\":\"Unauthorized, token is required\",\"data\":{\"type\":\"PopUp\"}}\n"
}
```

### Perilaku yang perlu diketahui

- Bus yang keluar dari radius tidak dikirimi pesan "hapus". Client sebaiknya membuang bus yang tidak mendapat update selama beberapa menit. UI bawaan memakai 5 menit.
- Hanya bus yang datanya berubah yang dikirim sebagai `update`. Polling REST mengulang semua bus setiap 10 detik, tetapi bus yang diam tidak dikirim ulang.
- Kalau client terlalu lambat membaca, antrean per client dibatasi 10.000 pesan (cukup untuk beberapa polling radius 20 km). Pesan terlama dibuang lebih dulu.
- Parameter yang tidak valid membuat handshake ditolak (kode 1008 menurut Starlette) sebelum `snapshot` dikirim.
- Untuk pindah area, tutup koneksi lalu buka koneksi baru dengan koordinat baru.

### Contoh client

JavaScript (browser atau Node 22+):

```js
const ws = new WebSocket("ws://localhost:8000/ws?lat=-6.1950&lon=106.8231&radius_km=0.5");
const buses = new Map();

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "snapshot") msg.buses.forEach((b) => buses.set(b.bus_body_no, b));
  if (msg.type === "update") buses.set(msg.bus.bus_body_no, msg.bus);
  if (msg.type === "error") console.error(msg.detail);
  console.log(`${buses.size} bus`);
};
```

Python (paket `websockets`):

```python
import asyncio, json, websockets

async def main():
    url = "ws://localhost:8000/ws?lat=-6.1950&lon=106.8231&radius_km=0.5"
    async with websockets.connect(url) as ws:
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] == "snapshot":
                print("awal:", len(msg["buses"]), "bus")
            elif msg["type"] == "update":
                b = msg["bus"]
                print(b["route_code"], b["bus_body_no"], "->", b["next_stop_name"])

asyncio.run(main())
```

---

## `GET /` dan `GET /ui/`

`GET /` membalas `307 Temporary Redirect` ke `/ui/`. `GET /ui/` menyajikan `app/static/index.html`, yaitu UI peta. Penjelasan UI ada di [08-ui.md](08-ui.md).

## Contoh client HTTP

Python dengan `httpx`:

```python
import httpx

with httpx.Client(base_url="http://localhost:8000") as api:
    r = api.get("/buses", params={"lat": -6.1950, "lon": 106.8231, "radius_km": 0.5, "wait": 3})
    r.raise_for_status()
    for bus in r.json()["buses"]:
        print(f'{bus["route_code"]:>6} {bus["bus_body_no"]:<12} {bus["distance_km"] * 1000:5.0f} m  → {bus["next_stop_name"]}')
```

Contoh keluaran:

```
     1 MYS-17022       54 m  → Harmoni
    4C DMR-230106      59 m  → Imam Bonjol
```

JavaScript dengan `fetch`:

```js
const res = await fetch("http://localhost:8000/stops?lat=-6.1950&lon=106.8231&radius_km=0.5");
const stops = await res.json();
console.log(stops.map((s) => `${s.stop_name} (${s.bus_stop_type})`));
```
