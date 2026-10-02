"""Konfigurasi pusat sistem absensi wajah."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "absensi.db"
FOTO_DIR = DATA_DIR / "foto"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
MODELS_DIR = BASE_DIR / "models"
SECRET_KEY_FILE = DATA_DIR / "secret.key"

YUNET_PATH = MODELS_DIR / "face_detection_yunet.onnx"
ARCFACE_PATH = MODELS_DIR / "w600k_mbf.onnx"
FACEMESH_PATH = MODELS_DIR / "face_landmarker.task"

# URL model untuk diunduh otomatis bila berkas belum ada
MODEL_URLS = {
    "face_detection_yunet.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "w600k_mbf.onnx": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",  # fallback manual; utama: salin dari proyek lama
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}

# ---- Admin default (seed saat DB dibuat pertama kali; ganti lewat menu Pengaturan) ----
ADMIN_DEFAULT_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"

# ---- Pengenalan wajah ----
FACE_MATCH_THRESHOLD = 0.45   # cosine similarity minimum agar dinyatakan cocok
FACE_MIN_SIZE = 56            # tinggi wajah minimum (px) — mentolerir webcam resolusi rendah
FACE_MAX_PER_USER = 10        # maksimum foto referensi per peserta
RECOGNIZE_FRAMES = 3          # jumlah frame terbaik untuk verifikasi identitas
RECOGNIZE_MIN_VOTES = 2       # minimal frame yang cocok ke peserta yang sama
DETECT_UPSCALE = 2.2          # faktor upscale bila wajah tak terdeteksi/terlalu kecil
MIN_BRIGHTNESS = 28           # batas kegelapan frame (0-255)
MAX_BRIGHTNESS = 235
MIN_SHARPNESS = 10            # batas keburaman (varians Laplacian ROI wajah)
ENHANCE_BELOW = 60            # frame lebih gelap dari ini diterangi CLAHE
EMBED_UPSCALE_BELOW = 80      # wajah lebih kecil dari ini (px) di-upscale 2x utk embedding

# ---- Kehadiran (default awal; diubah admin lewat menu Pengaturan) ----
JAM_DATANG_DEFAULT = "08:00"  # lewat dari jam ini -> status masuk "Terlambat"
JAM_PULANG_DEFAULT = "17:00"  # pulang sebelum jam ini -> status pulang "Pulang Cepat"

# ---- Liveness (anti-foto) ----
CLIENT_FRAME_MS = 160         # interval kirim frame dari browser (ms)
SESSION_TTL_S = 120           # sesi absensi hangus setelah ini
FRAME_GAP_MAX_S = 5.0         # jeda antar frame maksimal sebelum sesi dianggap putus

ALIGN_TIMEOUT_S = 15.0        # batas waktu mencari wajah + baseline
ALIGN_NEED_FRAMES = 10        # jumlah frame untuk mengukur baseline
ALIGN_MIN_DURATION_S = 1.2    # durasi minimal pengukuran baseline

CHALLENGE_TIMEOUT_S = 8.0     # batas waktu tiap tantangan
RETURN_TIMEOUT_S = 4.0        # batas waktu kembali ke posisi netral

BLINK_CLOSED_RATIO = 0.70     # mata dianggap tertutup bila EAR < 70% baseline
BLINK_CLOSED_ABS = 0.21       # ... dan di bawah nilai absolut ini
BLINK_MIN_DROP = 0.22         # penurunan minimum relatif terhadap baseline
TURN_DELTA = 0.16             # perubahan proxy yaw untuk lolos tantangan toleh
TURN_RETURN = 0.06            # kembali mendekati netral
NOD_DELTA = 0.10              # perubahan proxy pitch untuk tantangan angguk
NOD_RETURN = 0.05
SMILE_RATIO = 1.14            # lebar mulut membesar >= 14% dari baseline
SMILE_RETURN = 1.06
STATIC_VARIATION_MIN = 0.0015 # variasi sinyal minimum (anti frame identik/static)

# ---- Server ----
HOST = os.environ.get("ABS_HOST", "127.0.0.1")  # di balik nginx biarkan 127.0.0.1
PORT = int(os.environ.get("ABS_PORT", "5050"))

for _d in (DATA_DIR, FOTO_DIR, SNAPSHOT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
