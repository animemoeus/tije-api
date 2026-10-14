# Autentikasi di app

Semua fungsi login ada di `authService` dan dipanggil lewat `apiClient.post(path, body, { skipAuth: true })`, jadi request login tidak membawa header `Authorization`. Hook React Query yang membungkusnya: `useLoginEmail`, `useLoginGoogle`, `useLoginApple`, `useLoginGuest`, `useCheckPhone`, `useRegister`, `useForgotPassword`, `useForgotPasswordVerify`, `useResetPassword`.

## Daftar endpoint

| Fungsi | Method | Path | Body (dari kode) | Status |
|---|---|---|---|---|
| `guestLogin` | POST | `/v1/auth/login/guest` | `{}` | terverifikasi |
| `login` | POST | `/v1/auth/login` | `{ email, password }` | dari kode |
| `googleLogin` | POST | `/v1/auth/google-login` | token dari Google Sign-In | dari kode |
| `appleLogin` | POST | `/v1/auth/apple-login` | token dari Apple Sign-In | dari kode |
| `checkPhone` | POST | `/v1/auth/check/phone` | nomor telepon | dari kode |
| `register`, `postRegister` | POST | `/v1/auth/register` | data pendaftaran | dari kode |
| `forgotPassword` | POST | `/v1/auth/forget-password` | email | dari kode |
| `forgotPasswordVerify` | POST | `/v1/auth/forget-password/verify` | kode verifikasi | dari kode |
| `resetPassword` | POST | `/v1/auth/forget-password/new-password` | password baru | dari kode |
| `checkOldPassword` | POST | `/v1/auth/password/check` | password lama | dari kode |
| `logout` | POST | `/v1/auth/logout` | | dari kode |
| refresh otomatis | POST | `/v1/auth/token/refresh` | `{ refresh_token }` | dari kode |
| `changePassword` | PATCH | `/v1/user/password` | | dari kode |

Isi body untuk Google, Apple, register, dan lupa password tidak ditelusuri satu per satu. Nama field-nya bisa dilihat di sekitar pemanggilan `mutateAsync` masing-masing layar.

## Login guest

Dipakai saat pengguna menekan "lewati" di layar login. Potongan kode di halaman ini direkonstruksi dari hasil decompile Hermes. Alurnya sama dengan aslinya, tetapi nama variabel lokal dibuat ulang karena hasil decompile hanya berisi register (`r1`, `r2`, …):

```js
const guest = useLoginGuest();

async function onSkip() {
  const res = await guest.mutateAsync();                  // POST /v1/auth/login/guest {}
  analytics({ title: "login_guest", data: { response_code: "200" } });
  setUser({
    token: res.token,
    tokenReferesh: res.refresh_token,
    token_valid_until: res.token_valid_until,
    user: { ...res.user },
    moter: res.moter,
  });
  saveSession(JSON.stringify(stripTokensFromSessionPayload(session)));
  // lalu pindah ke layar utama
}
```

Request dan response asli:

```http
POST /v1/auth/login/guest HTTP/1.1
Host: tijeapi.transjakarta.co.id
Content-Type: application/json
Accept: application/json
X-App-Version: 3.0.4
X-Device-ID: <id perangkat>
X-Lang: id
X-FCM-Token: <token FCM>
X-App-OS: android
X-App-OS-Version: 14
X-App-Platform: 34
X-Device-Model: Google|Pixel 8

{}
```

```json
{
  "user": {
    "email": "<disamarkan>",
    "phone": "",
    "name": "<disamarkan>",
    "avatar": "",
    "have_password": false,
    "is_verified": false,
    "is_guest": true,
    "id": 0
  },
  "token": "<272 karakter>",
  "token_valid_until": 1791987416,
  "refresh_token": "<272 karakter>",
  "refresh_token_valid_until": 1791991016,
  "moter": null
}
```

Server membuatkan identitas guest dengan email dan nama acak (`is_guest: true`, `id: 0`). Masa berlaku token sekitar 24 jam, refresh token satu jam lebih lama.

## Login email dan password

```js
const login = useLoginEmail();

async function onSubmit() {
  if (!isValidEmail(form.email)) errors.email = t("Invalid email format");
  if (!form.password)            errors.password = t("Please enter your password");
  if (hasErrors) return;

  const res = await login.mutateAsync({ email: form.email, password: form.password });
  analytics({ title: "login_attempt", data: { response_code: "200", email: form.email } });
  toast.show({ type: "success2", position: "top", text1: t("Login Successful") });
  await onLoginSuccess(res);
}
```

```http
POST /v1/auth/login HTTP/1.1
Host: tijeapi.transjakarta.co.id
Content-Type: application/json
...

{"email": "nama@contoh.com", "password": "rahasia"}
```

Password dikirim sebagai teks biasa di dalam HTTPS. Tidak ada hashing atau enkripsi di sisi client. Response diproses oleh `onLoginSuccess` dengan pola yang sama seperti guest (`token`, `refresh_token`, `token_valid_until`, `user`, `moter`).

Email ikut dikirim ke analitik (`login_attempt`), jadi email pengguna sampai ke Firebase Analytics.

## Menyimpan token

Store user menyimpan field berikut dan mem-persist-nya ke AsyncStorage:

| Field | Isi |
|---|---|
| `token` | Access token |
| `tokenReferesh` | Refresh token (ejaan asli) |
| `token_valid_until` | Unix detik |
| `tokenPaymentBlu` | Token terpisah untuk SDK blu |
| `moter` | Data program MoTer |
| `user` | Profil |

`stripTokensFromSessionPayload` membuang token dari objek sesi sebelum disimpan sebagai string terpisah.

## Memakai token

Setiap request dari pembuat request utama:

1. membaca `userStore.getState().user`;
2. membandingkan `token_valid_until` dengan `getUnixNow()`;
3. kalau masih berlaku, memasang `Authorization: Bearer <token>`;
4. kalau tidak, atau kalau refresh sedang berjalan, masuk ke jalur refresh.

## Refresh token

Kode refresh memanggil axios secara langsung (bukan lewat `apiClient`) dengan header lengkap:

```js
axios.post(getBaseUrl() + "/v1/auth/token/refresh",
  { refresh_token: user.tokenReferesh },
  { headers: {
      "X-Device-ID": deviceId, "X-Lang": lang, "X-FCM-Token": fcm,
      "X-App-Version": version, "X-App-OS": os, "X-App-OS-Version": osVersion,
      "X-App-Platform": platform, "X-Device-Model": brand + "|" + model,
  } });
```

Response refresh belum dicoba ke server asli. Backend menerima token di tingkat atas maupun di dalam `data`.

## Response tanpa token

Semua endpoint selain yang `skipAuth` menolak request tanpa token:

```http
POST /v1/bus HTTP/1.1
Content-Type: application/json

{"latitude": -6.195, "longitude": 106.8231, "radius": 1, "event": "change_loc"}
```

```json
{
  "code": 401,
  "message": "Unauthorized, token is required",
  "data": { "type": "PopUp" }
}
```

`data.type: "PopUp"` kemungkinan memberi tahu app agar menampilkan dialog, bukan toast.

## Google dan Apple

- Google: `@react-native-google-signin/google-signin` dengan `GOOGLE_WEB_CLIENT_ID` (`719437284096-eigp7svs…`). Token ID dari Google dikirim ke `/v1/auth/google-login`.
- Apple: `@invertase/react-native-apple-authentication`, ke `/v1/auth/apple-login`.

Akun yang dibuat lewat Google atau Apple bisa jadi tidak punya password (`have_password: false`), sehingga tidak bisa login lewat `/v1/auth/login`.
