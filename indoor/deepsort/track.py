# indoor/deepsort/track.py

import numpy as np

# Track states
TENTATIVE = 1
CONFIRMED = 2
DELETED = 3


class Track:
    """
    Representasi 1 track pada DeepSORT.
    - Menyimpan mean/cov Kalman Filter
    - hit/miss counter
    - state (tentative / confirmed / deleted)
    - Sekarang juga menyimpan feature badan terakhir (OSNet)
    """

    def __init__(self, mean, covariance, track_id, n_init, max_age):
        self.mean = mean
        self.covariance = covariance

        self.track_id = track_id
        self.hits = 1
        self.age = 1
        self.time_since_update = 0

        self.n_init = n_init
        self.max_age = max_age

        self.state = TENTATIVE

        # embedding badan (OSNet) terakhir
        self.feature = None

    # ---------------------------------------------------------
    # PREDICT (Kalman)
    # ---------------------------------------------------------
    def predict(self, kf):
        self.mean, self.covariance = kf.predict(self.mean, self.covariance)
        self.age += 1
        self.time_since_update += 1

    # ---------------------------------------------------------
    # UPDATE (kalman correction)
    # ---------------------------------------------------------
    def update(self, kf, detection):
        self.mean, self.covariance = kf.update(
            self.mean, self.covariance, detection.to_xyah()
        )
        self.hits += 1
        self.time_since_update = 0

        # simpan feature badan kalau ada
        if detection.feature is not None:
            self.feature = detection.feature

        # If enough hits, confirm track
        if self.state == TENTATIVE and self.hits >= self.n_init:
            self.state = CONFIRMED

    # ---------------------------------------------------------
    # MARK MISSED
    # ---------------------------------------------------------
    def mark_missed(self):
        if self.state == TENTATIVE:
            self.state = DELETED
        elif self.time_since_update > self.max_age:
            self.state = DELETED

    # ---------------------------------------------------------
    # STATE CHECKERS
    # ---------------------------------------------------------
    def is_tentative(self):
        return self.state == TENTATIVE

    def is_confirmed(self):
        return self.state == CONFIRMED

    def is_deleted(self):
        return self.state == DELETED

    # ---------------------------------------------------------
    # OUTPUT BOUNDING BOX (x1, y1, x2, y2)
    # ---------------------------------------------------------
    def to_tlbr(self):
        # convert xyah → tlbr
        x, y, a, h = self.mean[:4]
        w = a * h
        return np.array([x - w/2, y - h/2, x + w/2, y + h/2])
