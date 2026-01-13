# indoor/body_registry.py
import numpy as np
import os
import time

import threading
from config.settings import SETTINGS

class BodyRegistry:
    def __init__(self, db_folder="data/body_embeddings"):
        self.db_folder = db_folder
        self.profiles = {} 
        self.last_seen = {} 
        self.last_save_time = {} # 🔥 Track waktu simpan terakhir 
        self.save_lock = threading.Lock() # 🛡️ Industrial Grade: Thread Safety Lock 
        
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            
            
        self.load()

    def clear_memory(self):
        """🔥 HARD RESET: Lupakan semua data di RAM 🔥"""
        self.profiles = {}
        self.last_seen = {}
        print("[BodyRegistry] MEMORY WIPED! Semua data lilt-lilt hilang.")

    def load(self):
        self.profiles = {}
        try:
            files = [f for f in os.listdir(self.db_folder) if f.endswith(".npy")]
            for f in files:
                name = os.path.splitext(f)[0]
                path = os.path.join(self.db_folder, f)
                
                # 🔥 AUTO-CLEANUP: Hapus hanya jika data > 18 Jam (Ganti Hari) 🔥
                # Biar kalau restart komputer di hari yang sama, data tidak hilang.
                try:
                    file_time = os.path.getmtime(path)
                    age_hours = (time.time() - file_time) / 3600
                    if age_hours > 18.0:
                        os.remove(path)
                        print(f"[BodyRegistry] 🧹 Menghapus data kadaluarsa untuk: {name} ({age_hours:.1f} jam)")
                        continue
                except: pass

                try:
                    data = np.load(path, allow_pickle=True)
                    if data.ndim == 1: 
                        norm = np.linalg.norm(data)
                        if norm > 0: feat = data / norm
                        self.profiles[name] = [feat]
                    elif data.ndim == 2:
                        self.profiles[name] = []
                        for vec in data:
                            norm = np.linalg.norm(vec)
                            if norm > 0: vec = vec / norm
                            self.profiles[name].append(vec)
                except Exception as e:
                    print(f"[BodyRegistry] Skip corrupt file {f}: {e}")
            
            print(f"[BodyRegistry] Loaded {len(self.profiles)} identities from {self.db_folder}")
        except Exception as e:
            print(f"[BodyRegistry] Error accessing folder: {e}")

    def register(self, name, feature, force_replace_anchors=False):
        if feature is None: return
        
        norm = np.linalg.norm(feature)
        if norm > 0: feature = feature / norm
        
        if name not in self.profiles:
            self.profiles[name] = []
            
        # 🔥 SMART ANCHOR REPLACEMENT (New Outfit) 🔥
        # Jika ganti baju, kita RESET total history lama.
        # Biar baju lama (yang mungkin mirip teman) tidak disimpan lagi.
        if force_replace_anchors:
            print(f"[BodyRegistry] FORCE RESET profile for {name} (New Outfit Detected). Old size: {len(self.profiles[name])}")
            self.profiles[name] = [] # HAPUS SEMUA DAFTAR LAMA
        
        is_duplicate = False
        for existing in self.profiles[name]:
            if np.dot(existing, feature) > 0.95: 
                is_duplicate = True
                break
        
        if not is_duplicate:
            self.profiles[name].append(feature)
            if len(self.profiles[name]) > 15:
                # 🔥 STRATEGI ANTI-DATA KOTOR (ANCHOR) 🔥
                # Kita JANGAN hapus data awal (index 0). Itu biasanya data registrasi paling murni/bagus.
                # Kita hapus data "tengah" (index 5) yang merupakan hasil auto-learn terlama.
                # Jadi: Index 0-4 (5 data pertama) ABADI (Safe Zone).
                #       Index 5-15 (10 data) adalah memori jangka pendek yang berputar.
                self.profiles[name].pop(5)
        
        # Simpan ke disk (Lazy Save Strategy)
        # Jangan simpan setiap frame! Berat!
        # Simpan cuma kalau:
        # 1. Data masih dikit (< 3) -> Penting buat inisialisasi
        # 2. Atau sudah > 15 detik berlalu sejak simpan terakhir
        
        curr_time = time.time()
        last_save = self.last_save_time.get(name, 0)
        
        should_write_disk = False
        if len(self.profiles[name]) < 3:
            should_write_disk = True
        elif (curr_time - last_save) > 15.0:
            should_write_disk = True
            
        if should_write_disk:
            safe_name = name.replace("/", "_").replace("\\", "_")
            path = os.path.join(self.db_folder, f"{safe_name}.npy")
            
            # 🔥 OPTIMISASI ASYNC (THREADING) + LOCK + SNAPSHOT 🛡️
            # 1. Ambil Snapshot data SEKARANG. Jangan kirim pointer list asli.
            snapshot_data = list(self.profiles[name]) 

            def _save_task(data_copy):
                with self.save_lock: # Cegah Race Condition
                    tmp_path = path + ".tmp"
                    try:
                        # 🔥 ATOMIC WRITE (INDUSTRIAL STANDARD) 🛡️
                        # 1. Tulis ke file .tmp dulu (Aman kalau mati listrik tengah jalan)
                        np.save(tmp_path, np.array(data_copy))
                        # 2. Rename cepat (Atomic Operation)
                        if os.path.exists(tmp_path):
                            if os.path.exists(path): os.remove(path)
                            os.rename(tmp_path, path)
                    except Exception as e:
                        print(f"[BodyRegistry] Failed to save {name}: {e}")
                        if os.path.exists(tmp_path): os.remove(tmp_path)

            from threading import Thread
            # 2. Kirim snapshot ke thread
            t = Thread(target=_save_task, args=(snapshot_data,), daemon=True)
            t.start()
            
            self.last_save_time[name] = curr_time

    def match_global(self, query_feat, active_names=[]):
        if len(self.profiles) == 0 or query_feat is None:
            return None, 0.0

        query_feat = query_feat.flatten()

        norm = np.linalg.norm(query_feat)
        if norm > 0: query_feat = query_feat / norm
        else: return None, 0.0

        best_name = None
        best_score = -1.0

        for name, gallery in self.profiles.items():
            local_max_score = 0.0
            for db_feat in gallery:
                db_feat = db_feat.flatten()
                if db_feat.shape[0] != query_feat.shape[0]: 
                    continue
                s = np.dot(query_feat, db_feat)
                if s > local_max_score:
                    local_max_score = s
            
            raw_score = local_max_score
            
            # 🔥 SOLUSI 3: HAPUS DISKON "ACTIVE USER" 🔥
            # Jangan turunkan ke 0.60 walau aktif. Tetap di 0.72.
            # Ini MENCEGAH teman mengambil alih ID saat Anda keluar.
            # UPDATE: Kita turunkan ke 0.40 agar Tracker bisa mengambil keputusan sendiri
            # (Misal untuk Same Room Handover yang butuh 0.48)
            gate_threshold = SETTINGS.get("gate_threshold_global", 0.55)
                
            if raw_score < gate_threshold: 
                continue 

            final_score = raw_score
            
            # Bonus kecil (0.05) hanya kalau skornya SANGAT TINGGI (>0.75)
            # Artinya: "Oke kamu memang Ilham beneran, bukan teman baju mirip"
            if name in active_names and raw_score > 0.75:
                final_score += 0.05 
            
            if final_score > best_score:
                best_score = final_score
                best_name = name
        
        return best_name, best_score

    def update_activity(self, name):
        self.last_seen[name] = time.time()

body_registry = BodyRegistry()