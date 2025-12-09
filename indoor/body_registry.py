# indoor/body_registry.py
import os
from typing import Dict, Optional, Tuple

import numpy as np

from config.paths import BODY_EMB_DIR
from config.settings import SETTINGS


class BodyRegistry:
    """
    Registry global untuk embedding tubuh (OSNet) per identity.
    Fungsi:
      - Menyimpan profil badan setiap identity (nama)
      - Dipakai untuk ReID lintas kamera tanpa harus lihat wajah lagi
    Disimpan ke disk: data/body_embeddings/<nama>.npy
    """

    def __init__(self):
        os.makedirs(BODY_EMB_DIR, exist_ok=True)
        self._profiles: Dict[str, np.ndarray] = {}
        self.threshold: float = SETTINGS["body_reid_threshold"]
        self.momentum: float = SETTINGS["body_profile_momentum"]

        self._load_all()

    # -----------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------
    def _path_for(self, name: str) -> str:
        safe_name = str(name).replace("/", "_")
        return os.path.join(BODY_EMB_DIR, f"{safe_name}.npy")

    def _load_all(self) -> None:
        self._profiles.clear()
        for fname in os.listdir(BODY_EMB_DIR):
            if not fname.endswith(".npy"):
                continue
            name = fname[:-4]
            fpath = os.path.join(BODY_EMB_DIR, fname)
            try:
                emb = np.load(fpath).astype(np.float32)
                if emb is not None:
                    self._profiles[name] = emb
            except Exception as e:
                print(f"[BodyRegistry] Skip {fname}: {e}")
        print(f"[BodyRegistry] Loaded {len(self._profiles)} body profiles.")

    # -----------------------------------------------------
    # PUBLIC: UPDATE / SAVE PROFILE
    # -----------------------------------------------------
    def update_profile(self, name: str, emb: np.ndarray) -> None:
        """
        Update / tambah profil body untuk identity 'name'.
        Menggunakan exponential moving average:
            new = m * emb + (1-m) * old
        Lalu disimpan ke file .npy.
        """
        if emb is None:
            return

        emb = emb.astype(np.float32)
        if name not in self._profiles:
            new_emb = emb
        else:
            old = self._profiles[name]
            m = self.momentum
            new_emb = (m * emb + (1.0 - m) * old).astype(np.float32)

        self._profiles[name] = new_emb

        # Simpan ke disk
        path = self._path_for(name)
        try:
            np.save(path, new_emb)
        except Exception as e:
            print(f"[BodyRegistry] Failed to save {path}: {e}")

    # -----------------------------------------------------
    # PUBLIC: MATCH BODY EMBEDDING → IDENTITY
    # -----------------------------------------------------
    def match(self, emb: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Cari identity paling mirip berdasarkan body embedding.
        Return: (name, score_cosine) atau (None, score) jika tidak cukup mirip.
        """
        if emb is None or len(self._profiles) == 0:
            return None, 0.0

        emb = emb.astype(np.float32)
        norm = np.linalg.norm(emb) + 1e-6
        emb_norm = emb / norm

        best_name: Optional[str] = None
        best_score: float = -1.0

        for name, prof in self._profiles.items():
            prof_norm = prof / (np.linalg.norm(prof) + 1e-6)
            s = float(np.dot(emb_norm, prof_norm))
            if s > best_score:
                best_score = s
                best_name = name

        if best_score < self.threshold:
            return None, best_score

        return best_name, best_score

    # -----------------------------------------------------
    # UTILITY
    # -----------------------------------------------------
    def list_identities(self):
        return list(self._profiles.keys())

    def get_profile(self, name: str) -> Optional[np.ndarray]:
        return self._profiles.get(name, None)

    def clear(self):
        self._profiles.clear()
        for fname in os.listdir(BODY_EMB_DIR):
            if fname.endswith(".npy"):
                try:
                    os.remove(os.path.join(BODY_EMB_DIR, fname))
                except Exception as e:
                    print(f"[BodyRegistry] Failed to remove {fname}: {e}")


# Singleton global yang dipakai semua kamera (thread)
body_registry = BodyRegistry()
