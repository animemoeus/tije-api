# Instalasi dan menjalankan

## Kebutuhan

- Windows, macOS, atau Linux.
- Python 3.12 atau lebih baru. Proyek ini dikembangkan dengan Python 3.14.6.
- Koneksi internet ke `tijeapi.transjakarta.co.id` (wajib) dan `mqtt.tj.co.id:8084` (opsional, lihat [10-troubleshooting.md](10-troubleshooting.md)).

Cek versi Python:

```powershell
python --version
```

## Membuat virtual environment

Semua perintah di bawah dijalankan dari folder `python`.

```powershell
cd C:\Users\arter\Downloads\c4e872d79c1110323c849349bbbf4845-smali\python
python -m venv .venv
```

Perintah ini membuat folder `.venv` berisi Python terpisah untuk proyek ini. Folder itu sudah masuk `.gitignore`.

## Memasang dependensi

```powershell
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Isi `requirements.txt` sudah dikunci ke versi yang dites:

```
fastapi==0.143.0
uvicorn[standard]==0.54.0
httpx==0.28.1
paho-mqtt==2.1.0
pydantic==2.14.1
pydantic-settings==2.15.0
pytest==9.1.1
```

Di macOS atau Linux, ganti `.\.venv\Scripts\python` dengan `.venv/bin/python`.

## Konfigurasi (opsional)

Tanpa konfigurasi apa pun, backend login sebagai guest dan semua fitur peta sudah jalan. Kalau ingin memakai akun TransJakarta sendiri atau mengubah perilaku lain:

```powershell
copy .env.example .env
notepad .env
```

Penjelasan setiap variabel ada di [03-konfigurasi.md](03-konfigurasi.md).

## Menjalankan server

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Log yang normal saat startup:

```
INFO:     Started server process [33424]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
2026-10-13 20:53:48,769 INFO httpx: HTTP Request: POST https://tijeapi.transjakarta.co.id/v1/auth/login/guest "HTTP/1.1 200 OK"
2026-10-13 20:53:48,770 INFO app.upstream: logged in as guest, token valid until 1791982427
2026-10-13 20:53:48,820 INFO httpx: HTTP Request: GET https://tijeapi.transjakarta.co.id/v1/settings/api/config/mqtt_url "HTTP/1.1 200 OK"
2026-10-13 20:53:48,946 INFO tj: MQTT broker: wss://mqtt.tj.co.id:8084/mqtt
```

Begitu server hidup, ia langsung login ke TransJakarta dan menanyakan alamat broker MQTT. Kalau broker bisa dihubungi, akan muncul juga baris `MQTT connect wss://mqtt.tj.co.id:8084/mqtt: Success`.

Hentikan server dengan `Ctrl+C`.

### Alamat yang bisa dibuka

| Alamat | Isi |
|---|---|
| http://localhost:8000/ | UI peta (redirect ke `/ui/`) |
| http://localhost:8000/docs | Swagger UI, bisa mencoba endpoint langsung dari browser |
| http://localhost:8000/redoc | Dokumentasi API versi ReDoc |
| http://localhost:8000/health | Status server |

### Mode pengembangan

Tambahkan `--reload` supaya server restart sendiri setiap kali file Python berubah:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Mengaktifkan venv (opsional)

Kalau tidak ingin mengetik `.\.venv\Scripts\python` terus-menerus:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8000
```

Kalau PowerShell menolak menjalankan skrip, izinkan sekali untuk user saat ini:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Mengakses dari HP atau komputer lain

1. Jalankan server dengan `--host 0.0.0.0` seperti di atas.
2. Cari IP komputer: `ipconfig`, lalu lihat `IPv4 Address`, misalnya `192.168.1.10`.
3. Di HP yang terhubung ke Wi-Fi yang sama, buka `http://192.168.1.10:8000/`.
4. Saat pertama kali, Windows Firewall biasanya menanyakan izin untuk Python. Pilih izinkan untuk jaringan privat.

Tombol **Lokasi saya** di UI butuh HTTPS atau `localhost` di sebagian besar browser HP. Lewat alamat IP biasa, pilih titik dengan mengetuk peta.

## Cek cepat setelah server jalan

```powershell
curl http://localhost:8000/health
curl "http://localhost:8000/buses?lat=-6.1950&lon=106.8231&radius_km=0.5"
```

Kalau response `/buses` berisi `"count"` lebih dari 0, semuanya bekerja. Contoh lengkap response ada di [04-referensi-api.md](04-referensi-api.md).

## Menjalankan test

```powershell
.\.venv\Scripts\python -m pytest -q
```

Hasil yang diharapkan: `21 passed`. Test tidak menghubungi server TransJakarta. Lihat [09-testing.md](09-testing.md).
