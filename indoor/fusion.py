class FaceBodyFusion:
    def __init__(self):
        # Menyimpan Label (Nama) untuk setiap Track ID
        self.labels = {}   # Format: {track_id: "Name"}
        
        # Menyimpan Status "Real" (Apakah sudah teridentifikasi?)
        # True = Hijau (Dikenal), False = Oranye (Unknown/Person X)
        self.is_real = {}  # Format: {track_id: True/False}

    def get_label(self, track_id):
        """Mengambil label dan status untuk Track ID tertentu"""
        # Jika ID belum pernah dicatat, kembalikan default
        if track_id not in self.labels:
            return f"Person {track_id}", False
        
        return self.labels[track_id], self.is_real.get(track_id, False)

    def lock_real_name(self, track_id, name):
        """Mengunci nama seseorang (Menjadi HIJAU)"""
        self.labels[track_id] = name
        self.is_real[track_id] = True

    def set_is_real(self, track_id, status):
        """
        🔥 FUNGSI BARU (FIX ERROR):
        Memaksa ubah status warna.
        Digunakan oleh Highlander Check untuk mereset "Ilham Palsu" jadi Oranye.
        """
        self.is_real[track_id] = status

    def clean_stale_tracks(self, active_track_ids):
        """Membersihkan memori ID yang sudah hilang"""
        # Hapus data ID yang tidak ada di list active_track_ids
        for tid in list(self.labels.keys()):
            if tid not in active_track_ids:
                del self.labels[tid]
                if tid in self.is_real:
                    del self.is_real[tid]