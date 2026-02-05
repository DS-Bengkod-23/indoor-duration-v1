import cv2
import numpy as np

class Visualizer:
    def __init__(self):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.green = (0, 255, 0)
        self.orange = (0, 165, 255)
        self.white = (255, 255, 255)
        self.black = (0, 0, 0)
        self.red = (0, 0, 255)
        
        # 🔥 PERSISTENT ID MAPPING 🔥
        self.name_to_id = {} # { "Ilham": 1, "Guest-2": 2 }
        self.next_pid = 1 # Start ID from 1
        self.tid_to_pid = {} # Map Tracker ID -> Persistent ID (for inheritance)
        self.name_to_id = {} # Map Identity Name -> Persistent ID
        
        # 🔥 GLOBAL SYNC: Shared active PIDs across all cameras per frame cycle
        self.active_pids_cycle = set()
        
    def start_new_cycle(self):
        """
        Dipanggil sekali setiap awal loop utama di video.py.
        Mereset daftar PID yang aktif agar sinkron antar kamera.
        """
        self.active_pids_cycle = set()
        
    def draw_tracks(self, frame, tracks, fusion_manager, face_vote_cache, local_pos_history):
        """
        Menggambar kotak bounding box dan label untuk setiap track.
        """
        active_names_in_frame = {}
        # 🔥 FIX: Use Global Set (Shared across cameras)
        active_pids_now = self.active_pids_cycle
        
        # Pre-pass untuk logika visual (siapa yang hijau, siapa yang orange)
        # Sebenarnya logika ini agak hybrid, tapi kita coba visualkan saja hasil dari fusion.
        
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = map(int, bbox) # Pastikan int
            
            # Ambil label dari Fusion
            # Ambil label dari Fusion
            # Label bisa berupa: "Ilham", "Person 55", atau "Guest-3"
            # label bisa "Ilham" (Hijau), "Guest-5" (Orange), atau "Person 10" (Orange/Raw)
            label, is_real = fusion_manager.get_label(tid)
            
            # --- 🔥 STABLE ID TRANSITION (INHERITANCE LOGIC) 🔥 ---
            pid = None
            
            # 🔥 FIX: Proper ID assignment for each unique identity
            # 1. Cek apakah Label ini (misal "Ilham" atau "Guest-2") sudah punya PID history?
            if label in self.name_to_id and "Person " not in label:
                # KASUS: Identity ini sudah pernah muncul sebelumnya
                # Gunakan PID yang sama
                pid = self.name_to_id[label]
                
                # Update memori Track ID agar ikut ID Identitas
                self.tid_to_pid[tid] = pid
            
            # 2. Jika tidak ada di name_to_id, cek apakah Track ID ini punya PID warisan?
            elif tid in self.tid_to_pid:
                pid = self.tid_to_pid[tid] # Inherit ID lama dari track ini
                
                # 🔥 FIX: Update name_to_id untuk label baru ini
                # Ini handle kasus: Guest-2 → "Ilham" (inheritance)
                if "Person " not in label: 
                    if label not in self.name_to_id:
                        self.name_to_id[label] = pid
            
            else:
                # 3. Benar-benar baru (Track baru & Identitas baru)
                # 🔥 FIX: Assign PID untuk semua non-Person labels (including Guests!)
                if "Person " not in label:
                    # 🔥 COLLISION PREVENTION 🔥
                    # Cari PID yang belum terpakai
                    # Kumpulkan semua PID yang sudah digunakan
                    used_pids = set(self.name_to_id.values()) | set(self.tid_to_pid.values())
                    
                    # Cari next available PID
                    while self.next_pid in used_pids:
                        self.next_pid += 1
                    
                    pid = self.next_pid
                    self.name_to_id[label] = pid
                    self.tid_to_pid[tid] = pid  # 🔥 FIX: Save mapping immediately
                    self.next_pid += 1

            # 🔥 FIX: COLLISION PREVENTION PER FRAME (LAST LINE OF DEFENSE) 🔥
            if pid is not None:
                if pid in active_pids_now:
                    # COLLISION DETECTED! PID ini sudah dipakai track lain di frame ini!
                    # Force Generate NEW PID
                    used_pids_global = set(self.name_to_id.values()) | set(self.tid_to_pid.values()) | active_pids_now
                    
                    new_pid = self.next_pid
                    while new_pid in used_pids_global:
                         new_pid += 1
                    
                    pid = new_pid
                    self.next_pid = new_pid + 1
                    
                    # 🔥 CRITICAL FIX: UPDATE MAPPING PERMANENTLY 🔥
                    # Jangan cuma ganti PID untuk frame ini, tapi update 'name_to_id' juga!
                    # Supaya frame depan dia tidak balik lagi ke PID lama yang conflict.
                    self.name_to_id[label] = pid
                    self.tid_to_pid[tid] = pid
                
                # Mark as used in this frame
                active_pids_now.add(pid)

            # --- DISPLAY LOGIC ---
            display_val = label # Default
            if pid is not None:
                if "Guest-" in label or "Person " in label: 
                     display_val = f"ID: {pid}" # User minta simpel untuk unknown
                else:
                     display_val = f"{label} (ID: {pid})" # Known user

            # Tentukan Warna dan Ketebalan
            if is_real:
                # HIJAU: TEBAL + NAMA
                color = self.green
                thickness = 2
                
                # Get Persistent ID
                if label in self.name_to_id:
                     pid = self.name_to_id[label]
                     display_val = f"{label} (ID: {pid})"
                else:
                     display_val = f"{label}" # Fallback (should not happen)
                
                # Gambar Kotak
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Gambar Label Background biar jelas
                display_text = display_val
                (text_w, text_h), baseline = cv2.getTextSize(display_text, self.font, 0.6, 2)
                cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w, y1), color, -1)
                cv2.putText(frame, display_text, (x1, y1 - 5), self.font, 0.6, self.black, 2)
                
            elif "Guest-" in label:
                # 🔥 MERGE KE ORANGE SEPERTI PERMINTAAN USER 🔥
                # Tetap Orange, tapi ID-nya Persistent!
                color = self.orange
                thickness = 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Display Persistent ID
                if label in self.name_to_id:
                     pid = self.name_to_id[label]
                     display_val = f"ID: {pid}" # User minta simpel
                else:
                     display_val = f"{label}" # Fallback
                
                cv2.putText(frame, display_val, (x1, y1 - 5), self.font, 0.6, color, 2)

            else:
                # ORANGE: TIPIS + POLOS (Bersih) - Raw Tracker
                # Label: "Person 55"
                color = self.orange
                thickness = 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Tampilkan ID agar user bisa register manual
                cv2.putText(frame, f"ID: {tid}", (x1, y1 - 5), self.font, 0.6, color, 2)

    def draw_fps(self, frame, fps):
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 40), self.font, 1.0, self.green, 2)

    def draw_notifications(self, frame, notification_queue):
        """
        Menggambar notifikasi dari queue.
        """
        if len(notification_queue) > 0:
            notif = notification_queue[0]
            text = notif["text"]
            color = notif["color"]
            # timer = notif["timer"] # Timer handled in tracker logic logic usually, but here we just draw
            
            # Draw Background Box
            (text_w, text_h), baseline = cv2.getTextSize(text, self.font, 1.0, 3)
            
            # Center aesthetic or Top Left? Existing code was (60, 100)
            cv2.rectangle(frame, (50, 100 - text_h - 10), (50 + text_w + 20, 100 + 10), self.black, -1)
            cv2.putText(frame, text, (60, 100), self.font, 1.0, color, 3)

    def draw_cam_id(self, frame, cam_id):
        cv2.putText(frame, f"CAM {cam_id}", (10, 20), 
                    self.font, 0.6, (0, 255, 255), 2)

visualizer = Visualizer()
