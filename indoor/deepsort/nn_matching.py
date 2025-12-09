# indoor/deepsort/nn_matching.py
import numpy as np

def cosine_distance(a, b):
    """Cosine distance untuk matching antar track."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))

    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)

    return 1.0 - np.dot(a_norm, b_norm.T)


class NearestNeighborDistanceMetric:
    """
    Matching metric untuk DeepSORT.
    Versi ringan (tanpa deep reID model).
    """
    def __init__(self, matching_threshold, budget=None):
        self.matching_threshold = matching_threshold
        self.budget = budget
        self.samples = {}

    def partial_fit(self, features, targets):
        """Update fitur track."""
        for feature, target in zip(features, targets):
            self.samples.setdefault(target, []).append(feature)

            if self.budget is not None:
                self.samples[target] = self.samples[target][-self.budget:]

    def distance(self, features, targets):
        """Hitung jarak fitur dari track ke detection."""
        cost_matrix = np.zeros((len(targets), len(features)))

        for i, target in enumerate(targets):
            target_features = self.samples.get(target, [])
            if len(target_features) > 0:
                distances = cosine_distance(np.asarray(target_features), features)
                cost_matrix[i, :] = distances.mean(axis=0)
            else:
                cost_matrix[i, :] = 1.0  # tidak cocok

        return cost_matrix
