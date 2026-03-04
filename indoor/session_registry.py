import numpy as np
import time
import threading
from config.settings import SETTINGS

class SessionRegistry:
    """
    Manages temporary identities (Guests) for the current session.
    Data is stored in RAM and lost when the system restarts.
    Used for tracking unknown people across cameras.
    """
    def __init__(self):
        self.guests = {}         # { "Guest-1": [feat1, feat2, ...], ... }
        self.guest_counter = 1
        self.last_seen = {}      # { "Guest-1": timestamp }
        self.expiry_time = SETTINGS.get("guest_memory_seconds", 300)
        self.lock = threading.Lock()

        # 🔥 GLOBAL CROSS-CAMERA OWNERSHIP MAP 🔥
        # Mencegah dua kamera yang berbeda mengklaim Guest yang sama.
        # { "Guest-5": (cam_id, tid, timestamp) }
        # Ownership expire setelah 3 detik jika tidak di-renew (track mati)
        self.global_claimed = {}   # guest_id → (cam_id, tid, ts)
        self._CLAIM_TTL = 3.0      # Ownership expire setelah 3 detik tanpa renew

    def claim_globally(self, guest_id, cam_id, tid):
        """Klaim ownership Guest secara global. Renew setiap frame di call OSNet."""
        with self.lock:
            self.global_claimed[guest_id] = (cam_id, tid, time.time())

    def release_globally(self, guest_id, cam_id, tid):
        """Lepas ownership. Hanya bisa release jika kamu yang punya."""
        with self.lock:
            entry = self.global_claimed.get(guest_id)
            if entry and entry[0] == cam_id and entry[1] == tid:
                del self.global_claimed[guest_id]

    def get_globally_claimed_by_others(self, cam_id, tid):
        """
        Kembalikan set guest_id yang sudah dimiliki track lain (bukan (cam_id, tid)).
        Ownership yang sudah expired (> TTL) tidak dihitung — dianggap bebas.
        """
        now = time.time()
        with self.lock:
            claimed = set()
            for gid, (c_id, t_id, ts) in list(self.global_claimed.items()):
                if now - ts > self._CLAIM_TTL:
                    # Ownership expired → hapus, guest bebas diklaim
                    del self.global_claimed[gid]
                    continue
                if (c_id, t_id) != (cam_id, tid):
                    claimed.add(gid)
        return claimed

    def match_or_register(self, feature, threshold=None, exclude_ids=None):
        """
        Cari apakah fitur ini cocok dengan Guest yang ada.
        Jika tidak, buat Guest ID baru.
        Return: (guest_id, is_new)

        exclude_ids: set of guest_ids yang tidak boleh diklaim.
        """
        if feature is None:
            return None, False

        if threshold is None:
            threshold = 0.72

        # Normalize fitur
        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm

        with self.lock:
            best_id = None
            best_score = -1.0

            # 1. Cari match terbaik (skip Guest yang sudah diklaim)
            for gid, feats in self.guests.items():
                if exclude_ids and gid in exclude_ids:
                    continue

                local_max = 0.0
                for f in feats:
                    score = float(np.dot(f, feature))
                    if score > local_max:
                        local_max = score

                if local_max > best_score:
                    best_score = local_max
                    best_id = gid

            # 2. Evaluasi match
            if best_score > threshold:
                # Update bank fitur guest (max 30)
                self.guests[best_id].append(feature)
                if len(self.guests[best_id]) > 30:
                    self.guests[best_id].pop(0)
                self.last_seen[best_id] = time.time()
                print(f"[GUEST REID] Match Found! {best_id} (Score: {best_score:.2f} > {threshold:.2f})")
                return best_id, False
            else:
                if best_score > 0.20:
                    print(f"[GUEST REID] No Match. Best: {best_id} (Score: {best_score:.2f} < {threshold:.2f}) → Creating New Guest")
                # 3. Register sebagai Guest baru
                new_id = f"Guest-{self.guest_counter}"
                self.guest_counter += 1
                self.guests[new_id] = [feature]
                self.last_seen[new_id] = time.time()
                print(f"[GUEST REID] 🆕 NEW GUEST: {new_id}")
                return new_id, True

    def clean_stale_guests(self):
        """Hapus Guest yang sudah lama tidak terlihat."""
        with self.lock:
            now = time.time()
            expired_ids = [gid for gid, ts in self.last_seen.items()
                           if now - ts > self.expiry_time]
            for gid in expired_ids:
                del self.guests[gid]
                del self.last_seen[gid]

session_registry = SessionRegistry()
