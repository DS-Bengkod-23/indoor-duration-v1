# indoor/deepsort/deep_sort.py
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from .detection import Detection
from .kalman_filter import KalmanFilter
from .track import Track, TENTATIVE, CONFIRMED, DELETED

class DeepSort:
    """
    DeepSORT Enhanced:
    - IOU Matching (Standard)
    - Center Distance Matching (Backup jika IOU gagal karena gerakan cepat/ekstrem)
    """

    def __init__(self, max_age=120, n_init=3, max_iou_distance=0.9, lambda_app=0.0):
        self.kf = KalmanFilter()
        self.max_age = max_age  # Ditingkatkan untuk toleransi track hilang
        self.n_init = n_init
        self.lambda_app = 0.0 

        self.tracks = []
        self._next_id = 1
        
        # 🔥 Thresholds yang dioptimalkan
        self.max_iou_distance = max_iou_distance # Mengikuti SETTINGS (0.90)
        self.max_center_dist = 0.3  # Diperketat agar backup matching lebih akurat

    def update(self, detections, features=None):
        # 1. Convert Detections
        detection_list = []
        for idx, det in enumerate(detections):
            x1, y1, x2, y2, conf = det
            w, h = x2 - x1, y2 - y1
            tlwh = [x1, y1, w, h]
            feat = features[idx] if features is not None and idx < len(features) else None
            detection_list.append(Detection(tlwh, conf, feat))

        # 2. Predict Tracks (Kalman Filter Prediction)
        for track in self.tracks:
            track.predict(self.kf)

        # 3. Match (Stage 1 & Stage 2)
        matches, unmatched_tracks, unmatched_detections = self._match(detection_list)

        # 4. Update Matched Tracks dengan Kalman Correction
        for track_idx, det_idx in matches:
            self.tracks[track_idx].update(self.kf, detection_list[det_idx])

        # 5. Mark Unmatched Tracks as Missed
        for track_idx in unmatched_tracks:
            self.tracks[track_idx].mark_missed()

        # 6. Init New Tracks for detections that didn't match
        for det_idx in unmatched_detections:
            self._initiate_track(detection_list[det_idx])

        # 7. Delete Dead Tracks (yang sudah melebihi max_age)
        self.tracks = [t for t in self.tracks if not t.is_deleted()]

    def _initiate_track(self, detection):
        mean, covariance = self.kf.initiate(detection.to_xyah())
        new_track = Track(
            mean, covariance, self._next_id, self.n_init, self.max_age
        )
        if detection.feature is not None:
            new_track.feature = detection.feature
        self.tracks.append(new_track)
        self._next_id += 1

    def _match(self, detections):
        if len(self.tracks) == 0:
            return [], [], list(range(len(detections)))

        # --- STAGE 1: IOU MATCHING (Sangat toleran dengan threshold 0.90) ---
        iou_cost = self._iou_cost(detections)
        matches_a, unmatched_tracks_a, unmatched_detections_a = \
            self._linear_assignment(iou_cost, self.max_iou_distance)

        # --- STAGE 2: CENTER DISTANCE MATCHING (BACKUP) ---
        # Digunakan jika IOU gagal total (misal: bentuk kotak berubah drastis)
        u_track_indices = unmatched_tracks_a
        u_det_indices = unmatched_detections_a

        if len(u_track_indices) > 0 and len(u_det_indices) > 0:
            dist_cost = self._center_distance_cost(u_track_indices, u_det_indices, detections)
            
            # Match berdasarkan kedekatan koordinat titik tengah
            matches_b, unmatched_tracks_b, unmatched_detections_b = \
                self._linear_assignment(dist_cost, self.max_center_dist)
            
            # Gabungkan hasil Stage 1 dan Stage 2
            final_matches = matches_a + [(u_track_indices[r], u_det_indices[c]) for r, c in matches_b]
            final_unmatched_tracks = [u_track_indices[t] for t in unmatched_tracks_b]
            final_unmatched_dets = [u_det_indices[d] for d in unmatched_detections_b]
        else:
            final_matches = matches_a
            final_unmatched_tracks = unmatched_tracks_a
            final_unmatched_dets = unmatched_detections_a

        return final_matches, final_unmatched_tracks, final_unmatched_dets

    def _linear_assignment(self, cost_matrix, threshold):
        if cost_matrix.size == 0:
            return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

        # Hungarian Algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        
        matches, unmatched_rows, unmatched_cols = [], [], []
        
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] > threshold:
                unmatched_rows.append(r)
                unmatched_cols.append(c)
            else:
                matches.append((r, c))
        
        all_rows, all_cols = set(range(cost_matrix.shape[0])), set(range(cost_matrix.shape[1]))
        matched_rows, matched_cols = set(row_ind), set(col_ind)
        
        unmatched_rows.extend(list(all_rows - matched_rows))
        unmatched_cols.extend(list(all_cols - matched_cols))
        
        return matches, sorted(list(set(unmatched_rows))), sorted(list(set(unmatched_cols)))

    def _iou_cost(self, detections):
        cost_matrix = np.zeros((len(self.tracks), len(detections)), dtype=float)
        for t_idx, track in enumerate(self.tracks):
            t_box = track.to_tlbr()
            for d_idx, det in enumerate(detections):
                d_box = det.to_tlbr()
                iou = self._iou(t_box, d_box)
                cost_matrix[t_idx, d_idx] = 1.0 - iou
        return cost_matrix

    def _center_distance_cost(self, track_indices, det_indices, detections):
        """Menghitung jarak Euclidean antara pusat track dan deteksi (Normalized)"""
        t_centers = []
        for i in track_indices:
            box = self.tracks[i].to_tlbr()
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            t_centers.append([cx, cy])
            
        d_centers = []
        for i in det_indices:
            box = detections[i].to_tlbr()
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            d_centers.append([cx, cy])
            
        if not t_centers or not d_centers:
            return np.zeros((0,0))

        # Normalisasi menggunakan dimensi frame standar (640x480)
        norm_factor = np.array([640.0, 480.0])
        t_centers = np.array(t_centers) / norm_factor
        d_centers = np.array(d_centers) / norm_factor
        
        return cdist(t_centers, d_centers)

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

    def get_active_tracks(self, with_feature=False):
        results = []
        for t in self.tracks:
            if t.is_confirmed():
                bbox = t.to_tlbr().astype(int).tolist()
                if with_feature:
                    results.append((t.track_id, bbox, t.feature))
                else:
                    results.append((t.track_id, bbox))
        return results