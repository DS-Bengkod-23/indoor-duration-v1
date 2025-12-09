# ============================================================
#   FACE DETECTOR – YUNET (FAST & LONG RANGE OPTIMAL)
#   • 640×480 saja (paling optimal untuk FPS)
#   • Sama seperti RealTimeMo
# ============================================================

import cv2
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

    def detect(self, frame):
        h, w = frame.shape[:2]

        resized = cv2.resize(frame, self.input_size)
        self.detector.setInputSize(self.input_size)

        _, faces = self.detector.detect(resized)
        if faces is None:
            return []

        sx = w / self.input_size[0]
        sy = h / self.input_size[1]

        results = []
        for f in faces:
            x, y, ww, hh = f[:4]
            results.append([
                int(x * sx),
                int(y * sy),
                int(ww * sx),
                int(hh * sy)
            ])

        return results
