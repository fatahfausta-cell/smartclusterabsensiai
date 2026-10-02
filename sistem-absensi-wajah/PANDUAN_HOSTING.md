# 📗 Panduan Hosting Lengkap — IDCloudHost

Panduan ini ditulis untuk pemula total: dari membuat VPS sampai aplikasi absensi
online dengan HTTPS. Setiap tahap dilengkapi **✅ tanda berhasil** dan
**⚠️ ANTISIPASI ERROR** beserta solusinya.

> IP contoh di panduan ini: `103.187.147.64` — ganti dengan IP VPS Anda sendiri.

---

## Daftar Isi

1. [Konsep Dasar (baca dulu, 1 menit)](#1-konsep-dasar)
2. [Tahap 1 — Membuat VPS di IDCloudHost](#2-tahap-1--membuat-vps-di-idcloudhost)
3. [Tahap 2 — Menghubungkan FileZilla ke VPS](#3-tahap-2--menghubungkan-filezilla-ke-vps)
4. [Tahap 3 — Meng-upload File Aplikasi](#4-tahap-3--meng-upload-file-aplikasi)
5. [Tahap 4 — Masuk ke VPS via SSH](#5-tahap-4--masuk-ke-vps-via-ssh)
6. [Tahap 5 — Menjalankan Setup Otomatis](#6-tahap-5--menjalankan-setup-otomatis)
7. [Tahap 6 — Memasang HTTPS (WAJIB)](#7-tahap-6--memasang-https-wajib)
8. [Tahap 7 — Verifikasi & Pemakaian](#8-tahap-7--verifikasi--pemakaian)
9. [Pemeliharaan Harian/Mingguan](#9-pemeliharaan)
10. [Tabel Ringkas Semua Error & Solusi](#10-tabel-ringkas-error--solusi)

---

## 1. Konsep Dasar

- Aplikasi ini berbasis **Python**, bukan PHP → **tidak bisa** di-host di shared
  hosting/cPanel biasa. Gunakan produk **Compute (VPS)** IDCloudHost.
- Alur deployment: **FileZilla** (upload file) → **SSH/terminal** (jalankan setup)
  → **certbot** (HTTPS). FileZilla tidak bisa menjalankan perintah Linux, jadi
  terminal tetap wajib dipakai sebentar.
- **HTTPS itu WAJIB**, bukan pelengkap: browser (Chrome/Edge/Safari) hanya
  mengizinkan akses kamera pada alamat `https://` atau `http://localhost`.
  Tanpa HTTPS, halaman absensi tidak bisa membuka kamera.

### Spek VPS yang disarankan
| Kebutuhan | Minimum | Nyaman |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB | 40 GB |
| OS | Ubuntu 24.04 LTS | sama |

RAM 2 GB cukup karena semua model AI berjalan di CPU dengan ukuran kecil
(YuNet 0.2 MB + ArcFace 13 MB + FaceLandmarker 3.7 MB).

---

## 2. TAHAP 1 — Membuat VPS di IDCloudHost

1. Login di **https://console.idcloudhost.com** (akun yang Anda beli/dapat).
2. Klik **Compute** → **Create New** / **Buat VM Baru**.
3. Isi form:
   - **Location**: Jakarta (bebas, tapi Jakarta paling rendah latensi untuk Indonesia)
   - **OS / Image**: **Ubuntu 24.04 LTS** (64-bit)
   - **Size / Flavor**: 2 vCPU / 2 GB RAM ke atas
   - **Hostname**: `absensi` (nama bebas)
   - **Password**: buat password root yang KUAT → **catat di tempat aman**,
     ini yang dipakai untuk FileZilla & SSH nanti.
4. Klik **Create / Deploy**, tunggu ±1–2 menit sampai status **Active**.
5. Catat **IP publik** yang muncul di kartu VM Anda.
6. Cek **firewall** (menu Network/Firewall/Security Group di VM):
   pastikan port **22 (SSH), 80 (HTTP), 443 (HTTPS)** terbuka (allow/inbound).
   Bila tidak ada aturan firewall sama sekali → semua port terbuka default,
   aman-aman saja untuk pemula.

### ✅ Tanda berhasil
Status VM **Active**, dan dari komputer Windows Anda (buka CMD → ketik):
```
ping 103.187.147.64
```
membalas `Reply from 103.187.147.64: bytes=32 time=xxms`.

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| Ping `Request timed out` | VM mati / IP salah / ICMP diblokir firewall | Cek status VM Active; cocokkan IP; coba buka aturan ICMP/ping di firewall portal. Port 22 tetap bisa terbuka meski ping diblokir — tes dengan `ssh root@IP` |
| Tidak bisa login portal | lupa password akun IDCloudHost | Gunakan fitur *Forgot Password* di halaman login |
| VM terhapus tiba-tiba | Paket trial / belum bayar | Cek tagihan & masa aktif di billing |
| Kapasitas penuh saat create | kuota region habis | Pilih lokasi lain (mis. SG/JKT alternatif) atau naikkan kuota di billing |

---

## 3. TAHAP 2 — Menghubungkan FileZilla ke VPS

1. Install **FileZilla Client** (gratis) dari https://filezilla-project.org
   → saat install, **tolak** penawaran software tambahan (WinZip dll).
2. Buka FileZilla. Di bar **Quickconnect** paling atas isi:

   | Kolom | Isi |
   |---|---|
   | Host | `sftp://103.187.147.64` ← awalan `sftp://` WAJIB |
   | Username | `root` |
   | Password | password root VPS |
   | Port | `22` |

3. Klik **Quickconnect**.
4. Dialog *"Unknown host key… changed/additional key"* → klik **OK**
   (centang *Always trust* boleh).

### ✅ Tanda berhasil
Panel kanan menampilkan folder Linux: `bin  boot  etc  opt  root  usr  var …`

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| `ECONNREFUSED` / koneksi ditolak | Lupa prefix `sftp://` (FileZilla mencoba FTP port 21) | Tulis ulang host lengkap dengan `sftp://` dan port 22 |
| `Connection timed out` | Port 22 tertutup / IP salah / VM mati | Cek firewall portal (buka 22), status VM Active, dan kebenaran IP |
| `Authentication failed` | Password root salah | Reset password root di portal IDCloudHost (kartu VM → Reset Password), tunggu ±1 menit, coba lagi |
| `Host key verification failed` / key mismatch | VPS pernah dibuat ulang dengan IP sama | Hapus entri lama: buka File → Site Manager → hapus situs; atau edit `C:\Users\<user>\.ssh\known_hosts` |
| Transfer lambat/putus | Koneksi internet tidak stabil | Klik kanan file gagal di antrean → **Resume**; file kecil, aman diulang |

---

## 4. TAHAP 3 — Meng-upload File Aplikasi

**Panel KIRI** (komputer Anda):
1. Di kolom alamat panel kiri ketik lokasi proyek, contoh:
   `C:\Users\MSI Modern 15\.zcode\workspace\default\sistem-absensi-wajah` → Enter.

**Panel KANAN** (VPS):
1. Masuk ke folder `/opt` (klik dua kali).
2. Klik kanan area kosong → **Create directory** → ketik `absensi` → OK.
3. Masuk ke folder `absensi` itu.

**Drag & drop dari KIRI ke KANAN, hanya 12 item ini:**

| ✅ Upload | ❌ JANGAN |
|---|---|
| `app.py` | `.venv` (ratusan MB, tak berguna di Linux) |
| `config.py` | `data` (DB uji lokal; server buat sendiri) |
| `db.py` | `__pycache__` |
| `face_engine.py` | `tests` |
| `liveness.py` | `PANDUAN_HOSTING.md`* |
| `excel_report.py` | |
| `serve.py` | |
| `requirements.txt` | |
| folder `deploy` | |
| folder `models` (±17 MB, terbesar) | |
| folder `templates` | |
| folder `static` | |

\* opsional boleh ikut, tidak berpengaruh.

Tunggu antrean transfer (bawah) sampai **kosong**.

### ✅ Tanda berhasil
Panel kanan (`/opt/absensi`) berisi 12 item tersebut; antrean transfer kosong.

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| `550 Permission denied` | Anda sedang berada di folder sistem (mis. `/etc`) | Upload hanya ke dalam `/opt/absensi` yang Anda buat sendiri |
| Folder `models` gagal sebagian | Koneksi putus | Klik kanan → Resume/Overwrite; atau hapus folder setengah-jadi di kanan lalu ulangi |
| `421 Too many connections` | Terlalu banyak tab transfer paralel | Edit → Settings → Connections → batasi "Maximum simultaneous transfers" ke 2, coba lagi |
| Tidak yakin file lengkap | — | Di terminal SSH nanti jalankan `ls /opt/absensi` — harus terlihat 12 item |

---

## 5. TAHAP 4 — Masuk ke VPS via SSH

1. Tekan **Windows** → ketik `cmd` → Enter.
2. Ketik:
   ```
   ssh root@103.187.147.64
   ```
3. Pertama kali: `"Are you sure you want to continue connecting?"` → ketik `yes` → Enter.
4. `password:` → **ketik password root**.
   ⚠️ Saat mengetik password, **layar tidak menampilkan apa pun** (tanpa bintang)
   — itu normal, teruskan mengetik lalu Enter.

### ✅ Tanda berhasil
Prompt berubah menjadi seperti: `root@absensi:~#`

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| `'ssh’ is not recognized` | Windows lama tanpa OpenSSH | Settings → Apps → Optional Features → Add "OpenSSH Client"; atau pakai **PuTTY** |
| `Connection refused/timed out` | Port 22 tertutup / VM mati | Sama seperti antisipasi FileZilla di atas |
| `Permission denied, please try again` | Password salah (3x) | Ketik ulang perlahan; atau reset password di portal |
| `REMOTE HOST IDENTIFICATION HAS CHANGED!` | VPS dibuat ulang, IP dipakai ulang | Jalankan: `ssh-keygen -R 103.187.147.64` lalu `ssh` lagi → `yes` |
| Layar "menggantung" diam | Koneksi SSH idle | Ketik `exit`, buka koneksi baru (pekerjaan server tidak terpengaruh) |

> 💡 Alternatif tanpa CMD: **Console/VNC** di portal IDCloudHost (tombol pada
> kartu VM) — layar hitam VPS langsung di browser, login `root` + password.

---

## 6. TAHAP 5 — Menjalankan Setup Otomatis

Di layar SSH (`root@...#`) ketik satu-satu:

```
cd /opt/absensi
ls
```
Pastikan `ls` menampilkan 12 item upload. Lanjut:

```
bash deploy/setup_vps.sh
```
Atau bila punya domain sendiri (A-record sudah mengarah ke IP VPS):
```
bash deploy/setup_vps.sh absensi.domainanda.com
```

Skrip berjalan **5–15 menit**, memasang: Python+nginx, virtualenv, semua
library, model AI (diunduh bila kurang), layanan `systemd` bernama `absensi`
(auto-start saat boot, auto-restart bila crash), dan reverse proxy nginx.
Versi terbaru skrip ini juga **otomatis mengisi `server_name`** dengan
`IP-ANDA.sslip.io` (atau domain Anda) sehingga tahap SSL berikutnya mulus.

### ✅ Tanda berhasil
Di akhir output tercetak kotak **`========== SELESAI ==========`**.
Cek layanan: `systemctl status absensi` → **`active (running)`** hijau.
Dari browser buka `http://103.187.147.64/` → halaman Absensi Wajah tampil.

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| `bash: deploy/setup_vps.sh: No such file or directory` | Folder deploy tak ter-upload / salah lokasi | `ls /opt/absensi` — pastikan folder `deploy` ada; ulangi upload tahap 3 |
| `E: Unable to locate package` / apt error | `apt update` bermasalah (DNS) | `echo "nameserver 8.8.8.8" > /etc/resolv.conf` lalu jalankan ulang skrip |
| `curl: (6) Could not resolve host` | DNS VPS bermasalah | Sama seperti di atas; coba `ping 8.8.8.8` (harus balas) |
| Gagal unduh model (github/googleapis lambat) | Koneksi VPS ke luar tersendat | Skrip aman diulang; atau unduh `*.onnx`/`*.task` dari komputer lalu upload via FileZilla ke `/opt/absensi/models/` |
| `pip` error `externally-managed-environment` | Memakai Python sistem | Tidak akan terjadi (skrip pakai venv); bila terjadi pastikan menjalankan skrip utuh, bukan potongan |
| `systemctl status absensi` → `failed` | Python error saat start | Lihat log: `journalctl -u absensi -n 50 --no-pager`; umumnya file upload kurang — bandingkan dengan `ls` |
| Port 80 dipakai (`nginx: [emerg] bind() failed`) | Ada web server lain (apache) | `systemctl disable --now apache2` lalu `systemctl restart nginx` |
| `http://IP/` tidak bisa diakses | Firewall port 80 tertutup | Buka port 80 & 443 di firewall portal IDCloudHost |
| Skrip berhenti di tengah (apapun alasannya) | Networking sementara | Cukup jalankan ulang `bash deploy/setup_vps.sh` — skrip idempoten (aman diulang) |

---

## 7. TAHAP 6 — Memasang HTTPS (WAJIB)

> Tanpa HTTPS, browser menolak akses kamera: aplikasi tampil tetapi tombol
> Mulai Absen akan menampilkan peringatan kamera.

Di SSH ketik:

```
apt install -y certbot python3-certbot-nginx
certbot --nginx -d 103-187-147-64.sslip.io
```
*(IP Anda, titik diganti strip. Bila pakai domain sendiri, ganti dengan domain itu.)*

Jawab pertanyaan interaktif:
1. `Enter email address` → email Anda.
2. Terms of Service `(Y/n)` → `Y`.
3. Share email EFF `(Y/n)` → `N`.
4. Redirect HTTP→HTTPS, pilih `1` atau `2` → pilih **`2`** (lebih aman).

### ✅ Tanda berhasil
`Successfully deployed certificate for 103-187-147-64.sslip.io`
Buka `https://103-187-147-64.sslip.io/` → ikon 🔒 muncul, tanpa peringatan.

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| **`Could not automatically find a matching server block`** | `server_name` di nginx masih `_` (versi skrip lama) | (1) `sed -i 's/server_name _;/server_name 103-187-147-64.sslip.io;/' /etc/nginx/sites-available/absensi` (2) `nginx -t && systemctl reload nginx` (3) `certbot install --nginx --cert-name 103-187-147-64.sslip.io` → pilih reinstall jika ditanya. Versi `setup_vps.sh` terbaru sudah otomatis mencegah ini |
| `Failed authorization … invalid response` / challenge gagal | Domain tidak mengarah ke IP ini / port 80 tertutup | Untuk sslip.io: cocokkan penulisan IP (titik→strip). Untuk domain sendiri: cek A-record = IP VPS; buka port 80 |
| `too many certificates already issued` | Batas quota Let's Encrypt (5x/domain/minggu — sslip.io shared) | Tunggu ±1 jam, atau ulangi; pertimbangkan domain sendiri |
| `certbot: command not found` | Belum terinstall | Jalankan `apt install -y certbot python3-certbot-nginx` |
| Sertifikat kedaluwarsa (bulan depan) | — | Tidak perlu tindakan: certbot memasang auto-renew (timer systemd). Cek: `certbot renew --dry-run` |
| Browser peringatan "Not secure" walau cert OK | Mengakses via IP, bukan nama sslip.io | Selalu gunakan alamat `https://103-187-147-64.sslip.io/` (nama = sertifikat) |

---

## 8. TAHAP 7 — Verifikasi & Pemakaian

1. **Halaman absensi**: `https://103-187-147-64.sslip.io/`
   → klik 🔒 / izinkan kamera saat browser bertanya → video kamera tampil.
2. **Admin**: `https://103-187-147-64.sslip.io/login` → `admin` / `admin123`.
3. **GANTI PASSWORD** segera: tab ⚙️ Pengaturan.
4. Tab 👥 Peserta → **＋ Tambah Peserta** → isi nama & kode → unggah 1–3 foto
   wajah (atau buka kamera → Jepret) → Simpan.
5. Peserta absen: buka alamat → **▶ Mulai Absen** → ikuti instruksi
   (kedipkan mata, toleh, dsb.) → kartu hijau "Absensi Tercatat".
6. Rekap: tab 🗓️ Rekap Absensi → pilih tanggal → **⬇ Ekspor Excel**.

### ✅ Tanda berhasil
Absensi pertama tercatat, muncul di Dashboard, dan file Excel terunduh berisi datanya.

### ⚠️ ANTISIPASI ERROR
| Gejala | Penyebab | Solusi |
|---|---|---|
| "Kamera tidak dapat digunakan" | Buka via `http://` atau via IP tanpa sslip | Gunakan alamat `https://…sslip.io/` penuh; cek izin kamera di ikon 🔒 |
| Tombol kamera tidak muncul di HP | Browser lama / izin ditolak | Chrome/Safari terbaru; izinkan kamera di pengaturan situs |
| "Wajah tidak dikenali" terus | Foto referensi kurang baik / berbeda penampilan | Tambah 2–3 foto referensi variasi (dengan/tanpa kacamata, dll) via Edit Peserta |
| "Tantangan tidak terdeteksi" | Pencahayaan buruk / terlalu jauh | Cahaya cukup, jarak ±40–60 cm, ikuti instruksi dengan jelas |
| Login admin 401 terus | Password sudah diganti & lupa | Reset via SSH: `cd /opt/absensi && .venv/bin/python -c "import db;from werkzeug.security import generate_password_hash;db.change_password(1,'passwordbaru')"` |
| Halaman 502 Bad Gateway | Layanan absensi mati | `systemctl restart absensi`; cek `journalctl -u absensi -n 50` |
| Database hilang setelah deploy ulang | Folder `data` tertimpa saat upload ulang | Jangan upload folder `data` dari lokal; backup rutin (lihat bawah) |

---

## 9. Pemeliharaan

```bash
systemctl status absensi        # cek hidup
systemctl restart absensi       # restart aplikasi
journalctl -u absensi -f        # pantau log realtime (Ctrl+C keluar)
certbot renew --dry-run         # tes perpanjangan SSL
```

**Backup rutin** (mingguan disarankan) — via FileZilla unduh folder:
```
/opt/absensi/data
```
Berisi: `absensi.db` (semua data peserta+absensi), `foto/` (foto referensi),
`snapshots/` (bukti absensi). Upload balik folder itu = pulihkan data.

**Update aplikasi** (setelah mengubah kode di komputer): upload ulang file yang
berubah (mis. `app.py`) → `systemctl restart absensi`.

---

## 10. Tabel Ringkas Error & Solusi

| # | Pesan / Gejala | Solusi Cepat |
|---|---|---|
| 1 | FileZilla `ECONNREFUSED` | Host wajib `sftp://IP`, port 22 |
| 2 | FileZilla `Auth failed` | Reset password root di portal |
| 3 | SSH `Permission denied` | Password salah; layar memang tak menampilkan ketikan |
| 4 | SSH host key changed | `ssh-keygen -R IP` lalu connect lagi |
| 5 | `setup_vps.sh not found` | Upload folder `deploy` ; cek `ls /opt/absensi` |
| 6 | Skrip gagal download model | Ulangi skrip (aman), atau upload manual ke `models/` |
| 7 | nginx bind failed port 80 | `systemctl disable --now apache2 && systemctl restart nginx` |
| 8 | certbot no matching server block | 3 perintah fix di Tahap 6 (versi skrip baru otomatis aman) |
| 9 | certbot authorization failed | Cek A-record / buka port 80 / tulis sslip.io benar |
| 10 | 502 Bad Gateway | `systemctl restart absensi` |
| 11 | Kamera tak bisa diakses | Wajib `https://` , izinkan kamera di 🔒 |
| 12 | Semua orang "tidak dikenali" | Foto referensi habis/berubah — tambah ulang via admin |
| 13 | Sertifikat mau expired | Certbot auto-renew; cek `certbot renew --dry-run` |
| 14 | Lupa password admin | Perintah reset via SSH di Tahap 7 |

---

*Panduan ini melengkapi `README.md` (arsitektur & pengujian sistem).*
