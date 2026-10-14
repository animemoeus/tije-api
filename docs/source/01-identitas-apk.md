# Identitas APK

## Ringkasan

| Hal | Nilai |
|---|---|
| Nama | TJ: Transjakarta |
| Package | `com.transjakmobile` |
| Versi | 3.0.4 (versionCode 260, `0x104`) |
| Flavor / build type | `production` / `release` |
| `minSdkVersion` | 24 (Android 7.0) |
| `targetSdkVersion` | 36 |
| Activity utama | `com.transjakmobile.MainActivityDefault` (alias dari `MainActivity`) |
| Kelas Application | `com.pairip.application.Application` (pembungkus Google Play, lalu `MainApplication`) |
| Teknologi | React Native, arsitektur lama (bridge), mesin JavaScript Hermes |
| Format distribusi | XAPK (APK dasar + split per ABI, bahasa, dan densitas layar) |
| Sumber | APKPure, 13 Oktober 2026 |

Data di atas berasal dari `manifest.json` di dalam XAPK, `AndroidManifest.xml` yang di-decode dengan androguard, dan `com/transjakmobile/BuildConfig`.

## `BuildConfig`

Nilai yang ditanam saat build dan dibaca JavaScript lewat `react-native-config`:

| Field | Nilai |
|---|---|
| `APPLICATION_ID` | `com.transjakmobile` |
| `APP_CONFIG` | `production` |
| `BASE_URL` | `https://tijeapi.transjakarta.co.id` |
| `CHATBOT_URL` | `wss://chatbot.transjakarta.co.id` |
| `ANDROID_APP_ID` / `IOS_APP_ID` | `transjakarta_apps` |
| `GOOGLE_WEB_CLIENT_ID` | `719437284096-eigp7svs…apps.googleusercontent.com` |
| `GOOGLE_IOS_CLIENT_ID` | `719437284096-ao1md35a…apps.googleusercontent.com` |
| `FREERASP_ANDROID_CERT_HASH` | `s0xr9Fq5oAi35yhppduM7oOINPkCXx/uqxs2QczUTSk=` |
| `FREERASP_WATCHER_MAIL` | `mobile-security@transjakarta.co.id` |
| `TRUEWATCH_SERVICE` | `transjakarta-mobile` |
| `IS_HERMES_ENABLED` | `true` |
| `IS_NEW_ARCHITECTURE_ENABLED` | `false` |
| `DEBUG` | `false` |

## Isi XAPK

```
TJ_Transjakarta_3.0.4_APKPure.xapk   88.244.968 byte
├── com.transjakmobile.apk           61.882.619 byte   APK dasar
├── config.arm64_v8a.apk             26.020.188 byte   native library arm64
├── config.en.apk                        70.041 byte   string bahasa Inggris
├── config.mdpi.apk                     185.502 byte   gambar densitas mdpi
├── icon.png                             83.644 byte
└── manifest.json                         2.218 byte   metadata XAPK
```

Split lain (armeabi-v7a, x86, densitas lain, bahasa lain) tidak disertakan APKPure. Artinya paket ini hanya bisa dipasang di perangkat arm64.

## Isi APK dasar

| Bagian | Isi |
|---|---|
| `classes.dex`, `classes2.dex`, `classes3.dex` | Bytecode Java/Kotlin. Kode milik app ada di `classes3.dex` |
| `AndroidManifest.xml` | Manifest biner (lihat [03-manifest.md](03-manifest.md)) |
| `resources.arsc`, `res/` | Resource Android: layout, string, ikon, warna |
| `assets/index.android.bundle` | Bundle JavaScript, bytecode Hermes v96, 14.090.380 byte |
| `assets/cdn/` | File untuk WebView peta: `maplibre-gl.js`, `maplibre-gl.css`, `mapstyle.json`, `mqtt.min.js`, `tailwind.js` |
| `assets/fonts/` | Plus Jakarta Sans dan PT Sans |
| `assets/mlkit_barcode_models/` | Model TensorFlow Lite untuk pemindai QR/barcode |
| `assets/webview/node_modules/` | Sisa `node_modules` (esbuild, rollup, `@types/estree`) yang ikut terbungkus tanpa sengaja |
| `assets/certs.ts` | File TypeScript 231 KB berisi sertifikat (kemungkinan untuk freeRASP atau pinning) |
| `assets/server-certificate.pem` | Sertifikat self-signed `CN=dyadic-EKP`, berlaku 2020-06-03 s.d. 2025-06-03 (sudah kedaluwarsa) |
| `assets/appcenter-config.json` | `app_secret` Microsoft App Center (lihat [11-temuan-keamanan.md](11-temuan-keamanan.md)) |
| `assets/ft_mcc_mnc_mini.json` | Tabel kode operator seluler untuk SDK TrueWatch |
| `assets/dexopt/baseline.prof` | Baseline profile ART |
| `encrypt_master_key_tables.dat`, `encrypt_platform_key_tables.dat` | Tabel kunci, kemungkinan milik SDK keamanan |
| `stamp-cert-sha256` | Jejak sertifikat source stamp Google Play |
| `*.properties` | Versi library Google Play Services dan Firebase |
| `okhttp3/`, `kotlin/`, `org/`, `javazoom/`, `junit/` | Resource milik library |

## Native library (`config.arm64_v8a.apk`)

```
libVisionCamera.so          libhermes.so             libreactnative.so
libandroidlame.so           libhermestooling.so      libreanimated.so
libbarhopper_v3.so          libimage_processing_util_jni.so
libc++_shared.so            libimagepipeline.so      librnscreens.so
libcrashlytics-common.so    libjsi.so                librnskia.so
libcrashlytics-handler.so   libnative-filters.so     librnworklets.so
libcrashlytics-trampoline.so libnative-imagetranscoder.so
libcrashlytics.so           libts.so                 libworklets.so
libdatastore_shared_counter.so  libfbjni.so
libft_native_dump_mgr.so    libft_native_exp_lib.so
```

Penjelasan masing-masing ada di [05-library-dan-sdk.md](05-library-dan-sdk.md#native-library-so).

## Proteksi yang terpasang

| Proteksi | Tanda | Akibat bagi analisis |
|---|---|---|
| Google Play PairIP | `com.pairip.application.Application`, `com.pairip.licensecheck.LicenseActivity`, permission `CHECK_LICENSE` | App memeriksa lisensi Play dan integritas. APK yang dipasang ulang atau dimodifikasi bisa menolak berjalan |
| freeRASP (Talsec) | `com/freeraspreactnative/`, hash sertifikat di `BuildConfig` | Mendeteksi root, emulator, hooking (Frida), debugger, dan tanda tangan yang berbeda. Laporan dikirim ke `mobile-security@transjakarta.co.id` |
| ScreenGuard | `com/screenguard/`, permission `DETECT_SCREEN_CAPTURE`, `DETECT_SCREEN_RECORDING` | Layar tertentu (tiket, pembayaran) tidak bisa di-screenshot |
| R8 | Nama kelas pendek (`A7/a`, `B6/a`, …) | Sebagian besar kode library diacak namanya |
| Hermes bytecode | Bundle bukan JavaScript teks | Perlu decompiler Hermes untuk dibaca (lihat [06-bundle-javascript.md](06-bundle-javascript.md)) |

Analisis di dokumentasi ini sepenuhnya statis. App tidak dijalankan, tidak dipasang ulang, dan tidak dimodifikasi, jadi proteksi di atas tidak dilewati.
