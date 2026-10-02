"""Liveness (anti-foto): sinyal wajah dari landmark FaceMesh + mesin status
tantangan acak yang diverifikasi DI SERVER.

Prinsip: foto statis tidak dapat menghasilkan transisi sinyal wajah yang
diminta tantangan (mis. kedipan butuh EAR terbuka->tertutup->terbuka,
toleh butuh perubahan geometri proyeksi kepala). Semua keputusan dihitung
dari frame yang dikirim browser; browser hanya menampilkan instruksi.
"""
import random

import numpy as np

import config

# ---- Indeks landmark MediaPipe FaceMesh (468 titik) ----
R_EYE = [33, 160, 158, 133, 153, 144]    # mata kanan (sisi kiri citra)
L_EYE = [362, 385, 387, 263, 373, 380]   # mata kiri
NOSE_TIP = 1
R_EYE_OUT, L_EYE_OUT = 33, 263           # sudut mata luar
MOUTH_R, MOUTH_L = 61, 291               # sudut mulut

CH_BLINK, CH_TURN_LEFT, CH_TURN_RIGHT, CH_NOD, CH_SMILE = (
    "BLINK", "TURN_LEFT", "TURN_RIGHT", "NOD", "SMILE",
)

INSTRUCTION_TEXT = {
    CH_BLINK: "Kedipkan mata Anda",
    CH_TURN_LEFT: "Tolah kepala ke kiri Anda",
    CH_TURN_RIGHT: "Tolah kepala ke kanan Anda",
    CH_NOD: "Anggukkan kepala ke bawah",
    CH_SMILE: "Tersenyumlah",
}
INSTRUCTION_ICON = {
    CH_BLINK: "😉", CH_TURN_LEFT: "⬅️", CH_TURN_RIGHT: "➡️",
    CH_NOD: "⬇️", CH_SMILE: "😄",
}


def _ear(pts: np.ndarray, idx: list[int]) -> float:
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in idx)
    vertical = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    horizontal = 2.0 * np.linalg.norm(p1 - p4) + 1e-9
    return float(vertical / horizontal)


def compute_signals(lm: np.ndarray) -> dict:
    """Sinyal liveness dari landmark (koordinat piksel)."""
    eye_mid = (lm[R_EYE_OUT] + lm[L_EYE_OUT]) / 2.0
    eye_dist = np.linalg.norm(lm[R_EYE_OUT] - lm[L_EYE_OUT]) + 1e-9
    return {
        "ear": (_ear(lm, R_EYE) + _ear(lm, L_EYE)) / 2.0,
        # >0 saat kepala menoleh ke kiri orang (hidung bergeser ke kanan citra mentah)
        "yaw_proxy": float((lm[NOSE_TIP][0] - eye_mid[0]) / eye_dist),
        # membesar saat kepala menunduk
        "pitch_proxy": float((lm[NOSE_TIP][1] - eye_mid[1]) / eye_dist),
        "smile_proxy": float(np.linalg.norm(lm[MOUTH_R] - lm[MOUTH_L]) / eye_dist),
    }


# ---------------- Pemeriksa tantangan ----------------
class BlinkChallenge:
    name = CH_BLINK

    def __init__(self, base_ear: float):
        self.closed_thr = min(config.BLINK_CLOSED_ABS, base_ear * config.BLINK_CLOSED_RATIO)
        self.min_ear = base_ear * (1.0 - config.BLINK_MIN_DROP)
        self.state = "need_open"
        self.open_run = 0
        self.saw_close = False
        self.min_seen = 1e9

    def feed(self, s: dict) -> str:
        closed = s["ear"] < self.closed_thr
        if self.state == "need_open":
            self.open_run = self.open_run + 1 if not closed else 0
            if self.open_run >= 2:
                self.state = "wait_close"
            return "waiting"
        # state == wait_close
        if closed:
            self.saw_close = True
            self.min_seen = min(self.min_seen, s["ear"])
        elif self.saw_close:
            # mata terbuka kembali; lolos bila kedipannya cukup dalam
            if self.min_seen <= self.min_ear:
                return "passed"
            self.saw_close = False  # terlalu dangkal; tunggu kedipan berikutnya
            self.min_seen = 1e9
        return "waiting"


class TurnChallenge:
    def __init__(self, base_yaw: float, sign: int, name: str):
        self.base_yaw = base_yaw
        self.sign = sign
        self.name = name
        self.performed = False

    def feed(self, s: dict) -> str:
        delta = (s["yaw_proxy"] - self.base_yaw) * self.sign
        if not self.performed:
            if delta >= config.TURN_DELTA:
                self.performed = True
                return "performed"
            return "waiting"
        if abs(s["yaw_proxy"] - self.base_yaw) < config.TURN_RETURN:
            return "passed"
        return "waiting"


class NodChallenge:
    name = CH_NOD

    def __init__(self, base_pitch: float):
        self.base_pitch = base_pitch
        self.performed = False

    def feed(self, s: dict) -> str:
        delta = s["pitch_proxy"] - self.base_pitch
        if not self.performed:
            if delta >= config.NOD_DELTA:
                self.performed = True
                return "performed"
            return "waiting"
        if abs(s["pitch_proxy"] - self.base_pitch) < config.NOD_RETURN:
            return "passed"
        return "waiting"


class SmileChallenge:
    name = CH_SMILE

    def __init__(self, base_smile: float):
        self.base_smile = max(base_smile, 1e-6)
        self.performed = False

    def feed(self, s: dict) -> str:
        ratio = s["smile_proxy"] / self.base_smile
        if not self.performed:
            if ratio >= config.SMILE_RATIO and (s["smile_proxy"] - self.base_smile) >= 0.03:
                self.performed = True
                return "performed"
            return "waiting"
        if ratio <= config.SMILE_RETURN:
            return "passed"
        return "waiting"


class LivenessSession:
    """Mesin status satu sesi liveness: align (baseline) -> tantangan -> verified."""

    def __init__(self):
        self.state = "align"
        self.samples: list[dict] = []
        self.challenges: list = []
        self.idx = 0
        self.phase_start: float | None = None  # diisi waktu (detik) oleh pemanggil
        self.baseline: dict | None = None

    # -- dipanggil pemanggil dengan waktu monotonik --
    def feed(self, signals: dict, t: float) -> dict:
        if self.state == "align":
            if self.phase_start is None:
                self.phase_start = t
            self.samples.append(signals)
            need = (
                len(self.samples) >= config.ALIGN_NEED_FRAMES
                and (t - self.phase_start) >= config.ALIGN_MIN_DURATION_S
            )
            if need:
                self._build_baseline()
            return self._response()

        if self.state == "challenge":
            cur = self.challenges[self.idx]
            if self.phase_start is None:
                self.phase_start = t
            result = cur.feed(signals)
            if result == "passed":
                self.idx += 1
                self.phase_start = t
                if self.idx >= len(self.challenges):
                    self.state = "verified"
            return self._response()

        return self._response()  # verified / kondisi lain

    def _build_baseline(self):
        keys = ("ear", "yaw_proxy", "pitch_proxy", "smile_proxy")
        base = {k: float(np.median([s[k] for s in self.samples])) for k in keys}
        std = sum(
            float(np.std([s[k] for s in self.samples])) for k in ("ear", "yaw_proxy", "smile_proxy")
        )
        if std < config.STATIC_VARIATION_MIN:
            # sinyal nyaris tidak bervariasi -> kemungkinan besar frame statis
            # (foto). Buang sampel: baseline hanya boleh dibangun dari frame
            # yang bervariasi alami. Sesi akan gagal lewat timeout align.
            self.samples = []
            return
        self.baseline = base
        extra = random.choice(
            [
                TurnChallenge(base["yaw_proxy"], +1, CH_TURN_LEFT),
                TurnChallenge(base["yaw_proxy"], -1, CH_TURN_RIGHT),
                NodChallenge(base["pitch_proxy"]),
                SmileChallenge(base["smile_proxy"]),
            ]
        )
        # Kedip selalu wajib: foto tidak dapat mengedip.
        self.challenges = [BlinkChallenge(base["ear"]), extra]
        self.state = "challenge"
        self.idx = 0

    def current_challenge(self):
        if self.state == "challenge" and self.idx < len(self.challenges):
            return self.challenges[self.idx]
        return None

    def _response(self) -> dict:
        cur = self.current_challenge()
        return {
            "state": self.state,
            "instruction": INSTRUCTION_TEXT.get(cur.name) if cur else "Posisikan wajah di dalam bingkai",
            "instruction_icon": INSTRUCTION_ICON.get(cur.name, "🙂") if cur else "🙂",
            "challenge_index": self.idx,
            "challenge_total": len(self.challenges),
            "performed": getattr(cur, "performed", False),
            "baseline": self.baseline,
        }

    def yaw_is_neutral(self, signals: dict) -> bool:
        """Frame depan (frontal) — dipakai memilih kandidat frame identitas."""
        if self.baseline is None:
            return True
        return abs(signals["yaw_proxy"] - self.baseline["yaw_proxy"]) < 0.05
