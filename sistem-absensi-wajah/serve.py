"""Menjalankan aplikasi dengan waitress (production, 1 proses multi-thread).

PENTING: gunakan SATU proses (threads, bukan multi-worker) karena sesi
absensi disimpan in-process; multi-worker akan memutus kontinuitas sesi.
Di belakang nginx, biarkan mendengarkan 127.0.0.1 (default).
"""
from waitress import serve

import config
from app import app

if __name__ == "__main__":
    print(f" * Absensi Wajah (waitress): http://{config.HOST}:{config.PORT}")
    print(f" * Admin default: {config.ADMIN_DEFAULT_USERNAME} / {config.ADMIN_DEFAULT_PASSWORD}")
    serve(app, host=config.HOST, port=config.PORT, threads=8)
