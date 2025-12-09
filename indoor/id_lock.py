# indoor/id_lock.py

import time
from config.settings import SETTINGS


class IDLockManager:
    """
    Manages ID locking:
    - Keeps face identity attached to a DeepSORT track
    - Ensures ID never jumps to another person
    - Lightweight & optimized (no heavy computation)
    """

    def __init__(self):
        # track_id → { "name": str, "time": float }
        self.locked = {}

        self.duration = SETTINGS["id_lock_duration"]
        self.sticky = SETTINGS["lock_sticky"]

    # ---------------------------------------------------------
    # LOCK ID TO A TRACK
    # ---------------------------------------------------------
    def lock(self, track_id: int, name: str):
        self.locked[track_id] = {
            "name": name,
            "time": time.time(),
        }

    # ---------------------------------------------------------
    # GET CURRENT LOCKED ID FOR TRACK
    # ---------------------------------------------------------
    def get(self, track_id: int):
        """
        Returns identity for this track, or None.
        """
        if track_id not in self.locked:
            return None

        data = self.locked[track_id]

        # sticky mode → never expire until track disappears
        if self.sticky:
            return data["name"]

        # non-sticky → expire after duration
        if time.time() - data["time"] <= self.duration:
            return data["name"]

        return None

    # ---------------------------------------------------------
    # REMOVE EXPIRED OR MISSING TRACKS
    # ---------------------------------------------------------
    def cleanup(self, active_track_ids):
        """
        Remove lock if track no longer exists (DeepSORT removed it).
        """
        to_delete = []
        for track_id in list(self.locked.keys()):
            if track_id not in active_track_ids:
                to_delete.append(track_id)

        for t in to_delete:
            del self.locked[t]
