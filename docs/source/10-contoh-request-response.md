# Contoh request dan response asli

Semua contoh di halaman ini dikirim ke `https://tijeapi.transjakarta.co.id` pada 13 Oktober 2026 dengan header identitas yang sama seperti app (lihat [06-bundle-javascript.md](06-bundle-javascript.md#header)). Titik yang dipakai: sekitar Bundaran HI, `-6.1950, 106.8231`.

Yang disamarkan: `token`, `refresh_token`, `email`, `name`. Daftar panjang dipotong menjadi dua item, ditandai `"... (N item total)"`.

Header yang selalu dikirim (kecuali `Authorization` pada login):

```http
X-App-Version: 3.0.4
X-Device-ID: 9f2c41d07ab35e18
X-Lang: id
X-FCM-Token:
X-App-OS: android
X-App-OS-Version: 14
X-App-Platform: 34
X-Device-Model: Google|Pixel 8
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>
```

## Tanpa token → 401

```http
POST /v1/bus HTTP/1.1

{"latitude": -6.195, "longitude": 106.8231, "radius": 1, "event": "change_loc"}
```

```json
{
  "code": 401,
  "message": "Unauthorized, token is required",
  "data": { "type": "PopUp" }
}
```

## `POST /v1/auth/login/guest`

```http
POST /v1/auth/login/guest HTTP/1.1

{}
```

HTTP 200:

```json
{
  "user": {
    "email": "<disamarkan>",
    "phone": "",
    "name": "<disamarkan>",
    "avatar": "",
    "have_password": false,
    "is_verified": false,
    "is_guest": true,
    "id": 0
  },
  "token": "<disamarkan>",
  "token_valid_until": 1791987416,
  "refresh_token": "<disamarkan>",
  "refresh_token_valid_until": 1791991016,
  "moter": null
}
```

Panjang `token` dan `refresh_token` masing-masing 272 karakter. Selisih `token_valid_until` dengan waktu request sekitar 86.400 detik (24 jam).

## `GET /v1/settings/api/config/mqtt_url`

```http
GET /v1/settings/api/config/mqtt_url HTTP/1.1
Authorization: Bearer <token>
```

HTTP 200:

```json
{
  "meta": {
    "code": 200,
    "status": "success",
    "message": "response.success"
  },
  "data": {
    "createdAt": "2025-10-16T04:25:32Z",
    "isActive": true,
    "name": "<tidak dicatat>",
    "properties": {
      "url": "wss://mqtt.tj.co.id:8084/mqtt"
    },
    "updatedAt": "2026-02-23T06:50:57Z"
  }
}
```

Endpoint konfigurasi memakai bentuk `meta` + `data`, berbeda dari endpoint lain yang memakai `code` + `message` + `data`.

## `POST /v1/bus`

```http
POST /v1/bus HTTP/1.1
Authorization: Bearer <token>

{"latitude": -6.195, "longitude": 106.8231, "radius": 1, "event": "change_loc"}
```

HTTP 200:

```json
{
  "code": 200,
  "message": "success",
  "session_id": "",
  "data": {
    "buses": [],
    "session_id": "",
    "polyline": "xzud@s~|jS?o}@o}@?n}@??o}@o}@?~{B~{B?o}@o}@?n}@??o}@o}@?~{B~{B?o}@o}@?n}@??o}@o}@?",
    "stops": [],
    "topics": [
      "/mobile_armada/0016-0020/#",
      "/mobile_armada/0016-0021/#",
      "... (6 item total)"
    ]
  }
}
```

Catatan:

- `buses` dan `stops` kosong pada semua percobaan. Posisi bus didapat dari MQTT atau `/v1/bus/offline`.
- Jumlah topik tergantung titik dan radius: 6 untuk Bundaran HI radius 1 km, 9 untuk Harmoni.
- `polyline` adalah Google encoded polyline dari kotak-kotak sel kisi topik.

## `POST /v1/bus/offline`

```http
POST /v1/bus/offline HTTP/1.1
Authorization: Bearer <token>

{"latitude": -6.195, "longitude": 106.8231, "radius": 1, "event": "change_loc"}
```

HTTP 200:

```json
{
  "code": 200,
  "message": "success",
  "data": [
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
    {
      "bus_body_no": "DMR-230106",
      "route_code": "4C",
      "route_name": "JIEP",
      "route_color": "553C62",
      "latitude": -6.19448,
      "longitude": 106.8232,
      "speed": 0,
      "bearing": 116,
      "timestamp": "0",
      "trip_id": "4C-L05",
      "direction": "",
      "distance": 0,
      "route_text_color": "FFFFFF",
      "type": "Angkutan Umum Integrasi",
      "stops": [],
      "trip_headsign": "JIEP",
      "estimated_time_next_stops": 0,
      "estimated_distance_next_stops": 230,
      "curr_stops": "",
      "next_stops": "B00790P-Imam Bonjol",
      "prev_stops": "B05774P-Tosari 2",
      "livery": null
    },
    "... (19 item total)"
  ]
}
```

| Field | Pengamatan |
|---|---|
| `bus_body_no` | Awalannya kemungkinan kode operator, misalnya `MYS-`, `DMR-`, `SAF-`, `PKT-`, `BMP-`, `MB-` |
| `trip_id` | `<rute>-<arah><nomor>`, misalnya `1-R07`, `4C-L05` |
| `type` | Nilai yang terlihat di data bus: `BRT`, `Angkutan Umum Integrasi`. Di `route_desc` halte juga muncul `Royaltrans`. Kode WebView juga mengenal `MIKROTRANS` |
| `timestamp` | `"0"` (string) di semua data yang diamati |
| `speed` | 0 di semua data yang diamati |
| `estimated_time_next_stops` | 0 di semua data yang diamati |
| `estimated_distance_next_stops` | Meter ke halte berikutnya, berisi nilai nyata |
| `next_stops`, `prev_stops` | `<kode>-<nama>`. Kode `H…` halte BRT, `B…` bus stop |
| `curr_stops`, `direction`, `livery` | Kosong atau `null` |

Untuk radius 1 km di Bundaran HI ada 19 bus; di Harmoni 24 bus. Upstream menyaring sesuai radius: pada pengukuran 0,5 / 1 / 5 / 10 / 20 km, bus terjauh selalu berada di dalam radius. Radius besar didukung (20 km: ±2.300 bus dalam ±1 detik).

Posisi di endpoint ini diperbarui terus. Dua panggilan berjarak 10 detik untuk radius 20 km: 1.354 dari 2.126 bus berubah, terutama `latitude`, `longitude`, `bearing`, dan `estimated_distance_next_stops`. Tidak ada `bus_body_no` yang muncul dua kali.

## `GET /v2/bus-stop`

```http
GET /v2/bus-stop?latitude=-6.195&longitude=106.8231&radius=1 HTTP/1.1
Authorization: Bearer <token>
```

HTTP 200:

```json
{
  "code": 200,
  "message": "success",
  "data": [
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
    {
      "stop_id": "B05892P",
      "platform_code": "",
      "stop_name": "Wisma Nusantara",
      "stop_lat": -6.193425,
      "stop_lon": 106.82319,
      "facilities": [],
      "routes": ["... (3 item total)"],
      "distance": 0.18,
      "bus_stop_type": "bus_stop",
      "v2_facilities": [],
      "stop_gates": {},
      "header_detail_color": ""
    },
    "... (20 item total)"
  ],
  "meta": {
    "limit": 20,
    "offset": 0,
    "total": 20
  }
}
```

`route_desc` memakai kategori yang sama dengan `type` pada data bus. `distance` dalam km dan sudah diurutkan dari yang terdekat. Hasil dibatasi 20 per halaman; parameter halaman berikutnya tidak ditelusuri.

## Broker MQTT

`wss://mqtt.tj.co.id:8084/mqtt` resolve ke `103.145.125.134`. Dari jaringan pengembang, koneksi TCP ke port 8084, 8083, 443, 8883, 1883, dan 80 semuanya timeout, sementara `tijeapi` bisa diakses normal. Karena itu isi pesan MQTT asli belum pernah tercatat. Field-nya hanya diketahui dari kode WebView (lihat [09-live-tracking.md](09-live-tracking.md#isi-pesan-mqtt)).
