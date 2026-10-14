# Konfigurasi

Semua pengaturan dibaca oleh `app/config.py` dengan pydantic-settings. Sumbernya, berurutan dari yang paling kuat:

1. Variabel environment dengan awalan `TJ_`, misalnya `TJ_LOGIN_EMAIL`.
2. File `.env` di folder `python` (folder tempat server dijalankan).
3. Nilai bawaan di kode.

Nama variabel tidak peka huruf besar-kecil. `TJ_POLL_SECONDS` dan `tj_poll_seconds` dianggap sama. Variabel yang tidak dikenal diabaikan.

Contoh `.env` lengkap ada di `.env.example`. Salin dan ubah seperlunya:

```powershell
copy .env.example .env
```

File `.env` sudah ada di `.gitignore`. Jangan pernah commit file ini kalau berisi password.

## Login ke upstream

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_LOGIN_EMAIL` | kosong | Email akun TransJakarta. Kalau diisi bersama password, backend login dengan akun ini |
| `TJ_LOGIN_PASSWORD` | kosong | Password akun. Tidak pernah ditulis ke log |
| `TJ_BEARER_TOKEN` | kosong | Token yang sudah dimiliki. Kalau diisi, backend tidak login dan tidak me-refresh token. Mengalahkan email/password |

Aturan pemilihan mode:

| `TJ_BEARER_TOKEN` | `TJ_LOGIN_EMAIL` + `TJ_LOGIN_PASSWORD` | Mode |
|---|---|---|
| terisi | apa saja | `static` |
| kosong | keduanya terisi | `user` (kalau login gagal, otomatis jatuh ke guest) |
| kosong | salah satu atau keduanya kosong | `guest` |

Penjelasan lengkap ada di [06-autentikasi-upstream.md](06-autentikasi-upstream.md).

## Sumber posisi bus

| Variabel | Bawaan | Keterangan |
|---|---|---|
Posisi bus hanya diambil dari `POST /v1/bus/offline`.

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_POLL_SECONDS` | `1` | Jarak antar polling upstream untuk area yang punya client WebSocket, sekaligus jarak antar `snapshot` yang dikirim ke setiap client WebSocket. `GET /buses` juga memakai data yang ada kalau umurnya belum melewati angka ini |

## Cache dan masa simpan

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_AREA_IDLE_SECONDS` | `60` | Area yang hanya diminta lewat `GET /buses` (tanpa client WebSocket) dilupakan setelah tidak diminta selama ini. Area dengan client WebSocket tidak pernah dilupakan selama client masih tersambung |
| `TJ_BUS_EXPIRY_SECONDS` | `300` | Bus yang tidak mendapat update selama ini dihapus dari memori. App asli juga memakai 5 menit |
| `TJ_ROUTE_CACHE_SECONDS` | `3600` | Jalur rute dari `GET /routes/{route_code}` disimpan di memori selama ini sebelum diambil ulang dari upstream |

Area dikenali dari lintang dan bujur yang dibulatkan ke 3 desimal (kisi sekitar 100 meter) ditambah radius. Dua client yang memilih titik hampir sama dengan radius sama memakai area dan polling yang sama.

## Area dan radius

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_DEFAULT_RADIUS_KM` | `1.0` | Radius kalau client tidak mengirim `radius_km` |
| `TJ_MAX_RADIUS_KM` | `20.0` | Radius terbesar yang diizinkan. Nilai yang lebih besar dipotong ke angka ini |

Beban untuk upstream dan browser naik cepat seiring radius. Hasil pengukuran di sekitar Bundaran HI (13 Oktober 2026):

| Radius | Bus dari `/v1/bus/offline` | Waktu respons upstream |
|---|---|---|
| 1 km | 16 | 0,3 dtk |
| 5 km | 395 | 0,6 dtk |
| 10 km | 1.329 | 0,9 dtk |
| 20 km | 2.347 | 1,1 dtk |

Setiap area yang punya client WebSocket berarti satu request per detik (dengan `TJ_POLL_SECONDS=1`) ke `tijeapi`. Client di area yang sama berbagi polling itu, tapi setiap area berbeda menambah satu request per detik. Pada radius 20 km waktu respons upstream sudah sekitar 1 detik, jadi polling area itu praktis berjalan terus-menerus (polling berikutnya dilewati selama yang sebelumnya belum selesai).

Setiap `snapshot` WebSocket berisi semua bus dalam radius. Pada radius 20 km itu sekitar 2.300 bus, atau 1 sampai 2 MB per detik untuk setiap client. UI membatasi daftar ke 200 bus terdekat dan hanya memperbarui marker yang berubah, jadi peta tetap lancar, tapi bandwidth tetap besar. Kalau server dipakai banyak client sekaligus, pertimbangkan menurunkan `TJ_MAX_RADIUS_KM` atau menaikkan `TJ_POLL_SECONDS`.

Batas koordinat tidak bisa diubah lewat konfigurasi. Nilainya ada di `app/main.py`: lintang -7.5 sampai -5.5 dan bujur 106.0 sampai 107.5, kira-kira Jabodetabek dan sekitarnya.

## Identitas perangkat

Backend mengirim header yang sama seperti app Android. Nilai bawaannya cukup untuk dipakai apa adanya.

| Variabel | Header upstream | Bawaan |
|---|---|---|
| `TJ_APP_VERSION` | `X-App-Version` | `3.0.4` |
| `TJ_APP_OS` | `X-App-OS` | `android` |
| `TJ_APP_OS_VERSION` | `X-App-OS-Version` | `14` |
| `TJ_APP_PLATFORM` | `X-App-Platform` | `34` (API level Android) |
| `TJ_DEVICE_MODEL` | `X-Device-Model` | `Google\|Pixel 8` (format app: `merek\|model`) |
| `TJ_DEVICE_ID` | `X-Device-ID` | 16 karakter hex acak, dibuat ulang setiap server start |
| `TJ_LANG` | `X-Lang` | `id` |
| `TJ_FCM_TOKEN` | `X-FCM-Token` | kosong |

Kalau ingin server terlihat sebagai perangkat yang sama setiap kali restart, isi `TJ_DEVICE_ID` dengan nilai tetap.

## Koneksi upstream

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_BASE_URL` | `https://tijeapi.transjakarta.co.id` | Alamat REST upstream. App juga mengenal `https://stg-tijeapi.transjakarta.co.id` (staging) dan `https://tije-api-dev.transjakarta.co.id` (development) |
| `TJ_TIMEOUT_SECONDS` | `15.0` | Batas waktu setiap request ke upstream |

## Contoh konfigurasi

Hanya peta, tanpa akun (cukup tanpa `.env` sama sekali):

```
# kosong
```

Memakai akun TransJakarta:

```
TJ_LOGIN_EMAIL=nama@contoh.com
TJ_LOGIN_PASSWORD=rahasia
TJ_DEVICE_ID=4f1c2a9be07d3e55
```

Mengurangi beban ke upstream dan bandwidth ke client (posisi diperbarui tiap 5 detik):

```
TJ_POLL_SECONDS=5
TJ_MAX_RADIUS_KM=5
```

## Mengecek konfigurasi yang aktif

`GET /health` dan `GET /account` menunjukkan mode login, email yang dipakai, jumlah area dan client WebSocket, serta interval polling (`tracker.poll_seconds`). Password dan token tidak pernah ditampilkan.
