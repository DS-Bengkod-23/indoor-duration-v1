# indoor/tracker_deepsort.py
# ============================================================
# MULTI-OBJECT TRACKER (FINAL – SAFE MULTI CAMERA)
# ------------------------------------------------------------
# GUARANTEES:
# - Face = ONLY authority to introduce identity
# - Face recognition = FINAL COMMIT (langsung lock)
# - Body = ONLY propagation AFTER face seen ON THAT TRACK
# - Unknown person NEVER gets a name
# - No cross-camera & no cross-person false identity
# ============================================================

import cv2
import time

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

        # ================= BODY CACHE =================
        self.body_feature_cache = {}      # tid -> (feat, last_frame)
        self.body_feature_interval = 5

        # body consistency counter
        self.body_match_counter = {}      # tid -> count

        # face → body cooldown
        self.last_body_update_time = {}   # name -> timestamp
        self.body_update_cooldown = 3.0

        # 🔑 TRACK YANG PERNAH MELIHAT WAJAH
        self.face_anchor_tracks = set()   # tid

        # 🔒 FINAL COMMIT TRACK (TIDAK BOLEH UNLOCK)
        self.final_locked_tracks = set()  # tid

        self.det_interval = max(1, SETTINGS.get("det_interval", 1))
        self.face_interval = max(1, SETTINGS.get("face_interval", 1))

        print("[INIT] MultiObjectTracker initialized (FINAL SAFE)")

    # =========================================================
    # BODY FEATURE EXTRACTION
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
    # FACE → TRACK MATCH (IOU)
    # =========================================================
    def _find_best_track_for_face(self, face_box, tracks):
        fx1, fy1, fx2, fy2 = face_box
        best_iou, best_tid = 0.0, None

        for tid, (x1, y1, x2, y2), _ in tracks:
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

        return best_tid

    # =========================================================
    # PROCESS FRAME
    # =========================================================
    def process_frame(self, frame):
        self.frame_idx += 1
        out = frame.copy()
        now = time.time()

        # -----------------------------------------------------
        # 1. DETECTION + TRACKING
        # -----------------------------------------------------
        if self.frame_idx % self.det_interval == 0:
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

        # cleanup when track truly gone
        for tid in list(self.body_feature_cache.keys()):
            if tid not in active_ids:
                self.body_feature_cache.pop(tid, None)
                self.body_match_counter.pop(tid, None)
                self.face_anchor_tracks.discard(tid)
                self.final_locked_tracks.discard(tid)

        # -----------------------------------------------------
        # 2. BODY RE-ID (ONLY IF FACE-ANCHORED & NOT FINAL)
        # -----------------------------------------------------
        for tid, (x1, y1, x2, y2), _ in tracks:
            if tid in self.final_locked_tracks:
                continue

            if tid not in self.face_anchor_tracks:
                continue

            feat = self.extract_body_feature(frame, (x1, y1, x2, y2), tid)
            if feat is None:
                continue

            name, _ = body_registry.match(feat)
            if name is None:
                self.body_match_counter[tid] = 0
                continue

            cnt = self.body_match_counter.get(tid, 0) + 1
            self.body_match_counter[tid] = cnt

            if cnt >= 3:
                self.fusion.lock(tid, name)
                self.final_locked_tracks.add(tid)
                print(f"[BODY→FINAL LOCK] {name}")
                self.body_match_counter[tid] = 0

        # -----------------------------------------------------
        # 3. FACE = FINAL AUTHORITY (INSTANT COMMIT)
        # -----------------------------------------------------
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
                if name is None or score < SETTINGS["face_recog_threshold"]:
                    continue

                tid = self._find_best_track_for_face(
                    (x, y, x + w, y + h), tracks
                )
                if tid is None:
                    continue

                # 🔑 FINAL COMMIT LANGSUNG
                if tid not in self.final_locked_tracks:
                    self.fusion.lock(tid, name)
                    self.face_anchor_tracks.add(tid)
                    self.final_locked_tracks.add(tid)
                    print(f"[FACE→FINAL LOCK] {name}")

                # body profile update (optional, cooldown)
                last_upd = self.last_body_update_time.get(name, 0)
                if now - last_upd >= self.body_update_cooldown:
                    for t_tid, (bx1, by1, bx2, by2), _ in tracks:
                        if t_tid == tid:
                            feat = self.extract_body_feature(
                                frame, (bx1, by1, bx2, by2), tid
                            )
                            if feat is not None:
                                body_registry.force_assign(name, feat)
                                self.last_body_update_time[name] = now
                            break

        # -----------------------------------------------------
        # 4. DRAW
        # -----------------------------------------------------
        for tid, (x1, y1, x2, y2), _ in tracks:
            name = self.fusion.get_id(tid)
            color = (0, 255, 0) if name else (0, 180, 255)
            label = name if name else f"ID {tid}"

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                out, label, (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )

        # -----------------------------------------------------
        # 5. FPS
        # -----------------------------------------------------
        fps = 1.0 / max(now - self.prev_time, 1e-6)
        self.prev_time = now

        if SETTINGS.get("show_fps", True):
            cv2.putText(
                out, f"{fps:.1f} FPS",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1, (0, 255, 0), 2
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
