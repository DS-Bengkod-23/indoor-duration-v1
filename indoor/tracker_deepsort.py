# indoor/tracker_deepsort.py
# ============================================================
# MULTI-OBJECT TRACKER (FINAL – TRUE CROSS-CAMERA, FIXED)
# ============================================================

import cv2
import time
import numpy as np

from indoor.face_detector import FaceDetectorYuNet
from indoor.person_detector import PersonDetectorYOLO
from indoor.fusion import FaceBodyFusion
from indoor.deepsort.deep_sort import DeepSort
from indoor.body_registry import body_registry
from indoor.shared_models import get_face_recognizer, get_osnet
from config.settings import SETTINGS


class MultiObjectTracker:

    def __init__(self):
        # ================= MODELS =================
        self.face_detector = FaceDetectorYuNet()
        self.face_recognizer = get_face_recognizer()
        self.person_detector = PersonDetectorYOLO()
        self.osnet = get_osnet()

        self.deepsort = DeepSort(
            max_age=SETTINGS["max_age"],
            n_init=SETTINGS["min_hits"],
            max_iou_distance=SETTINGS["max_iou_distance"],
            lambda_app=0.5,
        )

        self.fusion = FaceBodyFusion()

        # ================= STATE =================
        self.frame_idx = 0
        self.prev_time = time.time()
        self.last_tracks = []

        # ================= BODY STABILIZATION =================
        self.body_cache = {}   # tid -> {"feat": emb, "count": int}

        self.det_interval = SETTINGS["det_interval"]
        self.face_interval = SETTINGS["face_interval"]

        print("[INIT] MultiObjectTracker FINAL (CROSS-CAMERA FIXED)")

    # =========================================================
    # BODY FEATURE EXTRACTION
    # =========================================================
    def extract_body_feature(self, frame, box):
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        return self.osnet.extract(crop)

    # =========================================================
    # PROCESS FRAME
    # =========================================================
    def process_frame(self, frame):
        self.frame_idx += 1
        out = frame.copy()

        # =====================================================
        # 1. DETECTION + TRACKING
        # =====================================================
        if self.frame_idx % self.det_interval == 0:
            dets, feats = [], []
            for x1, y1, x2, y2, conf in self.person_detector.detect(frame):
                dets.append([x1, y1, x2, y2, conf])
                feats.append(None)
            self.deepsort.update(dets, feats)
        else:
            for t in self.deepsort.tracks:
                t.predict(self.deepsort.kf)

        # ⬇️ FIX: track hanya 2 value
        tracks = self.deepsort.get_active_tracks(with_feature=False)
        self.last_tracks = tracks

        active_ids = {tid for tid, _ in tracks}
        self.fusion.remove_missing(active_ids)

        # =====================================================
        # 2. GLOBAL BODY RE-ID (PRIMARY AFTER FACE)
        # =====================================================
        for tid, box in tracks:

            if self.fusion.get_id(tid):
                continue

            feat = self.extract_body_feature(frame, box)
            if feat is None:
                continue

            if tid not in self.body_cache:
                self.body_cache[tid] = {"feat": feat, "count": 1}
                continue

            cache = self.body_cache[tid]
            cache["feat"] = 0.7 * cache["feat"] + 0.3 * feat
            cache["count"] += 1

            if cache["count"] < SETTINGS["body_reid_min_frames"]:
                continue

            name, score = body_registry.match(cache["feat"])
            if name is not None:
                self.fusion.lock(tid, name)
                print(f"[BODY→GLOBAL LOCK] {name} score={score:.3f}")

        # =====================================================
        # 3. FACE = BOOTSTRAP ONLY
        # =====================================================
        if self.frame_idx % self.face_interval == 0:
            faces = self.face_detector.detect(frame)

            for x, y, w, h in faces:
                crop = frame[y:y+h, x:x+w]
                if crop.size == 0:
                    continue

                emb = self.face_recognizer.get_embedding(
                    cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                )
                if emb is None:
                    continue

                name, score = self.face_recognizer.identify(emb)
                if name is None or score < SETTINGS["face_recog_threshold"]:
                    continue

                best_tid, best_iou = None, 0.0
                fx1, fy1, fx2, fy2 = x, y, x+w, y+h

                for tid, (tx1, ty1, tx2, ty2) in tracks:
                    ix1 = max(fx1, tx1)
                    iy1 = max(fy1, ty1)
                    ix2 = min(fx2, tx2)
                    iy2 = min(fy2, ty2)
                    inter = max(0, ix2-ix1) * max(0, iy2-iy1)
                    area = (fx2-fx1)*(fy2-fy1) + (tx2-tx1)*(ty2-ty1)
                    iou = inter / (area - inter + 1e-6)
                    if iou > best_iou:
                        best_iou = iou
                        best_tid = tid

                if best_tid is None:
                    continue

                self.fusion.lock(best_tid, name)
                if best_tid in self.body_cache:
                    body_registry.force_assign(name, self.body_cache[best_tid]["feat"])

                print(f"[FACE BOOTSTRAP] {name} score={score:.3f}")

        # =====================================================
        # 4. DRAW
        # =====================================================
        for tid, (x1, y1, x2, y2) in tracks:
            name = self.fusion.get_id(tid)
            color = (0, 255, 0) if name else (0, 180, 255)
            label = name if name else f"ID {tid}"

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # =====================================================
        # 5. FPS
        # =====================================================
        now = time.time()
        fps = 1.0 / max(now - self.prev_time, 1e-6)
        self.prev_time = now
        cv2.putText(out, f"{fps:.1f} FPS", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return out

    def get_active_identities(self):
        return {
            self.fusion.get_id(tid)
            for tid, _ in self.last_tracks
            if self.fusion.get_id(tid)
        }
