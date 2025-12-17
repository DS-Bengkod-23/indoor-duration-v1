# indoor/fusion.py
# ============================================================
# GLOBAL ID LOCK
# ============================================================

class FaceBodyFusion:

    def __init__(self):
        self.locked = {}  # track_id -> name

    def lock(self, tid: int, name: str):
        self.locked[tid] = name

    def get_id(self, tid: int):
        return self.locked.get(tid)

    def remove_missing(self, active_ids):
        for tid in list(self.locked.keys()):
            if tid not in active_ids:
                self.locked.pop(tid)
