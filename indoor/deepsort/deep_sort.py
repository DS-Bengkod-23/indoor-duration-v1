# indoor/deepsort/deep_sort.py
import numpy as np
from scipy.optimize import linear_sum_assignment

from .detection import Detection
from .kalman_filter import KalmanFilter
from .track import Track, TENTATIVE, CONFIRMED, DELETED


class DeepSort:
    """
    DeepSORT versi ringan + simple appearance (OSNet).
    - Matching utamanya masih IOU
    - Jika feature badan tersedia (track & detection), akan dipakai juga:
        cost = (1 - lambda_app)*IOU_cost + lambda_app*appearance_cost
    """

    def __init__(self, max_age=30, n_init=3, max_iou_distance=0.7, lambda_app=0.5):
        # Kalman Filter tracking
        self.kf = KalmanFilter()

        # Parameters
        self.max_age = max_age
        self.n_init = n_init

        # Appearance weight (0..1)
        self.lambda_app = float(lambda_app)

        # Track state
        self.tracks = []
        self._next_id = 1

        # IOU gating threshold
        self.max_iou_distance = max_iou_distance

    # ----------------------------------------------------------------------
    # UPDATE: input = list deteksi YOLO [x1,y1,x2,y2,conf]
    #         + optional list features (embedding OSNet) seukuran detections
    # ----------------------------------------------------------------------
    def update(self, detections, features=None):
        # --------------------------------------------------------------
        # 1. Convert YOLO detections → DeepSORT Detection objects
        # --------------------------------------------------------------
        detection_list = []
        for idx, det in enumerate(detections):
            x1, y1, x2, y2, conf = det
            w = x2 - x1
            h = y2 - y1
            tlwh = [x1, y1, w, h]

            feat = None
            if features is not None and idx < len(features):
                feat = features[idx]

            detection_list.append(Detection(tlwh, conf, feat))

        # --------------------------------------------------------------
        # 2. Predict track movement
        # --------------------------------------------------------------
        for track in self.tracks:
            track.predict(self.kf)

        # --------------------------------------------------------------
        # 3. Data Association (Hungarian)
        # --------------------------------------------------------------
        matches, unmatched_tracks, unmatched_detections = \
            self._match(detection_list)

        # --------------------------------------------------------------
        # 4. Update matched tracks
        # --------------------------------------------------------------
        for track_idx, det_idx in matches:
            track = self.tracks[track_idx]
            detection = detection_list[det_idx]
            track.update(self.kf, detection)

        # --------------------------------------------------------------
        # 5. Mark unmatched tracks
        # --------------------------------------------------------------
        for track_idx in unmatched_tracks:
            track = self.tracks[track_idx]
            track.mark_missed()

        # --------------------------------------------------------------
        # 6. Create new tracks for unmatched detection
        # --------------------------------------------------------------
        for det_idx in unmatched_detections:
            detection = detection_list[det_idx]
            mean, covariance = self.kf.initiate(detection.to_xyah())
            new_track = Track(
                mean,
                covariance,
                self._next_id,
                self.n_init,
                self.max_age
            )
            # isi feature awal jika ada
            if detection.feature is not None:
                new_track.feature = detection.feature

            self.tracks.append(new_track)
            self._next_id += 1

        # --------------------------------------------------------------
        # 7. Remove deleted tracks
        # --------------------------------------------------------------
        self.tracks = [t for t in self.tracks if not t.is_deleted()]

    # ----------------------------------------------------------------------
    # MATCHING: Hungarian algorithm + IOU (+ optional appearance)
    # ----------------------------------------------------------------------
    def _match(self, detections):
        if len(self.tracks) == 0:
            return [], [], list(range(len(detections)))

        # IOU cost
        iou_cost = self._iou_cost(detections)

        # Appearance cost (1 - cosine sim), default 1 jika feature tidak ada
        app_cost = self._appearance_cost(detections)

        # Kombinasi
        if self.lambda_app > 0:
            cost_matrix = (1.0 - self.lambda_app) * iou_cost + self.lambda_app * app_cost
        else:
            cost_matrix = iou_cost

        track_indices = list(range(len(self.tracks)))
        detection_indices = list(range(len(detections)))

        row_idx, col_idx = linear_sum_assignment(cost_matrix)

        matches, unmatched_tracks, unmatched_dets = [], [], []

        for r, c in zip(row_idx, col_idx):
            # jika IOU terlalu kecil, jangan dipaksa match
            if iou_cost[r, c] > (1.0 - self.max_iou_distance):
                unmatched_tracks.append(r)
                unmatched_dets.append(c)
            else:
                matches.append((r, c))

        # Tambahkan yang benar-benar tidak terpakai
        for r in track_indices:
            if r not in row_idx:
                unmatched_tracks.append(r)

        for c in detection_indices:
            if c not in col_idx:
                unmatched_dets.append(c)

        return matches, unmatched_tracks, unmatched_dets

    # ----------------------------------------------------------------------
    # IOU cost between track boxes and detection boxes
    # ----------------------------------------------------------------------
    def _iou_cost(self, detections):
        cost_matrix = np.ones((len(self.tracks), len(detections)), dtype=float)

        for t_idx, track in enumerate(self.tracks):
            t_box = track.to_tlbr()  # [x1,y1,x2,y2]

            for d_idx, det in enumerate(detections):
                d_box = det.to_tlbr()
                iou = self._iou(t_box, d_box)
                cost_matrix[t_idx, d_idx] = 1.0 - iou  # cost = 1 - IOU

        return cost_matrix

    # ----------------------------------------------------------------------
    # Appearance cost (1 - cosine similarity) antara track.feature dan det.feature
    # ----------------------------------------------------------------------
    def _appearance_cost(self, detections):
        cost_matrix = np.ones((len(self.tracks), len(detections)), dtype=float)

        for t_idx, track in enumerate(self.tracks):
            if track.feature is None:
                continue

            t_feat = track.feature
            t_norm = np.linalg.norm(t_feat) + 1e-6
            t_feat = t_feat / t_norm

            for d_idx, det in enumerate(detections):
                if det.feature is None:
                    continue

                d_feat = det.feature
                d_norm = np.linalg.norm(d_feat) + 1e-6
                d_feat = d_feat / d_norm

                sim = float(np.dot(t_feat, d_feat))  # -1..1
                dist = 1.0 - sim                      # 0..2
                cost_matrix[t_idx, d_idx] = dist

        return cost_matrix

    # ----------------------------------------------------------------------
    # IOU helper
    # ----------------------------------------------------------------------
    @staticmethod
    def _iou(boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        inter_area = max(0, xB - xA) * max(0, yB - yA)

        boxA_area = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxB_area = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        return inter_area / float(boxA_area + boxB_area - inter_area + 1e-6)

    # ----------------------------------------------------------------------
    # GET CONFIRMED TRACKS ONLY
    # ----------------------------------------------------------------------
    def get_active_tracks(self, with_feature=False):
        """
        Return list of active tracks:
          if with_feature = False:
            (track_id, bbox)
          if with_feature = True:
            (track_id, bbox, feature)
        """
        results = []
        for t in self.tracks:
            if t.is_confirmed():
                bbox = t.to_tlbr().astype(int).tolist()
                if with_feature:
                    results.append((t.track_id, bbox, t.feature))
                else:
                    results.append((t.track_id, bbox))
        return results
