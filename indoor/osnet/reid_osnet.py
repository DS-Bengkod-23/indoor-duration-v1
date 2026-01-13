# indoor/osnet/reid_osnet.py
import onnxruntime as ort
import cv2
import numpy as np

class OSNetReID:
    def __init__(self, model_path):
        print("[OSNET] Loading ONNX model (Standard ImageNet Normalization Mode)...")
        self.session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, img):
        # 1. Resize standar OSNet
        img = cv2.resize(img, (128, 256))
        
        # [REMOVED] CLAHE sudah dipindah ke Global (video.py) untuk efisiensi
        # Biar YOLO & Human Eye juga dapat gambar terang.
        # Jangan Double CLAHE (Nanti noise parah).

        # 2. BGR ke RGB dan ubah ke float32
        img = img[:, :, ::-1].astype(np.float32) / 255.0
        
        # 3. 🔥 WAJIB: Normalisasi ImageNet (Mean & Std)
        # ⚠️ FIX: Tambahkan dtype=np.float32 agar tidak dianggap Double (float64)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        
        img = (img - mean) / std
        
        # 4. HWC ke CHW format
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, 0)
        
        # Pastikan output akhir tetap float32
        return img.astype(np.float32)

    def extract(self, crop):
        if crop is None or crop.size == 0:
            return None

        inp = self.preprocess(crop)
        feat = self.session.run(None, {self.input_name: inp})[0][0]
        
        # Normalisasi vektor ke unit length
        feat = feat / (np.linalg.norm(feat) + 1e-6)
        return feat