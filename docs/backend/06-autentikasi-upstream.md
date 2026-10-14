# Autentikasi ke upstream

Setiap endpoint `tijeapi`, termasuk yang dipakai peta, menolak request tanpa token:

```json
{ "code": 401, "message": "Unauthorized, token is required", "data": { "type": "PopUp" } }
```

Backend mengurus token ini sendiri. Client backend tidak perlu login apa pun.

## Tiga mode

| Mode | Cara mengaktifkan | Login ke | Refresh otomatis | Bisa akses endpoint akun |
|---|---|---|---|---|
| `guest` | Tidak mengisi apa-apa | `POST /v1/auth/login/guest` | Ya | Tidak |
| `user` | `TJ_LOGIN_EMAIL` + `TJ_LOGIN_PASSWORD` | `POST /v1/auth/login` | Ya | Ya |
| `static` | `TJ_BEARER_TOKEN` | Tidak login | Tidak | Ya, kalau tokennya milik akun |

Mode `guest` meniru tombol "lewati login" di app. Token guest cukup untuk peta, posisi bus, dan halte.

## Login guest

```http
POST /v1/auth/login/guest HTTP/1.1
Host: tijeapi.transjakarta.co.id
Content-Type: application/json
X-App-Version: 3.0.4
X-Device-ID: 9f2c41d07ab35e18
...

{}
```

Tidak ada header `Authorization`. Response:

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
  "token": "<272 karakter>",
  "token_valid_until": 1791987416,
  "refresh_token": "<272 karakter>",
  "refresh_token_valid_until": 1791991016,
  "moter": null
}
```

Yang disimpan backend: `token`, `token_valid_until`, `refresh_token`, `refresh_token_valid_until`. Token guest berlaku sekitar 24 jam. Refresh token berlaku satu jam lebih lama dari itu.

## Login dengan akun

Isi `.env`:

```
TJ_LOGIN_EMAIL=nama@contoh.com
TJ_LOGIN_PASSWORD=rahasia
```

Request yang dikirim (sama seperti layar login app):

```http
POST /v1/auth/login HTTP/1.1
Host: tijeapi.transjakarta.co.id
Content-Type: application/json
X-App-Version: 3.0.4
...

{"email": "nama@contoh.com", "password": "rahasia"}
```

Password dikirim apa adanya di dalam HTTPS, tanpa hash di sisi client. Itu juga yang dilakukan app. Response-nya berbentuk sama dengan login guest. Backend menerima field token di tingkat atas maupun di dalam `data`, jadi kedua bentuk ini sama-sama didukung:

```json
{ "token": "...", "token_valid_until": 1791990000, "refresh_token": "...", "refresh_token_valid_until": 1791993600 }
```

```json
{ "data": { "token": "...", "token_valid_until": 1791990000, "refresh_token": "...", "refresh_token_valid_until": 1791993600 } }
```

### Kalau login akun gagal

Misalnya password salah atau akun dikunci. Backend:

1. menulis log `ERROR account login failed: POST /v1/auth/login: HTTP 400 ...; falling back to guest`;
2. menyimpan pesan itu di `last_error`;
3. login sebagai guest supaya peta tetap jalan.

Akibatnya `GET /account` menunjukkan `"mode": "user"` tapi `"logged_in_as": "guest"`, dan `GET /account/trips` membalas 403. Perbaiki `.env`, lalu restart server.

## Token statis

```
TJ_BEARER_TOKEN=eyJhbGciOi...
```

Token dipakai apa adanya untuk semua request. Backend tidak login, tidak me-refresh, dan tidak mencoba login ulang saat mendapat 401. Kalau token kedaluwarsa, request ke upstream mulai gagal dengan 502 dan token harus diganti manual.

## Siklus hidup token

Logika ada di `TJClient._ensure_token()`:

1. Mode `static`: kembalikan token dari konfigurasi.
2. Token masih berlaku lebih dari 5 menit lagi (`TOKEN_MARGIN_SECONDS = 300`): pakai token itu.
3. Refresh token masih berlaku lebih dari 60 detik lagi: kirim `POST /v1/auth/token/refresh`.
4. Refresh gagal atau sudah tidak berlaku: login ulang (akun kalau dikonfigurasi, kalau tidak guest).

Request refresh:

```http
POST /v1/auth/token/refresh HTTP/1.1
Content-Type: application/json

{"refresh_token": "<refresh_token>"}
```

Response refresh diproses sama seperti response login. Field `refresh_token` yang baru dipakai kalau ada. Kalau tidak ada, refresh token lama tetap disimpan.

Selain itu, setiap request yang dijawab 401 oleh upstream diulang sekali setelah memaksa token baru (`_ensure_token(force=True)`). Ini menangani token yang dicabut server sebelum waktunya.

## Header lain yang dikirim

Semua request ke upstream membawa header identitas perangkat yang sama dengan app:

| Header | Contoh | Diatur oleh |
|---|---|---|
| `X-App-Version` | `3.0.4` | `TJ_APP_VERSION` |
| `X-Device-ID` | `9f2c41d07ab35e18` | `TJ_DEVICE_ID` |
| `X-Lang` | `id` | `TJ_LANG` |
| `X-FCM-Token` | kosong | `TJ_FCM_TOKEN` |
| `X-App-OS` | `android` | `TJ_APP_OS` |
| `X-App-OS-Version` | `14` | `TJ_APP_OS_VERSION` |
| `X-App-Platform` | `34` | `TJ_APP_PLATFORM` |
| `X-Device-Model` | `Google\|Pixel 8` | `TJ_DEVICE_MODEL` |
| `Content-Type`, `Accept` | `application/json` | tetap |
| `Authorization` | `Bearer <token>` | otomatis, kecuali saat login dan refresh |

## Keamanan

- Password hanya dibaca dari environment atau `.env`, hanya dikirim ke `POST /v1/auth/login`, dan tidak pernah muncul di log, `/health`, `/account`, atau pesan error. Test `test_wrong_password_falls_back_to_guest` dan `test_account_login_used_and_trips_available` memastikan hal ini.
- Token tidak pernah dikembalikan oleh endpoint mana pun. `GET /account` hanya menunjukkan `has_token` dan `valid_until`.
- Pesan error upstream yang diteruskan di `detail` atau `last_error` dipotong 200 karakter dan tidak berisi header request.
- Siapa pun yang bisa menjangkau backend bisa memanggil `/account/trips` dan melihat riwayat perjalanan akun yang dikonfigurasi. Jangan buka server ke jaringan publik saat memakai akun pribadi. Lihat [11-pengembangan-lanjut.md](11-pengembangan-lanjut.md).

## Status login saat ini

```powershell
curl http://localhost:8000/account
```

| `mode` | `logged_in_as` | Artinya |
|---|---|---|
| `guest` | `null` | Belum ada request ke upstream sejak start |
| `guest` | `guest` | Normal untuk mode guest |
| `user` | `user` | Login akun berhasil |
| `user` | `guest` | Login akun gagal, lihat `last_error` |
| `static` | `static` | Memakai `TJ_BEARER_TOKEN` |
