# Troubleshooting

## Peta kosong, status "Error: upstream error: POST /v1/bus: HTTP 401"

```json
{"type":"error","detail":"upstream error: POST /v1/bus: HTTP 401 {\"code\":401,\"message\":\"Unauthorized, token is required\",\"data\":{\"type\":\"PopUp\"}}\n"}
```

Server yang berjalan masih versi lama yang belum punya login guest. Hentikan server (`Ctrl+C`) dan jalankan lagi. Setelah restart, log harus memuat `logged in as guest`.

Kalau masih 401 setelah restart:

- `TJ_BEARER_TOKEN` di `.env` mungkin sudah kedaluwarsa. Hapus baris itu.
- Upstream mungkin mengubah aturan login. Cek dengan `curl -X POST https://tijeapi.transjakarta.co.id/v1/auth/login/guest -H "Content-Type: application/json" -d "{}"`.

## `/health` menunjukkan `"connected": false` terus

Broker MQTT tidak bisa dihubungi. Saat pengembangan, `mqtt.tj.co.id` (103.145.125.134) tidak menjawab di port mana pun dari jaringan pengembang:

```powershell
Test-NetConnection mqtt.tj.co.id -Port 8084
```

```
TcpTestSucceeded : False
```

Ini bukan kesalahan backend. Kemungkinannya broker hanya menerima koneksi dari jaringan tertentu, misalnya operator seluler Indonesia. Selama itu terjadi, backend memakai polling REST (`TJ_REST_POLL=auto`) dan peta tetap berisi data, hanya saja update datang setiap 10 detik, bukan realtime.

Hal yang bisa dicoba:

- jalankan backend di jaringan lain (tethering HP dengan kartu Indonesia, server di Indonesia);
- pastikan firewall atau proxy kantor tidak memblokir port 8084;
- kalau broker bisa dijangkau di alamat lain, isi `TJ_MQTT_URL`.

## Daftar bus kosong padahal ada bus di jalan

- Cek `/health`. Kalau `mqtt.connected` false dan `auth.has_token` false, backend belum berhasil login. Lihat log.
- Polling REST dimatikan (`TJ_REST_POLL=off`) sementara MQTT tidak terhubung. Kembalikan ke `auto`.
- Radius terlalu kecil. Coba `radius_km=1` atau `2`.
- Titik berada di area tanpa layanan. Upstream mengembalikan daftar kosong untuk area di luar jangkauan TransJakarta.
- Untuk panggilan pertama via `/buses`, tambahkan `wait=5` supaya backend menunggu data pertama.

## `GET /buses/{bus_body_no}` selalu 404

Bus hanya dikenal kalau areanya sedang dipantau. Panggil dulu `/buses` atau buka `/ws` untuk area bus itu, lalu ulangi. Bus juga hilang dari memori setelah 5 menit tanpa update.

## `GET /account/trips` membalas 403

```json
{ "detail": "needs a TransJakarta account: set TJ_LOGIN_EMAIL and TJ_LOGIN_PASSWORD in .env" }
```

- `.env` belum berisi email dan password, atau file `.env` tidak berada di folder tempat server dijalankan.
- Login akun gagal. Buka `/account` dan baca `last_error`.
- Server belum di-restart setelah `.env` diubah.

## `GET /account` menunjukkan `"logged_in_as": "guest"` padahal email sudah diisi

Login akun gagal dan backend jatuh ke guest. Isi `last_error` menjelaskan sebabnya, misalnya:

```
account login failed: POST /v1/auth/login: HTTP 400 {"code":400,"message":"..."}
```

Periksa email dan password dengan login di app resmi. Akun yang dibuat lewat Google atau Apple Sign-In mungkin tidak punya password (`have_password: false`); login seperti itu tidak didukung backend ini.

## Error 422 untuk koordinat yang terlihat benar

Batas koordinat API adalah lintang -7.5 sampai -5.5 dan bujur 106.0 sampai 107.5. Pastikan urutannya benar: `lat` bernilai negatif sekitar -6, `lon` sekitar 106. Tertukar adalah penyebab paling umum.

## Error 502

Upstream menolak atau gagal menjawab. Pesan aslinya ada di `detail`:

| Isi `detail` | Kemungkinan sebab |
|---|---|
| `HTTP 401 ...` | Token bermasalah. Restart server; kalau memakai `TJ_BEARER_TOKEN`, ganti tokennya |
| `HTTP 429 ...` | Terlalu banyak request. Naikkan `TJ_REST_POLL_SECONDS` dan `TJ_TOPICS_CACHE_SECONDS` |
| `HTTP 5xx ...` | Server TransJakarta sedang bermasalah. Coba lagi nanti |
| `ConnectTimeout`, `ConnectError` | Tidak ada internet atau `tijeapi` tidak terjangkau |
| `response is not JSON` | Upstream mengembalikan halaman HTML, biasanya gangguan atau maintenance |

## Port 8000 sudah dipakai

```
ERROR: [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```

Server lain (atau versi lama server ini) masih berjalan. Hentikan prosesnya, atau jalankan di port lain dengan `--port 8001`.

Mencari proses yang memakai port di Windows:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Get-Process -Id <OwningProcess>
```

## UI terus menulis "Terputus, coba lagi…"

- Server mati atau dijalankan di port berbeda. Cek alamat di address bar.
- Membuka file HTML langsung dari disk (`file:///...`). Buka lewat `http://localhost:8000/`, atau tambahkan `?api=http://localhost:8000`.
- Ada proxy yang tidak meneruskan WebSocket. Coba tanpa proxy.

## Tombol "Lokasi saya" tidak bekerja di HP

Browser hanya memberi akses lokasi untuk halaman HTTPS atau `localhost`. Lewat `http://192.168.x.x:8000`, pilih titik dengan mengetuk peta, atau pasang HTTPS di depan server.

## `Activate.ps1 cannot be loaded because running scripts is disabled`

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Atau tidak usah mengaktifkan venv dan panggil `.\.venv\Scripts\python` langsung.

## Test gagal setelah mengubah `.env`

Test membuat `Settings(bearer_token="")` sendiri, tetapi variabel lain dari `.env` (misalnya `TJ_REST_POLL=off` atau email/password) tetap terbaca dan bisa mengubah perilaku yang dites. Jalankan test dengan `.env` dipindahkan sementara, atau dari folder lain dengan `PYTHONPATH` diarahkan ke folder `python`.
