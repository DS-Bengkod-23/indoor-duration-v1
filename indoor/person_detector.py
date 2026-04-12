# indoor/person_detector.py
# ============================================================
#   PERSON DETECTOR (YOLOv8n) — FAST & CLEAN
# ============================================================

from config.settings import SETTINGS
from indoor.shared_models import get_yolo_model

import torch


class PersonDetectorYOLO:

    def __init__(self):
        # shared YOLO model + device
        self.model, self.device = get_yolo_model()

        self.conf = SETTINGS["yolo_conf_threshold"]
        self.iou = SETTINGS["yolo_iou_threshold"]
        self.classes = SETTINGS["yolo_classes"]

        # half precision hanya kalau cuda
        self.half = (self.device == "cuda")

    def detect(self, frame):
        # Ultralytics YOLO v8: device & half di-set di predict
        try:
            outputs = self.model.predict(
                frame,
                conf=self.conf,
                iou=self.iou,
                classes=self.classes,
                device=self.device,
                half=self.half,
                imgsz=320,
                verbose=False
            )
        except TypeError:
            # fallback kalau versi YOLO tidak support arg half/device
            outputs = self.model.predict(
                frame,
                conf=self.conf,
                iou=self.iou,
                classes=self.classes,
                verbose=False
            )

        boxes = []
        for r in outputs:
            for b in r.boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                conf = float(b.conf[0])
                boxes.append([x1, y1, x2, y2, conf])

        return boxes
