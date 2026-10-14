# Manifest

Manifest biner di-decode dengan androguard 4.1.4 dari `com.transjakmobile.apk`.

## Atribut `<application>`

| Atribut | Nilai | Catatan |
|---|---|---|
| `android:name` | `com.pairip.application.Application` | Pembungkus Google Play PairIP yang memanggil `MainApplication` |
| `android:allowBackup` | `false` | Data app tidak ikut backup Android |
| `android:usesCleartextTraffic` | `true` | HTTP tanpa TLS diizinkan |
| `android:extractNativeLibs` | `true` | `.so` diekstrak saat pemasangan |

## Permission

Manifest berisi 40 entri `<uses-permission>`, 39 di antaranya unik. Dikelompokkan menurut fungsi:

| Kelompok | Permission | Dipakai untuk |
|---|---|---|
| Jaringan | `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE` | API, MQTT, cek koneksi (`NetInfo`) |
| Lokasi | `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `ACCESS_BACKGROUND_LOCATION` | Halte dan bus terdekat, live tracking perjalanan saat app di belakang |
| Layanan latar | `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_LOCATION`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`, `WAKE_LOCK`, `RECEIVE_BOOT_COMPLETED`, `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`, `SCHEDULE_EXACT_ALARM` | Tracking lokasi di latar, pemutar audio, alarm notifikasi, `BatteryModule` |
| Notifikasi | `POST_NOTIFICATIONS`, `USE_FULL_SCREEN_INTENT`, `VIBRATE`, `ACCESS_NOTIFICATION_POLICY` | Notifee, Firebase Messaging, notifikasi perjalanan |
| NFC | `NFC` | QRIS Tap (HCE) dan pembaca kartu (`react-native-nfc-manager`) |
| Kamera dan media | `CAMERA`, `RECORD_AUDIO`, `READ_MEDIA_AUDIO`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE` | Pemindai QR, foto lampiran laporan, rekaman suara |
| Kontak | `READ_CONTACTS` | Kemungkinan untuk memilih nomor telepon |
| Overlay dan layar | `SYSTEM_ALERT_WINDOW`, `HIDE_OVERLAY_WINDOWS`, `DETECT_SCREEN_CAPTURE`, `DETECT_SCREEN_RECORDING` | ScreenGuard, mencegah overlay di layar sensitif |
| Biometrik | `USE_BIOMETRIC`, `USE_FINGERPRINT` | `react-native-keychain` |
| Google / Play | `c2dm.permission.RECEIVE`, `providers.gsf.permission.READ_GSERVICES`, `finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE`, `vending.CHECK_LICENSE` | Push FCM, install referrer, cek lisensi PairIP |
| Iklan dan atribusi | `gms.permission.AD_ID`, `ACCESS_ADSERVICES_ATTRIBUTION`, `ACCESS_ADSERVICES_AD_ID` | Firebase Analytics |
| Lain-lain | `BROADCAST_CLOSE_SYSTEM_DIALOGS`, `com.transjakmobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` | Sistem dan receiver internal AndroidX |

`POST_NOTIFICATIONS` tercantum dua kali di manifest.

## Activity

| Activity | Asal | Keterangan |
|---|---|---|
| `com.transjakmobile.MainActivity` | app | `ReactActivity` utama |
| `com.transjakmobile.BluActivity` | app | Layar SDK blu by BCA (binding akun, pembayaran) |
| `com.blu.qrscanner_mlkit.view.BluQrScannerActivity` | blu SDK | Pemindai QR blu |
| `com.pairip.licensecheck.LicenseActivity` | Google Play | Layar kalau lisensi tidak valid |
| `com.google.android.gms.auth.api.signin.internal.SignInHubActivity` | Google | Google Sign-In |
| `com.google.android.gms.common.api.GoogleApiActivity` | Google | Dialog Play Services |
| `com.jakewharton.processphoenix.ProcessPhoenix` | library | Restart proses (`react-native-restart`) |
| `app.notifee.core.NotificationReceiverActivity` | Notifee | Penerima tap notifikasi |

### Activity alias (ganti ikon)

| Alias | Aktif awal | Target |
|---|---|---|
| `com.transjakmobile.MainActivityDefault` | ya | `MainActivity` |
| `com.transjakmobile.MainActivityAppIconHutRi` | tidak | `MainActivity` |
| `com.transjakmobile.MainActivityAppIconNatal` | tidak | `MainActivity` |

App mengganti ikon di launcher (misalnya saat HUT RI atau Natal) dengan mengaktifkan salah satu alias dan mematikan yang lain, lewat `react-native-change-icon`.

## Deep link

`MainActivity` (`launchMode=singleTask`) punya satu intent filter `VIEW` + `BROWSABLE` dengan `autoVerify="true"`:

```xml
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW"/>
  <category android:name="android.intent.category.DEFAULT"/>
  <category android:name="android.intent.category.BROWSABLE"/>
  <data android:scheme="mytjapp"/>
  <data android:host="transjakarta.co.id"/>
</intent-filter>
```

Karena elemen `<data>` digabung dalam satu filter, tautan yang diterima berbentuk `mytjapp://transjakarta.co.id/...`.

## `<queries>` (aplikasi lain yang ingin dilihat app)

Android 11+ mengharuskan app menyebut aplikasi lain yang ingin dideteksi. Isinya memberi petunjuk tentang fitur keamanan:

| Entri | Kemungkinan tujuan |
|---|---|
| `VIEW` + `https://mmrl.dev` | Mendeteksi MMRL (pengelola modul Magisk/KernelSU) |
| provider `com.tsng.hidemyapplist.ServiceProvider`, `org.frknkrc44.hma_oss.ServiceProvider` | Mendeteksi Hide My Applist, alat untuk menyembunyikan root |
| package `com.huawei.hwid`, provider `com.huawei.appmarket.commondata` | Layanan Huawei |
| `SMS_RECEIVED`, `SMS_DELIVER`, `NEW_OUTGOING_CALL`, `SENDTO sms:` | Mendeteksi aplikasi SMS/telepon (kemungkinan pemeriksaan malware oleh freeRASP) |
| `MAIN` dan `MAIN` + `LAUNCHER` | Melihat daftar aplikasi yang terpasang |
| `org.chromium.intent.action.IS_READY_TO_PAY`, `UPDATE_PAYMENT_DETAILS` | Web Payments |
| `androidx.camera.extensions.action.VENDOR_ACTION` | Ekstensi kamera vendor |

Tiga kelompok pertama cocok dengan pemeriksaan root, hooking, dan malware yang dilakukan freeRASP.

## Service

| Service | Keterangan |
|---|---|
| `com.qristap.QrisTapHostApduService` | Kartu virtual QRIS Tap (Host Card Emulation). Diekspor, butuh `BIND_NFC_SERVICE` |
| `com.asterinet.react.bgactions.RNBackgroundActionsTask` | Tugas JavaScript di latar, `foregroundServiceType=location` (`0x8`) |
| `com.doublesymmetry.trackplayer.service.MusicService` | Pemutar audio, `foregroundServiceType=mediaPlayback` (`0x2`), diekspor |
| `io.invertase.firebase.messaging.ReactNativeFirebaseMessagingService` | Penerima push FCM |
| `io.invertase.firebase.messaging.ReactNativeFirebaseMessagingHeadlessService` | Menjalankan JavaScript saat push datang di latar |
| `app.notifee.core.ForegroundService`, `app.notifee.core.ReceiverService` | Notifee |
| `com.google.firebase.messaging.FirebaseMessagingService` | FCM bawaan |
| `com.google.firebase.sessions.SessionLifecycleService` | Firebase Sessions |
| `com.google.firebase.components.ComponentDiscoveryService` | Firebase |
| `com.google.android.gms.measurement.AppMeasurementService`, `AppMeasurementJobService` | Google Analytics |
| `com.google.android.gms.auth.api.signin.RevocationBoundService` | Google Sign-In |
| `com.google.mlkit.common.internal.MlKitComponentDiscoveryService` | ML Kit |
| `com.google.android.datatransport.runtime.*` | Pengiriman data Firebase |
| `androidx.work.impl.*` (3 service) | WorkManager |
| `androidx.camera.core.impl.MetadataHolderService` | CameraX |
| `androidx.room.MultiInstanceInvalidationService` | Room |

Service HeadlessJS milik app (`a7.a`, yang dijalankan oleh `NativeServiceModule` dan `NetworkChangeReceiver`) **tidak dideklarasikan di manifest**. Pemanggilan `startService`/`startForegroundService` untuk kelas yang tidak terdaftar akan gagal; `NetworkChangeReceiver` menangkap exception itu dan menulis log `Failed to start service`. Kemungkinan fitur ini sisa yang tidak lagi dipakai, dan tugas latar sekarang ditangani `RNBackgroundActionsTask`.

## Receiver

| Receiver | Keterangan |
|---|---|
| `com.transjakmobile.NetworkChangeReceiver` | Milik app, bereaksi pada perubahan koneksi (lihat [04-kode-native.md](04-kode-native.md)) |
| `io.invertase.firebase.messaging.ReactNativeFirebaseMessagingReceiver` | Push FCM |
| `com.google.firebase.iid.FirebaseInstanceIdReceiver` | FCM |
| `com.google.android.gms.measurement.AppMeasurementReceiver` | Analytics |
| `app.notifee.core.*` (4 receiver) | Alarm, reboot, izin alarm, status blokir notifikasi |
| `androidx.work.impl.*` (8 receiver) | WorkManager |
| `androidx.profileinstaller.ProfileInstallReceiver` | Baseline profile |
| `com.google.android.datatransport.runtime.scheduling.jobscheduling.AlarmManagerSchedulerBroadcastReceiver` | Firebase |

## Provider

| Provider | Keterangan |
|---|---|
| `androidx.startup.InitializationProvider` | Inisialisasi AndroidX |
| `com.google.firebase.provider.FirebaseInitProvider` | Firebase |
| `io.invertase.firebase.app.ReactNativeFirebaseAppInitProvider`, `...crashlytics.ReactNativeFirebaseCrashlyticsInitProvider` | React Native Firebase |
| `io.invertase.notifee.NotifeeInitProvider` | Notifee |
| `com.blusdk.util.BluFileProvider` | Berbagi file dari SDK blu |
| `cl.json.RNShareFileProvider` | `react-native-share` |
| `com.imagepicker.ImagePickerProvider` | `react-native-image-picker` |
| `com.reactnativecommunity.webview.RNCWebViewFileProvider` | Unggah file dari WebView |
| `com.ft.sdk.garble.db.FTContentProvider` | Database lokal TrueWatch |
| `com.google.mlkit.common.internal.MlKitInitProvider` | ML Kit |

## Metadata penting

| Nama | Nilai |
|---|---|
| `com.google.android.geo.API_KEY` | `AIzaSyBS…cAwP3I` (Google Maps, lihat [11-temuan-keamanan.md](11-temuan-keamanan.md)) |
| `firebase_analytics_collection_enabled` | `true` |
| `firebase_crashlytics_collection_enabled` | `false` |
| `google_analytics_adid_collection_enabled` | `true` |
| `google_analytics_ssaid_collection_enabled` | `true` |
| `google_analytics_default_allow_ad_storage` | `true` |
| `google_analytics_default_allow_ad_personalization_signals` | `true` |
| `firebase_messaging_auto_init_enabled` | `true` |
| `app_data_collection_default_enabled` | `true` |
| `android.nfc.cardemulation.host_apdu_service` | Mengarah ke konfigurasi AID untuk QRIS Tap |

Crashlytics dimatikan lewat metadata walau library-nya terpasang (termasuk versi NDK). Kemungkinan diaktifkan dari JavaScript saat runtime.
