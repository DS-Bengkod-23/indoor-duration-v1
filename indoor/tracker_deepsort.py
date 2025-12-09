# indoor/tracker_deepsort.py
import cv2
import time

from indoor.face_detector import FaceDetectorYuNet
from indoor.person_detector import PersonDetectorYOLO
from indoor.fusion import FaceBodyFusion
from indoor.registry import UserRegistry

from indoor.deepsort.deep_sort import DeepSort
from indoor.body_registry import body_registry
from indoor.shared_models import get_face_recognizer, get_osnet

from config.settings import SETTINGS


class MultiObjectTracker:

    def __init__(self):

        # Core modules
        self.face_detector = FaceDetectorYuNet()
        self.face_recognizer = get_face_recognizer()
        self.person_detector = PersonDetectorYOLO()
        self.registry = UserRegistry()

        # DeepSORT + simple appearance
        self.deepsort = DeepSort(
            max_age=SETTINGS["max_age"],
            n_init=SETTINGS["min_hits"],
            max_iou_distance=SETTINGS["max_iou_distance"],
            lambda_app=0.5,   # bobot appearance vs IOU
        )

        # OSNet ReID (shared)
        self.osnet = get_osnet()

        self.fusion = FaceBodyFusion()

        self.prev_time = time.time()
        self.prev_ids = set()

        # body_features per track (local, dari DeepSORT)
        self.body_features = {}  # track_id → embedding

        # Counter / interval
        self.frame_idx = 0
        self.det_interval = max(1, SETTINGS.get("det_interval", 1))
        self.face_interval = max(1, SETTINGS.get("face_interval", 3))

        # BODY ReID safety
        self.body_reid_strict = SETTINGS.get("body_reid_strict", 0.75)
        self.body_reid_min_frames = SETTINGS.get("body_reid_min_frames", 2)

        # kandidat nama dari body reid per track:
        # track_id -> {"name": str, "score": float, "count": int}
        self.body_reid_candidates = {}

    # ============================================================
    #  HELPER: Extract body feature using OSNet (untuk DETEKSI)
    # ============================================================
    def extract_body_feature(self, frame, box):
        x1, y1, x2, y2 = box
        h, w = frame.shape[:2]

        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w - 1))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h - 1))

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        return self.osnet.extract(crop)

    # ============================================================
    #  PROCESS FRAME
    # ============================================================
    def process_frame(self, frame):

        out = frame.copy()
        self.frame_idx += 1

        # ========================================================
        # 1. YOLO PERSON DETECTION (+ OSNET) (INTERVAL)
        # ========================================================
        detection_frame = (self.frame_idx % self.det_interval == 0)

        if detection_frame:
            # Deteksi baru
            raw_dets = self.person_detector.detect(frame)

            # Filter bbox kecil/aneh supaya tidak bikin h=0
            dets = []
            feats = []
            for x1, y1, x2, y2, conf in raw_dets:
                w = x2 - x1
                h = y2 - y1
                if w < 5 or h < 5:   # buang box aneh
                    continue

                dets.append([x1, y1, x2, y2, conf])

                # Ekstraksi fitur badan sekali per detection (OSNet)
                feat = self.extract_body_feature(frame, (x1, y1, x2, y2))
                feats.append(feat)

            # Update DeepSORT dengan bbox + feature
            self.deepsort.update(dets, feats)
            tracks = self.deepsort.get_active_tracks(with_feature=True)

        else:
            # Hanya prediksi Kalman, tanpa deteksi baru
            for t in self.deepsort.tracks:
                t.predict(self.deepsort.kf)

            tracks = []
            for t in self.deepsort.tracks:
                if t.is_confirmed() and (not t.is_deleted()):
                    bbox = t.to_tlbr().astype(int).tolist()
                    tracks.append((t.track_id, bbox, t.feature))

        # Simpan body_features per track dari DeepSORT (tidak panggil OSNet lagi)
        self.body_features = {}
        for tid, bbox, feat in tracks:
            if feat is not None:
                self.body_features[tid] = feat

        # Track ID info
        current_ids = {tid for tid, _, _ in tracks}
        new_ids = current_ids - self.prev_ids  # (kalau mau dipakai nanti)
        self.prev_ids = current_ids.copy()

        # Bersihkan lock ID & kandidat yang track-nya sudah hilang
        self.fusion.remove_missing(current_ids)
        for tid in list(self.body_reid_candidates.keys()):
            if tid not in current_ids:
                del self.body_reid_candidates[tid]

        # Track tanpa ID (belum punya nama)
        unlocked = {tid for tid, _, _ in tracks if self.fusion.get_id(tid) is None}

        # ========================================================
        # 2. BODY REID GLOBAL → TEBAK ID TANPA WAJAH (SAFE MODE)
        # ========================================================
        for tid in list(unlocked):
            feat = self.body_features.get(tid, None)
            if feat is None:
                continue

            name, score = body_registry.match(feat)
            if name is None:
                # tidak cukup mirip, reset kandidat
                if tid in self.body_reid_candidates:
                    del self.body_reid_candidates[tid]
                continue

            cand = self.body_reid_candidates.get(tid)

            # kandidat baru atau ganti nama
            if (cand is None) or (cand["name"] != name):
                self.body_reid_candidates[tid] = {
                    "name": name,
                    "score": score,
                    "count": 1,
                }
            else:
                # perkuat kandidat lama
                cand["count"] += 1
                cand["score"] = max(cand["score"], score)

            cand = self.body_reid_candidates[tid]

            # baru lock jika:
            #  - sudah muncul beberapa frame
            #  - skor cukup tinggi (strict threshold)
            if cand["count"] >= self.body_reid_min_frames and \
               cand["score"] >= self.body_reid_strict:

                self.fusion.lock_id(tid, cand["name"])
                unlocked.discard(tid)
                del self.body_reid_candidates[tid]

        # ========================================================
        # 3. FACE DETECTION + RECOGNITION (INTERVAL)
        # ========================================================
        faces = []
        faces_xyxy = []
        matches = {}

        if self.frame_idx % self.face_interval == 0:

            faces = self.face_detector.detect(frame)  # (x,y,w,h)
            faces_xyxy = [[x, y, x + w, y + h] for (x, y, w, h) in faces]

            # IoU face ↔ body untuk mapping
            matches = self.fusion.match_face_to_body(
                faces_xyxy,
                [(tid, bbox) for tid, bbox, _ in tracks]
            )

            # Face recog hanya untuk track yang masih unlocked
            for idx, tid in matches.items():

                if tid not in unlocked:
                    continue

                x, y, w, h = faces[idx]

                crop = frame[y:y + h, x:x + w]
                if crop.size == 0:
                    continue

                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                emb = self.face_recognizer.get_embedding(rgb)
                if emb is None:
                    continue

                name, score = self.face_recognizer.identify(emb)

                if name:
                    # Lock ID ke track
                    self.fusion.lock_id(tid, name)
                    unlocked.discard(tid)

                    # Jika sudah ada fitur badan → update BodyRegistry global
                    body_feat = self.body_features.get(tid, None)
                    if body_feat is not None:
                        body_registry.update_profile(name, body_feat)
        else:
            faces = []
            matches = {}

        # ========================================================
        # 4. DRAW TRACKS (BADAN + IDENTITY)
        # ========================================================
        for tid, (x1, y1, x2, y2), feat in tracks:
            name = self.fusion.get_id(tid)

            color = (0, 255, 0) if name else (0, 180, 255)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            label = f"ID {tid}"
            if name:
                label += f" | {name}"

            cv2.putText(
                out,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )

        # ========================================================
        # 5. DRAW FACES (HANYA YANG BELUM PUNYA ID)
        # ========================================================
        for idx, (x, y, w, h) in enumerate(faces):
            tid = matches.get(idx, None)
            if tid and self.fusion.get_id(tid):
                continue
            cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 0), 2)

        # ========================================================
        # 6. FPS
        # ========================================================
        now = time.time()
        dt = now - self.prev_time
        if dt <= 0:
            fps = 0.0
        else:
            fps = 1.0 / dt
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
