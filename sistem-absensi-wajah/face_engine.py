"""Face engine: deteksi wajah (YuNet) + embedding identitas (ArcFace ONNX)
+ landmark padat (MediaPipe FaceMesh) untuk liveness.

Semua model berjalan di CPU lewat ONNX Runtime / MediaPipe; hasil identitas
berupa vektor 512-d L2-normalized yang dibandingkan dengan cosine similarity.
"""
import base64
import threading
from io import BytesIO

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

import config


class FaceEngineError(Exception):
    """Error ramah-user (pesan bahasa Indonesia) untuk frontend."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# Titik referensi ArcFace 112x112 (mata kanan, kiri, hidung, sudut mulut kanan,
# kiri — koordinat citra, urutan sama dengan landmark YuNet).
ARCFACE_REF = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


class FaceInfo:
    __slots__ = ("bbox", "kps", "score", "size")

    def __init__(self, bbox: np.ndarray, kps: np.ndarray, score: float):
        self.bbox = bbox  # x1,y1,x2,y2
        self.kps = kps    # (5,2) landmark YuNet
        self.score = score
        self.size = float(bbox[3] - bbox[1])


class FaceEngine:
    def __init__(self):
        self._detector = None
        self._embed_session = None
        self._embed_input = None
        self._mesh = None
        self._clahe = None
        self._lock = threading.RLock()
        self.ready = False
        self.error: str | None = None

    # ---------- lifecycle ----------
    def load(self):
        try:
            self.error = None
            self._detector = cv2.FaceDetectorYN.create(
                str(config.YUNET_PATH), "", (320, 320), score_threshold=0.6, top_k=50
            )
            so = ort.SessionOptions()
            so.intra_op_num_threads = max(1, min(4, __import__("os").cpu_count() or 2))
            self._embed_session = ort.InferenceSession(
                str(config.ARCFACE_PATH), sess_options=so,
                providers=["CPUExecutionProvider"],
            )
            self._embed_input = self._embed_session.get_inputs()[0].name

            import mediapipe as mp  # API Tasks (mediapipe >= 1.0)
            from mediapipe.tasks.python import vision
            opts = vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(config.FACEMESH_PATH)),
                num_faces=1,
            )
            self._mp = mp
            self._mesh = vision.FaceLandmarker.create_from_options(opts)
            self._clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            self.ready = True
            print("[face] engine siap: YuNet + ArcFace(w600k_mbf) + FaceMesh", flush=True)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            print(f"[face] gagal memuat model: {self.error}", flush=True)
            raise

    def ensure_ready(self):
        if not self.ready:
            raise FaceEngineError(
                "Model wajah belum siap" + (f" ({self.error})" if self.error else "")
            )

    # ---------- decoding ----------
    @staticmethod
    def decode_image_bytes(raw: bytes) -> np.ndarray:
        """Bytes gambar -> BGR, menghormati orientasi EXIF (foto kamera/HP)."""
        try:
            pil = ImageOps.exif_transpose(Image.open(BytesIO(raw)))
            if pil.mode != "RGB":
                pil = pil.convert("RGB")
            return np.asarray(pil, dtype=np.uint8)[:, :, ::-1].copy()
        except FaceEngineError:
            raise
        except Exception:
            buf = np.frombuffer(raw, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if img is None:
                raise FaceEngineError("Berkas gambar tidak valid.")
            return img

    @classmethod
    def decode_data_uri(cls, data_uri: str) -> np.ndarray:
        """data:image/jpeg;base64,... -> gambar BGR."""
        try:
            b64 = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
            return cls.decode_image_bytes(base64.b64decode(b64))
        except FaceEngineError:
            raise
        except Exception as e:
            raise FaceEngineError(f"Frame kamera tidak dapat dibaca: {e}")

    # ---------- deteksi & kualitas ----------
    def detect(self, img: np.ndarray, min_score: float = 0.6) -> list[FaceInfo]:
        h, w = img.shape[:2]
        with self._lock:
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img)
        if faces is None:
            return []
        out = []
        for f in faces:
            if f[14] < min_score:
                continue
            bbox = np.array([f[0], f[1], f[0] + f[2], f[1] + f[3]], dtype=np.float32)
            kps = np.array(f[4:14], dtype=np.float32).reshape(5, 2)
            out.append(FaceInfo(bbox, kps, float(f[14])))
        out.sort(key=lambda x: x.size, reverse=True)
        return out

    def detect_robust(self, img: np.ndarray) -> list[FaceInfo]:
        """Deteksi dengan fallback upscale + penerangan CLAHE.

        Bila deteksi normal gagal atau wajah terbesar di bawah ambang ukuran,
        gambar diperbesar (dan diterangi bila gelap) lalu dideteksi ulang;
        koordinat dipetakan balik ke skala asli supaya pemanggil tidak peduli.
        """
        faces = self.detect(img)
        if faces and faces[0].size >= config.FACE_MIN_SIZE:
            return faces

        h, w = img.shape[:2]
        if w >= 1600:  # gambar besar tidak butuh bantuan upscale
            return faces
        up = cv2.resize(img, (int(w * config.DETECT_UPSCALE),
                              int(h * config.DETECT_UPSCALE)),
                        interpolation=cv2.INTER_CUBIC)
        if float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) < config.ENHANCE_BELOW:
            up = self._enhance(up)
        faces_up = self.detect(up)
        if not faces_up:
            return faces  # tetap hasil skala asli (mungkin kosong)

        k = 1.0 / config.DETECT_UPSCALE
        remap = []
        for f in faces_up:
            remap.append(FaceInfo(f.bbox * k, f.kps * k, f.score))
        remap.sort(key=lambda x: x.size, reverse=True)

        # gabungkan: pilih himpunan dengan wajah terbesar
        best_asli = faces[0].size if faces else 0.0
        best_up = remap[0].size if remap else 0.0
        if best_up > best_asli:
            return remap
        return faces

    def check_quality(self, img: np.ndarray, face: FaceInfo):
        """Validasi kualitas wajah — laporkan masalah paling memberatkan.

        Ambang ketajaman adaptif ukuran wajah: wajah kecil (kamera jauh /
        resolusi rendah) secara alami punya varians Laplacian lebih rendah,
        maka ambangnya diturunkan proporsional.
        """
        if face.size < config.FACE_MIN_SIZE:
            raise FaceEngineError("Wajah terlalu jauh — mendekatlah sedikit ke kamera.")
        x1, y1, x2, y2 = face.bbox.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            raise FaceEngineError("Wajah tidak terdeteksi dengan benar.")
        brightness = float(roi.mean())
        if brightness < config.MIN_BRIGHTNESS:
            raise FaceEngineError("Terlalu gelap — nyalakan lampu / cari tempat lebih terang.")
        if brightness > config.MAX_BRIGHTNESS:
            raise FaceEngineError("Pencahayaan terlalu menyilaukan.")
        sharpness = float(
            cv2.Laplacian(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
        )
        batas_tajam = max(4.0, config.MIN_SHARPNESS * min(1.0, face.size / 90.0))
        if sharpness < batas_tajam:
            raise FaceEngineError("Gambar kurang tajam — tahan kepala agar stabil.")

    # ---------- embedding identitas ----------
    def align(self, img: np.ndarray, kps: np.ndarray) -> np.ndarray:
        M, _ = cv2.estimateAffinePartial2D(
            kps.astype(np.float32), ARCFACE_REF, method=cv2.LMEDS
        )
        if M is None:
            raise FaceEngineError("Gagal menyelaraskan wajah.")
        return cv2.warpAffine(img, M, (112, 112), borderValue=0)

    def embed_aligned(self, aligned: np.ndarray) -> np.ndarray:
        x = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)
        x = (x / 127.5) - 1.0
        x = x.transpose(2, 0, 1)[None]
        with self._lock:
            emb = self._embed_session.run(None, {self._embed_input: x})[0][0]
        n = np.linalg.norm(emb)
        if n < 1e-6:
            raise FaceEngineError("Gagal membuat embedding wajah.")
        return (emb / n).astype(np.float32)

    def embed_face(self, img: np.ndarray, face: FaceInfo) -> np.ndarray:
        """Embedding satu wajah; wajah kecil di-upscale dulu agar warp 112x112 memadai."""
        if face.size < config.EMBED_UPSCALE_BELOW:
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            kps = face.kps * 2.0
        else:
            kps = face.kps
        return self.embed_aligned(self.align(img, kps))

    def extract(self, img: np.ndarray) -> tuple[np.ndarray, FaceInfo]:
        """Embedding wajah TERBESAR pada gambar + validasi kualitas."""
        self.ensure_ready()
        faces = self.detect_robust(img)
        if not faces:
            raise FaceEngineError("Wajah tidak terdeteksi. Pastikan wajah terlihat jelas.")
        if len(faces) > 1:
            raise FaceEngineError("Terdeteksi lebih dari satu wajah pada foto.")
        face = faces[0]
        self.check_quality(img, face)
        return self.embed_face(img, face), face

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    @staticmethod
    def embed_to_bytes(emb: np.ndarray) -> bytes:
        return emb.astype(np.float32).tobytes()

    @staticmethod
    def bytes_to_embed(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32).copy()

    # ---------- landmark padat (liveness) ----------
    def _enhance(self, img: np.ndarray) -> np.ndarray:
        """Terangkan frame gelap (CLAHE pada kanal L LAB)."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = self._clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _landmarks_once(self, img: np.ndarray) -> np.ndarray | None:
        with self._lock:
            mp_img = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB,
                data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
            )
            res = self._mesh.detect(mp_img)
        if not res.face_landmarks:
            return None
        h, w = img.shape[:2]
        return np.array(
            [[p.x * w, p.y * h] for p in res.face_landmarks[0]], dtype=np.float64
        )

    def get_landmarks(self, img: np.ndarray) -> np.ndarray | None:
        """Landmark FaceLandmarker (478 titik) dalam koordinat piksel asli.

        Tahan resolusi rendah / gelap / kurang tajam: bila percobaan pertama
        gagal, ulangi pada versi 2x-upscale (diterangi CLAHE bila gelap);
        koordinat hasil dipetakan balik ke skala asli.
        """
        pts = self._landmarks_once(img)
        if pts is not None:
            return pts

        h, w = img.shape[:2]
        if w >= 1400:
            return None  # sudah resolusi tinggi, retry tak akan menolong
        up = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        if float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) < config.ENHANCE_BELOW:
            up = self._enhance(up)
        pts = self._landmarks_once(up)
        if pts is None:
            return None
        return pts * 0.5


engine = FaceEngine()
