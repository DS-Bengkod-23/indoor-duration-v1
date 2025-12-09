# ============================================================
#   FACE RECOGNIZER – GPU LONG RANGE (FINAL)
#   • EXACT pipeline RealTimeMo (CUDA)
#   • Brighten + sharpen only (ringan)
#   • Resize 112x112 (default ArcFace)
#   • Threshold 0.40 → long range optimal
# ============================================================

import cv2
import numpy as np
from numpy.linalg import norm
from insightface.app import FaceAnalysis
from config.paths import get_data_paths
from config.settings import SETTINGS


class FaceRecognizer:

    def __init__(self):
        paths = get_data_paths()

        # GPU INSIGHTFACE (HUGE BOOST)
        self.app = FaceAnalysis(
            name="buffalo_s",
            providers=["CUDAExecutionProvider"]
        )
        self.app.prepare(ctx_id=0, det_size=(160,160))

        self.db = {}
        self.threshold = SETTINGS["face_recog_threshold"]

        self.load_embeddings(paths["embeddings_dir"])

    def load_embeddings(self, emb_dir):
        import os
        self.db = {}
        for f in os.listdir(emb_dir):
            if f.endswith(".npy"):
                v = np.load(os.path.join(emb_dir, f))
                self.db[f[:-4]] = v / norm(v)

    def enhance_fast(self, img):
        img = cv2.convertScaleAbs(img, alpha=1.65, beta=45)
        k = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
        return cv2.filter2D(img, -1, k)

    def get_embedding(self, rgb):

        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        bgr = self.enhance_fast(bgr)

        # ArcFace optimal size
        face = cv2.resize(bgr, (112,112))
        rgb2 = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)

        det = self.app.get(rgb2)
        if not det:
            return None

        emb = det[0].embedding
        if emb is None:
            return None

        return emb / norm(emb)

    def identify(self, emb):
        if emb is None:
            return None, 0

        best, score = None, -1
        for name, dbv in self.db.items():
            s = float(np.dot(emb, dbv))
            if s > score:
                best, score = name, s

        if score < self.threshold:
            return None, score

        return best, score
