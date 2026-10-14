# Katalog API upstream

Base URL produksi: `https://tijeapi.transjakarta.co.id`. Staging: `https://stg-tijeapi.transjakarta.co.id`. Development: `https://tije-api-dev.transjakarta.co.id`.

Katalog ini disusun otomatis dari bundle Hermes yang sudah di-decompile: setiap string path `/v1/…`, `/v2/…`, `/v3/…` dicatat bersama nama fungsi terdekat (`// Original name: …`) dan method HTTP (`apiClient.get/post/put/patch/delete` atau objek `{method, url}`). Hasilnya **152 kombinasi method + path**:

| Method | Jumlah |
|---|---|
| GET | 72 |
| POST | 59 |
| PATCH | 5 |
| DELETE | 2 |
| PUT | 1 |
| belum jelas (`?`) | 13 |

Method `/v1/auth/token/refresh` dipastikan POST secara manual dari kode refresh; sisanya hasil pemindaian otomatis.

## Cara membaca tabel

- **Method `?`** berarti path ditemukan tapi method-nya tidak bisa dipastikan dari kode di sekitarnya. Biasanya path itu disusun dengan menggabungkan string (misalnya `'/v1/route/' + id`) di tempat yang jauh dari pemanggilan HTTP-nya.
- **`{id}`** di akhir path berarti di kode path-nya berakhir dengan `/` lalu disambung nilai lain saat runtime. Isi persisnya (ID, kode halte, nomor invoice) tergantung fungsinya.
- **Fungsi di bundle** adalah nama asli fungsi JavaScript. Satu path bisa dipakai beberapa fungsi.
- **Status `terverifikasi`** berarti endpoint sudah dipanggil ke server asli dan response-nya tercatat di [10-contoh-request-response.md](10-contoh-request-response.md). Sisanya dibaca dari kode.
- Semua endpoint, kecuali login, register, guest, dan cek nomor telepon, butuh header `Authorization: Bearer <token>`. Lihat [08-autentikasi-upstream.md](08-autentikasi-upstream.md).
- Bentuk response umumnya `{ "code": 200, "message": "success", "data": … }`, kadang dengan `meta` untuk paginasi. Beberapa endpoint konfigurasi memakai `{ "meta": { "code", "status", "message" }, "data": … }`.

## Endpoint

### Autentikasi

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/auth/apple-login` | `appleLogin` |  |
| POST | `/v1/auth/check/phone` | `checkPhone` |  |
| POST | `/v1/auth/forget-password` | `forgotPassword` |  |
| POST | `/v1/auth/forget-password/new-password` | `resetPassword` |  |
| POST | `/v1/auth/forget-password/verify` | `forgotPasswordVerify` |  |
| POST | `/v1/auth/google-login` | `googleLogin` |  |
| POST | `/v1/auth/login` | `login` |  |
| POST | `/v1/auth/login/guest` | `guestLogin` | terverifikasi |
| POST | `/v1/auth/logout` | `logout` |  |
| POST | `/v1/auth/password/check` | `checkOldPassword` |  |
| POST | `/v1/auth/register` | `postRegister`, `register` |  |
| POST | `/v1/auth/token/refresh` | pembuat request (refresh otomatis) |  |

### Sesi dan konfigurasi

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/menu` | `getMenu` |  |
| GET | `/v1/session` | `getSession` |  |
| GET | `/v1/settings/api/config` | `getConfigBe` | terverifikasi |
| GET | `/v1/settings/api/config/{id}` | – |  |
| GET | `/v1/settings/api/config/benefit_ott` | `getBenefitTicketTour` |  |
| GET | `/v1/settings/api/config/link_ppid` | `getEPPID` |  |
| GET | `/v1/settings/api/config/royal_trans_config` | `getRoyalTransConfig` |  |

### Bus dan live tracking

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/bus` | `getAllbus`, `getNearbyBus` |  |
| POST | `/v1/bus` | `getBusNearest` | terverifikasi |
| GET | `/v1/bus-stop` | `getSearchBusStop` |  |
| ? | `/v1/bus-stop/{id}` | `getAllbus`, `getSearchBusStopNewDetail` |  |
| ? | `/v1/bus/{id}` | `getDetailHalteCampaign` |  |
| POST | `/v1/bus/offline` | `getBusNearestOffline` | terverifikasi |

### Halte

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v2/bus-stop` | `getSearchBusStopNew`, `searchBusStops` | terverifikasi |
| GET | `/v2/bus-stop/{id}` | `getHalteDetail` |  |

### Rute dan perencana perjalanan

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/direction` | `getAllRoute` |  |
| POST | `/v1/direction` | `postTripPoint` |  |
| GET | `/v1/route` | `getSearchRoute` |  |
| GET | `/v1/route-diversion` | – |  |
| ? | `/v1/route/{id}` | `getSearchBusStopDetail` |  |
| GET | `/v2/route` | – |  |
| GET | `/v2/route/{id}` | `getRouteDetail` |  |

### Peta dan pencarian tempat

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/maps/autocomplete` | `getSearchAutoComplete` |  |
| GET | `/v1/maps/details/{id}` | `getPlaceDetail`, `getSearchDetailAutoComplete` |  |
| GET | `/v1/maps/geocode` | `getGeocoder` |  |
| POST | `/v2/maps/autocomplete` | `searchAutoComplete` |  |

### Tiket reguler dan umum

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/ticket/available` | `getTicketAvailable` |  |
| GET | `/v1/ticket/available/new` | `getTicketAvailableNew` |  |
| POST | `/v1/ticket/book/{id}` | `postBookTicketGeneral` |  |
| POST | `/v1/ticket/book/astrapay` | `postBookTicket`, `postBookTicketAstrapay` |  |
| POST | `/v1/ticket/book/bayarind` | `postBookTicketBayarind` |  |
| POST | `/v1/ticket/book/bayarind_va_dki` | `postBookBankDkiVa` |  |
| POST | `/v1/ticket/book/blu` | `postBookTicketBlu` |  |
| GET | `/v1/ticket/generate` | `getGenerateInvoice` |  |
| GET | `/v1/ticket/reguler/invoice/{id}` | `getInvoiceDetail` |  |
| GET | `/v1/ticket/status` | `getStatusTicket` |  |
| GET | `/v1/ticket/types` | – |  |
| GET | `/v2/ticket/available` | – |  |
| GET | `/v2/ticket/list` | `getTicket` |  |
| ? | `/v2/ticket/reguler/detail/{id}` | `getTicketAvailable`, `getTicketDetailBrt` |  |
| POST | `/v2/ticket/reguler/generate` | `generate` |  |
| ? | `/v2/ticket/reguler/invoices/{id}` | `getTicketStatusBrt` |  |
| POST | `/v3/ticket/book` | `postBookTicketV3` |  |
| GET | `/v3/ticket/list` | `getTicketList` |  |

### Tiket wisata (Open Top Tour, tiket lain)

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| ? | `/v1/ticket/other/{id}` | `postPaymentTicketOther` |  |
| POST | `/v1/ticket/other/{id}` | `postBookTicketTourV1` |  |
| GET | `/v1/ticket/other/open-roof/category` | `getCategoryTicketTour` |  |
| ? | `/v1/ticket/other/payment/{id}` | `postCheckInTicketOther` |  |
| POST | `/v1/ticket/other/payment/{id}` | `postPaymentTicketOther`, `postPaymentTicketOtherGeneral` |  |
| ? | `/v1/ticket/other/schedule/{id}` | `getpaymentChannel` |  |
| GET | `/v1/ticket/other/schedule/{id}` | `getScheduleTicketTour` |  |
| ? | `/v1/ticket/other/status/check-in` | `getAccountBindingBayarind` |  |
| POST | `/v1/ticket/other/status/check-in` | `postCheckinOTT` |  |
| POST | `/v2/ticket/open-top-tour/book` | `postBookTicketTourV2` |  |

### Royaltrans

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v2/ticket/royal-trans/book` | `bookTicket` |  |
| POST | `/v2/ticket/royal-trans/check-in-out` | `checkIn` |  |
| GET | `/v2/ticket/royal-trans/invoice/{id}` | `getInvoiceDetails` |  |
| GET | `/v2/ticket/royal-trans/multi-pickup-stops/{id}` | `getDepartureStops` |  |
| POST | `/v2/ticket/royal-trans/refund` | `submitRefund` |  |
| GET | `/v2/ticket/royal-trans/refund/eligibility/{id}` | `getEligibility` |  |
| POST | `/v2/ticket/royal-trans/reschedule` | `rescheduleTicket` |  |
| GET | `/v2/ticket/royal-trans/reschedule/eligibility/{id}` | `getRescheduleEligibility` |  |
| GET | `/v2/ticket/royal-trans/route-recent-search` | `getRecent` |  |
| GET | `/v2/ticket/royal-trans/routes` | `getRoutes` |  |
| GET | `/v2/ticket/royal-trans/seats/{id}` | – |  |
| GET | `/v2/ticket/royal-trans/timetable/{id}` | – |  |

### Langganan (TJ Pass)

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| ? | `/v1/subscription/book-b2c/{id}` | `getTicket` |  |
| POST | `/v1/subscription/book-b2c/{id}` | `postBookB2CTJPassGeneral` |  |
| GET | `/v1/subscription/me` | `getStatus` |  |
| GET | `/v1/subscription/me/history` | `getHistory` |  |
| GET | `/v1/subscription/packages` | `getPackages` |  |
| POST | `/v1/subscription/ticket` | `generateTicket` |  |

### Pembayaran: blu by BCA Digital

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/payment/blu/account-binding/balance` | `getBluBalance` |  |
| POST | `/v1/payment/blu/account-binding/inquiry` | `getAccountBindingBlu`, `postAccountBindingBlu` |  |
| GET | `/v1/payment/blu/account-binding/refresh` | `getCekTokenRefreshBlu` |  |
| POST | `/v1/payment/blu/account-unbinding` | `getUnBindingBlu` |  |
| POST | `/v1/payment/blu/linkage/status` | `getBluLinkage`, `postBluLinkage` |  |

### Pembayaran: AstraPay

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/payment/astrapay/account-binding` | `getAccountBindingAstra`, `postAccountBindingAstra` |  |
| GET | `/v1/payment/astrapay/account-binding/refresh` | `getCekTokenRefresh` |  |

### Pembayaran: Bayarind dan QRIS Tap

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/payment/bayarind/account-binding` | `getAccountBindingBayarind`, `postAccountBindingBayarind` |  |
| POST | `/v1/payment/bayarind/account-binding/balance` | `postBayarindBalace`, `postBayarindBalance` |  |
| GET | `/v1/payment/bayarind/account-binding/refresh` | `getCekTokenRefreshBayarind` |  |
| GET | `/v1/payment/bayarind/api/v1.0/auth-code-transaction` | `getAuthCodeTransaction` |  |
| POST | `/v1/payment/bayarind/list-transaction` | `postListTransactionBayarind` |  |
| POST | `/v1/payment/bayarind/qr-tap/auth-code` | `postQrTapAuthCode` |  |
| POST | `/v1/payment/bayarind/qr-tap/qr-generate` | `postQrGenerate` |  |
| POST | `/v1/payment/bayarind/qr/decode` | `decodeQr` |  |
| GET | `/v1/payment/bayarind/transactions/{id}` | `getTransactionDetail` |  |

### Pembayaran: umum

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| ? | `/v1/payment/{id}` | `onchangeBalance` |  |
| GET | `/v1/payment/{id}` | `getPaymentBalance` |  |
| GET | `/v1/payment/channels` | `getpaymentChannel` |  |

### Akun pengguna

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| DELETE | `/v1/user` | `deleteAccount` |  |
| PUT | `/v1/user` | `editProfile` |  |
| GET | `/v1/user/achievements` | `getAchievements` |  |
| POST | `/v1/user/achievements/trip` | `submitTripAchievement` |  |
| GET | `/v1/user/delete/reasons` | `getDeleteReasons` |  |
| POST | `/v1/user/feed/follow` | `followRoute` |  |
| GET | `/v1/user/feed/following` | `getUserFollowing` |  |
| POST | `/v1/user/feed/unfollow` | `unfollowRoute` |  |
| PATCH | `/v1/user/password` | `changePassword` |  |
| GET | `/v1/user/saved-places` | `getSavedPlaces` |  |
| POST | `/v1/user/saved-places` | `savePlace` |  |
| DELETE | `/v1/user/saved-places/{id}` | `deletePlace` |  |
| GET | `/v1/user/section` | `getSection` |  |
| ? | `/v1/user/trips` | – |  |
| GET | `/v1/user/trips/{id}` | `getTripById` |  |

### Laporan dan keluhan

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/reports/category/{id}` | `getCategories` |  |
| PATCH | `/v2/reports/cancel-report/{id}` | `cancelReport` |  |
| GET | `/v2/reports/category` | `getAllCategories` |  |
| GET | `/v2/reports/category/{id}` | `getSubCategories` |  |
| POST | `/v2/reports/create-report` | `createReport` |  |
| GET | `/v2/reports/detail/{id}` | `getDetailReport` |  |
| ? | `/v2/reports/list` | `getReportList` |  |
| GET | `/v2/reports/list` | `getReportList` |  |
| PATCH | `/v2/reports/update-location/{id}` | `updateLocation` |  |
| POST | `/v2/reports/upload-attachment` | `uploadAttachment` |  |

### Rating

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/ratings` | `postCreateRating` |  |
| GET | `/v1/ratings/categories` | `getCategories` |  |
| GET | `/v1/ratings/check-rating-user-today` | `getCheckRatingToday` |  |

### Notifikasi

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/notif/unsubscribe` | `postNotifUnSubscribe` |  |
| POST | `/v1/notification/fcm/init` | `postNotifSubscribe` |  |
| POST | `/v1/notification/fcm/subscribe-area` | `postNotifSubscribeArea` |  |

### Kampanye dan banner

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| GET | `/v1/campaign/name/feedback` | `getFeedback` |  |
| GET | `/v1/campaign/screen/{id}` | `getBannerScreen` |  |
| GET | `/v1/campaign/screen/BottomTabNavigation` | `getPopUpMainCampaign` |  |
| GET | `/v1/campaign/screen/BusDetail` | `getBusDetailCampaign` |  |
| GET | `/v1/campaign/screen/BuyTicket` | `getTicketCampaign` |  |
| GET | `/v1/campaign/screen/DetailHalte` | `getDetailHalteCampaign`, `getHalteCampaign` |  |
| GET | `/v1/campaign/screen/DetailInfoRute` | `getDetailRouteCampaign` |  |
| GET | `/v1/campaign/screen/Feed` | `getFeedCampaign` |  |
| GET | `/v1/campaign/screen/Home` | `getBannerCampaign` |  |
| GET | `/v1/campaign/screen/TripPlannerStep4` | `getTripPlannerStep4Campaign` |  |
| PATCH | `/v2/banner/mobile/clicks/{id}` | `patchBannerClick` |  |
| PATCH | `/v2/banner/mobile/views/{id}` | `patchBannerView` |  |

### Feed, loyalti, voucher, MoTer

| Method | Path | Fungsi di bundle | Status |
|---|---|---|---|
| POST | `/v1/loyalty-tije/user/mobile/me/badges` | `getBadges` |  |
| POST | `/v1/moter/points` | – |  |
| POST | `/v1/moter/refresh` | `refreshToken` |  |
| POST | `/v1/moter/url` | `getWebviewUrl` |  |
| GET | `/v1/tweet/following` | `getListFeedFollowing` |  |
| POST | `/v1/vouchers/redeem` | `redeemVoucher` |  |

## Catatan per endpoint penting

### `POST /v1/bus` (`getBusNearest`)

Body:

```json
{ "latitude": -6.195, "longitude": 106.8231, "radius": 1, "event": "change_loc" }
```

Response `data` berisi `topics` (topik MQTT), `buses`, `stops`, `polyline`, dan `session_id`. Dipakai layar peta untuk tahu topik mana yang harus di-subscribe. `GET /v1/bus` (`getAllbus`, `getNearbyBus`) adalah varian GET yang tidak dipakai backend.

### `POST /v1/bus/offline` (`getBusNearestOffline`)

Body sama dengan `POST /v1/bus`. Response `data` berupa array posisi bus lengkap (rute, warna, posisi, halte sebelum dan berikutnya, jarak). WebView peta punya fungsi `updateBusMarker(data, isOffline)`, jadi kemungkinan hasil ini digambar sebagai marker "offline" sampai data MQTT datang.

### `GET /v2/bus-stop` (`getSearchBusStopNew`, `searchBusStops`)

Query `latitude`, `longitude`, `radius`. Maksimal 20 halte (`meta.limit`). `GET /v2/bus-stop/{stop_id}` (`getHalteDetail`) memberi detail satu halte.

### `GET /v1/settings/api/config/{nama}` (`getConfigBe`)

Konfigurasi dari server. Nama yang ditemukan: `mqtt_url`, `benefit_ott`, `link_ppid`, `royal_trans_config`. Nilainya ada di `data.properties`.

### `POST /v1/direction` (`postTripPoint`)

Perencana perjalanan dari titik A ke titik B. `GET /v1/direction` (`getAllRoute`) mengambil daftar rute.

### `GET /v1/route`, `GET /v2/route/{id}`

Pencarian rute dan detail rute (halte, jadwal, polyline). `GET /v1/route-diversion` kemungkinan memberi daftar pengalihan rute yang sedang berlaku (string terkait: `{{count}} Rute terdampak`).

### Endpoint yang mengubah data atau melibatkan uang

Kelompok berikut punya efek nyata dan sebaiknya tidak dipanggil sembarangan: semua `/v1/payment/*` yang `POST`, `/v1/ticket/book/*`, `/v2/ticket/*/book`, `/v3/ticket/book`, `/v2/ticket/royal-trans/refund`, `/v2/ticket/royal-trans/reschedule`, `/v1/subscription/book-b2c/`, `/v1/vouchers/redeem`, `PUT /v1/user`, `DELETE /v1/user`, `PATCH /v1/user/password`, `/v2/reports/create-report`.
