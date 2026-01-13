# indoor/face_recognizer.py
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
        self.debug = True 
        
        try:
            providers = ["CUDAExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=0, det_size=(160, 160))
        except Exception:
            providers = ["CPUExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=-1, det_size=(160, 160))

        self.db = {}
        # Threshold dasar untuk kandidat
        self.threshold = SETTINGS.get("face_recog_threshold", 0.55)
        # Threshold absolut untuk konfirmasi
        self.confirmed_threshold = SETTINGS.get("face_recog_confirmed", 0.78)
        self.load_embeddings(paths["embeddings_dir"])

    def load_embeddings(self, emb_dir):
        self.db = {}
        for f in os.listdir(emb_dir):
            if not f.endswith(".npy"): continue
            try:
                v = np.load(os.path.join(emb_dir, f)).astype(np.float32)
                v = v / (norm(v) + 1e-6)
                self.db[f[:-4]] = v
            except: pass
        print(f"[FaceRecognizer] Loaded {len(self.db)} identities")

    def get_embedding(self, rgb):
        if rgb is None or rgb.size == 0: return None
        
        # 🔥 PERUBAHAN PENTING: MENURUNKAN BATAS UKURAN
        # Sebelumnya 60, sekarang 25 pixel.
        # Wajah yang jauh (kecil) sekarang akan tetap diproses.
        h, w = rgb.shape[:2]
        if h < 25 or w < 25: 
            return None

        try:
            bgr_input = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            det = self.app.get(bgr_input)
            
            if not det: return None
            
            # Ambil face dengan confidence deteksi tertinggi
            best_face = max(det, key=lambda x: x.det_score)
            
            # Turunkan sedikit syarat confidence agar wajah blur (jauh) tetap masuk
            if best_face.det_score < 0.55: 
                return None

            emb = best_face.embedding
            if emb is None: return None
            
            emb = emb.astype(np.float32)
            return emb / (norm(emb) + 1e-6)
            
        except Exception:
            return None

    def identify(self, emb):
        """Mengembalikan (Nama, Skor, Status Konfirmasi)"""
        if emb is None or len(self.db) == 0:
            return None, 0.0, False

        best_name = None
        best_score = -1.0
        
        for name, dbv in self.db.items():
            s = float(np.dot(emb, dbv))
            # if s > 0.40 and self.debug:
            #    print(f"   [FACE CHECK] vs {name} = {s:.3f}")

            if s > best_score:
                best_score = s
                best_name = name

        # 1. Jika di bawah threshold dasar -> Unknown
        if best_score < self.threshold:
            return None, best_score, False
        
        # 2. Status Konfirmasi (Untuk Entry)
        is_confirmed = best_score >= self.confirmed_threshold
        
        if is_confirmed and self.debug:
             # print(f"✅ [CONFIRMED] Wajah terkonfirmasi sebagai {best_name} (Skor: {best_score:.3f})")
             pass

        return best_name, best_score, is_confirmed