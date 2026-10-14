# Konfigurasi

Semua pengaturan dibaca oleh `app/config.py` dengan pydantic-settings. Sumbernya, berurutan dari yang paling kuat:

1. Variabel environment dengan awalan `TJ_`, misalnya `TJ_LOGIN_EMAIL`.
2. File `.env` di folder `python` (folder tempat server dijalankan).
3. Nilai bawaan di kode.

Nama variabel tidak peka huruf besar-kecil. `TJ_REST_POLL` dan `tj_rest_poll` dianggap sama. Variabel yang tidak dikenal diabaikan.

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
| `TJ_MQTT_URL` | kosong | Alamat broker MQTT. Kosong berarti backend menanyakannya ke upstream (`/v1/settings/api/config/mqtt_url`). Skema yang didukung: `ws://`, `wss://`, `mqtt://`, `tcp://`, `mqtts://`, `ssl://` |
| `TJ_REST_POLL` | `auto` | `auto`: polling `POST /v1/bus/offline` hanya saat MQTT tidak terhubung. `always`: selalu polling, walau MQTT terhubung. `off`: tidak pernah polling |
| `TJ_REST_POLL_SECONDS` | `10` | Jarak antar polling per area, dalam detik |

## Cache dan masa simpan

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_TOPICS_CACHE_SECONDS` | `60` | Lama hasil `POST /v1/bus` (daftar topik) disimpan per area. Area dibulatkan ke kisi sekitar 100 meter |
| `TJ_TOPIC_IDLE_SECONDS` | `600` | Area atau topik yang tidak diminta client selama ini akan dilepas: berhenti di-polling dan di-unsubscribe |
| `TJ_BUS_EXPIRY_SECONDS` | `300` | Bus yang tidak mendapat update selama ini dihapus dari memori. App asli juga memakai 5 menit |

## Area dan radius

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `TJ_DEFAULT_RADIUS_KM` | `1.0` | Radius kalau client tidak mengirim `radius_km` |
| `TJ_MAX_RADIUS_KM` | `20.0` | Radius terbesar yang diizinkan. Nilai yang lebih besar dipotong ke angka ini |

Beban untuk upstream dan browser naik cepat seiring radius. Hasil pengukuran di sekitar Bundaran HI (13 Oktober 2026):

| Radius | Topik MQTT | Bus dari `/v1/bus/offline` | Waktu respons upstream |
|---|---|---|---|
| 1 km | 6 | 16 | 0,3 dtk |
| 5 km | 100 | 395 | 0,6 dtk |
| 10 km | 361 | 1.329 | 0,9 dtk |
| 20 km | 1.332 | 2.347 | 1,1 dtk |

Pada radius 20 km, satu polling bisa mengubah posisi ±1.300 bus sekaligus. Backend hanya mengirim bus yang datanya berubah, dan UI membatasi daftar ke 200 bus terdekat, jadi tetap lancar. Kalau server dipakai banyak client sekaligus, pertimbangkan menurunkan `TJ_MAX_RADIUS_KM`.

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

Jaringan yang bisa menjangkau broker, tapi ingin data REST tetap masuk:

```
TJ_REST_POLL=always
TJ_REST_POLL_SECONDS=15
```

Mematikan polling sama sekali (hanya MQTT):

```
TJ_REST_POLL=off
```

Memakai broker lain secara langsung, tanpa bertanya ke upstream:

```
TJ_MQTT_URL=wss://mqtt.tj.co.id:8084/mqtt
```

## Mengecek konfigurasi yang aktif

`GET /health` dan `GET /account` menunjukkan mode login, email yang dipakai, alamat broker, dan status koneksi. Password dan token tidak pernah ditampilkan.
