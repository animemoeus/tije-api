# Alur end to end

Halaman ini mengikuti data dari saat server dinyalakan sampai titik bus muncul di layar client. Setiap alur disertai diagram urutan dan contoh request yang benar-benar dikirim ke server TransJakarta.

Singkatan di diagram:

- **Client**: UI peta atau aplikasi lain yang memanggil backend.
- **API**: `app/main.py`.
- **TJClient**: `app/upstream.py`.
- **Tracker**: `app/tracker.py`.
- **tijeapi**: `https://tijeapi.transjakarta.co.id`.

## 1. Server dinyalakan

```mermaid
sequenceDiagram
    participant U as uvicorn
    participant API
    participant TJ as TJClient
    participant TR as Tracker

    U->>API: lifespan start
    API->>TJ: buat TJClient(settings)
    API->>TR: buat Tracker(bus_expiry_seconds)
    API->>API: app.state.areas = {}
    API->>API: jalankan tugas latar: _prune_loop (30 dtk), _poll_loop (TJ_POLL_SECONDS)
```

Saat startup backend belum menghubungi upstream sama sekali. Login terjadi pada request pertama yang butuh data dari `tijeapi` (lihat alur 2 dan 6), dan `_poll_loop` tidak melakukan apa pun selama belum ada area dengan client WebSocket.

## 2. Client meminta bus di sebuah area

Contoh: `GET /buses?lat=-6.1950&lon=106.8231&radius_km=0.5`.

```mermaid
sequenceDiagram
    participant C as Client
    participant API
    participant TJ as TJClient
    participant TR as Tracker
    participant T as tijeapi

    C->>API: GET /buses?lat&lon&radius_km
    API->>API: validasi lat, lon, radius
    API->>API: track_area: cari/buat area (lat, lon dibulatkan 3 desimal, radius)
    alt polling terakhir area ini < TJ_POLL_SECONDS lalu
        API->>API: pakai data yang ada
    else belum pernah atau sudah lebih lama
        API->>TJ: get_offline_buses(lat, lon, 0.5)
        TJ->>T: POST /v1/bus/offline {latitude, longitude, radius, event: change_loc}
        T-->>TJ: daftar posisi bus
        API->>TR: ingest(posisi, source = rest:/v1/bus/offline)
    end
    API->>TR: buses_near(lat, lon, 0.5)
    TR-->>API: bus dalam radius, urut jarak
    API-->>C: {count, radius_km, routes, routes_available, buses}
```

Kalau polling pertama untuk area itu gagal, client menerima 502. Kalau area sudah pernah berhasil di-polling, kegagalan berikutnya hanya dicatat di log dan client menerima data terakhir yang ada.

Area yang hanya diminta lewat `GET /buses` disimpan di `app.state.areas`, tapi tidak di-polling di latar belakang. Area itu dihapus setelah `TJ_AREA_IDLE_SECONDS` (60 detik) tanpa request.

Kalau ini request pertama sejak server dinyalakan, TJClient login dulu sebagai guest (atau dengan akun, lihat [06-autentikasi-upstream.md](06-autentikasi-upstream.md)):

```http
POST /v1/auth/login/guest HTTP/1.1
Host: tijeapi.transjakarta.co.id
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

{}
```

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
  "token": "<disamarkan, 272 karakter>",
  "token_valid_until": 1791987416,
  "refresh_token": "<disamarkan, 272 karakter>",
  "refresh_token_valid_until": 1791991016,
  "moter": null
}
```

Lalu request posisi bus:

```http
POST /v1/bus/offline HTTP/1.1
Host: tijeapi.transjakarta.co.id
Authorization: Bearer <token>
Content-Type: application/json

{"latitude": -6.195, "longitude": 106.8231, "radius": 0.5, "event": "change_loc"}
```

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
    "... (19 item total)"
  ]
}
```

Tracker mengubah setiap item menjadi [objek bus](04-referensi-api.md#objek-bus), lalu `buses_near` menghitung jarak haversine ke titik pusat dan membuang yang di luar radius. Hasil akhirnya contoh response `GET /buses` di referensi API.

## 3. Client tersambung lewat WebSocket

```mermaid
sequenceDiagram
    participant C as Client
    participant API
    participant TR as Tracker
    participant P as _poll_loop
    participant B as _broadcast_loop

    C->>API: WS /ws?lat&lon&radius_km&hz
    API->>C: accept
    API->>API: track_area(...) seperti alur 2
    alt polling pertama gagal
        API->>C: {"type": "error", "detail": "..."}
        API->>C: close 1011
    else berhasil
        API->>C: snapshot pertama
        API->>API: daftarkan client ke area.clients
        par di latar belakang
            P->>TR: ingest(posisi dari /v1/bus/offline) tiap TJ_POLL_SECONDS
        and setiap tick (TJ_WS_BASE_SECONDS / 4)
            B->>TR: buses_near(area), sekali per area
            B->>B: json.dumps sekali per filter jalur
            B->>API: taruh frame di slot client yang jatuh tempo
            API->>C: {"type": "snapshot", "buses": [...]}
        end
    end
    C--xAPI: tutup koneksi
    API->>API: hapus client dari area.clients
```

Setiap koneksi WebSocket punya dua tugas kecil: satu membaca dari client hanya untuk mengetahui kapan koneksi putus, satu lagi menunggu frame baru di slot miliknya lalu mengirimnya.

Isi `snapshot` dihitung oleh satu tugas latar, `_broadcast_loop`. Setiap tick (0,25 detik dengan bawaan) tugas ini memeriksa client mana yang jatuh tempo: client `hz=4` setiap tick, `hz=2` setiap 2 tick, `hz=1` setiap 4 tick. Untuk setiap area yang punya client jatuh tempo, `buses_near` dipanggil sekali, lalu hasilnya disaring dan di-encode ke JSON sekali per filter jalur. String yang sama dipakai untuk semua client dengan filter itu, jadi menambah client di area yang sama hanya menambah biaya kirim.

Slot setiap client hanya menyimpan frame terbaru. Kalau client lambat dan frame sebelumnya belum terkirim, frame itu ditimpa. Client lambat tidak menahan `_broadcast_loop` ataupun client lain.

Client `mode=delta` dikelompokkan per area berdasarkan filter jalur dan `hz`. Setiap kelompok menyimpan state terakhir yang sudah dikirim. Di setiap tick, `_broadcast_loop` membandingkan state itu dengan hasil `buses_near` yang sudah dihitung untuk area tersebut. Perbedaannya di-encode sekali, lalu dikirim ke semua client di kelompok itu. Client baru menerima `snapshot` dari state kelompok, jadi delta berikutnya pasti cocok dengan data yang dipegangnya.

Pesan delta tidak boleh terlewat, jadi client delta memakai antrean, bukan slot. Kalau antrean melewati 8 pesan, isinya diganti satu `snapshot` dari state terbaru. Memori per client tetap terbatas, dan `_broadcast_loop` tidak pernah menunggu client.

Jadwal tick tetap (`next_at += tick`), jadi waktu yang dipakai untuk menghitung tidak menggeser interval. Pengiriman tidak menunggu polling: `_broadcast_loop` hanya membaca Tracker, yang diperbarui `_poll_loop` secara terpisah. Di antara dua polling, Tracker menggeser posisi bus sedikit demi sedikit (lihat [interpolasi posisi](04-referensi-api.md#interpolasi-posisi)), jadi `snapshot` dengan `hz=4` tetap menunjukkan gerakan.

## 4. Polling di latar belakang

Tugas `_poll_loop` berjalan terus di latar belakang:

```mermaid
flowchart TD
    A[tidur TJ_POLL_SECONDS] --> C[untuk setiap area di app.state.areas]
    C --> S{punya client<br/>WebSocket?}
    S -- tidak --> D{tidak diminta<br/>> TJ_AREA_IDLE_SECONDS?}
    D -- ya --> E[hapus area]
    D -- tidak --> C
    S -- ya --> F{sudah di-polling<br/>dalam interval ini?}
    F -- ya --> C
    F -- tidak --> G{polling sebelumnya<br/>masih berjalan?}
    G -- ya --> C
    G -- tidak --> H[jalankan POST /v1/bus/offline<br/>sebagai tugas terpisah]
    H --> C
    E --> C
    C -- selesai --> A
```

Polling semua area yang jatuh tempo berjalan paralel. Area yang polling sebelumnya belum selesai (penanda `busy`) dilewati, jadi area yang lambat tidak menumpuk request dan tidak menunda area lain. Hasil polling masuk ke Tracker lewat `ingest`, dan sampai ke client lewat `snapshot` berikutnya.

Bebannya ke upstream: dua request per detik untuk setiap area yang punya client WebSocket (dengan `TJ_POLL_SECONDS=0.5`). Client yang memilih titik dan radius yang sama berbagi satu polling, dan `hz` tidak menambah polling.

## 5. Bus diperbarui, kedaluwarsa, dan dibersihkan

```mermaid
flowchart LR
    M[hasil POST /v1/bus/offline] --> V{objek dengan<br/>bus_body_no?}
    V -- tidak --> X[abaikan]
    V -- ya --> O{timestamp lebih lama<br/>dari yang tersimpan?}
    O -- ya --> X
    O -- tidak --> S[simpan: data, source, received_at]
```

Tugas `_prune_loop` berjalan setiap 30 detik dan menghapus bus dengan `received_at` lebih lama dari `TJ_BUS_EXPIRY_SECONDS` (300 detik). Bus yang keluar dari radius langsung hilang dari `snapshot` berikutnya karena `buses_near` menyaring ulang setiap kali, walaupun datanya masih tersimpan di Tracker sampai kedaluwarsa.

Data REST selalu ber-`timestamp` `"0"`. Karena aturan urutan hanya menolak data yang lebih lama, data baru dengan timestamp yang sama tetap diterima.

## 6. Token kedaluwarsa

```mermaid
sequenceDiagram
    participant API
    participant TJ as TJClient
    participant T as tijeapi

    API->>TJ: request apa pun
    TJ->>TJ: _ensure_token()
    alt token masih berlaku > 5 menit lagi
        TJ->>T: request dengan Bearer token lama
    else hampir habis atau sudah habis
        alt refresh_token masih berlaku
            TJ->>T: POST /v1/auth/token/refresh {refresh_token}
            T-->>TJ: token baru
        else refresh gagal atau habis
            TJ->>T: POST /v1/auth/login atau /v1/auth/login/guest
            T-->>TJ: token baru
        end
        TJ->>T: request dengan Bearer token baru
    end
    alt upstream membalas 401
        TJ->>TJ: _ensure_token(force=True)
        TJ->>T: ulangi request sekali dengan token baru
    end
```

Semua pengambilan token dikunci dengan `asyncio.Lock`, jadi beberapa request yang bersamaan tidak memicu login berkali-kali. Detail ada di [06-autentikasi-upstream.md](06-autentikasi-upstream.md).

## 7. Contoh lengkap dari sisi client

Urutan yang terjadi saat seseorang membuka UI peta dan mengklik dekat Bundaran HI:

1. Browser membuka `http://localhost:8000/`, diarahkan ke `/ui/`, lalu memuat Leaflet dari unpkg dan tile dari OpenStreetMap.
2. UI memanggil `GET /health` untuk menampilkan sumber data dan status login.
3. UI membuka `WS /ws?lat=-6.1754&lon=106.8272&radius_km=1` (titik awal Monas).
4. Pengguna mengklik peta. UI menutup WebSocket lama dan membuka `WS /ws?lat=-6.195&lon=106.8231&radius_km=1`.
5. Backend memanggil `POST /v1/bus/offline` untuk area baru, lalu mulai mengirim `snapshot`.
6. Setiap detik backend mem-polling area itu lagi dan mengirim `snapshot` baru. UI memindahkan marker yang berubah, menghapus marker bus yang tidak ada lagi di `snapshot`, dan mengurutkan ulang daftar.
7. Kalau pengguna menekan **Tampilkan halte**, UI memanggil `GET /stops` dan menggambar lingkaran halte.
8. Area lama (Monas) tidak punya client lagi, jadi berhenti di-polling dan dihapus setelah 60 detik. Bus yang tidak mendapat update selama 5 menit dihapus dari memori oleh backend.
