# indoor/tracker_deepsort.py
# ============================================================
# MULTI-OBJECT TRACKER (FINAL – SAFE + HIGH FPS)
# ------------------------------------------------------------
# DESIGN PRINCIPLES:
# - Face = GLOBAL AUTHORITY (BOOTSTRAP identity)
# - Body = GLOBAL PROPAGATION (AFTER face verified)
# - Track = temporary carrier
# - NO identity guessing
# - NO weak propagation
# - OSNet cached per track
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
        self.last_tracks = []
        self.prev_time = time.time()

        # ================= FPS OPT =================
        self.body_feature_cache = {}  # tid -> (feature, last_frame)
        self.body_feature_interval = 5

        self.det_interval = max(1, SETTINGS.get("det_interval", 1))
        self.face_interval = max(1, SETTINGS.get("face_interval", 1))

        print("[INIT] MultiObjectTracker initialized")

    # =========================================================
    # BODY FEATURE EXTRACTION (CACHED)
    # =========================================================
    def extract_body_feature(self, frame, box, tid):
        if tid in self.body_feature_cache:
            feat, last_f = self.body_feature_cache[tid]
            if self.frame_idx - last_f < self.body_feature_interval:
                return feat

        x1, y1, x2, y2 = box
        h, w = frame.shape[:2]

        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        try:
            feat = self.osnet.extract(crop)
            if feat is not None:
                self.body_feature_cache[tid] = (feat, self.frame_idx)
            return feat
        except Exception:
            return None

    # =========================================================
    # MATCH FACE → TRACK (IOU ONLY)
    # =========================================================
    def _find_best_track_for_face(self, face_box, tracks):
        fx1, fy1, fx2, fy2 = face_box
        best_iou = 0.0
        best_tid = None
        best_feat = None

        for tid, (x1, y1, x2, y2), feat in tracks:
            ix1 = max(fx1, x1)
            iy1 = max(fy1, y1)
            ix2 = min(fx2, x2)
            iy2 = min(fy2, y2)

            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            area_f = (fx2 - fx1) * (fy2 - fy1)
            area_t = (x2 - x1) * (y2 - y1)

            iou = inter / (area_f + area_t - inter + 1e-6)

            if iou > best_iou:
                best_iou = iou
                best_tid = tid
                best_feat = feat

        return best_tid, best_feat

    # =========================================================
    # PROCESS FRAME
    # =========================================================
    def process_frame(self, frame):
        self.frame_idx += 1
        out = frame.copy()

        # =====================================================
        # 1. PERSON DETECTION + DEEPSORT
        # =====================================================
        run_det = (self.frame_idx % self.det_interval == 0)

        if run_det:
            dets, feats = [], []
            for x1, y1, x2, y2, conf in self.person_detector.detect(frame):
                dets.append([x1, y1, x2, y2, conf])
                feats.append(None)
            self.deepsort.update(dets, feats)
        else:
            for t in self.deepsort.tracks:
                t.predict(self.deepsort.kf)

        tracks = self.deepsort.get_active_tracks(with_feature=True)
        self.last_tracks = tracks

        active_ids = {tid for tid, _, _ in tracks}
        self.fusion.remove_missing(active_ids)

        for tid in list(self.body_feature_cache.keys()):
            if tid not in active_ids:
                self.body_feature_cache.pop(tid)

        # =====================================================
        # 2. BODY RE-ID (ONLY AFTER FACE VERIFIED)
        # =====================================================
        if len(tracks) == 1:
            tid, (x1, y1, x2, y2), _ = tracks[0]
            if not self.fusion.get_id(tid):
                feat = self.extract_body_feature(frame, (x1, y1, x2, y2), tid)
                if feat is not None:
                    name, _ = body_registry.match(feat)
                    if name is not None:
                        self.fusion.lock(tid, name)
                        print(f"[BODY→LOCK] {name} via OSNet")

        # =====================================================
        # 3. FACE = GLOBAL AUTHORITY (BOOTSTRAP)
        # =====================================================
        if self.frame_idx % self.face_interval == 0:
            faces = self.face_detector.detect(frame)

            for x, y, w, h in faces:
                crop = frame[y:y + h, x:x + w]
                if crop.size == 0:
                    continue

                emb = self.face_recognizer.get_embedding(
                    cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                )
                if emb is None:
                    continue

                name, score = self.face_recognizer.identify(emb)
                if name is None:
                    continue

                if len(tracks) == 1:
                    if score < SETTINGS["face_recog_threshold"]:
                        continue
                else:
                    if score < SETTINGS["face_recog_strict"]:
                        continue

                tid, body_feat = self._find_best_track_for_face(
                    (x, y, x + w, y + h), tracks
                )
                if tid is None:
                    continue

                if self.fusion.get_id(tid) == name:
                    continue

                self.fusion.lock(tid, name)
                print(f"[FACE→LOCK] {name} (score={score:.3f})")

                if body_feat is not None:
                    body_registry.force_assign(name, body_feat)

        # =====================================================
        # 4. DRAW
        # =====================================================
        for tid, (x1, y1, x2, y2), _ in tracks:
            name = self.fusion.get_id(tid)
            color = (0, 255, 0) if name else (0, 180, 255)
            label = name if name else f"ID {tid}"

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                out,
                label,
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

        # =====================================================
        # 5. FPS
        # =====================================================
        now = time.time()
        fps = 1.0 / max(now - self.prev_time, 1e-6)
        self.prev_time = now

        if SETTINGS.get("show_fps", True):
            cv2.putText(
                out,
                f"{fps:.1f} FPS",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

        return out

    # =========================================================
    # PRESENCE SUPPORT
    # =========================================================
    def get_active_identities(self):
        return {
            self.fusion.get_id(tid)
            for tid, _, _ in self.last_tracks
            if self.fusion.get_id(tid)
        }
