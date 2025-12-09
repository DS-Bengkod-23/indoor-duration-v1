# indoor/osnet/reid_osnet.py
import onnxruntime as ort
import cv2
import numpy as np

class OSNetReID:
    """
    Wrapper OSNet (ONNX)
    Mode A = paling ringan → hanya dipanggil saat:
        - track baru muncul
        - bounding box tidak stabil
    """

    def __init__(self, model_path):
        print("[OSNET] Loading ONNX model (light mode A)...")
        self.session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])

        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape  # (1,3,256,128)

    def preprocess(self, img):
        img = cv2.resize(img, (128, 256))
        img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB->CHW
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, 0)
        return img

    def extract(self, crop):
        if crop is None or crop.size == 0:
            return None

        inp = self.preprocess(crop)
        feat = self.session.run(None, {self.input_name: inp})[0][0]
        feat = feat / np.linalg.norm(feat)
        return feat
