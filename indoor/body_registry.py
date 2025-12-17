# indoor/body_registry.py
# ============================================================
# GLOBAL BODY REGISTRY (FINAL SAFE VERSION)
# ------------------------------------------------------------
# RULES:
# - Face = GLOBAL AUTHORITY (ONLY source of identity)
# - Body = GLOBAL PROPAGATION (ONLY for face-verified IDs)
# - Margin-based safety to prevent false identity
# - NEVER assign identity to person without prior face anchor
# ============================================================

import os
import numpy as np
from typing import Dict, Optional, Tuple
from config.paths import BODY_EMB_DIR
from config.settings import SETTINGS


class BodyRegistry:

    def __init__(self):
        os.makedirs(BODY_EMB_DIR, exist_ok=True)

        # name -> normalized embedding
        self._profiles: Dict[str, np.ndarray] = {}

        # 🔑 ONLY identities that have appeared with FACE
        self.face_verified = set()

        # thresholds
        self.threshold = SETTINGS["body_reid_threshold"]
        self.margin = SETTINGS["body_reid_margin"]
        self.momentum = SETTINGS["body_profile_momentum"]

        self._load_all()

    # ========================================================
    # PATH
    # ========================================================
    def _path(self, name: str):
        return os.path.join(BODY_EMB_DIR, f"{name}.npy")

    # ========================================================
    # LOAD EXISTING BODY PROFILES
    # ========================================================
    def _load_all(self):
        self._profiles.clear()

        if not os.path.exists(BODY_EMB_DIR):
            return

        for f in os.listdir(BODY_EMB_DIR):
            if f.endswith(".npy"):
                name = f[:-4]
                emb = np.load(self._path(name)).astype(np.float32)
                emb = emb / (np.linalg.norm(emb) + 1e-6)

                self._profiles[name] = emb
                # NOTE:
                # face_verified will be filled ONLY when face is seen again

        print(f"[BodyRegistry] Loaded {len(self._profiles)} body profiles")

    # ========================================================
    # 🔑 FACE → BODY (GLOBAL ANCHOR)
    # ========================================================
    def force_assign(self, name: str, emb: np.ndarray):
        """
        Called ONLY after successful FACE recognition.
        This is the ONLY place where identity is authorized.
        """
        if emb is None:
            return

        emb = emb.astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-6)

        if name in self._profiles:
            old = self._profiles[name]
            m = self.momentum
            emb = (m * emb + (1 - m) * old)
            emb = emb / (np.linalg.norm(emb) + 1e-6)

        self._profiles[name] = emb
        self.face_verified.add(name)          # 🔑 MARK AS FACE-VERIFIED
        np.save(self._path(name), emb)

        print(f"[BodyRegistry] FACE ANCHOR → BODY '{name}'")

    # ========================================================
    # BODY MATCH (SAFE, FACE-VERIFIED ONLY)
    # ========================================================
    def match(self, emb: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Body Re-ID is allowed ONLY for identities that:
        - Have been previously verified by FACE
        - Pass threshold AND margin test
        """
        if emb is None or not self._profiles or not self.face_verified:
            return None, 0.0

        emb = emb / (np.linalg.norm(emb) + 1e-6)

        scores = []
        for name, ref in self._profiles.items():
            # ❗ HARD SAFETY: skip identities without face anchor
            if name not in self.face_verified:
                continue

            s = float(np.dot(emb, ref))
            scores.append((name, s))

        if not scores:
            return None, 0.0

        scores.sort(key=lambda x: x[1], reverse=True)

        best_name, best_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0.0

        if (
            best_score >= self.threshold
            and (best_score - second_score) >= self.margin
        ):
            return best_name, best_score

        return None, best_score


# ============================================================
# SINGLETON
# ============================================================
body_registry = BodyRegistry()
