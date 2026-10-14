# Kode native milik app

Kode Java/Kotlin yang ditulis tim TransJakarta ada di package `com.transjakmobile` (12 kelas) ditambah beberapa kelas yang namanya diacak R8 di package `a7`. Path di bawah mengacu ke hasil JADX di `c4e872d79c1110323c849349bbbf4845-java/`.

| Kelas | Jenis | Nama di JavaScript |
|---|---|---|
| `MainApplication` | `Application`, `ReactApplication` | |
| `MainActivity` | `ReactActivity` | |
| `BuildConfig` | konstanta | lewat `react-native-config` |
| `NotifCompat` | native module | `NotifCompat` |
| `LocationModule` | native module | `LocationModule` |
| `NativeServiceModule` | native module | `NativeService` |
| `BatteryModule` | native module | `BatteryModule` |
| `MyReactNativePackage` | native module | `MyNativeModule` |
| `BluMyNativeModule` | native module | `BluMyNativeModule` |
| `BluActivity` | `FragmentActivity` | dibuka dari JavaScript |
| `BluViewManager` | view manager | komponen view blu |
| `NetworkChangeReceiver` | `BroadcastReceiver` | |
| `a7.h` | `DefaultReactNativeHost` | |
| `a7.a` | `HeadlessJsTaskService` (abstrak, kosong) | |

## `MainApplication`

```java
public void onCreate() {
    super.onCreate();
    FTAutoTrack.startApp(this);          // TrueWatch / Guance RUM
    SoLoader.init(this, OpenSourceMergedSoMapping.INSTANCE);
    ...
}
```

Menyalakan SDK TrueWatch (FT SDK, `com.ft.sdk`) untuk telemetri, lalu memuat native library React Native. `getReactNativeHost()` mengembalikan `a7.h`.

## `a7.h` (ReactNativeHost)

- `getJSBundleFile()`: pakai `files/index.android` kalau ada (bundle OTA), kalau tidak pakai bundle di assets. Dibahas di [02-arsitektur-aplikasi.md](02-arsitektur-aplikasi.md#bundle-javascript-dan-pembaruan-ota).
- `getJSMainModuleName()`: `index`.
- `getPackages()`: `PackageList` + `B7.b(16)`, `B7.b(15)`, `B7.b(28)`.
- `getUseDeveloperSupport()`: `false`.
- `isHermesEnabled()`: `true`. `isNewArchEnabled()`: `false`.

## `NotifCompat`

Satu method: `showNotification(tujuan, estimasi, jumlah)`. Dipakai fitur perjalanan untuk menampilkan notifikasi yang menempel selama pengguna di dalam bus.

```js
// dari JavaScript
NativeModules.NotifCompat.showNotification("Harmoni", "10 Menit", "3 Halte");
```

Yang dilakukan:

1. Membuat notification channel (Android 8+).
2. Membuat `RemoteViews` dari layout `notification_transjakarta` dan mengisi:
   - `notification_title_tujuan` = tujuan;
   - `notification_content_count` = jumlah + `" "`;
   - `notification_content_time` = `" ~ "` + estimasi.
3. Membangun notifikasi di channel `default_channel`:
   - judul `"Tujuan " + tujuan`, teks `"Estimasi tiba " + estimasi`;
   - `setOngoing(true)`, jadi tidak bisa di-swipe;
   - prioritas tinggi, terlihat di layar kunci, warna `#1B7B3A`;
   - `android.showWhen` dan `android.showChronometer` dimatikan.
4. `notify(1001, ...)`. ID tetap, jadi setiap panggilan memperbarui notifikasi yang sama.

Ada dua hal kecil di kode ini:

- Tampilan besar (`setCustomBigContentView`) memakai `RemoteViews` baru yang tidak diisi teks, jadi saat notifikasi dibuka penuh isinya hanya teks bawaan layout.
- `BigTextStyle` diisi teks contoh `"1B  • 10 Menit"` yang tertinggal dari pengembangan.

## `LocationModule`

`getCurrentLocation(promise)` mengambil lokasi satu kali lewat `LocationManager.getCurrentLocation` dengan executor satu thread.

| Hasil | Isi |
|---|---|
| resolve | `{ latitude: number, longitude: number }` |
| reject `PERMISSION_DENIED` | `"Izin lokasi belum diberikan."` |
| reject `LOCATION_UNAVAILABLE` | `"Lokasi tidak ditemukan."` |

Untuk lokasi yang terus diperbarui, app memakai library JavaScript (`react-native-geolocation-service`, `@react-native-community/geolocation`, `react-native-get-location`), bukan modul ini.

## `NativeServiceModule` (`NativeService`)

`startBackgroundService()` membuat `Intent` ke `a7.a` dengan extra contoh `foo=bar`, lalu menjalankannya lewat helper yang namanya diacak R8 (`androidx.work.impl.background.systemjob.a.n`, kemungkinan pembungkus `startForegroundService`). Karena `a7.a` tidak terdaftar di manifest, pemanggilan ini kemungkinan gagal di perangkat. Lihat catatan di [03-manifest.md](03-manifest.md#service).

## `BatteryModule`

| Method | Keterangan |
|---|---|
| `isIgnoringBatteryOptimizations(promise)` | `true` kalau app sudah dikecualikan dari optimasi baterai |
| `requestIgnoreBatteryOptimizations()` | Membuka dialog sistem untuk meminta pengecualian |

Dipakai supaya tracking perjalanan di latar tidak dimatikan sistem.

## `MyReactNativePackage` (`MyNativeModule`)

| Method | Keterangan |
|---|---|
| `greet(name, promise)` | Mengembalikan `"Hello, <name>!"`. Sisa contoh |
| `reloadBundle(bundlePath)` | Restart activity utama dan matikan proses supaya bundle OTA baru dimuat. `bundlePath` tidak dipakai di dalam method; lokasi bundle ditentukan `a7.h` |

## `BluMyNativeModule` dan `BluActivity`

`BluMyNativeModule.greetBlu(companyCode, username, deviceId, challenge, challengeId, ...)` membuka `BluActivity` dengan parameter dari server TransJakarta. `BluActivity` membaca extra berikut:

| Extra | Isi |
|---|---|
| `companyCode` | Kode mitra di blu |
| `username` | Pengguna |
| `deviceId` | ID perangkat |
| `challenge`, `challengeId` | Tantangan autentikasi dari server |
| `email` | Email pengguna |
| `homepageUrl` | Halaman awal di SDK |
| `tncConsents` | Persetujuan syarat dan ketentuan |
| `env` | `"prod"` → `BluSdk.ENV_PROD`, lainnya → `ENV_UAT` |
| `partnerLinkageId` | ID tautan akun |

Hasilnya dikirim kembali ke JavaScript lewat promise yang disimpan di `BluMyNativeModule`. Endpoint server yang terkait ada di [07-katalog-api-upstream.md](07-katalog-api-upstream.md#pembayaran-blu-by-bca-digital).

## `NetworkChangeReceiver`

Saat broadcast perubahan koneksi diterima:

1. Kalau app sedang di foreground (`importance == 100`), tidak melakukan apa-apa.
2. Kalau tidak, membaca jaringan aktif dan mengisi `hasInternet = hasTransport(1)`. Angka 1 adalah `NetworkCapabilities.TRANSPORT_WIFI`, jadi nilai ini `true` hanya saat memakai Wi-Fi, bukan saat memakai data seluler.
3. Menjalankan `a7.a` dengan extra `hasInternet`, lalu `HeadlessJsTaskService.acquireWakeLockNow`.
4. Kalau gagal, menulis log `Failed to start service: ...` ke TrueWatch.

Sejak Android 7, broadcast `CONNECTIVITY_ACTION` tidak lagi dikirim ke receiver yang hanya dideklarasikan di manifest. Ditambah `a7.a` yang tidak terdaftar, receiver ini kemungkinan besar tidak berfungsi di perangkat modern.

## Tabrakan nama di hasil smali

Hasil smali di folder akar diekstrak di filesystem Windows yang tidak membedakan huruf besar-kecil. Kelas R8 yang namanya hanya beda kapitalisasi saling menimpa. Contoh nyata: `La7/a` (service HeadlessJS) tertimpa `LA7/a` (sebuah `Comparator`) di `A7/a.smali`.

Hasil JADX tidak kena masalah ini karena JADX mengganti nama kelas yang bentrok, misalnya `a7.a` menjadi `A7/AbstractServiceC0176a.java` dengan komentar `/* renamed from: a7.a, reason: case insensitive filesystem */`. Selalu percayai direktif `.class` di dalam file smali, atau komentar `renamed from` di JADX, daripada path file.
