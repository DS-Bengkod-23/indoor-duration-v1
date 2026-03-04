import cv2
import threading
from config.paths import get_model_paths
from config.settings import SETTINGS

class FaceDetectorYuNet:

    def __init__(self):
        paths = get_model_paths()

        # 640x480 = sweet spot (RealTimeMo)
        self.input_size = (640, 480)

        self.detector = cv2.FaceDetectorYN_create(
            model=paths["yunet"],
            config="",
            input_size=self.input_size
        )

        self.detector.setScoreThreshold(SETTINGS["face_conf_threshold"])
        self.detector.setNMSThreshold(SETTINGS["face_nms_threshold"])

        # 🔥 THREAD SAFETY: YuNet singleton dipakai banyak kamera sekaligus.
        # setInputSize + detect harus atomic agar tidak ada race condition
        # yang menyebabkan crash: "inputBlobs total mismatch"
        self._lock = threading.Lock()

    def detect(self, frame):
        h, w = frame.shape[:2]
        # Guard: minimal 20x20 pixel agar model tidak crash
        if h < 20 or w < 20:
            return []

        max_dim = 640
        scale = 1.0
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            nh, nw = int(h * scale), int(w * scale)
            process_frame = cv2.resize(frame, (nw, nh))
        else:
            process_frame = frame
            nh, nw = h, w

        # 🔥 ATOMIC: setInputSize dan detect dalam satu lock
        # Mencegah CAM 0 dan CAM 1 saling menimpa inputSize
        with self._lock:
            self.detector.setInputSize((nw, nh))
            _, faces = self.detector.detect(process_frame)

        if faces is None:
            return []

        results = []
        for f in faces:
            x, y, ww, hh = f[:4]
            results.append([
                int(x / scale),
                int(y / scale),
                int(ww / scale),
                int(hh / scale)
            ])

        return results
