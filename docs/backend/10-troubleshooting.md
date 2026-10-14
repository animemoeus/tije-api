# Troubleshooting

## Peta kosong, status "Error: upstream error: POST /v1/bus/offline: HTTP 401"

```json
{"type":"error","detail":"upstream error: POST /v1/bus/offline: HTTP 401 {\"code\":401,\"message\":\"Unauthorized, token is required\",\"data\":{\"type\":\"PopUp\"}}\n"}
```

Server yang berjalan masih versi lama yang belum punya login guest. Hentikan server (`Ctrl+C`) dan jalankan lagi. Setelah restart, log harus memuat `logged in as guest`.

Kalau masih 401 setelah restart:

- `TJ_BEARER_TOKEN` di `.env` mungkin sudah kedaluwarsa. Hapus baris itu.
- Upstream mungkin mengubah aturan login. Cek dengan `curl -X POST https://tijeapi.transjakarta.co.id/v1/auth/login/guest -H "Content-Type: application/json" -d "{}"`.

## Daftar bus kosong padahal ada bus di jalan

- Cek `/health`. Kalau `auth.has_token` false, backend belum berhasil login. Lihat log.
- Cek log server. Baris `poll failed: ...` berarti polling `POST /v1/bus/offline` gagal; isi pesannya sama dengan kolom `detail` di [Error 502](#error-502).
- Radius terlalu kecil. Coba `radius_km=1` atau `2`.
- Titik berada di area tanpa layanan. Upstream mengembalikan daftar kosong untuk area di luar jangkauan TransJakarta.
- Bandingkan dengan data mentah `GET /buses/offline` untuk titik dan radius yang sama. Kalau di sana juga kosong, masalahnya ada di upstream, bukan di backend.

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
| `HTTP 429 ...` | Terlalu banyak request. Setiap area dengan client WebSocket berarti dua request per detik (`TJ_POLL_SECONDS=0.5`). Naikkan `TJ_POLL_SECONDS` atau kurangi jumlah area yang dibuka bersamaan |
| `HTTP 5xx ...` | Server TransJakarta sedang bermasalah. Coba lagi nanti |
| `ConnectTimeout`, `ConnectError` | Tidak ada internet atau `tijeapi` tidak terjangkau |
| `response is not JSON` | Upstream mengembalikan halaman HTML, biasanya gangguan atau maintenance |

Hanya polling pertama sebuah area yang menghasilkan 502 (atau pesan `error` di WebSocket). Kalau area sudah pernah berhasil di-polling, kegagalan berikutnya hanya muncul di log sebagai `poll failed: ...` dan client tetap menerima data terakhir. Naiknya `age_seconds` pada semua bus adalah tanda polling sedang gagal.

## Peta patah-patah atau browser berat pada radius besar

Setiap `snapshot` berisi semua bus dalam radius, `hz` kali per detik. Pada radius 20 km itu sekitar 2.300 bus, atau 1 sampai 2 MB per `snapshot`, dan empat kali lipatnya dengan `hz=4`. Pakai `mode=delta` supaya hanya perubahan yang dikirim (sekitar 10 kali lebih kecil), turunkan radius, pakai `hz=1`, atau batasi `TJ_MAX_RADIUS_KM` di server. Klien yang hanya butuh beberapa jalur bisa memakai `WS /ws?routes=...` supaya `snapshot` lebih kecil.

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

Test membuat `Settings(_env_file=None, ...)` sendiri, jadi isi `.env` tidak terbaca oleh test. Yang tetap terbaca adalah variabel environment `TJ_*` yang di-set langsung di terminal (misalnya `$env:TJ_LOGIN_EMAIL`). Kalau test gagal setelah mengubah konfigurasi, cek `Get-ChildItem env:TJ_*` dan hapus variabel yang tidak perlu dengan `Remove-Item env:TJ_...`.
