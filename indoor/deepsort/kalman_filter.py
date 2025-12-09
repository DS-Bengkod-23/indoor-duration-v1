# indoor/deepsort/kalman_filter.py
import numpy as np
from scipy.linalg import cho_factor, cho_solve


class KalmanFilter:
    """
    Kalman Filter untuk DeepSORT
    Versi standar (simple, cepat, ringan)
    """

    def __init__(self):
        ndim, dt = 4, 1.

        # State mean: [x, y, a, h, vx, vy, va, vh]
        self._motion_mat = np.eye(2 * ndim)
        for i in range(ndim):
            self._motion_mat[i, ndim + i] = dt

        self._update_mat = np.eye(ndim, 2 * ndim)

        # Noise parameters (DeepSORT default)
        self._std_weight_position = 1. / 20
        self._std_weight_velocity = 1. / 160

    # ---------------------------------------------------------
    # INIT TRACK STATE
    # ---------------------------------------------------------
    def initiate(self, measurement):
        mean_pos = measurement
        mean_vel = np.zeros_like(mean_pos)
        mean = np.r_[mean_pos, mean_vel]

        std = [
            2 * self._std_weight_position * measurement[3],
            2 * self._std_weight_position * measurement[3],
            1e-2,
            2 * self._std_weight_position * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            1e-5,
            10 * self._std_weight_velocity * measurement[3]
        ]

        covariance = np.diag(np.square(std))
        return mean, covariance

    # ---------------------------------------------------------
    # PREDICT TRACK (movement)
    # ---------------------------------------------------------
    def predict(self, mean, covariance):
        std_pos = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-2,
            self._std_weight_position * mean[3]
        ]

        std_vel = [
            self._std_weight_velocity * mean[3],
            self._std_weight_velocity * mean[3],
            1e-5,
            self._std_weight_velocity * mean[3]
        ]

        motion_cov = np.diag(np.square(np.r_[std_pos, std_vel]))

        mean = np.dot(self._motion_mat, mean)
        covariance = np.dot(self._motion_mat, np.dot(covariance, self._motion_mat.T)) + motion_cov
        return mean, covariance

    # ---------------------------------------------------------
    # PROJECT MEASUREMENT
    # ---------------------------------------------------------
    def project(self, mean, covariance):
        std = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-1,
            self._std_weight_position * mean[3]
        ]

        innovation_cov = np.diag(np.square(std))
        projected_mean = np.dot(self._update_mat, mean)
        projected_cov = np.dot(self._update_mat,
                               np.dot(covariance, self._update_mat.T)) + innovation_cov

        return projected_mean, projected_cov

    # ---------------------------------------------------------
      # ---------------------------------------------------------
    # UPDATE TRACK WITH DETECTION (CORRECTED)
    # ---------------------------------------------------------
    def update(self, mean, covariance, measurement):
        projected_mean, projected_cov = self.project(mean, covariance)

        # Cholesky factorization
        chol_factor, lower = cho_factor(projected_cov, lower=True, check_finite=False)

        # Kalman gain (correct matrix shapes)
        kalman_gain = np.dot(
            np.dot(covariance, self._update_mat.T),
            cho_solve((chol_factor, lower), np.eye(4), check_finite=False)
        )

        innovation = measurement - projected_mean
        new_mean = mean + np.dot(kalman_gain, innovation)

        new_covariance = covariance - np.dot(kalman_gain, np.dot(projected_cov, kalman_gain.T))

        return new_mean, new_covariance


    # ---------------------------------------------------------
    # DISTANCE (for Hungarian matching)
    # ---------------------------------------------------------
    @staticmethod
    def gating_distance(mean, covariance, measurements, degrees_of_freedom=4):
        projected_mean, projected_cov = mean, covariance
        d = measurements - projected_mean
        cholesky = np.linalg.cholesky(projected_cov)
        z = np.linalg.solve(cholesky, d.T)
        return np.sum(z * z, axis=0)
