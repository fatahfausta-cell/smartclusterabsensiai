"""Aplikasi utama sistem absensi wajah (Flask).

Halaman publik `/` hanya untuk akses kamera + absensi; seluruh pengenalan,
liveness, dan pencatatan terjadi di server berbasis foto referensi yang
diunggah admin. Panel admin mengelola peserta, rekap, dan ekspor Excel.
"""
import re
import secrets
import threading
import time
import uuid
from datetime import datetime
from functools import wraps

import cv2
import numpy as np
from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash

import config
import db
import excel_report
from face_engine import FaceEngineError, engine
from liveness import LivenessSession, compute_signals

app = Flask(__name__)


def _load_secret() -> str:
    try:
        return config.SECRET_KEY_FILE.read_text().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        config.SECRET_KEY_FILE.write_text(key)
        return key


app.secret_key = _load_secret()
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB per request


@app.after_request
def _anti_cache_html(resp):
    """HTML jangan di-cache browser agar pembaruan tampilan langsung terlihat."""
    if resp.content_type and resp.content_type.startswith("text/html"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

db.init_db()
try:
    engine.load()
except Exception:
    pass  # endpoint akan menolak dengan pesan bila model gagal dimuat


# ============================ SESI ABSENSI ============================
ATT_SESSIONS: dict[str, "AttendanceSession"] = {}
ATT_LOCK = threading.Lock()
MAX_SESSIONS = 30


class AttendanceSession:
    """State satu sesi absensi: kualitas frame -> liveness -> identitas -> catat.

    mode: "datang" (absen masuk) atau "pulang" (absen pulang).
    """

    def __init__(self, token: str, mode: str = "datang"):
        self.token = token
        self.mode = mode if mode in ("datang", "pulang") else "datang"
        self.created = time.time()
        self.last_frame = time.time()
        self.liveness = LivenessSession()
        self.candidates: list[tuple[float, object]] = []  # (skor, frame BGR)
        self.final: dict | None = None

    @staticmethod
    def _fail(reason: str, code: str = "gagal") -> dict:
        return {"status": "failed", "reason": reason, "code": code, "final": True}

    def _consider_candidate(self, img, face, signals):
        if not self.liveness.yaw_is_neutral(signals):
            return
        self.candidates.append((face.size, img))
        self.candidates.sort(key=lambda c: c[0], reverse=True)
        del self.candidates[5:]

    def feed(self, img) -> dict:
        if self.final is not None:
            return self.final
        t = time.time()
        self.last_frame = t

        faces = engine.detect_robust(img)
        if not faces:
            return self._progress("Wajah tidak terdeteksi — posisikan wajah di dalam bingkai")
        if len(faces) > 1:
            return self._progress("Hanya boleh satu orang di dalam frame")
        face = faces[0]
        try:
            engine.check_quality(img, face)
        except FaceEngineError as e:
            return self._progress(e.message)

        lm = engine.get_landmarks(img)
        if lm is None:
            return self._progress("Wajah kurang jelas — perbaiki posisi/pencahayaan")
        signals = compute_signals(lm)

        lv = self.liveness
        resp = lv.feed(signals, t)
        self._consider_candidate(img, face, signals)

        # batas waktu per fase (anti-stall: menunda frame tidak membantu)
        if lv.state == "align" and t - (lv.phase_start or t) > config.ALIGN_TIMEOUT_S:
            return self.finalize(self._fail(
                "Wajah tidak dapat diproses dengan jelas. Coba lagi dengan pencahayaan lebih baik.",
                "align_timeout"))
        if lv.state == "challenge" and lv.phase_start is not None:
            if t - lv.phase_start > config.CHALLENGE_TIMEOUT_S + config.RETURN_TIMEOUT_S:
                return self.finalize(self._fail(
                    "Tantangan tidak terdeteksi. Sistem hanya menerima wajah ASLI "
                    "(bukan foto/video). Silakan ulangi dan ikuti instruksi.",
                    "liveness_gagal"))

        if lv.state == "verified":
            return self.finalize(self._recognize())

        out = {"status": lv.state, "final": False}
        out.update({k: v for k, v in resp.items() if k != "state"})
        return out

    def _progress(self, detail: str) -> dict:
        lv = self.liveness
        resp = lv._response()
        out = {"status": lv.state, "detail": detail, "final": False}
        out.update({k: v for k, v in resp.items() if k != "state"})
        return out

    def _recognize(self) -> dict:
        if not self.candidates:
            return self._fail("Frame wajah tidak cukup baik untuk verifikasi. Ulangi.")
        gallery = db.all_active_embeddings()
        if not gallery:
            return self._fail("Belum ada peserta terdaftar. Hubungi admin.")

        votes: dict[int, int] = {}
        best_sim: dict[int, float] = {}
        n_used = 0
        for _, frame in self.candidates[: config.RECOGNIZE_FRAMES]:
            try:
                faces = engine.detect_robust(frame)
                if not faces:
                    continue
                emb = engine.embed_face(frame, faces[0])
            except (FaceEngineError, cv2.error):
                continue
            n_used += 1
            frame_best_uid, frame_best_sim = None, -1.0
            for uid, _kode, _nama, blob in gallery:
                sim = engine.cosine(emb, engine.bytes_to_embed(blob))
                if sim > frame_best_sim:
                    frame_best_uid, frame_best_sim = uid, sim
            if frame_best_uid is not None and frame_best_sim >= config.FACE_MATCH_THRESHOLD:
                votes[frame_best_uid] = votes.get(frame_best_uid, 0) + 1
                best_sim[frame_best_uid] = max(best_sim.get(frame_best_uid, 0.0), frame_best_sim)

        if n_used < config.RECOGNIZE_MIN_VOTES:
            return self._fail("Frame wajah tidak cukup baik untuk verifikasi. Ulangi.")
        if not votes:
            return self._fail(
                "Wajah tidak dikenali / tidak cocok dengan data peserta terdaftar.",
                "tak_dikenal")
        uid, n_votes = max(votes.items(), key=lambda kv: kv[1])
        if n_votes < config.RECOGNIZE_MIN_VOTES:
            return self._fail(
                "Verifikasi identitas tidak konsisten. Ulangi dengan wajah menghadap kamera.",
                "tak_konsisten")

        with db.get_conn() as c:
            row = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            return self._fail("Peserta tidak ditemukan / nonaktif.")
        user = dict(row)

        settings = db.get_settings()
        now = datetime.now()
        tanggal = now.strftime("%Y-%m-%d")
        waktu = now.strftime("%H:%M:%S")
        existing = db.get_attendance_today(uid, tanggal)

        # ---------- MODE PULANG ----------
        if self.mode == "pulang":
            if not existing:
                return self._fail(
                    "Anda belum absen DATANG hari ini. Lakukan absen datang dahulu.",
                    "belum_datang")
            if existing["waktu_pulang"]:
                return {
                    "status": "already", "final": True, "mode": "pulang",
                    "nama": existing["nama"], "kode": existing["kode"],
                    "waktu": existing["waktu_pulang"],
                    "status_kehadiran": existing["status_pulang"] or "Pulang",
                    "pesan": "Anda sudah absen masuk dan pulang hari ini.",
                }
            jam_pulang = settings["jam_pulang"] + ":00"
            status_pulang = "Tepat Waktu" if waktu >= jam_pulang else "Pulang Cepat"
            snapshot_rel = self._save_snapshot(user["kode"], "pulang")
            db.record_pulang(uid, tanggal, waktu, status_pulang)
            return {
                "status": "success", "final": True, "mode": "pulang",
                "nama": user["nama"], "kode": user["kode"],
                "tanggal": tanggal, "waktu": waktu,
                "status_kehadiran": status_pulang,
                "skor": round(best_sim.get(uid, 0.0), 3),
                "snapshot": snapshot_rel,
            }

        # ---------- MODE DATANG ----------
        if existing:
            if existing["waktu_pulang"]:
                return {
                    "status": "already", "final": True, "mode": "datang",
                    "nama": existing["nama"], "kode": existing["kode"],
                    "waktu": existing["waktu"],
                    "status_kehadiran": existing["status"],
                    "pesan": "Anda sudah absen masuk dan pulang hari ini.",
                }
            return {
                "status": "already", "final": True, "mode": "datang",
                "nama": existing["nama"], "kode": existing["kode"],
                "waktu": existing["waktu"],
                "status_kehadiran": existing["status"],
                "pesan": "Sudah absen masuk. Untuk pulang, tekan tombol ABSEN PULANG.",
            }

        jam_datang = settings["jam_datang"] + ":00"
        status = "Hadir" if waktu <= jam_datang else "Terlambat"
        skor = best_sim.get(uid, 0.0)
        snapshot_rel = self._save_snapshot(user["kode"], "datang")
        db.insert_attendance(uid, user["kode"], user["nama"], tanggal, waktu,
                             status, skor, snapshot_rel)
        return {
            "status": "success", "final": True, "mode": "datang",
            "nama": user["nama"], "kode": user["kode"],
            "tanggal": tanggal, "waktu": waktu,
            "status_kehadiran": status, "skor": round(skor, 3),
            "snapshot": snapshot_rel,
        }

    def _save_snapshot(self, kode: str, mode: str = "datang") -> str | None:
        if not self.candidates:
            return None
        _, frame = self.candidates[0]
        now = datetime.now()
        tag = "masuk" if mode == "datang" else "pulang"
        rel = f"{now.strftime('%Y-%m-%d')}/{_safe_name(kode)}_{tag}_{now.strftime('%H%M%S')}.jpg"
        path = config.SNAPSHOT_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return rel.replace("\\", "/")

    def finalize(self, result: dict) -> dict:
        self.final = result
        self.candidates = []
        return result


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "peserta"


def _cleanup_sessions():
    now = time.time()
    stale = [
        tok for tok, s in ATT_SESSIONS.items()
        if (s.final is not None and now - s.last_frame > 30)
        or now - s.created > config.SESSION_TTL_S
        or now - s.last_frame > config.FRAME_GAP_MAX_S * 6
    ]
    for tok in stale:
        ATT_SESSIONS.pop(tok, None)


# ============================ ROUTE PUBLIK ============================
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/attendance/start")
def api_attendance_start():
    engine.ensure_ready()
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "datang")
    if mode not in ("datang", "pulang"):
        return jsonify({"error": "Mode absen tidak valid."}), 400
    with ATT_LOCK:
        _cleanup_sessions()
        if len(ATT_SESSIONS) >= MAX_SESSIONS:
            return jsonify({"error": "Terlalu banyak sesi aktif, coba beberapa saat lagi."}), 429
        token = secrets.token_urlsafe(16)
        ATT_SESSIONS[token] = AttendanceSession(token, mode)
    return jsonify({"ok": True, "token": token, "mode": mode})


@app.post("/api/attendance/frame")
def api_attendance_frame():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    image = data.get("image", "")
    if not token or not image:
        return jsonify({"error": "Parameter tidak lengkap."}), 400
    with ATT_LOCK:
        sess = ATT_SESSIONS.get(token)
        if sess is None:
            return jsonify({
                "status": "failed", "final": True, "code": "sesi_kedaluwarsa",
                "reason": "Sesi berakhir. Silakan mulai ulang absensi.",
            })
        if time.time() - sess.created > config.SESSION_TTL_S:
            ATT_SESSIONS.pop(token, None)
            return jsonify({
                "status": "failed", "final": True, "code": "sesi_kedaluwarsa",
                "reason": "Sesi kedaluwarsa. Silakan mulai ulang absensi.",
            })
        try:
            img = engine.decode_data_uri(image)
        except FaceEngineError as e:
            return jsonify({"error": e.message}), 400
        try:
            resp = sess.feed(img)
        except FaceEngineError as e:
            resp = sess.finalize(sess._fail(e.message))
        if resp.get("final"):
            ATT_SESSIONS.pop(token, None)
    return jsonify(resp)


@app.post("/api/attendance/cancel")
def api_attendance_cancel():
    data = request.get_json(silent=True) or {}
    with ATT_LOCK:
        ATT_SESSIONS.pop(data.get("token", ""), None)
    return jsonify({"ok": True})


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "engine_ready": engine.ready, "engine_error": engine.error})


# ============================ ADMIN: AUTH ============================
def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            return jsonify({"error": "Silakan login terlebih dahulu."}), 401
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = db.verify_admin(request.form.get("username", ""),
                               request.form.get("password", ""))
        if user:
            session.clear()
            session["admin_id"] = user["id"]
            session["admin_username"] = user["username"]
            return redirect(url_for("admin_page"))
        time.sleep(0.8)  # perlambat percobaan brute force
        error = "Username atau password salah."
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/admin")
def admin_page():
    if "admin_id" not in session:
        return redirect(url_for("login"))
    return render_template("admin.html", username=session.get("admin_username", "admin"))


# ============================ ADMIN: PESERTA ============================
def _store_photo(user_id: int, file_storage) -> tuple[bool, str]:
    """Validasi + simpan satu foto referensi; return (sukses, pesan)."""
    raw = file_storage.read()
    if len(raw) > 8 * 1024 * 1024:
        return False, "Ukuran file terlalu besar (maks 8 MB)."
    try:
        img = engine.decode_image_bytes(raw)
    except FaceEngineError as e:
        return False, f"{file_storage.filename}: {e.message}"
    try:
        emb, _face = engine.extract(img)
    except FaceEngineError as e:
        return False, f"{file_storage.filename}: {e.message}"

    h, w = img.shape[:2]
    scale = 1024 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    folder = config.FOTO_DIR / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:12]}.jpg"
    cv2.imwrite(str(folder / fname), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    db.add_photo(user_id, fname, engine.embed_to_bytes(emb))
    return True, f"{file_storage.filename}: OK"


@app.get("/api/admin/users")
@login_required_api
def api_list_users():
    return jsonify({"users": db.list_users()})


@app.post("/api/admin/users")
@login_required_api
def api_create_user():
    engine.ensure_ready()
    nama = (request.form.get("nama") or "").strip()
    kode = (request.form.get("kode") or "").strip()
    if not nama or not kode:
        return jsonify({"error": "Nama dan kode peserta wajib diisi."}), 400
    if db.kode_exists(kode):
        return jsonify({"error": f"Kode '{kode}' sudah dipakai peserta lain."}), 400
    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Minimal satu foto wajah diperlukan."}), 400

    user_id = db.create_user(kode, nama)
    sukses, gagal = [], []
    for f in files:
        ok, msg = _store_photo(user_id, f)
        (sukses if ok else gagal).append(msg)
    if not sukses:
        db.delete_user(user_id)
        return jsonify({"error": "Tidak ada foto yang valid.", "detail": gagal}), 400
    return jsonify({"ok": True, "user_id": user_id, "berhasil": len(sukses),
                    "detail": gagal, "jumlah_foto": db.get_user(user_id) and
                    len(db.list_photos(user_id))})


@app.patch("/api/admin/users/<int:user_id>")
@login_required_api
def api_update_user(user_id):
    data = request.get_json(silent=True) or {}
    nama = (data.get("nama") or "").strip()
    kode = (data.get("kode") or "").strip()
    if not db.get_user(user_id):
        return jsonify({"error": "Peserta tidak ditemukan."}), 404
    if not nama or not kode:
        return jsonify({"error": "Nama dan kode wajib diisi."}), 400
    if db.kode_exists(kode, exclude_id=user_id):
        return jsonify({"error": f"Kode '{kode}' sudah dipakai peserta lain."}), 400
    db.update_user(user_id, kode, nama)
    return jsonify({"ok": True})


@app.post("/api/admin/users/<int:user_id>/toggle")
@login_required_api
def api_toggle_user(user_id):
    if not db.get_user(user_id):
        return jsonify({"error": "Peserta tidak ditemukan."}), 404
    user = db.get_user(user_id)
    db.toggle_user(user_id, not bool(user["aktif"]))
    return jsonify({"ok": True, "aktif": not bool(user["aktif"])})


@app.delete("/api/admin/users/<int:user_id>")
@login_required_api
def api_delete_user(user_id):
    if not db.get_user(user_id):
        return jsonify({"error": "Peserta tidak ditemukan."}), 404
    db.delete_user(user_id)
    return jsonify({"ok": True})


@app.get("/api/admin/users/<int:user_id>/photos")
@login_required_api
def api_list_photos(user_id):
    return jsonify({"photos": db.list_photos(user_id)})


@app.delete("/api/admin/photos/<int:photo_id>")
@login_required_api
def api_delete_photo(photo_id):
    photo = db.get_photo(photo_id)
    if not photo:
        return jsonify({"error": "Foto tidak ditemukan."}), 404
    db.delete_photo(photo_id)
    try:
        (config.FOTO_DIR / str(photo["user_id"]) / photo["file"]).unlink(missing_ok=True)
    except OSError:
        pass
    if not db.list_photos(photo["user_id"]):
        return jsonify({"ok": True, "warning": "Peserta ini tidak punya foto lagi — "
                        "tidak akan dikenali sampai foto ditambahkan."})
    return jsonify({"ok": True})


@app.post("/api/admin/users/<int:user_id>/photos")
@login_required_api
def api_add_photos(user_id):
    engine.ensure_ready()
    if not db.get_user(user_id):
        return jsonify({"error": "Peserta tidak ditemukan."}), 404
    existing = len(db.list_photos(user_id))
    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Tidak ada file foto."}), 400
    if existing + len(files) > config.FACE_MAX_PER_USER:
        return jsonify({"error": f"Maksimal {config.FACE_MAX_PER_USER} foto per peserta "
                                 f"(saat ini {existing})."}), 400
    sukses, gagal = [], []
    for f in files:
        ok, msg = _store_photo(user_id, f)
        (sukses if ok else gagal).append(msg)
    if not sukses:
        return jsonify({"error": "Tidak ada foto yang valid.", "detail": gagal}), 400
    return jsonify({"ok": True, "berhasil": len(sukses), "detail": gagal})


@app.get("/foto-referensi/<int:user_id>/<path:fname>")
@login_required_api
def serve_foto(user_id, fname):
    return send_from_directory(config.FOTO_DIR / str(user_id), fname)


# ============================ ADMIN: ABSENSI & EKSPOR ============================
@app.get("/api/admin/stats")
@login_required_api
def api_stats():
    tanggal = datetime.now().strftime("%Y-%m-%d")
    return jsonify({"tanggal": tanggal, **db.stats_today(tanggal),
                    "hari_ini": db.attendance_today_detail(tanggal)})


@app.get("/api/admin/attendance")
@login_required_api
def api_attendance_list():
    d_from = request.args.get("from") or datetime.now().strftime("%Y-%m-01")
    d_to = request.args.get("to") or datetime.now().strftime("%Y-%m-%d")
    return jsonify({"from": d_from, "to": d_to, "records": db.list_attendance(d_from, d_to)})


@app.delete("/api/admin/attendance/<int:att_id>")
@login_required_api
def api_attendance_delete(att_id):
    db.delete_attendance(att_id)
    return jsonify({"ok": True})


@app.get("/api/admin/export")
@login_required_api
def api_export():
    d_from = request.args.get("from") or datetime.now().strftime("%Y-%m-01")
    d_to = request.args.get("to") or datetime.now().strftime("%Y-%m-%d")
    records = db.list_attendance(d_from, d_to)
    buf = excel_report.build_rekap(records, db.list_users(), d_from, d_to)
    return send_file(
        buf, as_attachment=True, download_name=f"rekap_absensi_{d_from}_{d_to}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/snapshots/<path:sub>")
@login_required_api
def serve_snapshot(sub):
    return send_from_directory(config.SNAPSHOT_DIR, sub)


# ============================ ADMIN: PENGATURAN ============================
@app.post("/api/admin/password")
@login_required_api
def api_password():
    data = request.get_json(silent=True) or {}
    lama, baru = data.get("lama", ""), data.get("baru", "")
    if len(baru) < 6:
        return jsonify({"error": "Password baru minimal 6 karakter."}), 400
    with db.get_conn() as c:
        row = c.execute("SELECT * FROM admin WHERE id = ?",
                        (session.get("admin_id"),)).fetchone()
    if not row or not check_password_hash(row["password_hash"], lama):
        return jsonify({"error": "Password lama salah."}), 400
    db.change_password(row["id"], baru)
    return jsonify({"ok": True})


@app.get("/api/admin/settings")
@login_required_api
def api_get_settings():
    return jsonify(db.get_settings())


@app.post("/api/admin/settings")
@login_required_api
def api_set_settings():
    data = request.get_json(silent=True) or {}
    jam_datang = (data.get("jam_datang") or "").strip()
    jam_pulang = (data.get("jam_pulang") or "").strip()
    import re as _re
    pola = _re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    if not pola.match(jam_datang) or not pola.match(jam_pulang):
        return jsonify({"error": "Format jam harus HH:MM (00:00-23:59)."}), 400
    if jam_datang >= jam_pulang:
        return jsonify({"error": "Jam datang harus lebih awal daripada jam pulang."}), 400
    db.set_setting("jam_datang", jam_datang)
    db.set_setting("jam_pulang", jam_pulang)
    return jsonify({"ok": True, **db.get_settings()})


@app.get("/api/admin/info")
@login_required_api
def api_info():
    s = db.get_settings()
    return jsonify({
        "jam_datang": s["jam_datang"],
        "jam_pulang": s["jam_pulang"],
        "threshold": config.FACE_MATCH_THRESHOLD,
        "model": "YuNet + ArcFace (w600k_mbf) + FaceLandmarker",
        "versi": "1.1",
    })


if __name__ == "__main__":
    print(f" * Absensi Wajah: http://{config.HOST}:{config.PORT}")
    print(f" * Admin default: {config.ADMIN_DEFAULT_USERNAME} / {config.ADMIN_DEFAULT_PASSWORD}")
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False, use_reloader=False)
