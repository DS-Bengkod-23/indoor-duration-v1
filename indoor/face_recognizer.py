# indoor/face_recognizer.py
import cv2
import os
import numpy as np
from numpy.linalg import norm
from insightface.app import FaceAnalysis
from config.settings import SETTINGS

# Import Qdrant client
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except ImportError:
    print("[FaceRecognizer] Warning: qdrant-client not installed")

class FaceRecognizer:

    def __init__(self, qdrant_host="localhost", qdrant_port=6333):
        self.qdrant_host = os.environ.get("QDRANT_HOST", qdrant_host)
        self.qdrant_port = int(os.environ.get("QDRANT_PORT", qdrant_port))
        self.collection_name = "face_embeddings"
        self.debug = True 
        
        try:
            providers = ["CUDAExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=0, det_size=(160, 160))
        except Exception:
            providers = ["CPUExecutionProvider"]
            self.app = FaceAnalysis(name="buffalo_s", providers=providers)
            self.app.prepare(ctx_id=-1, det_size=(160, 160))

        # In-memory database cache {name: embedding_vector}
        self.db = {}
        
        # Thresholds
        self.threshold = SETTINGS.get("face_recog_threshold", 0.55)
        self.confirmed_threshold = SETTINGS.get("face_recog_confirmed", 0.78)
        
        # Initialize Qdrant and load embeddings
        try:
            self.client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
            self.load_embeddings_from_qdrant()
        except Exception as e:
            print(f"[FaceRecognizer] ERROR connecting to Qdrant: {e}")
            self.client = None


    def load_embeddings_from_qdrant(self):
        """Load all face embeddings from Qdrant into memory"""
        self.db = {}
        
        if self.client is None:
            print("[FaceRecognizer] No Qdrant client, face DB empty")
            return
        
        try:
            # Scroll all face embeddings
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
                ),
                limit=10000,
                with_vectors=True
            )
            
            # Take first embedding per person
            loaded = {}
            for point in results:
                name = point.payload.get("name")
                if name and name not in loaded:
                    vector = np.array(point.vector, dtype=np.float32)
                    # Normalize
                    vector = vector / (norm(vector) + 1e-6)
                    self.db[name] = vector
                    loaded[name] = True
            
            print(f"[FaceRecognizer] Loaded {len(self.db)} identities from Qdrant")
        except Exception as e:
            print(f"[FaceRecognizer] Error loading from Qdrant: {e}")
    
    def reload_embeddings(self):
        """Reload embeddings from Qdrant (useful when new users registered)"""
        self.load_embeddings_from_qdrant()

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