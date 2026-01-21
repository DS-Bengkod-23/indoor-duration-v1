import numpy as np
import time

class SessionRegistry:
    """
    Manages temporary identities (Guests) for the current session.
    Data is stored in RAM and lost when the system restarts.
    Used for tracking unknown people across cameras.
    """
    def __init__(self):
        self.guests = {} # { "Guest-1": [feat1, feat2, ...], ... }
        self.guest_counter = 1
        self.last_seen = {} # { "Guest-1": timestamp }
        self.expiry_time = 300 # 5 Menit (Guest hilang kalau tidak terlihat 5 menit)
        
    def match_or_register(self, feature, threshold=0.65):
        """
        Cari apakah fitur ini cocok dengan Guest yang ada.
        Jika tidak, buat Guest ID baru.
        Return: (guest_id, is_new)
        """
        if feature is None: return None, False
        
        # Normalize
        norm = np.linalg.norm(feature)
        if norm > 0: feature = feature / norm
        
        best_id = None
        best_score = -1.0
        
        # 1. Cari Match
        for gid, feats in self.guests.items():
            # Compare with recent features (max 5)
            # Ambil rata-rata skor atau max skor
            local_max = 0
            for f in feats[-5:]: 
                score = np.dot(f, feature)
                if score > local_max: local_max = score
            
            if local_max > best_score:
                best_score = local_max
                best_id = gid
                
        # 2. Evaluasi Match
        if best_score > threshold:
            # Update data guest ini
            self.guests[best_id].append(feature)
            # Keep only last 10 features to save RAM
            if len(self.guests[best_id]) > 10:
                self.guests[best_id].pop(0)
                
            self.last_seen[best_id] = time.time()
            return best_id, False
        else:
            # 3. Register Baru
            new_id = f"Guest-{self.guest_counter}"
            self.guest_counter += 1
            self.guests[new_id] = [feature]
            self.last_seen[new_id] = time.time()
            return new_id, True

    def clean_stale_guests(self):
        now = time.time()
        expired_ids = []
        for gid, ts in self.last_seen.items():
            if now - ts > self.expiry_time:
                expired_ids.append(gid)
        
        for gid in expired_ids:
            del self.guests[gid]
            del self.last_seen[gid]
            # print(f"[SessionRegistry] Guest {gid} expired.")

session_registry = SessionRegistry()
