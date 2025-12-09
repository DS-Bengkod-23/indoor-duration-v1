# indoor/deepsort/detection.py
import numpy as np

class Detection:
    """
    Representasi satu hasil deteksi YOLO untuk DeepSORT.
    Sekarang bisa menyimpan:
      - tlwh
      - confidence
      - feature (embedding OSNet) -> opsional
    """
    def __init__(self, tlwh, confidence, feature=None):
        self.tlwh = np.asarray(tlwh, dtype=float)
        self.confidence = float(confidence)
        self.feature = None if feature is None else np.asarray(feature, dtype=float)

    def to_tlbr(self):
        """Convert tlwh → tlbr format."""
        x, y, w, h = self.tlwh
        return np.array([x, y, x + w, y + h], dtype=float)

    def to_xyah(self):
        """
        Convert tlwh → xyah (x_center, y_center, aspect_ratio, height).
        Dijaga supaya tidak division by zero kalau h sangat kecil.
        """
        x, y, w, h = self.tlwh
        cx = x + w / 2.0
        cy = y + h / 2.0
        h_safe = max(h, 1e-3)
        aspect = w / h_safe
        return np.array([cx, cy, aspect, h_safe], dtype=float)
