"""Uji integrasi pipeline absensi secara in-process (Flask test client).

Alur yang diuji:
1.  Admin login -> tambah peserta Obama + Biden                  -> tersimpan
2.  Pengaturan jam: format salah & datang>=pulang ditolak; valid disimpan
3.  Foto 2-wajah ditolak                                         -> validasi admin
4.  ABSEN DATANG DENGAN FOTO STATIS (frame identik)              -> GAGAL (anti-foto)
5.  Absen PULANG sebelum absen datang                            -> GAGAL belum_datang
6.  Absen DATANG wajah "hidup"                                   -> SUKSES (Terlambat, jam 07:00)
7.  Absen DATANG kedua kali                                      -> already
8.  Absen PULANG wajah "hidup"                                   -> SUKSES (Pulang Cepat, jam 23:59)
9.  Absen PULANG kedua kali                                      -> already
10. Biden datang                                                 -> SUKSES (multi-user)
11. Ekspor Excel: kolom datang+pulang                            -> diverifikasi openpyxl

Jalankan: .venv/Scripts/python tests/test_session.py
"""
import base64
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

import app as modul_app
import db
from face_engine import engine

ASSET = Path(__file__).parent / "assets"
KLIEN = modul_app.app.test_client()

# ---------------- aktuator landmark "wajah hidup" ----------------
_orig_get_landmarks = engine.get_landmarks
AKSI = {"kini": "netral"}


def _get_landmarks_hidup(img):
    lm = _orig_get_landmarks(img)
    if lm is None:
        return None
    lm = lm.copy()
    lm += np.random.uniform(-1.2, 1.2, lm.shape)
    eye_dist = float(np.linalg.norm(lm[33] - lm[263]))
    aksi = AKSI["kini"]
    if aksi == "kedip":
        for atas, bawah in ((160, 144), (158, 153), (385, 380), (387, 373)):
            lm[atas] = lm[atas] + 0.78 * (lm[bawah] - lm[atas])
    elif aksi == "toleh_kiri":
        lm[1][0] += 0.27 * eye_dist
    elif aksi == "toleh_kanan":
        lm[1][0] -= 0.27 * eye_dist
    elif aksi == "senyum":
        lm[61][0] -= 0.13 * eye_dist
        lm[291][0] += 0.13 * eye_dist
    elif aksi == "angguk":
        lm[1][1] += 0.16 * eye_dist
    return lm


def data_uri(img_bgr) -> str:
    _, enc = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode()


def muat(nama):
    return engine.decode_image_bytes((ASSET / nama).read_bytes())


POLA_AKSI = {
    "kedip": ["netral", "netral", "kedip", "kedip", "netral"],
    "toleh_kiri": ["netral", "toleh_kiri", "toleh_kiri", "netral", "netral"],
    "toleh_kanan": ["netral", "toleh_kanan", "toleh_kanan", "netral", "netral"],
    "senyum": ["netral", "senyum", "senyum", "senyum", "netral"],
    "angguk": ["netral", "angguk", "angguk", "netral", "netral"],
}
PETA_INSTRUKSI = [
    ("Kedipkan", "kedip"), ("ke kiri", "toleh_kiri"), ("ke kanan", "toleh_kanan"),
    ("Anggukkan", "angguk"), ("Tersenyum", "senyum"),
]


def absensi_sebagai_wajah_hidup(img_bgr, mode="datang") -> dict:
    r = KLIEN.post("/api/attendance/start", json={"mode": mode}).get_json()
    token = r["token"]
    uri = data_uri(img_bgr)
    langkah = 0
    for _ in range(500):
        resp = KLIEN.post("/api/attendance/frame",
                          json={"token": token, "image": uri}).get_json()
        if resp.get("final"):
            return resp
        AKSI["kini"] = "netral"
        if resp.get("status") == "challenge" and not resp.get("performed"):
            instruksi = resp.get("instruction", "")
            jenis = next((j for kata, j in PETA_INSTRUKSI if kata in instruksi), None)
            if jenis:
                siklus = POLA_AKSI[jenis]
                AKSI["kini"] = siklus[langkah % len(siklus)]
        langkah += 1
        time.sleep(0.17)
    return {"status": "timeout_uji"}


def absensi_dengan_foto_statis(img_bgr, durasi_s=20) -> dict:
    r = KLIEN.post("/api/attendance/start").get_json()
    token = r["token"]
    uri = data_uri(img_bgr)
    t0 = time.time()
    while time.time() - t0 < durasi_s:
        resp = KLIEN.post("/api/attendance/frame",
                          json={"token": token, "image": uri}).get_json()
        if resp.get("final"):
            return resp
        time.sleep(0.15)
    return {"status": "tidak_final"}


def main():
    hasil = []

    with db.get_conn() as c:
        c.execute("DELETE FROM users")
        c.execute("DELETE FROM attendance")

    # 1. login admin + tambah peserta Obama & Biden
    lr = KLIEN.post("/login", data={"username": "admin", "password": "admin123"},
                    follow_redirects=True)
    assert lr.status_code == 200 and b"Dashboard" in lr.data, "login admin gagal"
    for nama, kode, foto in (("Barack Obama", "P001", "obama.jpg"),
                             ("Joe Biden", "P002", "biden.jpg")):
        with open(ASSET / foto, "rb") as f:
            rr = KLIEN.post("/api/admin/users", data={
                "nama": nama, "kode": kode, "photos": [(f, foto)],
            }, content_type="multipart/form-data")
        j = rr.get_json()
        print(f"[admin  ] tambah {nama} -> {rr.status_code} {j}")
        hasil.append((f"tambah peserta {kode}", rr.status_code == 200 and j.get("berhasil") == 1))

    # 2. pengaturan jam: invalid ditolak, valid tersimpan (07:00 / 23:59 -> deterministik)
    rr = KLIEN.post("/api/admin/settings",
                    json={"jam_datang": "9:00", "jam_pulang": "17:00"})
    hasil.append(("format jam invalid ditolak", rr.status_code == 400))
    rr = KLIEN.post("/api/admin/settings",
                    json={"jam_datang": "17:00", "jam_pulang": "08:00"})
    hasil.append(("datang>=pulang ditolak", rr.status_code == 400))
    rr = KLIEN.post("/api/admin/settings",
                    json={"jam_datang": "07:00", "jam_pulang": "23:59"})
    j = rr.get_json()
    print(f"[jam    ] simpan 07:00/23:59 -> {rr.status_code} {j}")
    hasil.append(("simpan jam valid", rr.status_code == 200 and
                  j.get("jam_datang") == "07:00" and j.get("jam_pulang") == "23:59"))

    # 3. foto dua-wajah ditolak
    with open(ASSET / "two_people.jpg", "rb") as f:
        rr = KLIEN.post("/api/admin/users", data={
            "nama": "Dua Orang", "kode": "P003",
            "photos": [(f, "two_people.jpg")],
        }, content_type="multipart/form-data")
    print(f"[admin  ] foto 2-wajah ditolak -> {rr.status_code}")
    hasil.append(("validasi foto admin", rr.status_code == 400))

    # 4. ABSEN DATANG MEMAKAI FOTO STATIS -> GAGAL
    print("[serang ] absen datang memakai FOTO STATIS obama2.jpg ...")
    engine.get_landmarks = _orig_get_landmarks
    resp = absensi_dengan_foto_statis(muat("obama2.jpg"))
    print(f"[serang ] hasil: {resp.get('status')} / {resp.get('code')}")
    hasil.append(("foto statis DITOLAK",
                  resp.get("status") == "failed" and resp.get("code") in
                  ("liveness_gagal", "align_timeout")))

    engine.get_landmarks = _get_landmarks_hidup

    # 5. pulang tanpa datang -> belum_datang
    print("[pulang ] Biden absen PULANG tanpa absen datang ...")
    resp = absensi_sebagai_wajah_hidup(muat("biden.jpg"), mode="pulang")
    print(f"[pulang ] hasil: {resp.get('status')} / {resp.get('code')}")
    hasil.append(("pulang tanpa datang DITOLAK", resp.get("code") == "belum_datang"))

    # 6. absen datang Obama -> SUKSES Terlambat (jam kini > 07:00)
    print("[datang ] Obama absen datang (wajah hidup)...")
    resp = absensi_sebagai_wajah_hidup(muat("obama2.jpg"), mode="datang")
    print(f"[datang ] hasil: {resp}")
    hasil.append(("absen datang sukses",
                  resp.get("status") == "success" and resp.get("mode") == "datang" and
                  resp.get("nama") == "Barack Obama" and resp.get("status_kehadiran") == "Terlambat"))

    # 7. datang kedua kali -> already
    resp = absensi_sebagai_wajah_hidup(muat("obama2.jpg"), mode="datang")
    print(f"[duplik ] datang kedua: {resp.get('status')} — {resp.get('pesan')}")
    hasil.append(("anti duplikat datang", resp.get("status") == "already"))

    # 8. absen pulang Obama -> SUKSES Pulang Cepat (jam kini < 23:59)
    print("[pulang ] Obama absen pulang (wajah hidup)...")
    resp = absensi_sebagai_wajah_hidup(muat("obama2.jpg"), mode="pulang")
    print(f"[pulang ] hasil: {resp}")
    hasil.append(("absen pulang sukses",
                  resp.get("status") == "success" and resp.get("mode") == "pulang" and
                  resp.get("status_kehadiran") == "Pulang Cepat"))

    # 9. pulang kedua kali -> already
    resp = absensi_sebagai_wajah_hidup(muat("obama2.jpg"), mode="pulang")
    print(f"[duplik ] pulang kedua: {resp.get('status')}")
    hasil.append(("anti duplikat pulang", resp.get("status") == "already"))

    # 10. Biden datang -> sukses (multi-user)
    resp = absensi_sebagai_wajah_hidup(muat("biden.jpg"), mode="datang")
    print(f"[datang ] Biden datang: {resp.get('status')} ({resp.get('status_kehadiran')})")
    hasil.append(("multi-user", resp.get("status") == "success" and
                  resp.get("nama") == "Joe Biden"))
    engine.get_landmarks = _orig_get_landmarks

    # verifikasi DB
    recs = db.list_attendance("2000-01-01", "2999-12-31")
    obama = next(r for r in recs if r["kode"] == "P001")
    biden = next(r for r in recs if r["kode"] == "P002")
    print(f"[db     ] Obama: datang={obama['waktu']}({obama['status']}) "
          f"pulang={obama['waktu_pulang']}({obama['status_pulang']}) snap={obama['snapshot']}")
    print(f"[db     ] Biden: datang={biden['waktu']} pulang={biden['waktu_pulang'] or '-'}")
    snap_ok = all((modul_app.config.SNAPSHOT_DIR / r["snapshot"]).exists()
                  for r in recs if r["snapshot"])
    hasil.append(("snapshot bukti tersimpan", bool(snap_ok)))
    hasil.append(("DB jam pulang tercatat", bool(obama["waktu_pulang"]) and
                  obama["status_pulang"] == "Pulang Cepat" and biden["waktu_pulang"] is None))

    # 11. ekspor Excel + baca balik (kolom baru: F=G datang/status, H/I pulang/status)
    xr = KLIEN.get("/api/admin/export?from=2000-01-01&to=2999-12-31")
    assert xr.status_code == 200, "ekspor gagal"
    from openpyxl import load_workbook
    from io import BytesIO
    wb = load_workbook(BytesIO(xr.data))
    ws, ws2 = wb["Rekap Absensi"], wb["Ringkasan"]
    baris = [row for row in ws.iter_rows(min_row=6, values_only=True) if row[3]]
    ringk = [row for row in ws2.iter_rows(min_row=4, values_only=True) if row[2]]
    print(f"[excel  ] {len(baris)} baris; Obama: {baris[0][:8]}")
    print(f"[excel  ] ringkasan Obama: {[r for r in ringk if r[2]=='Barack Obama'][0]}")
    ob = next(b for b in baris if b[3] == "Barack Obama")
    orr = next(r for r in ringk if r[2] == "Barack Obama")
    hasil.append(("excel datang+pulang",
                  ob[6] != "-" and ob[7] == "Pulang Cepat" and orr[6] == 1))

    print()
    gagal = [nama for nama, ok in hasil if not ok]
    for nama, ok in hasil:
        print(f"  {'✅' if ok else '❌'} {nama}")
    print("\nHASIL:", "SEMUA UJI INTEGRASI LOLOS ✅" if not gagal else f"GAGAL: {gagal} ❌")
    sys.exit(0 if not gagal else 1)


if __name__ == "__main__":
    main()
