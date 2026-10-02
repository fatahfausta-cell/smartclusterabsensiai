# 💻 Panduan Menjalankan Sistem Absensi Secara LOKAL (di Komputer Sendiri)

Panduan untuk pemula — tanpa perlu hafal perintah apa pun.

---

## Cara Menyalakan (cukup 1 langkah!)

1. Buka File Explorer → masuk ke folder proyek:
   ```
   C:\Users\MSI Modern 15\.zcode\workspace\default\sistem-absensi-wajah
   ```
2. **Dobel-klik file `start_local.bat`** ⚡
3. Akan muncul jendela hitam bertulis "SISTEM ABSENSI WAJAH - MODE LOKAL" —
   **biarkan jendela itu terbuka** selama sistem dipakai (itu servernya).
4. ± 15 detik kemudian browser terbuka otomatis ke **http://localhost:5050**.
   Selesai! 🎉

> Yang terjadi di belakang layar: file .bat menjalankan Python + memuat model AI
> (± 15 detik) lalu membuka browser. Halaman akan gagal bila dibuka terlalu cepat —
> tunggu sebentar lalu refresh (F5).

## Alamat yang tersedia

| Halaman | Alamat | Keterangan |
|---|---|---|
| 📷 Absensi (peserta) | http://localhost:5050 | Kiosk kamera: tombol Absen Datang / Pulang |
| 🔐 Admin | http://localhost:5050/login | Login: `admin` / `admin123` (ganti setelah login!) |

Kamera hanya bisa diakses lewat `localhost` atau HTTPS — jadi pastikan alamatnya
selalu `http://localhost:5050`, bukan `http://127.0.0.1:5050` pun sebenarnya aman,
tapi jangan lewat alamat IP lain.

## Cara Mematikan

Salah satu dari:
- **Tutup jendela hitam** server, atau tekan `Ctrl+C` di jendela itu, atau
- Dobel-klik `stop_local.bat`.

## Pemakaian Harian (ringkas)

1. Nyalakan → daftarkan peserta baru (Admin → 👥 Peserta → ＋ Tambah Peserta →
   unggah foto wajahnya).
2. Peserta absen: buka http://localhost:5050 → pilih **🌅 Absen Datang** atau
   **🏠 Absen Pulang** → ikuti instruksi (kedipkan mata, toleh, dsb.).
3. Jam datang/pulang diatur di Admin → ⚙️ Pengaturan (default 08:00 / 17:00).
4. Unduh rekap Excel di Admin → 🗓️ Rekap Absensi → **⬇ Ekspor Excel**.
5. Matikan server bila sudah selesai.

## ⚠️ Antisipasi Masalah

| Gejala | Penyebab | Solusi |
|---|---|---|
| Jendela hitam muncul lalu langsung tertutup | `.venv` belum ada (komputer baru) | Jalankan sekali di CMD dari folder proyek: `python -m venv .venv` lalu `.venv\Scripts\pip install -r requirements.txt` |
| Browser terbuka tapi "This site can't be reached" | Server belum selesai memuat (±15 dtk) / jendela hitam tertutup | Tunggu lalu F5; pastikan jendela hitam masih terbuka |
| `Address already in use` / server tak mau nyala | Sudah ada server berjalan di port 5050 | Dobel-klik `stop_local.bat` dulu, lalu `start_local.bat` lagi |
| "Kamera tidak dapat digunakan" | Akses kamera ditolak / buka bukan via localhost | Klik ikon 🔒 di address bar → izinkan Kamera → refresh; pastikan alamat localhost |
| Kamera dipakai aplikasi lain (Zoom/dll) | Webcam hanya bisa 1 aplikasi | Tutup Zoom/Meet dll, refresh halaman |
| Absen "Wajah tidak dikenali" terus | Foto referensi kurang mirip / pencahayaan beda | Tambah 2–3 foto variasi via Edit Peserta; pastikan wajah terang |
| Login admin gagal | Password sudah diganti & lupa | Dobel-klik `reset_admin_password.bat` untuk mengatur password baru |

## Data Tersimpan di Mana?

Semua data (peserta, foto, absensi, snapshot bukti) ada di folder:
```
sistem-absensi-wajah\data\
  ├── absensi.db      ← database utama
  ├── foto\           ← foto referensi peserta
  └── snapshots\      ← bukti foto tiap absensi
```
**Backup = salin folder `data` itu.** Jangan hapus bila tidak ingin kehilangan data.

---

*Untuk meng-online-kan ke internet (VPS IDCloudHost), lihat `PANDUAN_HOSTING.md`.*
