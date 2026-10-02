"""Uji face engine: identitas (match/mismatch), jumlah wajah, sinyal liveness.

Jalankan dari root proyek:
    .venv/Scripts/python tests/test_engine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from face_engine import engine
from liveness import compute_signals

ASSET = Path(__file__).parent / "assets"


def muat(nama: str) -> np.ndarray:
    return engine.decode_image_bytes((ASSET / nama).read_bytes())


def main():
    engine.load()
    ok = True

    # ---- 1. ekstraksi embedding ----
    emb = {}
    for nama in ("obama.jpg", "obama2.jpg", "biden.jpg"):
        e, face = engine.extract(muat(nama))
        emb[nama] = e
        print(f"[extract] {nama}: wajah {face.size:.0f}px skor det {face.score:.2f}")

    sama = engine.cosine(emb["obama.jpg"], emb["obama2.jpg"])
    beda = engine.cosine(emb["obama.jpg"], emb["biden.jpg"])
    print(f"[identitas] obama vs obama2 (orang SAMA) : {sama:.3f}  (harus >= 0.45)")
    print(f"[identitas] obama vs biden   (orang BEDA) : {beda:.3f}  (harus < 0.45)")
    ok &= sama >= 0.45
    ok &= beda < 0.45

    # ---- 2. jumlah wajah ----
    dua = engine.detect(muat("two_people.jpg"))
    print(f"[deteksi] two_people.jpg -> {len(dua)} wajah (harus 2)")
    ok &= len(dua) == 2

    # ---- 3. landmark & sinyal liveness pada wajah frontal ----
    lm = engine.get_landmarks(muat("obama.jpg"))
    assert lm is not None, "landmark tidak terdeteksi pada obama.jpg"
    sig = compute_signals(lm)
    print(f"[sinyal] ear={sig['ear']:.3f} (wajar 0.15-0.45) yaw={sig['yaw_proxy']:+.3f} "
          f"pitch={sig['pitch_proxy']:+.3f} smile={sig['smile_proxy']:.3f}")
    ok &= 0.12 < sig["ear"] < 0.5
    ok &= abs(sig["yaw_proxy"]) < 0.12
    ok &= 0.6 < sig["smile_proxy"] < 1.6

    # ---- 4. dekode data URI (alur kamera) ----
    import base64
    _, enc = cv2.imencode(".jpg", muat("obama2.jpg"))
    uri = "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode()
    img2 = engine.decode_data_uri(uri)
    e2, _ = engine.extract(img2)
    sim = engine.cosine(e2, emb["obama2.jpg"])
    print(f"[kamera-loop] data URI round-trip vs asli: {sim:.3f} (harus >= 0.95)")
    ok &= sim >= 0.95

    print("\nHASIL:", "SEMUA UJI LOLOS ✅" if ok else "ADA UJI GAGAL ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    import cv2  # dipakai di poin 4
    main()
