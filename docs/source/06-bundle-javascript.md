# Bundle JavaScript

## Format

| Hal | Nilai |
|---|---|
| File | `assets/index.android.bundle` |
| Ukuran | 14.090.380 byte |
| Format | Bytecode Hermes (HBC) |
| Magic | `c6 1f bc 03 c1 03 19 1f` |
| Versi bytecode | 96 (`0x60`) |
| Jumlah string | 73.034 |
| Hasil decompile | Pseudo-JavaScript ±79 MB |

Bundle bukan JavaScript teks, jadi `grep` biasa hanya menemukan potongan string yang tersambung tanpa pemisah. Cara membacanya ada di [12-cara-reproduksi-analisis.md](12-cara-reproduksi-analisis.md#3-decompile-bundle-hermes).

## Bentuk modul

Bundle berisi modul Metro yang didaftarkan dengan `__d(fungsi, id, dependensi)`. Contoh store konfigurasi MQTT (modul 5528) setelah decompile:

```js
r2['mqttConfigStore'] = r0;
...
r1 = function(a0) {
    var _closure2_slot0 = a0;               // set dari Zustand
    r0 = {};
    r0['mqtt_url'] = '';
    r0['setmqtt_url'] = function(a0) {      // Original name: setmqtt_url
        return _closure2_slot0({ 'mqtt_url': a0 });
    };
    return r0;
};
r2['mqttConfigStore'] = create(immer(r1));
```

Nama fungsi asli sering masih tersimpan sebagai komentar `// Original name: ...`. Dari nama-nama itu katalog endpoint di [07-katalog-api-upstream.md](07-katalog-api-upstream.md) disusun.

## API client

Semua request ke `tijeapi` lewat satu fungsi pembuat request (sekitar baris 1.192.440 di hasil decompile) yang dipakai hook React Query. Setiap layanan didefinisikan sebagai objek kecil:

```js
// Original name: getConfigBe
function getConfigBe({ param = {}, payload = {} }) {
    return { method: 'get', url: '/v1/settings/api/config', param, payload };
}

// Original name: getBusNearest
{ method: 'post', url: '/v1/bus' }
```

Pemanggil boleh menimpa bagian request lewat opsi berikut (ejaan sesuai kode asli):

| Opsi | Efek |
|---|---|
| `altenativeQuery` | Ditempel di belakang `url`, misalnya `'/mqtt_url'` → `/v1/settings/api/config/mqtt_url` |
| `alternativefullUrl` | Mengganti seluruh URL |
| `altenativeparams` | Query string |
| `altenativePayload` | Body request |
| `altenativeMessageSucces` | Pesan toast saat berhasil |
| `alternativeConfig` | Header tambahan; header standar dibuat ulang |
| `disableErrorMessage` | Tidak menampilkan toast error |
| `navigation` | Objek navigasi React Navigation, kemungkinan untuk pindah layar saat error tertentu |

Kode pembuat URL-nya:

```js
config['method'] = method || 'get';
config['url'] = alternativefullUrl ? alternativefullUrl
              : altenativeQuery     ? service.url + altenativeQuery
              :                       service.url;
config['params'] = altenativeparams || service.param || {};
config['data']   = altenativePayload || service.payload || {};
```

### Header

Setiap request membawa header ini (dari kode, cocok dengan yang diterima server):

```js
{
  'X-App-Version':    DeviceInfo.getCurrentVersion(),         // "3.0.4"
  'X-Device-ID':      deviceId,
  'X-Lang':           i18n.language,                          // "id" / "en"
  'X-FCM-Token':      fcmToken,
  'X-App-OS':         Platform.OS,                            // "android"
  'X-App-OS-Version': DeviceInfo.getSystemVersion(),          // "14"
  'X-App-Platform':   Platform.Version,                       // API level, mis. 34
  'Content-Type':     'application/json',
  'X-Device-Model':   DeviceInfo.getBrand() + '|' + DeviceInfo.getModel(),
  'Accept':           'application/json',
  'Authorization':    'Bearer ' + user.token                  // kalau ada user
}
```

### Token dan refresh

Sebelum mengirim, pembuat request membaca `userStore.getState().user`:

1. Kalau sedang ada proses refresh (`getIsRefreshing()` bernilai benar), request diarahkan ke jalur terpisah.
2. Kalau `user.token_valid_until` sudah lewat dari `getUnixNow()`, request juga diarahkan ke jalur terpisah. Jalur ini tidak ditelusuri sampai habis, tapi di modul lain ada pemanggilan `POST /v1/auth/token/refresh` dengan body `{ refresh_token: user.tokenReferesh }` dan header lengkap, jadi kemungkinan besar token di-refresh di sini. Ejaan field lokal memang `tokenReferesh`.
3. Kalau token masih berlaku, `Authorization: Bearer <token>` dipasang. Kalau tidak ada user, header `Authorization` berisi nilai kosong.

Field yang disimpan di store user dan di-persist: `token`, `tokenReferesh`, `token_valid_until`, `tokenPaymentBlu`, `moter`. Fungsi `stripTokensFromSessionPayload` membuang token sebelum sesi disimpan di tempat lain.

Instance kedua, `apiClient`, dipakai layanan autentikasi (`authService`). Request dengan opsi `skipAuth: true` (login, register, guest, cek nomor telepon) tidak membawa token.

## State store (Zustand)

Beberapa store yang terlihat di bundle:

| Store | Isi |
|---|---|
| store utama (persist) | `rehydrated`, `api: 'prod'`, `fcmToken`, `user`, `session`, `modalLapor`, … |
| `userStore` | Data user dan token |
| `mqttConfigStore` (`mqtt-config-storage`) | `mqtt_url`, `setmqtt_url` |
| `mapStore` | `setCompassBearing`, `setPostMessageToMap` (jembatan ke WebView peta) |
| `myticketStore` | Tiket pengguna |

`mqtt-config-storage` dihapus dari AsyncStorage setiap kali layar peta dipasang, jadi URL broker selalu diambil ulang dari server.

## WebView peta

HTML lengkap peta (MapLibre + mqtt.js + Tailwind) tertanam sebagai string template di bundle dan disusun saat runtime. Bagian yang berubah-ubah, misalnya URL broker, disisipkan dengan penggabungan string:

```js
"...client=mqtt.connect(\n              '" + mqtt_url + "',\n              'id_' + parseInt(Math.random() * 100000),\n            );..."
```

Komunikasi React Native ↔ WebView lewat `postMessage`. Daftar pesannya ada di [09-live-tracking.md](09-live-tracking.md#pesan-antara-react-native-dan-webview).

## String menarik lainnya

| String | Arti |
|---|---|
| `Start Tracking Location 10 minutes` | Label fitur tracking lokasi berbatas waktu |
| `Location Out of Service Area` | Toast saat `GET /v2/bus-stop` kosong |
| `We couldnt find a bus stop near you.` | Tidak ada halte terdekat |
| `We have launched a new and improved app. Please update to continue us...` | Paksa update (`react-native-version-check`) |
| `MQTT URL: ` | Label teks, kemungkinan di layar debug |
| `{{count}} Rute terdampak Pembaruan Layanan Bus Non-BRT` | Info pengalihan rute |
| `login_guest`, `login_attempt` | Nama event analitik |
