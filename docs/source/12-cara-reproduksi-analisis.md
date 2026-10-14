# Cara mengulang analisis

Langkah-langkah ini mengulang semua temuan di folder `source/` dari file XAPK. Semuanya analisis statis: app tidak dipasang dan tidak dijalankan.

Simpan hasil ekstraksi di folder baru yang kosong, terpisah dari skrip yang dijalankan. File dari APK adalah data yang tidak dipercaya; jangan jalankan interpreter dari dalam folder itu.

## Alat yang dipakai

| Alat | Versi | Untuk |
|---|---|---|
| Python | 3.14 | Skrip bantu, androguard, hermes-dec |
| androguard | 4.1.4 | Decode manifest biner, daftar komponen |
| hermes-dec (P1sec) | dari GitHub | Decompile bytecode Hermes v96 |
| JADX (lewat MobSF) | | Decompile DEX ke Java |
| apktool (lewat MobSF) | | DEX ke smali, resource |
| REA (`rea-agents`) | 6.4.0 | CLI + MCP untuk reverse engineering; rute Android-nya butuh APK dan JADX |
| `tar` bawaan Windows | | Membuka XAPK/APK (keduanya ZIP) |
| Node.js + playwright-core | 24 / 1.58.2 | Uji UI backend di Edge headless |

## 1. Buka XAPK dan APK

```powershell
$work = "$env:TEMP\tj-analisis"
New-Item -ItemType Directory -Force "$work\xapk", "$work\base" | Out-Null
tar -xf "apk\TJ_Transjakarta_3.0.4_APKPure.xapk" -C "$work\xapk"
tar -xf "$work\xapk\com.transjakmobile.apk" -C "$work\base"
Get-Content "$work\xapk\manifest.json"
```

Cek bahwa bundle adalah Hermes:

```powershell
$b = [IO.File]::ReadAllBytes("$work\base\assets\index.android.bundle")[0..11]
($b | ForEach-Object { $_.ToString("x2") }) -join " "
# c6 1f bc 03 c1 03 19 1f 60 00 00 00   -> magic Hermes, versi 0x60 = 96
```

## 2. Decode manifest

```powershell
python -m venv "$work\agvenv"
& "$work\agvenv\Scripts\python" -m pip install androguard==4.1.4
```

Skrip `manifest.py` (simpan di luar folder kerja):

```python
import sys
from loguru import logger

logger.remove()
from androguard.core.apk import APK

a = APK(sys.argv[1])
print(
    a.get_package(),
    a.get_androidversion_name(),
    a.get_androidversion_code(),
    "min",
    a.get_min_sdk_version(),
    "target",
    a.get_target_sdk_version(),
)
print("main:", a.get_main_activity())
open(sys.argv[2], "w", encoding="utf-8").write(
    a.get_android_manifest_axml().get_xml().decode()
)
for kind, items in (
    ("activity", a.get_activities()),
    ("service", a.get_services()),
    ("receiver", a.get_receivers()),
    ("provider", a.get_providers()),
):
    print(f"[{kind}] {len(items)}")
    [print("  ", i) for i in items]
```

```powershell
& "$work\agvenv\Scripts\python" -I manifest.py "$work\xapk\com.transjakmobile.apk" "$work\AndroidManifest.xml"
```

## 3. Decompile bundle Hermes

```powershell
git clone --depth 1 https://github.com/P1sec/hermes-dec.git "$work\hermes-dec"
$env:PYTHONPATH = "$work\hermes-dec\src"
python -I -c "import sys; sys.path.insert(0, r'$work\hermes-dec\src'); from hermes_dec.decompilation.hbc_decompiler import main; sys.argv=['x', r'$work\base\assets\index.android.bundle', r'$work\bundle.decomp.js']; main()"
```

Butuh beberapa menit. Hasilnya pseudo-JavaScript ±79 MB.

Tabel string (satu string per baris) lebih enak untuk pencarian awal:

```python
# dumpstr.py
import sys

sys.path.insert(0, sys.argv[1])
from hermes_dec.parsers.hbc_file_parser import HBCReader

r = HBCReader()
with open(sys.argv[2], "rb") as f:
    r.read_whole_file(f)
with open(sys.argv[3], "w", encoding="utf-8", errors="backslashreplace") as o:
    for i, s in enumerate(r.strings):
        o.write(f"{i}\t{s!r}\n" if "\n" in s else f"{i}\t{s}\n")
print(len(r.strings))  # 73034
```

### Pencarian yang berguna

| Mencari | Pola |
|---|---|
| Semua path API | `'/v[0-9]/[^']*'` di `bundle.decomp.js`, atau `^\d+\t/v[0-9]/` di tabel string |
| Definisi layanan | `{'method': '...', 'url': '...'}` |
| Nama fungsi asli | `Original name: ` |
| Header request | `'X-App-Version'` |
| Konfigurasi MQTT | `mqttConfigStore`, `'/mqtt_url'`, `fetchDataAndConnectMQTT` |
| Login | `'/v1/auth/login'`, `useLoginEmail`, `useLoginGuest` |
| Pesan WebView | `message.name === '` |

Membuat katalog endpoint otomatis (dipakai untuk [07-katalog-api-upstream.md](07-katalog-api-upstream.md)):

```python
# catalog.py
import re, sys, collections

lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().split("\n")
name_re = re.compile(r"Original name: ([A-Za-z0-9_$]+)")
path_re = re.compile(r"'(/v\d+/[A-Za-z0-9_\-/{}.:]*)'")
svc_re = re.compile(r"\{'method': '([a-z]+)', 'url': '(/v\d+/[^']*)'")
meth_re = re.compile(r"= r\d+\.(get|post|put|patch|delete);")
out = collections.OrderedDict()
for i, line in enumerate(lines):
    m = svc_re.search(line)
    if m:
        nm = next(
            (
                name_re.search(lines[j]).group(1)
                for j in range(i, max(0, i - 40), -1)
                if name_re.search(lines[j])
            ),
            "?",
        )
        out.setdefault((m.group(2), m.group(1).upper()), set()).add(nm)
        continue
    m = path_re.search(line)
    if not m:
        continue
    meth = None
    for j in range(max(0, i - 6), min(len(lines), i + 3)):
        mm = meth_re.search(lines[j])
        if mm:
            meth = mm.group(1).upper()
    nm = next(
        (
            name_re.search(lines[j]).group(1)
            for j in range(i, min(len(lines), i + 40))
            if name_re.search(lines[j])
            and not name_re.search(lines[j]).group(1).startswith("?")
        ),
        "?",
    )
    out.setdefault((m.group(1), meth or "?"), set()).add(nm)
for (p, meth), names in sorted(out.items()):
    print(f"{meth}\t{p}\t{','.join(sorted(names))}")
```

## 4. Kode Java dan smali

Hasil JADX dan apktool di proyek ini dibuat MobSF di Linux (`/home/mobsf/.MobSF/uploads/c4e872d79c1110323c849349bbbf4845/`), lalu disalin ke Windows. Akibatnya:

- **smali**: kelas yang namanya hanya beda huruf besar-kecil saling menimpa. Contoh: `La7/a` (service) hilang, tertimpa `LA7/a`.
- **JADX**: kelas bentrok diberi nama baru, misalnya `A7/AbstractServiceC0176a.java` dengan komentar `renamed from: a7.a`.

Untuk hasil lengkap, decompile ulang di WSL atau Linux:

```bash
apktool d com.transjakmobile.apk -o smali_out
jadx -d java_out com.transjakmobile.apk
```

Mencari kelas di smali yang tidak bisa dipercaya path-nya:

```powershell
# cari berdasarkan direktif .class, bukan nama file
rg "^\.class .*La7/a;" .
rg "\.super Lcom/facebook/react/HeadlessJsTaskService;" .
```

## 5. Memakai REA

REA sudah dipasang global dan terdaftar sebagai MCP server di Claude Code. Untuk target ini:

- Rute Android (`inspect_android_package`, `search_android_classes`, `inspect_android_method`, `trace_android_references`) butuh path APK dan JAR JADX MCP 0.7.1 + Java 17 (`REA_JADX_MCP_JAR`).
- Rute arsip (`open_binary` + `inspect_artifact`) bisa dipakai langsung untuk inventaris isi APK.
- Status pemasangan: `rea doctor --client claude_code --skill`.

## 6. Mencoba endpoint ke server asli

Gunakan seperlunya dan hanya endpoint baca. Contoh dengan PowerShell:

```powershell
$h = @{ "X-App-Version"="3.0.4"; "X-App-OS"="android"; "X-Device-ID"="0123456789abcdef"; "Content-Type"="application/json" }
$g = Invoke-RestMethod -Method Post -Uri https://tijeapi.transjakarta.co.id/v1/auth/login/guest -Headers $h -Body "{}"
$h["Authorization"] = "Bearer $($g.token)"
$body = '{"latitude":-6.195,"longitude":106.8231,"radius":1,"event":"change_loc"}'
Invoke-RestMethod -Method Post -Uri https://tijeapi.transjakarta.co.id/v1/bus/offline -Headers $h -Body $body |
  Select-Object -ExpandProperty data | Select-Object -First 3 bus_body_no, route_code, next_stops
```

Cek jangkauan broker:

```powershell
Resolve-DnsName mqtt.tj.co.id
Test-NetConnection mqtt.tj.co.id -Port 8084
```

## 7. Bukti yang dipakai di dokumentasi

| Klaim | Bukti |
|---|---|
| Endpoint dan body `POST /v1/bus` | `bundle.decomp.js` sekitar baris 1.209.988 (`altenativePayload` dengan `event: 'change_loc'`) |
| Topik dikirim ke WebView | sekitar baris 1.209.540 (`name: 'session'`, `value: res.data.topics`) |
| `mqtt_url` dari `getConfigBe` + `/mqtt_url` | sekitar baris 1.160.552–1.160.660 |
| Header request | sekitar baris 1.192.580 (`'X-App-Version'` dst.) |
| Login guest | sekitar baris 1.227.255 (`/v1/auth/login/guest`), 2.003.900 (layar) |
| Login email | sekitar baris 1.227.078 dan 1.979.253 |
| Refresh token | sekitar baris 1.113.887 (`axios.post(getBaseUrl() + '/v1/auth/token/refresh')`) |
| HTML peta + MQTT | tabel string, potongan `fetchDataAndConnectMQTT` |
| Native module | hasil JADX `com/transjakmobile/*.java` |
| Manifest | androguard, `AndroidManifest.xml` hasil decode |

Nomor baris berlaku untuk hasil decompile hermes-dec versi saat analisis dan bisa bergeser di versi lain.
