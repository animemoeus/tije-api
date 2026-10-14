# Pengembangan lanjut

## Menambah endpoint baru yang memanggil upstream

Katalog lengkap endpoint `tijeapi` ada di [../source/07-katalog-api-upstream.md](../source/07-katalog-api-upstream.md). Polanya selalu sama:

1. Tambah method di `TJClient` (`app/upstream.py`) kalau akan dipakai di beberapa tempat, atau panggil `client.request(...)` langsung.
2. Tambah route di `create_app` (`app/main.py`).
3. Ubah `UpstreamError` menjadi `HTTPException(502, ...)`.
4. Tambah test dengan `FakeTJ` di `tests/test_api.py`.

### Contoh: detail halte

Endpoint upstream: `GET /v2/bus-stop/{stop_id}` (`getHalteDetail` di app).

`app/upstream.py`:

```python
    async def get_bus_stop_detail(self, stop_id: str) -> Any:
        body = await self._request("GET", f"/v2/bus-stop/{stop_id}")
        return (body or {}).get("data")
```

`app/main.py`, di dalam `create_app`:

```python
    @app.get("/stops/{stop_id}")
    async def stop_detail(request: Request, stop_id: str) -> Any:
        """Detail satu halte (GET /v2/bus-stop/{stop_id})."""
        try:
            return await request.app.state.client.get_bus_stop_detail(stop_id)
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e
```

`tests/test_api.py`, tambahkan cabang di `FakeTJ.__call__` lalu test-nya:

```python
if path == "/v2/bus-stop/H00278P":
    return httpx.Response(
        200, json={"data": {"stop_id": "H00278P", "stop_name": "Harmoni"}}
    )
```

```python
def test_stop_detail(client):
    assert client.get("/stops/H00278P").json() == {
        "stop_id": "H00278P",
        "stop_name": "Harmoni",
    }
```

### Contoh: endpoint yang butuh akun

```python
    @app.get("/account/saved-places")
    async def saved_places(request: Request) -> Any:
        """Tempat tersimpan akun (GET /v1/user/saved-places)."""
        client: TJClient = request.app.state.client
        try:
            await client._ensure_token()
            if not client.is_user_session:
                raise HTTPException(403, "needs a TransJakarta account")
            return await client.request("GET", "/v1/user/saved-places")
        except UpstreamError as e:
            raise HTTPException(502, f"upstream error: {e}") from e
```

Sebaiknya hanya buka endpoint baca (`GET`). Endpoint yang mengubah data akun, membeli tiket, atau memindahkan saldo (`PUT /v1/user`, `DELETE /v1/user`, `/v1/payment/*`, `/v1/ticket/book/*`) punya akibat nyata dan tidak perlu diakses dari backend seperti ini.

## Deployment

### Satu proses saja

Posisi bus, area yang dipantau, dan token disimpan di memori proses. Kalau uvicorn dijalankan dengan beberapa worker (`--workers 4`) atau di beberapa container, setiap proses punya data sendiri dan masing-masing mem-polling upstream untuk areanya sendiri, sehingga client di area yang sama tidak lagi berbagi polling. Jalankan satu proses. Satu proses asyncio sudah cukup untuk banyak client WebSocket; yang lebih cepat habis biasanya bandwidth (lihat batasan di bawah).

Kalau suatu saat memang butuh beberapa proses, pindahkan keadaan bersama ke Redis (posisi bus dan daftar area) dan jadikan satu proses sebagai satu-satunya yang mem-polling upstream.

### Menjalankan sebagai layanan

Windows, dengan Task Scheduler atau NSSM:

```powershell
nssm install TJLiveTracking "C:\...\python\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
nssm set TJLiveTracking AppDirectory "C:\...\python"
nssm start TJLiveTracking
```

Linux, dengan systemd (`/etc/systemd/system/tj-live.service`):

```ini
[Unit]
Description=TJ Live Tracking API
After=network-online.target

[Service]
WorkingDirectory=/opt/tj-live/python
ExecStart=/opt/tj-live/python/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
EnvironmentFile=/opt/tj-live/python/.env

[Install]
WantedBy=multi-user.target
```

### Docker

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```powershell
docker build -t tj-live .
docker run --rm -p 8000:8000 --env-file .env tj-live
```

### Membuka ke internet

Backend tidak punya autentikasi untuk client. Sebelum dibuka ke publik:

- Pasang reverse proxy (Caddy, Nginx) dengan HTTPS. Teruskan header `Upgrade` dan `Connection` supaya WebSocket jalan.
- Tambahkan autentikasi sederhana di proxy (basic auth atau token) atau di FastAPI (dependency yang memeriksa header `X-API-Key`).
- Jangan isi `TJ_LOGIN_EMAIL`/`TJ_LOGIN_PASSWORD` dengan akun pribadi kalau server publik, karena `/account/trips` akan menampilkan riwayat perjalanan akun itu ke siapa pun.
- Batasi laju request dan jumlah koneksi WebSocket per IP di proxy. Setiap area baru yang dibuka client berarti satu request per detik ke `tijeapi`.
- Sempitkan `allow_origins` di `CORSMiddleware` ke domain yang benar-benar memakai API.

Contoh Caddy:

```
tj.contoh.id {
    basicauth {
        tamu $2a$14$...hash...
    }
    reverse_proxy 127.0.0.1:8000
}
```

## Batasan yang diketahui

| Batasan | Dampak | Kemungkinan solusi |
|---|---|---|
| Data hanya dari polling `POST /v1/bus/offline` | Posisi paling cepat diperbarui sekali per `TJ_POLL_SECONDS`, dan setiap area aktif berarti satu request per detik ke upstream | Naikkan `TJ_POLL_SECONDS` kalau beban upstream jadi masalah |
| `snapshot` selalu berisi semua bus dalam radius | Radius 20 km ≈ 2.300 bus ≈ 1–2 MB per detik per client | Turunkan `TJ_MAX_RADIUS_KM`, pakai filter `routes`, atau kirim hanya bus yang berubah (diff) |
| `estimated_time_next_stops` dari upstream sering 0 | ETA tidak bisa ditampilkan | Hitung sendiri dari `estimated_distance_next_stops` dan kecepatan rata-rata |
| `speed` dari REST selalu 0 | Tidak bisa tahu bus berhenti atau jalan | Hitung dari perubahan posisi antar polling |
| Upstream membatasi halte 20 per request | Daftar halte terpotong di area padat | Pakai radius lebih kecil, atau panggil beberapa titik |
| Format upstream tidak resmi | Bisa berubah tanpa pemberitahuan | Pantau log 502 dan test live secara berkala |
| Data di memori | Hilang saat restart | Wajar untuk data live; simpan ke database kalau butuh riwayat |
| Tidak ada autentikasi client | Siapa pun di jaringan bisa memakai API | Lihat bagian "Membuka ke internet" |

## Ide pengembangan

- Endpoint `GET /routes/{route_code}/buses` yang mengumpulkan bus satu rute dari beberapa area.
- Riwayat posisi per bus (simpan N titik terakhir) untuk menghitung kecepatan dan ETA sendiri.
- Endpoint rute dan polyline (`GET /v2/route/{id}`) supaya UI bisa menggambar jalur koridor.
- Notifikasi "bus rute X akan tiba di halte Y" lewat WebSocket.
- Metrik Prometheus: jumlah request upstream, umur data, jumlah client.
