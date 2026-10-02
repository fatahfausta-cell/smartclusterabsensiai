"""Uji mesin status liveness dengan urutan sinyal sintetis.

Mensimulasikan: (a) frame foto statis (sinyal identik) -> harus DITOLAK di align;
(b) wajah hidup: jitter natural -> kedip -> toleh kiri -> harus TERVERIFIKASI;
(c) wajah hidup tapi tidak pernah kedip -> tantangan BLINK tidak pernah lolos.

Jalankan: .venv/Scripts/python tests/test_liveness.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import liveness
from liveness import LivenessSession

BASE = {"ear": 0.30, "yaw_proxy": 0.00, "pitch_proxy": 0.47, "smile_proxy": 0.90}


def sinyal(**ubah):
    s = dict(BASE)
    s.update(ubah)
    return s


def jitter(kecil=True):
    amp = 0.004 if kecil else 0.02  # mikro-variasi wajah hidup
    return sinyal(
        ear=BASE["ear"] + random.uniform(-amp, amp),
        yaw_proxy=BASE["yaw_proxy"] + random.uniform(-amp, amp),
        pitch_proxy=BASE["pitch_proxy"] + random.uniform(-amp, amp),
        smile_proxy=BASE["smile_proxy"] + random.uniform(-amp, amp),
    )


def uji_statis():
    """Foto statis: sinyal identik -> tidak boleh lolos tahap align."""
    random.seed(1)
    ses = LivenessSession()
    t = 0.0
    for _ in range(200):
        ses.feed(sinyal(), t)
        t += 0.16
    lolos = ses.state != "align"
    print(f"[statis ] setelah 200 frame identik -> state={ses.state} "
          f"({'LOLOS (GAGAL UJI ❌)' if lolos else 'TERTAHAN DI ALIGN ✅'})")
    return not lolos


def uji_hidup():
    """Wajah hidup: jitter -> kedip -> toleh kiri (challenge ke-2 dipatok) -> verified."""
    random.seed(2)
    liveness.random.choice = lambda seq: seq[0]  # pastikan tantangan ke-2 = TURN_LEFT
    ses = LivenessSession()
    t = 0.0

    # fase align: 12 frame jitter natural
    for _ in range(12):
        r = ses.feed(jitter(), t)
        t += 0.16
    ok_align = ses.state == "challenge"
    print(f"[hidup  ] align -> {ses.state}, tantangan: "
          f"{[c.name for c in ses.challenges]} {'✅' if ok_align else '❌'}")
    if not ok_align:
        return False

    # tantangan 1: BLINK — terbuka(2) -> tertutup(2) -> terbuka(2)
    urutan = [jitter() for _ in range(2)] + \
             [sinyal(ear=0.08, yaw_proxy=0.01) for _ in range(2)] + \
             [jitter() for _ in range(2)]
    for sg in urutan:
        r = ses.feed(sg, t)
        t += 0.16
    ok_blink = r["challenge_index"] == 1
    print(f"[hidup  ] setelah kedip -> tantangan ke-{r['challenge_index']+1 if ok_blink else 1} "
          f"({'BLINK LOLOS ✅' if ok_blink else 'BLINK GAGAL ❌'})")
    if not ok_blink:
        return False

    # tantangan 2: TURN_LEFT — toleh lalu kembali netral
    for sg in [sinyal(yaw_proxy=0.28) for _ in range(2)] + \
              [sinyal(yaw_proxy=0.22)] + [jitter() for _ in range(3)]:
        r = ses.feed(sg, t)
        t += 0.16
    ok_ver = ses.state == "verified"
    print(f"[hidup  ] setelah toleh+kembali -> state={ses.state} "
          f"({'TERVERIFIKASI ✅' if ok_ver else 'GAGAL ❌'})")
    return ok_ver


def uji_tidak_kedip():
    """Wajah 'hidup' (jitter) tapi tak pernah kedip -> BLINK tak pernah lolos."""
    random.seed(3)
    liveness.random.choice = lambda seq: seq[0]
    ses = LivenessSession()
    t = 0.0
    for _ in range(14):
        ses.feed(jitter(), t)
        t += 0.16
    if ses.state != "challenge":
        print("[noledip] gagal mencapai fase challenge ❌")
        return False
    for _ in range(60):  # 9.6 detik tanpa kedip
        r = ses.feed(jitter(), t)
        t += 0.16
    tetap = ses.state == "challenge" and r["challenge_index"] == 0
    print(f"[noledip] 60 frame tanpa kedip -> masih tantangan ke-1 "
          f"({'TERTAHAN ✅ (foto tidak bisa mengedip)' if tetap else 'LOLOS ❌'})")
    return tetap


if __name__ == "__main__":
    hasil = [uji_statis(), uji_hidup(), uji_tidak_kedip()]
    print("\nHASIL:", "SEMUA UJI LIVENESS LOLOS ✅" if all(hasil) else "ADA UJI GAGAL ❌")
    sys.exit(0 if all(hasil) else 1)
