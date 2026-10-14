# Library dan SDK

## Library React Native

Daftar ini disusun dari package Java yang punya native module atau view manager di hasil JADX. Nama npm adalah padanan yang paling mungkin berdasarkan nama package; versi tidak tercatat di APK.

### Tampilan dan navigasi

| Package Java | Library npm | Dipakai untuk |
|---|---|---|
| `com.swmansion.rnscreens` | `react-native-screens` | Layar native untuk React Navigation |
| `com.swmansion.gesturehandler` | `react-native-gesture-handler` | Gestur, bottom sheet |
| `com.swmansion.reanimated`, `com.worklets` | `react-native-reanimated`, `react-native-worklets` | Animasi |
| `com.th3rdwave.safeareacontext` | `react-native-safe-area-context` | Area aman layar |
| `com.reactnativepagerview` | `react-native-pager-view` | Halaman geser (onboarding, banner) |
| `com.horcrux.svg` | `react-native-svg` | Ikon dan grafik SVG |
| `com.BV.LinearGradient` | `react-native-linear-gradient` | Gradasi |
| `com.shopify.reactnative.skia` | `@shopify/react-native-skia` | Grafik 2D (`librnskia.so`) |
| `com.airbnb.android.react.lottie` | `lottie-react-native` | Animasi Lottie |
| `com.reactnative.pulltorefresh` | pull-to-refresh native | Tarik untuk memuat ulang |
| `com.reactnativechangeicon` | `react-native-change-icon` | Ganti ikon launcher (alias HUT RI, Natal) |

Dari string di bundle juga terlihat React Navigation, `@gorhom/bottom-sheet`, i18next, TanStack Query (`useMutation`, `getMutationCache`), Zustand + Immer (`create`, `immer`), dan Moment.js.

### Peta dan lokasi

| Package Java | Library npm | Dipakai untuk |
|---|---|---|
| `com.rnmaps.maps` | `react-native-maps` | Peta Google native |
| `com.reactnativecommunity.webview` | `react-native-webview` | WebView peta MapLibre (live tracking) dan halaman web |
| `com.agontuk.RNFusedLocation` | `react-native-geolocation-service` | Lokasi dari Fused Location Provider |
| `com.reactnativecommunity.geolocation` | `@react-native-community/geolocation` | Lokasi |
| `com.github.douglasjunior.reactNativeGetLocation` | `react-native-get-location` | Lokasi satu kali |
| `com.asterinet.react.bgactions` | `react-native-background-actions` | Tugas JavaScript di latar dengan notifikasi foreground |

### Perangkat dan sistem

| Package Java | Library npm | Dipakai untuk |
|---|---|---|
| `com.reactnativecommunity.netinfo` | `@react-native-community/netinfo` | Status koneksi |
| `com.reactnativecommunity.asyncstorage` | `@react-native-async-storage/async-storage` | Penyimpanan lokal (`mqtt-config-storage`, sesi) |
| `com.reactnativecommunity.clipboard` | `@react-native-clipboard/clipboard` | Salin teks |
| `com.learnium.RNDeviceInfo` | `react-native-device-info` | Versi app, merek, model, OS untuk header API |
| `com.lugg.RNCConfig` | `react-native-config` | Membaca `BuildConfig` |
| `com.zoontek.rnlocalize` | `react-native-localize` | Bahasa perangkat |
| `com.zoontek.rnpermissions` | `react-native-permissions` | Permintaan izin |
| `com.reactnativerestart` | `react-native-restart` | Restart app |
| `com.rnfs` | `react-native-fs` | Akses file |
| `io.xogus.reactnative.versioncheck` | `react-native-version-check` | Cek versi di Play Store, paksa update |
| `community.revteltech.nfc` | `react-native-nfc-manager` | Membaca kartu NFC |
| `com.oblador.keychain` | `react-native-keychain` | Menyimpan rahasia di Keystore, biometrik |
| `com.tectiv3.aes` | `react-native-aes-crypto` | Enkripsi AES di JavaScript |

### Media dan berkas

| Package Java | Library npm | Dipakai untuk |
|---|---|---|
| `com.mrousavy.camera` | `react-native-vision-camera` | Kamera, pemindai QR (`libVisionCamera.so`) |
| `com.reactnativeqrimagereader` | modul `QrImageReader` | Membaca QR dari gambar galeri |
| `com.imagepicker` | `react-native-image-picker` | Memilih foto (lampiran laporan) |
| `com.reactnativecompressor` | `react-native-compressor` | Kompres gambar dan video |
| `com.reactlibrary.createthumbnail` | `react-native-create-thumbnail` | Thumbnail video |
| `com.brentvatne` | `react-native-video` | Pemutar video (ExoPlayer) |
| `com.doublesymmetry.trackplayer` | `react-native-track-player` | Pemutar audio di latar |
| `cl.json` | `react-native-share` | Berbagi |

### Akun, notifikasi, analitik

| Package Java | Library npm | Dipakai untuk |
|---|---|---|
| `io.invertase.firebase.*` | `@react-native-firebase/app`, `messaging`, `analytics`, `crashlytics`, `remote-config` | Push, analitik, crash, konfigurasi jarak jauh |
| `io.invertase.notifee` | `@notifee/react-native` | Notifikasi lokal |
| `com.reactnativegooglesignin` | `@react-native-google-signin/google-signin` | Login Google |
| `com.RNAppleAuthentication` | `@invertase/react-native-apple-authentication` | Login Apple |
| `com.ft.sdk` (+ `FTMobilePackage`) | SDK TrueWatch / Guance untuk React Native | RUM, log, trace |

### Keamanan

| Package Java | Library | Dipakai untuk |
|---|---|---|
| `com.freeraspreactnative` | `freerasp-react-native` (Talsec) | Deteksi root, emulator, hook, debugger, tanda tangan palsu, instalasi dari luar Play |
| `com.screenguard` | `react-native-screenguard` | Blokir screenshot dan rekam layar |

## SDK pihak ketiga

### blu by BCA Digital

Package `com.blusdk` dan `com.blu.qrscanner_mlkit`. Dipanggil dari `BluActivity` (lihat [04-kode-native.md](04-kode-native.md#blumynativemodule-dan-bluactivity)).

| Konstanta | Nilai | Base URL | Auth base URL |
|---|---|---|---|
| `ENV_PROD` | 0 | `https://page.blubybcadigital.id/blupay` | `https://page.blubybcadigital.id/blunion-api/` |
| `ENV_UAT` | 1 | `https://mdigi.umundus.net/blupay` | `https://mdigi.umundus.net/blunion-api/` |
| `ENV_DEV` | 2 | `https://mdigi.dmundus.net/blupay` | `https://mdigi.dmundus.net` |
| `ENV_STG` | 3 | `https://stg2-api-dg.cermati.com/blupay` | `https://stg2-api-dg.cermati.com` |
| `ENV_DRC` | 4 | `https://test-blu.blubybcadigital.id/blupay` | `https://test-blu.blubybcadigital.id` |
| `ENV_GCP` | 5 | `https://deunion.gibaprox.com/blupay` | `https://deunion.gibaprox.com` |
| `ENV_UAT2` | 6 | `https://mdigi.umundus.net/altblupay` | `https://mdigi.umundus.net` |
| `ENV_PROD2` | 7 | `https://page.blubybcadigital.id/altblupay` | `https://app.blubybcadigital.id` |
| `ENV_CUSTOM` | 99 | kosong | kosong |

App TransJakarta hanya memakai `ENV_PROD` (kalau parameter `env` = `"prod"`) atau `ENV_UAT`.

### QRIS Tap (HCE)

Package `com.qristap`. Membuat ponsel bisa "ditempel" ke terminal pembayaran seperti kartu, memakai Host Card Emulation.

- `QrisTapHostApduService` menjawab perintah APDU dari terminal. AID yang didaftarkan: `A0000006022020`. Status sukses `90 00`. Payload yang panjang dipecah per 254 byte.
- `HceControlModule` adalah native module untuk JavaScript:

| Method | Keterangan |
|---|---|
| `isSupported(promise)` | Perangkat punya NFC dengan HCE |
| `isEnabled(promise)` | NFC menyala |
| `isDefaultPaymentApp(promise)` | App terpilih sebagai aplikasi pembayaran bawaan (kategori `payment`) |
| `requestDefaultPaymentApp(promise)` | Membuka pengaturan NFC agar pengguna memilih app ini |
| `setEnabled(enabled, promise)` | Menyalakan atau mematikan layanan QRIS Tap di app |
| `setPayload(a, b, promise)` | Memasang data transaksi yang akan dikirim ke terminal |
| `setRawQrContent(content, promise)` | Memasang isi QR mentah |

Event yang dikirim ke JavaScript berisi `timestamp` dan `message`, misalnya `"Payment terminal is reading the card"` dan `"QRIS TAP transaction completed successfully"`. Data transaksinya diambil dari server lewat `/v1/payment/bayarind/qr-tap/auth-code` dan `/v1/payment/bayarind/qr-tap/qr-generate`.

### freeRASP (Talsec)

Kode inti Talsec diacak R8 ke folder `N/`. Konfigurasi dari `BuildConfig`:

- `FREERASP_ANDROID_CERT_HASH`: hash sertifikat penandatangan yang sah. APK yang ditandatangani ulang akan terdeteksi.
- `FREERASP_WATCHER_MAIL`: `mobile-security@transjakarta.co.id`, alamat laporan Talsec.

Bagian `<queries>` di manifest (MMRL, Hide My Applist, aplikasi SMS) kemungkinan besar dipakai freeRASP untuk pemeriksaan root dan malware.

### TrueWatch / Guance (FT SDK)

Package `com.ft.sdk`, native `libft_native_dump_mgr.so` dan `libft_native_exp_lib.so`. Dinyalakan di `MainApplication.onCreate()` dengan `FTAutoTrack.startApp(this)`. Nama layanan `transjakarta-mobile`, endpoint `id1-rum-openway.truewatch.com`. Banyak log app (`TrackLog.d`, `TrackLog.e`) ikut terkirim ke sini.

### Firebase

Messaging (push), Analytics (dengan Ad ID dan SSAID), Crashlytics (dimatikan di manifest), Remote Config, Installations, Sessions, ABT. Push dari FCM bisa membangunkan JavaScript lewat `ReactNativeFirebaseMessagingHeadlessService`.

Endpoint server yang terkait push:

- `POST /v1/notification/fcm/init`: daftarkan token FCM;
- `POST /v1/notification/fcm/subscribe-area`: berlangganan notifikasi per area;
- `POST /v1/notif/unsubscribe`: berhenti berlangganan.

### Google

- Maps SDK (`com.google.android.geo.API_KEY`) untuk `react-native-maps`.
- Sign-In (`GOOGLE_WEB_CLIENT_ID`).
- ML Kit barcode scanning (`libbarhopper_v3.so`, model di `assets/mlkit_barcode_models/`).
- Play Integrity / PairIP untuk lisensi.

### Microsoft App Center

`assets/appcenter-config.json` berisi `app_secret`. Library App Center sendiri tidak terlihat di daftar native module, jadi file ini kemungkinan sisa dari konfigurasi lama (CodePush lama juga memakai App Center).

## Native library (`.so`)

| Library | Asal |
|---|---|
| `libhermes.so`, `libhermestooling.so` | Mesin JavaScript Hermes |
| `libreactnative.so`, `libjsi.so`, `libfbjni.so`, `libc++_shared.so` | React Native |
| `libreanimated.so`, `libworklets.so`, `librnworklets.so` | Reanimated, Worklets |
| `librnscreens.so` | react-native-screens |
| `librnskia.so` | Skia |
| `libimagepipeline.so`, `libnative-filters.so`, `libnative-imagetranscoder.so` | Fresco (pemuat gambar RN) |
| `libVisionCamera.so` | Vision Camera |
| `libimage_processing_util_jni.so` | CameraX |
| `libbarhopper_v3.so` | ML Kit barcode |
| `libandroidlame.so` | Encoder MP3 LAME (rekaman suara) |
| `libcrashlytics*.so` | Firebase Crashlytics NDK |
| `libdatastore_shared_counter.so` | AndroidX DataStore |
| `libft_native_dump_mgr.so`, `libft_native_exp_lib.so` | TrueWatch (crash native) |
| `libts.so` | Kemungkinan Talsec (freeRASP) |

## Aset WebView peta

Di `assets/cdn/`, dimuat oleh HTML peta yang tertanam di bundle:

| File | Ukuran | Isi |
|---|---|---|
| `maplibre-gl.js`, `maplibre-gl.css` | 800 KB, 68 KB | Mesin peta vektor MapLibre GL |
| `mapstyle.json` | 13 KB | Gaya peta lokal |
| `mqtt.min.js` | 578 KB | Client MQTT untuk browser (mqtt.js) |
| `tailwind.js` | 638 KB | Tailwind CSS versi CDN untuk popup dan indikator |

Detail cara WebView memakainya ada di [09-live-tracking.md](09-live-tracking.md).
