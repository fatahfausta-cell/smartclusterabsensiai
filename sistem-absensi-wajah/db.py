"""Layer database SQLite untuk sistem absensi wajah."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kode       TEXT UNIQUE NOT NULL,
    nama       TEXT NOT NULL,
    aktif      INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file       TEXT NOT NULL,
    encoding   BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kode          TEXT NOT NULL,
    nama          TEXT NOT NULL,
    tanggal       TEXT NOT NULL,
    waktu         TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('Hadir', 'Terlambat')),
    skor          REAL NOT NULL,
    snapshot      TEXT,
    waktu_pulang  TEXT,
    status_pulang TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (user_id, tanggal)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attendance_tanggal ON attendance(tanggal);
CREATE INDEX IF NOT EXISTS idx_photos_user ON photos(user_id);
"""

DEFAULT_SETTINGS = {
    "jam_datang": config.JAM_DATANG_DEFAULT,
    "jam_pulang": config.JAM_PULANG_DEFAULT,
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)
        # ---- migrasi basis data lama ----
        cols = {r["name"] for r in c.execute("PRAGMA table_info(attendance)").fetchall()}
        if "waktu_pulang" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN waktu_pulang TEXT")
        if "status_pulang" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN status_pulang TEXT")
        # ---- seed ----
        if c.execute("SELECT COUNT(*) FROM admin").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
                (
                    config.ADMIN_DEFAULT_USERNAME,
                    generate_password_hash(config.ADMIN_DEFAULT_PASSWORD),
                ),
            )
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))


# ---------------- Pengaturan (settings) ----------------
def get_settings() -> dict:
    with get_conn() as c:
        rows = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
    out = dict(DEFAULT_SETTINGS)
    out.update({k: v for k, v in rows.items() if k in DEFAULT_SETTINGS})
    return out


def set_setting(key: str, value: str):
    with get_conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------------- Admin ----------------
def verify_admin(username: str, password: str):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM admin WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def change_password(admin_id: int, new_password: str):
    with get_conn() as c:
        c.execute(
            "UPDATE admin SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), admin_id),
        )


# ---------------- Peserta (users) ----------------
def list_users(only_active: bool = False):
    q = """
        SELECT u.id, u.kode, u.nama, u.aktif, u.created_at,
               (SELECT COUNT(*) FROM photos p WHERE p.user_id = u.id) AS jumlah_foto,
               (SELECT file FROM photos p WHERE p.user_id = u.id ORDER BY p.id LIMIT 1) AS foto
        FROM users u
    """
    if only_active:
        q += " WHERE u.aktif = 1"
    q += " ORDER BY u.nama COLLATE NOCASE"
    with get_conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def get_user(user_id: int):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_user(kode: str, nama: str):
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO users (kode, nama, created_at) VALUES (?, ?, ?)",
            (kode.strip(), nama.strip(), datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def update_user(user_id: int, kode: str, nama: str):
    with get_conn() as c:
        c.execute(
            "UPDATE users SET kode = ?, nama = ? WHERE id = ?",
            (kode.strip(), nama.strip(), user_id),
        )


def toggle_user(user_id: int, aktif: bool):
    with get_conn() as c:
        c.execute("UPDATE users SET aktif = ? WHERE id = ?", (1 if aktif else 0, user_id))


def delete_user(user_id: int):
    with get_conn() as c:
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))


def kode_exists(kode: str, exclude_id: int | None = None) -> bool:
    with get_conn() as c:
        if exclude_id is None:
            row = c.execute("SELECT 1 FROM users WHERE kode = ?", (kode,)).fetchone()
        else:
            row = c.execute(
                "SELECT 1 FROM users WHERE kode = ? AND id != ?", (kode, exclude_id)
            ).fetchone()
    return row is not None


# ---------------- Foto referensi ----------------
def add_photo(user_id: int, filename: str, encoding: bytes) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO photos (user_id, file, encoding, created_at) VALUES (?, ?, ?, ?)",
            (user_id, filename, encoding, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def delete_photo(photo_id: int):
    with get_conn() as c:
        c.execute("DELETE FROM photos WHERE id = ?", (photo_id,))


def get_photo(photo_id: int):
    with get_conn() as c:
        row = c.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return dict(row) if row else None


def list_photos(user_id: int):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT id, user_id, file, created_at FROM photos WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        ]


def all_active_embeddings():
    """[(user_id, kode, nama, encoding_blob), ...] untuk pencocokan wajah."""
    with get_conn() as c:
        return [
            (r["user_id"], r["kode"], r["nama"], r["encoding"])
            for r in c.execute(
                """SELECT p.user_id, u.kode, u.nama, p.encoding
                   FROM photos p JOIN users u ON u.id = p.user_id
                   WHERE u.aktif = 1"""
            ).fetchall()
        ]


# ---------------- Absensi ----------------
def get_attendance_today(user_id: int, tanggal: str):
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND tanggal = ?",
            (user_id, tanggal),
        ).fetchone()
    return dict(row) if row else None


def insert_attendance(user_id: int, kode: str, nama: str, tanggal: str, waktu: str,
                      status: str, skor: float, snapshot: str | None) -> int:
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO attendance
               (user_id, kode, nama, tanggal, waktu, status, skor, snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, kode, nama, tanggal, waktu, status, skor, snapshot,
             datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def record_pulang(user_id: int, tanggal: str, waktu: str, status_pulang: str):
    """Catat jam pulang pada baris absensi hari tsb (sudah dipastikan ada)."""
    with get_conn() as c:
        c.execute(
            "UPDATE attendance SET waktu_pulang = ?, status_pulang = ? "
            "WHERE user_id = ? AND tanggal = ? AND waktu_pulang IS NULL",
            (waktu, status_pulang, user_id, tanggal),
        )


def list_attendance(d_from: str, d_to: str):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                """SELECT * FROM attendance
                   WHERE tanggal BETWEEN ? AND ?
                   ORDER BY tanggal DESC, waktu DESC""",
                (d_from, d_to),
            ).fetchall()
        ]


def delete_attendance(att_id: int):
    with get_conn() as c:
        c.execute("DELETE FROM attendance WHERE id = ?", (att_id,))


def stats_today(tanggal: str):
    with get_conn() as c:
        total_peserta = c.execute(
            "SELECT COUNT(*) FROM users WHERE aktif = 1"
        ).fetchone()[0]
        hadir = c.execute(
            "SELECT COUNT(*) FROM attendance WHERE tanggal = ?", (tanggal,)
        ).fetchone()[0]
        terlambat = c.execute(
            "SELECT COUNT(*) FROM attendance WHERE tanggal = ? AND status = 'Terlambat'",
            (tanggal,),
        ).fetchone()[0]
        pulang = c.execute(
            "SELECT COUNT(*) FROM attendance WHERE tanggal = ? AND waktu_pulang IS NOT NULL",
            (tanggal,),
        ).fetchone()[0]
    return {
        "total_peserta": total_peserta,
        "hadir": hadir,
        "terlambat": terlambat,
        "sudah_pulang": pulang,
        "belum_hadir": max(0, total_peserta - hadir),
    }


def attendance_today_detail(tanggal: str):
    with get_conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM attendance WHERE tanggal = ? ORDER BY waktu", (tanggal,)
            ).fetchall()
        ]
