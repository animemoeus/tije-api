# Temuan keamanan

Halaman ini mencatat hal-hal terkait keamanan yang terlihat dari analisis statis. Tujuannya dokumentasi dan pemahaman, bukan panduan menyerang. Kunci dan rahasia hanya ditulis sebagian.

## Proteksi yang dipasang app

| Proteksi | Keterangan |
|---|---|
| Google Play PairIP | Cek lisensi dan integritas Play. APK yang dipasang dari luar Play atau dimodifikasi bisa ditolak |
| freeRASP (Talsec) | Deteksi root, Magisk/MMRL, Hide My Applist, emulator, Frida/hooking, debugger, tanda tangan berbeda. Laporan ke `mobile-security@transjakarta.co.id` |
| ScreenGuard + `DETECT_SCREEN_CAPTURE` / `DETECT_SCREEN_RECORDING` | Mencegah dan mendeteksi screenshot/rekam layar |
| `HIDE_OVERLAY_WINDOWS` | Mencegah overlay dari app lain di layar sensitif (tapjacking) |
| `allowBackup="false"` | Data app tidak bisa diambil lewat `adb backup` |
| `react-native-keychain` | Rahasia disimpan di Android Keystore, bisa dikunci biometrik |
| R8 | Nama kelas dan method library diacak |
| Hermes bytecode | Kode JavaScript tidak tersimpan sebagai teks |

## Kunci dan identitas yang tertanam

Nilai-nilai ini ada di dalam APK dan bisa dibaca siapa pun yang mengunduhnya. Sebagian memang dirancang publik (kunci client-side), tetapi tetap perlu dibatasi di sisi penyedia.

| Jenis | Lokasi | Nilai (sebagian) | Catatan |
|---|---|---|---|
| Google Maps API key | manifest `com.google.android.geo.API_KEY` | `AIzaSyBS…cAwP3I` | Sebaiknya dibatasi ke package `com.transjakmobile` + sidik jari sertifikat di Google Cloud Console |
| Mapbox access token | bundle (`api.mapbox.com/v4/mapbox.mapbox-traffic-v1.json?access_token=`) | `pk.eyJ1IjoiZGV2ZWxvcG1lbnR0aiIs…` | Token publik (`pk.`), akun `developmenttj`. Sebaiknya dibatasi URL/scope |
| MapTiler key (style) | bundle | `kLEr…zHk47` | Untuk `maps/c0e27dd8-…/style.json` |
| MapTiler key (tiles) | bundle | `oxSI…3Ww` | Untuk `tiles/v3/tiles.json` |
| Microsoft App Center secret | `assets/appcenter-config.json` | `46105143-…-74fd28b7bfc0` | Library App Center tidak terlihat dipakai; kemungkinan sisa |
| Google OAuth client ID (web) | `BuildConfig` | `719437284096-eigp7svs…` | Client ID memang publik |
| Google OAuth client ID (iOS) | `BuildConfig` | `719437284096-ao1md35a…` | Publik |
| freeRASP cert hash | `BuildConfig` | `s0xr9Fq5…QczUTSk=` | Hash sertifikat, bukan rahasia |
| Sertifikat `dyadic-EKP` | `assets/server-certificate.pem` | self-signed, berlaku sampai 2025-06-03 | Sudah kedaluwarsa. Fungsinya tidak jelas, kemungkinan sisa SDK |

## Konfigurasi yang perlu diperhatikan

| Temuan | Dampak | Catatan |
|---|---|---|
| `usesCleartextTraffic="true"` | App boleh membuka koneksi HTTP tanpa TLS | Semua endpoint utama memakai HTTPS. Beberapa URL gambar di bundle masih `http://` (misalnya `openweathermap.org/img/...`) |
| Password login dikirim apa adanya di body JSON | Normal di atas HTTPS | Pencarian `CertificatePinner` di kode Java tidak menemukan pinning untuk `tijeapi`. `assets/certs.ts` mungkin terkait pinning, belum ditelusuri |
| Email dikirim ke analitik pada event `login_attempt` | Data pribadi masuk Firebase Analytics | |
| Login guest tanpa batasan terlihat | Siapa pun bisa mendapat token guest dengan satu request | Token guest cukup untuk data peta, bus, dan halte |
| Broker MQTT tanpa username/password | Siapa pun yang bisa menjangkau broker bisa subscribe topik `/mobile_armada/...` | Akses tampaknya dibatasi di tingkat jaringan |
| `a7.a` (HeadlessJsTaskService) tidak terdaftar di manifest | Fitur latar lewat `NativeService` dan `NetworkChangeReceiver` tidak berjalan | Bug fungsional, bukan celah |
| `NetworkChangeReceiver` mengisi `hasInternet` dari `TRANSPORT_WIFI` | Bernilai `false` saat memakai data seluler | Bug fungsional |
| `assets/webview/node_modules/` ikut terbungkus (termasuk biner `esbuild` macOS 9,8 MB) | Ukuran APK membengkak | Tidak berbahaya |
| `QrisTapHostApduService` diekspor | Wajar untuk HCE; dilindungi `BIND_NFC_SERVICE` | |
| `MusicService` diekspor | Wajar untuk kontrol media | |
| Bundle bisa diganti lewat OTA (`files/index.android`) | Integritas bergantung pada keamanan jalur unduhan dan penyimpanan internal | Alur verifikasi bundle OTA tidak ditelusuri |

## Data yang dikirim ke pihak ketiga

| Penerima | Data |
|---|---|
| Firebase Analytics | Event layar dan aksi, Ad ID, SSAID, email pada `login_attempt` |
| TrueWatch (`id1-rum-openway.truewatch.com`) | RUM: sesi, layar, error, log `TrackLog` dari kode native, info perangkat dan operator |
| Firebase Cloud Messaging | Token perangkat, langganan area notifikasi |
| Google, Apple | Saat login dengan akun masing-masing |
| blu by BCA Digital | Saat binding akun dan pembayaran: `companyCode`, `username`, `deviceId`, `email`, challenge |
| Penyedia peta (MapTiler, Carto, Mapbox, Google) | Permintaan tile, yang menyiratkan area yang sedang dilihat |
| Open-Meteo, OpenWeatherMap | Lokasi untuk cuaca |

## Catatan untuk backend Python

- Backend memakai token guest atau akun milik penggunanya sendiri, tidak mencoba melewati proteksi app.
- Backend tidak mengirim apa pun ke analitik atau TrueWatch.
- Kunci peta dari APK tidak dipakai. UI backend memakai OpenStreetMap.
