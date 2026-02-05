import numpy as np
import time
import threading  # 🔥 FIX: Add thread safety
from config.settings import SETTINGS

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
        self.expiry_time = SETTINGS.get("guest_memory_seconds", 300) # Default 5 menit kalau setting tidak ada
        self.lock = threading.Lock()  # 🔥 FIX: Thread safety for multi-camera access
        
    def match_or_register(self, feature, threshold=None):
        """
        Cari apakah fitur ini cocok dengan Guest yang ada.
        Jika tidak, buat Guest ID baru.
        Return: (guest_id, is_new)
        """
        if feature is None: return None, False
        
        # 🔥 FIX: Use stricter threshold for better guest separation
        # Lower threshold = easier to match (more permissive)
        # Higher threshold = harder to match (more strict, creates more unique IDs)
        if threshold is None:
            # Changed from 0.65 to 0.80 for stricter matching
            # This ensures different people get different Guest IDs
            threshold = 0.80  
        
        # Normalize
        norm = np.linalg.norm(feature)
        if norm > 0: feature = feature / norm
        
        # 🔥 FIX: Thread-safe access to shared data
        with self.lock:
            best_id = None
            best_score = -1.0
            
            # 1. Cari Match
            for gid, feats in self.guests.items():
                # Compare with recent features (max 5)
                # Ambil rata-rata skor atau max skor
                local_max = 0
                for f in feats: 
                    score = np.dot(f, feature)
                    if score > local_max: local_max = score
                
                if local_max > best_score:
                    best_score = local_max
                    best_id = gid
                    
            # 2. Evaluasi Match
            if best_score > threshold:
                # Update data guest ini
                self.guests[best_id].append(feature)
                # Keep only last 30 features to save RAM (Updated from 10)
                if len(self.guests[best_id]) > 30:
                    self.guests[best_id].pop(0)
                    
                self.last_seen[best_id] = time.time()
                # 🔥 DEBUG LOG: Show why we matched
                print(f"[GUEST REID] Match Found! {best_id} (Score: {best_score:.2f} > {threshold:.2f})")
                return best_id, False
            else:
                # 🔥 DEBUG LOG: Show why we FAILED (helpful for tuning)
                # Only print if score is decent (prevent spam for random noise)
                if best_score > 0.20:
                    print(f"[GUEST REID] No Match. Best: {best_id} (Score: {best_score:.2f} < {threshold:.2f}) → Creating New Guest")
                # 3. Register Baru
                new_id = f"Guest-{self.guest_counter}"
                self.guest_counter += 1
                self.guests[new_id] = [feature]
                self.last_seen[new_id] = time.time()
                print(f"[GUEST REID] 🆕 NEW GUEST: {new_id}")
                return new_id, True

    def clean_stale_guests(self):
        """Clean expired guests - thread-safe version"""
        # 🔥 FIX: Thread-safe access to shared data
        with self.lock:
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
