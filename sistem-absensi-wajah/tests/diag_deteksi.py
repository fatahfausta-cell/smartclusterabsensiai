"""Diagnosis deteksi wajah pada frame menyerupai webcam.

Mensimulasikan apa yang dikirim browser: resize ke lebar 640, JPEG quality 0.72.
Menguji berbagai skala jarak (wajah mengecil) + gelap + blur.
Jalankan: .venv/Scripts/python tests/diag_deteksi.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

import config
from face_engine import engine

ASSET = Path(__file__).parent / "assets"


def frame_webcam(img, skala=1.0, gelap=1.0, blur=0, kval=0.72, lebar=640):
    """Ubah foto jadi frame mirip kamera: kecilkan, gelapkan, blur, JPEG."""
    h, w = img.shape[:2]
    kecil = cv2.resize(img, (int(w * skala), int(h * skala)))
    if kecil.shape[1] > lebar:
        r = lebar / kecil.shape[1]
        kecil = cv2.resize(kecil, (lebar, int(kecil.shape[0] * r)))
    if gelap != 1.0:
        kecil = (kecil.astype(np.float32) * gelap).astype(np.uint8)
    if blur > 0:
        kecil = cv2.GaussianBlur(kecil, (blur, blur), 0)
    _, enc = cv2.imencode(".jpg", kecil, [cv2.IMWRITE_JPEG_QUALITY, int(kval * 100)])
    return cv2.imdecode(np.frombuffer(enc.tobytes(), np.uint8), cv2.IMREAD_COLOR)


def lap(img, face):
    x1, y1, x2, y2 = face.bbox.astype(int)
    roi = img[max(0, y1):y2, max(0, x1):x2]
    return float(cv2.Laplacian(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def main():
    engine.load()
    asli = engine.decode_image_bytes((ASSET / "obama.jpg").read_bytes())

    print(f"ambang aktif: min_size={config.FACE_MIN_SIZE} "
          f"terang={config.MIN_BRIGHTNESS}-{config.MAX_BRIGHTNESS} "
          f"tajam>={config.MIN_SHARPNESS} upscale={config.DETECT_UPSCALE}")
    print(f"{'skenario':<28} {'deteksi':<7} {'tinggi wajah':<12} {'skor':<5} {'terang':<7} {'ketajaman':<9} {'gate kualitas':<18} landmark")
    for nama, kw in [
        ("normal (dekat)", dict(skala=1.0)),
        ("agak jauh", dict(skala=0.55)),
        ("jauh", dict(skala=0.35)),
        ("sangat jauh", dict(skala=0.22)),
        ("redup", dict(skala=0.6, gelap=0.45)),
        ("sangat redup", dict(skala=0.6, gelap=0.25)),
        ("sedikit blur", dict(skala=0.6, blur=5)),
        ("blur gerak", dict(skala=0.6, blur=9)),
        ("jauh + agak blur", dict(skala=0.4, blur=5)),
        ("jauh + redup", dict(skala=0.4, gelap=0.5)),
        # --- kondisi ekstrem (webcam murah / HP jauh) ---
        ("res 480 + jauh", dict(skala=0.35, lebar=480)),
        ("res 480 + sangat jauh", dict(skala=0.22, lebar=480)),
        ("res 360 + jauh", dict(skala=0.35, lebar=360)),
        ("res 360 + sangat jauh", dict(skala=0.24, lebar=360)),
        ("res 480 + jpeg kasar", dict(skala=0.45, lebar=480, kval=0.5)),
        ("res 480 + blur berat", dict(skala=0.45, lebar=480, blur=7)),
        ("res 480 + gelap berat", dict(skala=0.5, lebar=480, gelap=0.3)),
        ("res 480 + gelap + blur", dict(skala=0.5, lebar=480, gelap=0.35, blur=5)),
    ]:
        f = frame_webcam(asli, **kw)
        faces = engine.detect_robust(f)
        if not faces:
            print(f"{nama:<28} GAGAL   -")
            continue
        fc = faces[0]
        x1, y1, x2, y2 = fc.bbox.astype(int)
        roi = f[max(0, y1):y2, max(0, x1):x2]
        terang = float(roi.mean())
        tajam = lap(f, fc)
        gate = []
        if fc.size < config.FACE_MIN_SIZE: gate.append(f"KECIL({fc.size:.0f}<{config.FACE_MIN_SIZE})")
        if terang < config.MIN_BRIGHTNESS: gate.append(f"GELAP({terang:.0f}<{config.MIN_BRIGHTNESS})")
        batas = max(4.0, config.MIN_SHARPNESS * min(1.0, fc.size / 90.0))
        if tajam < batas: gate.append(f"BLUR({tajam:.0f}<{batas:.0f})")
        lm = "OK" if engine.get_landmarks(f) is not None else "GAGAL"
        print(f"{nama:<28} OK      {fc.size:<12.0f} {fc.score:<5.2f} {terang:<7.0f} {tajam:<9.0f} {'; '.join(gate) or 'LOLOS':<18} {lm}")


if __name__ == "__main__":
    main()
