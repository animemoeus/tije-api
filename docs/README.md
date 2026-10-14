# Dokumentasi TJ Live Tracking

Dokumentasi ini dibagi dua.

**`backend/`** menjelaskan backend Python di folder ini: cara memasang, cara menjalankan, setiap endpoint beserta contoh request dan response, alur data dari ujung ke ujung, sampai cara menambah fitur.

**`source/`** menjelaskan aplikasi Android TransJakarta (APK v3.0.4) yang menjadi sumber semua pengetahuan di backend: isi APK, manifest, kode native, library, bundle JavaScript, katalog API upstream, autentikasi, dan cara kerja live tracking di app aslinya.

Kalau baru pertama kali membuka proyek ini, urutan bacanya kira-kira begini:

1. [backend/01-gambaran-umum.md](backend/01-gambaran-umum.md): apa yang dikerjakan backend dan bagaimana bagian-bagiannya terhubung.
2. [backend/02-instalasi-dan-menjalankan.md](backend/02-instalasi-dan-menjalankan.md): sampai server jalan dan peta tampil.
3. [backend/04-referensi-api.md](backend/04-referensi-api.md): daftar endpoint untuk client.
4. [backend/05-alur-end-to-end.md](backend/05-alur-end-to-end.md): apa yang terjadi di balik satu request.
5. [source/09-live-tracking.md](source/09-live-tracking.md): bagaimana app asli melakukan hal yang sama.

## Isi

### Backend

| File | Isi |
|---|---|
| [01-gambaran-umum.md](backend/01-gambaran-umum.md) | Tujuan, arsitektur, komponen, sumber data |
| [02-instalasi-dan-menjalankan.md](backend/02-instalasi-dan-menjalankan.md) | Python, venv, dependensi, menjalankan server, akses dari HP |
| [03-konfigurasi.md](backend/03-konfigurasi.md) | Semua variabel `TJ_*` dan file `.env` |
| [04-referensi-api.md](backend/04-referensi-api.md) | Setiap endpoint HTTP dan WebSocket, parameter, contoh response, kode error |
| [05-alur-end-to-end.md](backend/05-alur-end-to-end.md) | Diagram urutan: startup, request pertama, WebSocket, polling, token |
| [06-autentikasi-upstream.md](backend/06-autentikasi-upstream.md) | Login guest, login akun, token statis, refresh, fallback |
| [07-struktur-kode.md](backend/07-struktur-kode.md) | Penjelasan file per file, kelas, fungsi, model data bus |
| [08-ui.md](backend/08-ui.md) | Template UI peta di `/ui` |
| [09-testing.md](backend/09-testing.md) | Test otomatis dan uji live dengan Playwright |
| [10-troubleshooting.md](backend/10-troubleshooting.md) | Masalah yang sering muncul dan cara mengatasinya |
| [11-pengembangan-lanjut.md](backend/11-pengembangan-lanjut.md) | Menambah endpoint, deployment, batasan |

### Source (APK)

| File | Isi |
|---|---|
| [01-identitas-apk.md](source/01-identitas-apk.md) | Paket, versi, SDK, split APK, isi arsip |
| [02-arsitektur-aplikasi.md](source/02-arsitektur-aplikasi.md) | React Native + Hermes, lapisan aplikasi, OTA bundle, environment |
| [03-manifest.md](source/03-manifest.md) | Permission, komponen, deep link, metadata |
| [04-kode-native.md](source/04-kode-native.md) | Kelas `com.transjakmobile` dan native module |
| [05-library-dan-sdk.md](source/05-library-dan-sdk.md) | Library React Native, SDK pihak ketiga, native library `.so` |
| [06-bundle-javascript.md](source/06-bundle-javascript.md) | Bundle Hermes, API client, header, state store |
| [07-katalog-api-upstream.md](source/07-katalog-api-upstream.md) | 152 endpoint `tijeapi` dikelompokkan per fitur |
| [08-autentikasi-upstream.md](source/08-autentikasi-upstream.md) | Guest, email/password, Google, Apple, refresh token |
| [09-live-tracking.md](source/09-live-tracking.md) | Alur live tracking di app: REST, MQTT, WebView peta, notifikasi |
| [10-contoh-request-response.md](source/10-contoh-request-response.md) | Request dan response asli dari server TransJakarta |
| [11-temuan-keamanan.md](source/11-temuan-keamanan.md) | Proteksi app, kunci API yang tertanam, hal yang perlu diperhatikan |
| [12-cara-reproduksi-analisis.md](source/12-cara-reproduksi-analisis.md) | Langkah dan alat untuk mengulang analisis |

## Catatan penting

- `tijeapi.transjakarta.co.id` bukan API publik resmi. Formatnya bisa berubah kapan saja, dan memakainya di luar app resmi bisa melanggar ketentuan layanan TransJakarta.
- Contoh response di dokumentasi ini diambil dari server asli pada 13 Oktober 2026. Token, email, dan nama pengguna sudah disamarkan. Daftar panjang dipotong menjadi satu atau dua item.
- Kunci API yang ditemukan di APK hanya ditulis sebagian (contoh: `AIzaSyBS…cAwP3I`).
