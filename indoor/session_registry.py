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

        # LOKAL intra-camera ownership: mencegah dua track di DALAM SATU KAMERA mengklaim ID Guest yang sama.
        # Secara GLOBAL (antar kamera), kita BISA memakai ID Guest yang sama, karena memang itu orangnya.
        self.local_claimed = {}    # { cam_id: {guest_id: (tid, ts)} }
        self._CLAIM_TTL = 3.0      # Ownership expire setelah 3 detik tanpa renew

    def claim_locally(self, guest_id, cam_id, tid):
        """Klaim ownership Guest KHUSUS untuk kamera ini."""
        with self.lock:
            if cam_id not in self.local_claimed:
                self.local_claimed[cam_id] = {}
            self.local_claimed[cam_id][guest_id] = (tid, time.time())

    def release_locally(self, guest_id, cam_id, tid):
        """Lepas ownership lokal."""
        with self.lock:
            if cam_id in self.local_claimed and guest_id in self.local_claimed[cam_id]:
                entry = self.local_claimed[cam_id].get(guest_id)
                if entry and entry[0] == tid:
                    del self.local_claimed[cam_id][guest_id]

    def get_locally_claimed_by_others(self, cam_id, tid):
        """
        Kembalikan set guest_id yang sudah dimiliki track lain di DALAM KAMERA YANG SAMA.
        Kamera lain BOLEH punya Guest ID yang sama, tapi track lain di kamera ini TIDAK BOLEH.
        """
        now = time.time()
        with self.lock:
            claimed = set()
            if cam_id in self.local_claimed:
                for gid, (t_id, ts) in list(self.local_claimed[cam_id].items()):
                    if now - ts > self._CLAIM_TTL:
                        # Ownership expired
                        del self.local_claimed[cam_id][gid]
                        continue
                    if t_id != tid:
                        claimed.add(gid)
        return claimed

    def find_best_match(self, feature, exclude_ids=None):
        """Mencari Guest dengan kemiripan tertinggi tanpa mendaftarkan ID baru."""
        if feature is None:
            return None, 0.0

        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm

        with self.lock:
            best_id = None
            best_score = -1.0
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
            
            return best_id, best_score

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
                # 🔥 FIX GUEST IDENTITY THEFT (OCCLUSION POISONING) 🔥
                # Sebelumnya max 30. Tapi kalau Guest berpapasan dengan orang lain, 
                # DeepSORT box-nya sering gabung dan menelan baju orang sebelah!
                # Jika 30 fitur 'racun' ini ditelan, identitas Guest rusak dan pindah-pindah.
                # Solusi: Pangkas memori Guest maksimal ke 3 fitur terawal/terbersih saja.
                
                if len(self.guests[best_id]) < 3: 
                    self.guests[best_id].append(feature)
                
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

    def update_guest(self, guest_id, feature=None):
        """Perbarui last_seen dari Guest ID yang sudah valid. Opsional: tambah limit fitur."""
        with self.lock:
            if guest_id in self.guests:
                self.last_seen[guest_id] = time.time()
                if feature is not None and len(self.guests[guest_id]) < 3:
                    # Normalize fitur
                    norm = np.linalg.norm(feature)
                    if norm > 0:
                        feature = feature / norm
                    self.guests[guest_id].append(feature)

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
