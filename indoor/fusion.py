# ============================================================
#   FACE → BODY FUSION (ID LOCK)
# ============================================================

import time
import numpy as np
from config.settings import SETTINGS

class FaceBodyFusion:

    def __init__(self):
        self.locked = {}
        self.iou_thresh = SETTINGS["face_body_iou_match"]

    @staticmethod
    def iou(a, b):
        xA = max(a[0], b[0])
        yA = max(a[1], b[1])
        xB = min(a[2], b[2])
        yB = min(a[3], b[3])

        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = (a[2]-a[0])*(a[3]-a[1])
        areaB = (b[2]-b[0])*(b[3]-b[1])

        return inter / (areaA + areaB - inter + 1e-6)

    def match_face_to_body(self, faces, tracks):
        mapping = {}

        for f_idx, fbox in enumerate(faces):
            best_iou = 0
            best_tid = None

            for tid, tbox in tracks:
                score = self.iou(fbox, tbox)
                if score > best_iou:
                    best_iou = score
                    best_tid = tid

            if best_iou >= self.iou_thresh:
                mapping[f_idx] = best_tid

        return mapping

    def lock_id(self, tid, name):
        self.locked[tid] = name

    def get_id(self, tid):
        return self.locked.get(tid, None)

    def remove_missing(self, active_ids):
        to_del = [t for t in self.locked if t not in active_ids]
        for t in to_del:
            del self.locked[t]
