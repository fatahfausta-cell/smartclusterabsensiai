# Sistem Absensi Wajah (Face Recognition + Anti-Foto)

Aplikasi absensi berbasis pengenalan wajah dengan **liveness detection anti-foto**:
peserta cukup menghadap kamera, sistem memverifikasi wajah **asli** (bukan foto),
lalu mencocokkannya dengan foto referensi yang **diunggah admin**, dan mencatat
kehadiran otomatis. Rekap dapat diekspor ke **Excel (.xlsx)**.

## Fitur

| Fitur | Keterangan |
|---|---|
| Halaman absensi publik | Hanya kamera + instruksi — tanpa login peserta; tombol **Absen Datang** & **Absen Pulang** |
| Anti-foto (liveness) | Tantangan acak terverifikasi **di server**: selalu KEDIP + 1 dari {toleh kiri/kanan, senyum, angguk}; frame statis ditolak sejak tahap baseline |
| Pengenalan wajah | YuNet (deteksi + fallback upscale utk wajah jauh) + ArcFace/MobileFaceNet 512-d (ONNX, CPU), cosine similarity; frame gelap diterangi CLAHE otomatis utk landmark |
| Verifikasi identitas | Minimal 2 dari 3 frame terbaik harus cocok ke peserta yang sama |
| Absen datang & pulang | 1x datang + 1x pulang per hari; pulang wajib setelah datang |
| Jam datang & pulang diatur admin | Tab ⚙️ Pengaturan (default 08:00 / 17:00) → status `Hadir`/`Terlambat` & `Tepat Waktu`/`Pulang Cepat` |
| Panel admin | Kelola peserta + foto (upload / ambil dari webcam), nonaktifkan, rekap, hapus |
| Ekspor Excel | 2 sheet: *Rekap Absensi* (detail datang+pulang + bukti foto) & *Ringkasan* per peserta |
| Bukti audit | Snapshot frame tersimpan otomatis tiap absen datang & pulang |

## Cara Kerja Anti-Foto

1. Browser hanya **terminal**: menampilkan instruksi dan mengirim frame JPEG ±7 fps.
   Semua keputusan (deteksi wajah, liveness, identitas) dihitung **di server**.
2. Server menetapkan **tantangan acak** per sesi. Foto cetak/layar **tidak mungkin**
   lolos karena tidak dapat mengedipkan mata (transisi EAR terbuka→tertutup→terbuka
   dari 478 landmark wajah).
3. **Baseline adaptif** per sesi + deteksi variasi sinyal: barisan frame yang identik
   (foto statis) ditolak sebelum masuk tantangan.
4. Identitas diambil dari ≥3 frame berbeda; snapshot tersimpan sebagai bukti.

> Limitasi yang disadari: video *replay* yang kebetulan mengandung gerakan kedip
> secara teoretis bisa lolos challenge; mitigasi penuh memerlukan kamera depth/IR.

## Menjalankan di Komputer Lokal

```bash
cd sistem-absensi-wajah
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows (Linux/Mac: .venv/bin/pip)
.venv/Scripts/python app.py
```

Buka **http://localhost:5050** (halaman absensi) dan **http://localhost:5050/login**
(admin). Login default: `admin` / `admin123` — **segera ganti** di tab Pengaturan.

Catatan kamera: browser hanya mengizinkan akses kamera via `localhost` atau HTTPS.

## Deploy ke IDCloudHost (VPS Ubuntu)

> Aplikasi ini bukan PHP, jadi **jangan** pakai shared hosting cPanel — gunakan
> produk **Compute/VPS** IDCloudHost.

### 1. Buat VPS di portal IDCloudHost
- Pilih **Compute**, OS **Ubuntu 24.04 LTS**, lokasi **Jakarta**.
- Spek minimum: **2 vCPU / 2 GB RAM** (4 GB lebih nyaman). Storage 20 GB cukup.
- Set password root / SSH key, tunggu VM aktif, catat **IP publik**.
- Pastikan port **22, 80, 443** terbuka (firewall di portal IDCloudHost).

### 2. Unggah proyek dari komputer ini (Git Bash / terminal)
```bash
cd "/c/Users/MSI Modern 15/.zcode/workspace/default"
tar --exclude=sistem-absensi-wajah/.venv --exclude=sistem-absensi-wajah/data -czf absensi.tgz sistem-absensi-wajah
scp absensi.tgz root@IP_VPS:/opt/
ssh root@IP_VPS "mkdir -p /opt/absensi && tar xzf /opt/absensi.tgz -C /opt/absensi --strip-components=1"
```

### 3. Jalankan skrip setup (sekali saja)
```bash
ssh root@IP_VPS
cd /opt/absensi
bash deploy/setup_vps.sh
```
Skrip memasang Python + nginx, membuat virtualenv, mengunduh model bila belum ada,
memasang layanan `systemd` (auto-start saat boot), dan reverse proxy nginx ke
`127.0.0.1:5050`.

### 4. Pasang HTTPS (WAJIB agar kamera bisa diakses)
Browser memblokir `getUserMedia` di HTTP non-localhost, maka sertifikat SSL wajib.

**Punya domain** (arahkan A-record ke IP VPS):
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d absensi.domainanda.com
```

**Tidak punya domain** — pakai nama gratis berbasis IP (sslip.io):
```bash
certbot --nginx -d 103-27-206-10.sslip.io   # ganti sesuai IP VPS Anda (titik jadi strip)
```

### 5. Selesai
Buka `https://domain-anda/` → login admin → tambah peserta + foto → peserta
tinggal absen dari HP/laptop (Chrome/Edge/Safari) menghadap kamera.

### Alternatif: Unggah dengan FileZilla Client

FileZilla hanya untuk **memindahkan file** (SFTP); perintah setup tetap lewat SSH.

1. **Buka FileZilla** → kolom kiri atas (Quickconnect) isi:
   - Host: `sftp://IP_VPS_ANDA`
   - Username: `root`
   - Password: password root VPS
   - Port: `22` → klik **Quickconnect** → klik **OK** saat muncul peringatan host key.
2. **Panel kiri** (komputer Anda): masuk ke folder
   `C:\Users\MSI Modern 15\.zcode\workspace\default\sistem-absensi-wajah`.
3. **Panel kanan** (VPS): masuk ke `/opt` → klik kanan → *Create directory* → beri nama `absensi` → masuk ke dalamnya.
4. **Unggah** (drag & drop kiri → kanan) HANYA item berikut:
   `app.py`, `config.py`, `db.py`, `face_engine.py`, `liveness.py`,
   `excel_report.py`, `serve.py`, `requirements.txt`, folder `models/`,
   `templates/`, `static/`, `deploy/`.
   **Jangan** unggah folder `.venv` (besar & tidak berguna) dan `data/`
   (berisi database uji lokal — server akan membuat yang baru otomatis).
5. Lanjutkan ke tahap 3 (setup) di atas melalui SSH.

Troubleshooting FileZilla: gagal connect biasanya karena port/IP salah,
port 22 tertutup di firewall portal IDCloudHost, atau lupa prefix
`sftp://` (tanpa itu FileZilla mencoba FTP biasa dan gagal).

### Perintah operasional
```bash
systemctl status|restart|stop absensi   # kelola layanan
journalctl -u absensi -f                # lihat log aplikasi
```
Backup rutin folder `/opt/absensi/data/` (database SQLite + foto + snapshot).

## Konfigurasi

Jam datang & jam pulang diatur lewat **Admin → ⚙️ Pengaturan** (tersimpan di DB,
berlaku langsung). Parameter teknis lain di `config.py`: `FACE_MATCH_THRESHOLD`
(0.45), jumlah frame verifikasi, timeout tantangan, ambang kualitas frame,
port (`ABS_PORT`), host (`ABS_HOST`).

## Struktur Proyek

```
app.py            # Routing Flask + mesin sesi absensi (liveness → identitas → catat)
config.py         # Seluruh ambang/konfigurasi
db.py             # SQLite (users, photos+embedding, attendance, admin)
face_engine.py    # YuNet + ArcFace ONNX + MediaPipe FaceLandmarker
liveness.py       # Sinyal wajah (EAR/yaw/senyum) + mesin status tantangan
excel_report.py   # Rekap .xlsx (openpyxl)
serve.py          # Entry produksi (waitress, 1 proses multi-thread)
deploy/           # setup_vps.sh, nginx config
templates/static  # UI (kiosk absensi, login, panel admin)
tests/            # test_engine.py, test_liveness.py, test_session.py
```

## Hasil Pengujian (ringkas)

- Identitas: orang sama 0.728 vs orang berbeda −0.030 (ambang 0.45) — lolos.
- Liveness: frame identik (foto) **tertahan**; kedip/toleh lolos; tanpa kedip tertahan.
- Integrasi: unggah foto admin, **absensi dengan foto statis DITOLAK**, absensi
  wajah hidup SUKSES (skor 0.725), duplikat harian ditolak, orang asing ditolak,
  snapshot tersimpan, Excel berisi catatan — semua lolos.
- GUI: login salah/benar, dashboard, tabel peserta, halaman kiosk + kamera aktif.
