# indoor/registry.py
import os
import numpy as np
from typing import Dict, List, Optional

from config.paths import EMBED_DIR


class UserRegistry:
    """
    Registry ringan untuk manage user face embedding.
    - 1 user = 1 file .npy di data/embeddings/
    - Nama file = <nama_user>.npy
    - Dipakai bareng FaceRecognizer + pipeline ID Lock
    """

    def __init__(self):
        os.makedirs(EMBED_DIR, exist_ok=True)
        self._cache: Dict[str, np.ndarray] = {}
        self._load_all()

    # ---------------------------------------------------------
    # INTERNAL: LOAD SEMUA EMBEDDING KE MEMORY (RINGAN)
    # ---------------------------------------------------------
    def _load_all(self):
        self._cache.clear()
        for fname in os.listdir(EMBED_DIR):
            if not fname.endswith(".npy"):
                continue
            name = fname.replace(".npy", "")
            path = os.path.join(EMBED_DIR, fname)
            try:
                emb = np.load(path)
                if emb is not None:
                    self._cache[name] = emb.astype(np.float32)
            except Exception as e:
                print(f"[REGISTRY] Skip {fname}: {e}")

        print(f"[REGISTRY] Loaded {len(self._cache)} users from {EMBED_DIR}")

    # ---------------------------------------------------------
    # PUBLIC: LIST + CEK USER
    # ---------------------------------------------------------
    def list_users(self) -> List[str]:
        return sorted(self._cache.keys())

    def exists(self, name: str) -> bool:
        return name in self._cache

    # ---------------------------------------------------------
    # GET / SET EMBEDDING
    # ---------------------------------------------------------
    def get_embedding(self, name: str) -> Optional[np.ndarray]:
        return self._cache.get(name, None)

    def save_embedding(self, name: str, embedding: np.ndarray, overwrite: bool = False) -> bool:
        """
        Simpan 1 embedding .npy per user.
        - name: nama user (tanpa .npy)
        - embedding: vector 512D dari InsightFace
        """
        if (not overwrite) and self.exists(name):
            print(f"[REGISTRY] User '{name}' sudah ada. Set overwrite=True jika ingin ganti.")
            return False

        if embedding is None:
            print("[REGISTRY] Embedding kosong, tidak disimpan.")
            return False

        path = os.path.join(EMBED_DIR, f"{name}.npy")
        np.save(path, embedding.astype(np.float32))
        self._cache[name] = embedding.astype(np.float32)

        print(f"[REGISTRY] Saved embedding for '{name}' → {path}")
        return True

    # ---------------------------------------------------------
    # HAPUS USER
    # ---------------------------------------------------------
    def delete_user(self, name: str) -> bool:
        if not self.exists(name):
            print(f"[REGISTRY] User '{name}' tidak ditemukan.")
            return False

        path = os.path.join(EMBED_DIR, f"{name}.npy")
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"[REGISTRY] Gagal hapus file {path}: {e}")

        if name in self._cache:
            del self._cache[name]

        print(f"[REGISTRY] Deleted user '{name}'")
        return True

    # ---------------------------------------------------------
    # RELOAD (Jika ada perubahan eksternal)
    # ---------------------------------------------------------
    def reload(self):
        """
        Reload ulang semua .npy dari disk ke cache.
        Dipanggil kalau kamu lupa atau ada edit manual di folder.
        """
        self._load_all()
