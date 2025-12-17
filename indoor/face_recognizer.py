# indoor/face_recognizer.py
# ============================================================
#   FACE RECOGNIZER – InsightFace wrapper
#   - Enhancement (brighten + sharpen)
#   - Resize 112x112
#   - Uses FaceAnalysis; loads .npy embeddings from data/embeddings
# ============================================================

import cv2
import numpy as np
from numpy.linalg import norm
from insightface.app import FaceAnalysis
from config.paths import get_data_paths
from config.settings import SETTINGS
import os

class FaceRecognizer:

    def __init__(self):
        paths = get_data_paths()

        # debug flags (set before loading embeddings)
        self.debug = SETTINGS.get("debug_mode", False)
        self.debug_save_unknown = SETTINGS.get("debug_save_unknown", False)
        if self.debug and self.debug_save_unknown:
            os.makedirs("debug_faces", exist_ok=True)

        # Prepare InsightFace app (try GPU then CPU)
        try:
            providers = ["CUDAExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=0, det_size=(160, 160))
        except Exception:
            providers = ["CPUExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=-1, det_size=(160, 160))

        # Embedding DB (name -> normalized vector)
        self.db = {}
        # threshold dasar (kalau skor < ini → UNKNOWN)
        self.threshold = SETTINGS.get("face_recog_threshold", 0.38)

        self.load_embeddings(paths["embeddings_dir"])

    def load_embeddings(self, emb_dir):
        import os
        self.db = {}
        for f in os.listdir(emb_dir):
            if not f.endswith(".npy"):
                continue
            try:
                v = np.load(os.path.join(emb_dir, f)).astype(np.float32)
                v = v / (norm(v) + 1e-6)
                self.db[f[:-4]] = v
            except Exception as e:
                if self.debug:
                    print(f"[FaceRecognizer] skip {f}: {e}")
        if self.debug:
            print(f"[FaceRecognizer] Loaded {len(self.db)} identities from {emb_dir}")

    def enhance_fast(self, img):
        # match your old enhancer: brighten + sharpen
        img = cv2.convertScaleAbs(img, alpha=1.55, beta=32)
        k = np.array([[0, -1, 0],
                      [-1, 5, -1],
                      [0, -1, 0]], dtype=np.float32)
        return cv2.filter2D(img, -1, k)

    def get_embedding(self, rgb):
        """
        Input: RGB crop (numpy)
        Return: normalized embedding (float32) or None
        """
        if rgb is None or rgb.size == 0:
            return None
        try:
            # convert to BGR for our enhancer then to 112x112 RGB for inference
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            bgr = self.enhance_fast(bgr)
            face = cv2.resize(bgr, (112, 112))
            rgb2 = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)

            det = self.app.get(rgb2)
            if not det:
                return None
            emb = det[0].embedding
            if emb is None:
                return None
            emb = emb.astype(np.float32)
            return emb / (norm(emb) + 1e-6)
        except Exception as e:
            if self.debug:
                print(f"[FaceRecognizer] get_embedding error: {e}")
            return None

    def identify(self, emb):
        """
        Return (name, score) or (None, score) if not confident.
        Score is cosine similarity (higher better).
        """
        if emb is None or len(self.db) == 0:
            return None, 0.0

        best_name = None
        best_score = -1.0
        for name, dbv in self.db.items():
            s = float(np.dot(emb, dbv))
            if s > best_score:
                best_score = s
                best_name = name

        if best_score < self.threshold:
            # not confident
            if self.debug and self.debug_save_unknown:
                # optionally save the unknown crop for inspection (not implemented path arg here)
                pass
            return None, best_score

        return best_name, best_score
