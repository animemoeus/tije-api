# Dokumentasi source: APK TransJakarta

Bagian ini mendokumentasikan isi aplikasi Android **TJ: Transjakarta** versi 3.0.4 (`com.transjakmobile`, versionCode 260) berdasarkan analisis statis APK dan beberapa request ke server aslinya.

Semua yang dikerjakan backend di folder `python` berasal dari temuan di sini. Kalau upstream berubah dan backend perlu disesuaikan, mulai dari [07-katalog-api-upstream.md](07-katalog-api-upstream.md) dan [09-live-tracking.md](09-live-tracking.md).

## Bahan yang dianalisis

| Bahan | Lokasi | Keterangan |
|---|---|---|
| XAPK asli | `apk/TJ_Transjakarta_3.0.4_APKPure.xapk` | Unduhan APKPure, 88 MB, berisi APK dasar dan tiga split |
| Hasil smali | folder akar proyek (`A/`, `com/`, `io/`, …) | Hasil apktool. Tidak lengkap karena tabrakan nama di filesystem Windows |
| Hasil JADX | `c4e872d79c1110323c849349bbbf4845-java/` | Kode Java hasil decompile, 17.575 file. Hasil MobSF |
| Bundle JavaScript | `assets/index.android.bundle` di dalam APK dasar | Bytecode Hermes versi 96, 14 MB |

## Isi

| File | Isi |
|---|---|
| [01-identitas-apk.md](01-identitas-apk.md) | Paket, versi, SDK, split, isi arsip, proteksi |
| [02-arsitektur-aplikasi.md](02-arsitektur-aplikasi.md) | Lapisan aplikasi, React Native + Hermes, OTA bundle, environment |
| [03-manifest.md](03-manifest.md) | Permission, activity, service, receiver, provider, deep link, metadata |
| [04-kode-native.md](04-kode-native.md) | Kelas di `com.transjakmobile` dan native module untuk JavaScript |
| [05-library-dan-sdk.md](05-library-dan-sdk.md) | Library React Native, SDK pembayaran, keamanan, analitik, native `.so` |
| [06-bundle-javascript.md](06-bundle-javascript.md) | Cara membaca bundle Hermes, API client, header, state store |
| [07-katalog-api-upstream.md](07-katalog-api-upstream.md) | 152 endpoint `tijeapi` per kelompok fitur |
| [08-autentikasi-upstream.md](08-autentikasi-upstream.md) | Guest, email/password, Google, Apple, refresh token, logout |
| [09-live-tracking.md](09-live-tracking.md) | Alur live tracking di app dari layar peta sampai notifikasi |
| [10-contoh-request-response.md](10-contoh-request-response.md) | Request dan response asli dari `tijeapi` |
| [11-temuan-keamanan.md](11-temuan-keamanan.md) | Proteksi, kunci yang tertanam, konfigurasi yang perlu diperhatikan |
| [12-cara-reproduksi-analisis.md](12-cara-reproduksi-analisis.md) | Alat dan langkah untuk mengulang analisis |

## Tingkat kepastian

Tidak semua temuan sama kuatnya. Di dokumen-dokumen ini:

- **Terverifikasi** berarti sudah dicoba ke server asli dan response-nya cocok. Contoh: login guest, `POST /v1/bus`, `POST /v1/bus/offline`, `GET /v2/bus-stop`, `mqtt_url`.
- **Dari kode** berarti terbaca jelas di kode yang di-decompile, tapi belum dicoba. Contoh: login email/password, refresh token, sebagian besar katalog endpoint.
- **Dugaan** berarti disimpulkan dari petunjuk tidak langsung. Selalu ditandai dengan kata "kemungkinan" atau "diduga".
