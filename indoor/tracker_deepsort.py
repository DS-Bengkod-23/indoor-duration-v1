# indoor/tracker_deepsort.py
import cv2, time, numpy as np
import threading # 🔥 THREAD SAFETY
from indoor.face_detector import FaceDetectorYuNet
from indoor.person_detector import PersonDetectorYOLO
from indoor.fusion import FaceBodyFusion
from indoor.deepsort.deep_sort import DeepSort
from indoor.body_registry import body_registry
from indoor.shared_models import get_face_recognizer, get_osnet
from indoor.session_registry import session_registry
from config.settings import SETTINGS
from indoor.visualizer import visualizer

class GlobalIdentityManager:
    def __init__(self):
        self.active_identities = {} 
        self.room_mapping = SETTINGS.get("room_mapping", {})
        self.lock = threading.Lock() # 🛡️ Industrial Grade Thread Safety

    def get_room_name(self, cam_index):
        # Read-only dari config, gak perlu lock strict, tapi access dictionary aman in Python.
        key = f"CAM_{cam_index}"
        # UPDATE: USER CONFIRM "MASIH SATU RUANGAN" 
        # Jadi default-nya kita anggap SATU RUANGAN BESAR (Shared).
        # Ini mengaktifkan logika "Same Room Handover" (bukan Diff Room).
        return self.room_mapping.get(key, "Shared_Room_Alpha")

    def get_active_names_list(self):
        now = time.time()
        active = []
        with self.lock: # 🛡️ Safe Reading
            for name, data in self.active_identities.items():
                last_seen = data[3]
                # Ingatan global 15 detik biar handover antar kamera santai
                if now - last_seen < 15.0: 
                    active.append(name)
        return active

    def is_identity_verified(self, name):
        """
        Check if identity is currently active/known in the session.
        Digunakan untuk 'Fast-ID' (Re-entry).
        """
        with self.lock:
            return name in self.active_identities

    def try_claim_identity(self, name, cam_index, track_id, score, claim_type='BODY'):
        now = time.time()
        
        with self.lock: # 🛡️ Safe Writing (CRITICAL SECTION)
            if name not in self.active_identities:
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True
        
            curr_cam, curr_id, curr_score, last_seen = self.active_identities[name]
        
        # Cek Kesamaan Ruangan
        room_curr = self.get_room_name(curr_cam)
        room_new = self.get_room_name(cam_index)
        is_same_room = (room_curr == room_new)

        if curr_cam == cam_index and curr_id == track_id:
            self.active_identities[name] = (cam_index, track_id, max(score, curr_score), now)
            return True

        if curr_cam != cam_index:
            # JALUR VIP: SATU RUANGAN
            if is_same_room:
                # 🔥 SOLUSI OVERLAP KAMERA (SATU RUANGAN) 🔥
                # Jika time_diff < 3.0 (Target masih aktif di kamera lain):
                
                # 🔥 FACE BYPASS: WAJAH ADALAH KUNCI UTAMA 🔥
                # Jika ini claim dari DETEKSI WAJAH ('FACE'), kita langsung izinkan 100%.
                # Karena wajah itu bukti mutlak, tidak perlu debat soal threshold body.
                if claim_type == 'FACE':
                    self.active_identities[name] = (cam_index, track_id, score, now)
                    return True

                # Jika Body Only, baru kita pakai aturan ketat:
                # Kita Izinkan "Double Presence" HANYA jika kemiripan TINGGI (> 0.82).
                # Jika time_diff < frame_count (Target masih aktif di kamera lain):
                # Kita Izinkan "Double Presence" HANYA jika kemiripan TINGGI.
                time_diff = now - last_seen
                if time_diff < SETTINGS.get("time_back_view_window", 3.0):
                    # 🔥 RELAXED FOR SEQUENTIAL ENTRY (SAME ROOM):
                    if score > SETTINGS.get("thresh_same_room", 0.68):
                        self.active_identities[name] = (cam_index, track_id, score, now)
                        return True
                    else:
                        print(f"[CLAIM REJECT] Same Room Low Score. {score:.2f} <= {SETTINGS.get('thresh_same_room', 0.68)}")
                        return False 
                
                # Normal Handover
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True
            else:
                # BEDA RUANGAN
                time_diff = now - last_seen
                if time_diff < 1.5: 
                    if score < SETTINGS.get("thresh_anti_clone", 0.82):
                        print(f"[CLAIM REJECT] Diff Room Anti Teleport. {score:.2f} < {SETTINGS.get('thresh_anti_clone', 0.82)}")
                        return False 
                
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True

        # Anti-Hijack dalam satu kamera
        if curr_cam == cam_index and curr_id != track_id:
            time_gap = now - last_seen
            
            # 🔥 STRICT LOCK
            # Reduce lock time: 3.0 -> 1.5 seconds.
            # Agar kalau orang yang sama masuk lagi (handover cepet / re-entry), tidak dianggap imposter.
            if time_gap < 1.5:
                 if claim_type == 'FACE':
                     self.active_identities[name] = (cam_index, track_id, score, now)
                     return True

                 # Relaxed score check: Allow if score > 0.65 (was 0.85)
                 if score > SETTINGS.get("thresh_strict_lock", 0.65) or score > (curr_score + 0.20):
                     self.active_identities[name] = (cam_index, track_id, score, now)
                     return True
                 
                 print(f"[CLAIM REJECT] Strict Lock. Score {score:.2f} not enough vs Curr {curr_score:.2f} (+0.20 needed or >0.65)")
                 return False
            
            if claim_type == 'FACE': 
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True
            else: return True # 🔥 Auto-Allow if time_gap >= 1.5s (Reset Lock)

        if score > (curr_score + 0.05): # 🔥 UPDATE: Butuh margin +0.05 untuk update score (Stabilizer)
            self.active_identities[name] = (cam_index, track_id, score, now)
            return True
            
        return True 

global_id_manager = GlobalIdentityManager()

class MultiObjectTracker:
    def __init__(self):
        self.face_detector = FaceDetectorYuNet()
        self.face_recognizer = get_face_recognizer()
        self.person_detector = PersonDetectorYOLO()
        self.osnet = get_osnet()
        self.deepsort = DeepSort(
            max_age=SETTINGS["max_age"],
            n_init=SETTINGS["min_hits"],
            max_iou_distance=SETTINGS["max_iou_distance"]
        )
        self.fusion = FaceBodyFusion()
        self.frame_idx = 0
        self.prev_time = time.time()
        self.camera_id = -1 
        self.local_pos_history = {}
        self.face_vote_cache = {}
        self.reid_skip_timer = {} 
        self.last_face_confirmed = {} # 🔥 BARU: Catat kapan terakhir lihat wajah
        self.notification_queue = [] # Queue untuk notifikasi visual (Teks, Warna, Durasi)
        
        # 🔥 STATE BARU UNTUK SAFETY 🔥
        self.occlusion_cooldown = {} # Mencatat kapan terakhir kena macet/occlusion
        self.verification_counter = {} # Menghitung berapa kali berturut-turut match (Stabilizer)
        self.track_start_times = {} # 🔥 RETROACTIVE: ID -> First Seen Timestamp
        
        # 🔥 FAST-ID Identity Map (Missing Init Fix)
        self.guest_identity_map = {}

    def set_camera_id(self, cam_id):
        self.camera_id = cam_id

    def process_frame(self, frame):
        self.frame_idx += 1
        out = frame.copy()
        
        run_detection = (self.frame_idx % SETTINGS["det_interval"] == 0)
        if run_detection:
            raw_dets = self.person_detector.detect(frame)
            filtered_dets = []
            
            # 🔥 1. FILTER KURSI & OBYEK BANTET 🔥
            for d in raw_dets:
                x1, y1, x2, y2, conf = d
                w = x2 - x1
                h = y2 - y1
                
                # Hitung Rasio Tinggi : Lebar
                if w > 0:
                    ratio = h / w
                    # Manusia biasanya ratio > 1.8 (Jangkung)
                    # Kursi/Kotak biasanya ratio < 1.5 (Bantet)
                    
                    # ATURAN: Kalau "Bantet" (ratio < 1.6) DAN Confidence pas-pasan (< 0.75), BUANG!
                    # Kecuali kalau conf sangat tinggi (misal orang duduk jelas banget), kita loloskan.
                    sitting_ratio = SETTINGS.get("thresh_sitting_ratio", 1.6)
                    sitting_conf = SETTINGS.get("thresh_sitting_conf", 0.60)
                    if ratio < sitting_ratio and conf < sitting_conf:
                        continue 
                    
                filtered_dets.append([x1, y1, x2, y2, conf])

            # 🔥 SOLUSI ANTI-NYANGKUT 1: DYNAMIC GATING 🔥
            # Jika ada lebih dari 1 orang, MATIKAN Mode Ninja.
            # Gunakan setting 'gate_threshold_global' (Default 0.40 - Sangat Strict)
            strict_gate = SETTINGS.get("gate_threshold_global", 0.40)
            
            if len(filtered_dets) > 1:
                self.deepsort.max_iou_distance = strict_gate # STRICT MODE (Anti-Nyangkut)
            else:
                self.deepsort.max_iou_distance = strict_gate + 0.30 # Relaxed dikit tapi jangan 1.1 (Bahaya)

            self.deepsort.update(filtered_dets)
        else:
            for track in self.deepsort.tracks:
                track.predict(self.deepsort.kf)
        
        tracks = self.deepsort.get_active_tracks(with_feature=True)
        
        run_ai_recognition = (self.frame_idx % SETTINGS["face_interval"] == 0)
        current_face_map = {} 
        curr_time_now = time.time()

        # --- LOGIKA FACE RECOG ---
        if len(tracks) > 0 and run_ai_recognition:
            faces_processed_count = 0 
            for t in tracks:
                tid, bbox = t[0], t[1]
                x1, y1, x2, y2 = bbox
                label, is_real = self.fusion.get_label(tid)
                
                if is_real: continue
                # 🔥 NAIKKAN LIMIT: Pakai Settings (Default 10)
                max_faces = SETTINGS.get("max_faces_to_process", 10)
                if faces_processed_count >= max_faces: break
                
                # 🔥 SITTING OPTIMIZATION: EXPAND SEARCH AREA 🔥
                # Saat duduk, kepala ada di bagian atas, tapi proporsi tubuh memendek.
                # Jadi kita harus cari agak lebih dalam ke bawah (1.2 instead of 1.5 divider).
                search_y1 = max(0, y1 - 40) 
                face_search_area = frame[search_y1:min(frame.shape[0], y1 + int((y2-y1)/1.2)), max(0, x1):x2]
                
                if face_search_area.size > 0:
                    faces = self.face_detector.detect(face_search_area)
                    if len(faces) > 0:
                        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                        if fw > 15 and fh > 15: 
                            abs_x, abs_y = x1 + fx, search_y1 + fy
                            y_start = max(0, abs_y)
                            y_end = min(frame.shape[0], abs_y + fh)
                            x_start = max(0, abs_x)
                            x_end = min(frame.shape[1], abs_x + fw)
                            if y_end > y_start and x_end > x_start:
                                face_crop = frame[y_start:y_end, x_start:x_end]
                                if face_crop.size > 0:
                                    try:
                                        emb = self.face_recognizer.get_embedding(cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB))
                                        if emb is not None:
                                            name, score, _ = self.face_recognizer.identify(emb)
                                            if name:
                                                current_face_map[tid] = name
                                                self.face_vote_cache.setdefault(tid, {}).setdefault(name, 0)
                                                self.face_vote_cache[tid][name] += 1
                                                
                                                # 🔥 UPDATE LAST CONFIRMED TIME 🔥
                                                self.last_face_confirmed[tid] = curr_time_now

                                                if self.face_vote_cache[tid][name] >= 1: # Instan 1 frame
                                                    if global_id_manager.try_claim_identity(name, self.camera_id, tid, score, 'FACE'):
                                                        self.fusion.lock_real_name(tid, name)
                                                        self.reid_skip_timer[tid] = 0
                                                        
                                                        # 🔥 LANGSUNG SIMPAN BODY SAAT PERTAMA KALI DIKENALI 🔥
                                                        # Ini mengatasi race condition dimana is_real_now masih False
                                                        try:
                                                            body_feat = self.extract_body_feature(frame, bbox, tid)
                                                            if body_feat is not None:
                                                                current_len = len(body_registry.profiles.get(name, []))
                                                                if current_len < 15:
                                                                    body_registry.register(name, body_feat)
                                                                    print(f"[FIRST-SAVE] Body pertama untuk {name} tersimpan! (Total: {current_len+1})")
                                                        except: pass
                                            else:
                                                current_face_map[tid] = "UNKNOWN_FACE"
                                    except Exception as e: pass
                faces_processed_count += 1 

        # --- DETEKSI OCCLUSION (TUMPANG TINDIH) ---
        # Cek apakah ada 2 orang yang saling menutupi?
        # Kalau ada, kita harus LEBIH STRICT (Anti-Switch) & STOP BELAJAR.
        
        occluded_tracks = set()
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                tid1, box1 = tracks[i][0], tracks[i][1]
                tid2, box2 = tracks[j][0], tracks[j][1]
                
                # IOU-based Occlusion Detection (Industrial Grade)
                x_left = max(box1[0], box2[0])
                y_top = max(box1[1], box2[1])
                x_right = min(box1[2], box2[2])
                y_bottom = min(box1[3], box2[3])
                
                if x_right > x_left and y_bottom > y_top:
                    intersection_area = (x_right - x_left) * (y_bottom - y_top)
                    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
                    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
                    union_area = area1 + area2 - intersection_area
                    
                    if union_area > 0:
                        iou = intersection_area / union_area
                        if iou > 0.25: # Strict Occlusion Threshold
                            occluded_tracks.add(tid1)
                            occluded_tracks.add(tid2)
                            # 🔥 RECORD OCCLUSION TIME 🔥
                            self.occlusion_cooldown[tid1] = curr_time_now
                            self.occlusion_cooldown[tid2] = curr_time_now

        # --- PROSES OSNET (Body ReID) ---
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = bbox
            label, is_real_now = self.fusion.get_label(tid)
            
            # 🔥 KEEP ALIVE (PENTING BUAT ANTI-CLONING) 🔥 
            # Jika identitas sudah verified, kita harus lapor "SAYA MASIH DISINI" setiap frame.
            # Kalau tidak lapor, timestamp akan expired > 3 detik, dan kamera lain bisa mencuri ID ini.
            if is_real_now:
                 still_valid = global_id_manager.try_claim_identity(label, self.camera_id, tid, 1.0, 'KEEP_ALIVE')
                 if not still_valid:
                     # 🚨 HIGHLANDER PROTOCOL: THERE CAN BE ONLY ONE 🚨
                     # Global Manager menolak klaim kita (berarti diambil alih kamera lain).
                     # Kita harus MENGALAH (Drop Identity) sekarang juga.
                     print(f"[ANTI-CLONE] ID {label} diambil alih kamera lain. Drop tracking di Cam {self.camera_id}.")
                     self.fusion.lock_real_name(tid, f"Person {tid}")
                     self.fusion.set_is_real(tid, False)
                     is_real_now = False # Update status lokal biar gak lanjut proses di bawah
            
            should_run_osnet = False 
            if is_real_now:
                if self.reid_skip_timer.get(tid, 0) > 0:
                    should_run_osnet = False
                    self.reid_skip_timer[tid] -= 1 
                else:
                    should_run_osnet = True
            else:
                if (self.frame_idx + int(tid)) % 3 == 0:
                    should_run_osnet = True
                else:
                    should_run_osnet = False
            
            if should_run_osnet:
                feat = self.extract_body_feature(frame, bbox, tid)
            else:
                feat = None

            if feat is not None:
                active_list = global_id_manager.get_active_names_list()
                
                # [LOGIKA 1] INTEGRITY CHECK (Orang yang sudah hijau)
                processed_face_flag = (tid in current_face_map)
                
                if is_real_now:
                    # CASING A: Ada Wajah Terdeteksi
                    if processed_face_flag:
                        face_name = current_face_map.get(tid, "UNKNOWN")
                        
                        # 🔥 UPDATE LAST CONFIRMED TIME (Double check) 🔥
                        if face_name != "UNKNOWN" and face_name != "UNKNOWN_FACE":
                             self.last_face_confirmed[tid] = curr_time_now

                        # Jika wajah cocok dengan label body -> REKAM BODY (Front View)
                        if face_name == label:
                            try:
                                current_len = len(body_registry.profiles.get(label, []))
                                
                                # 🔥 OPTIMAL BOOTSTRAPPING STRATEGY 🔥
                                # Fase Awal (< 3 data): Agresif, setiap 5 frame.
                                # Fase Normal (>= 3 data): Santai, setiap 15 frame.
                                is_bootstrapping = (current_len < 3)
                                
                                should_save = False
                                if is_bootstrapping:
                                    should_save = (self.frame_idx % 5 == 0)  # Lebih cepat
                                else:
                                    should_save = (self.frame_idx % 15 == 0) # Normal
                                
                                if should_save and current_len < 15:
                                    body_registry.register(label, feat)
                                    print(f"[AUTO-LEARN-FACE] Menambahkan pose DEPAN untuk {label} (Total: {current_len+1})")
                            except: pass

                    # CASING B: Tidak Ada Wajah (Cek Integrity Body)
                    elif label in body_registry.profiles:
                        gallery = body_registry.profiles[label]
                        norm_q = np.linalg.norm(feat)
                        feat_norm = feat.flatten() / norm_q if norm_q > 0 else feat.flatten()
                        
                        raw_score = -1.0
                        if isinstance(gallery, list):
                            for db_feat in gallery:
                                db_feat = db_feat.flatten() 
                                s = np.dot(feat_norm, db_feat)
                                if s > raw_score: raw_score = s
                        else:
                            db_feat = gallery.flatten()
                            raw_score = np.dot(feat_norm, db_feat)
                        
                        detected_face = current_face_map.get(tid, None)
                        if detected_face == "UNKNOWN_FACE": raw_score -= 0.15 
                        
                        # 🔥 ANTI-NYANGKUT LOGIC 🔥
                        # Kalau ID sudah verified:
                        # - Normal: 0.40 (TURUNIN DIKIT: 0.45 -> 0.40 biar toleransi lighting beda kamera)
                        # - Occluded (Tumpang Tindih): 0.65 (LEBIH STRICT!)
                        is_occluded = (tid in occluded_tracks)
                        cutoff_threshold = 0.65 if is_occluded else 0.40
                        
                        # 🔥 SOLUSI GANTI BAJU / NEW OUTFIT 🔥
                        # Jika Wajah COCOK, kita TRUST FACE 100%. Abaikan skor body rendah.
                        # Kita anggap ini "Ganti Baju" & Kita Paksa Belajar.
                        is_face_confirmed = (detected_face == label)
                        
                        if is_face_confirmed:
                            # BYPASS ANTI-NYANGKUT
                            # Jangan reset walau skor body 0.2 (karena baju beda).
                            # Justru harus kita simpan biar sistem tau baju baru ini.
                            self.reid_skip_timer[tid] = 0 # Biar next frame diproses lagi
                            
                            # PAKSA SIMPAN (Force Learn) & GANTI ANCHOR
                            # Karena skor sangat rendah (baju beda total), kita request REPLACE ANCHORS.
                            # Artinya: Lupakan baju lama, fokus ke baju baru ini.
                            try:
                                # 🔥 TUNED: 0.50 -> 0.60. Biar lebih sensitif kalau warna baju mirip (misal Biru Tua vs Hitam)
                                should_replace = (raw_score < 0.60) 
                                body_registry.register(label, feat, force_replace_anchors=should_replace)
                                
                                action_msg = "REPLACE OLD DATA" if should_replace else "ADD NEW DATA"
                                print(f"[NEW-OUTFIT] Wajah cocok! {action_msg} untuk {label} (Skor lama: {raw_score:.2f})")
                                
                                # 🔥 TAMBAHKAN NOTIFIKASI VISUAL 🔥
                                self.notification_queue.append({
                                    "text": f"OUTFIT CHANGE: {label}", 
                                    "color": (0, 0, 255), # Merah
                                    "timer": 90 # 3 detik @ 30 FPS
                                })
                            except: pass
                            
                        elif raw_score < cutoff_threshold: 
                            # 🔥 GRACE PERIOD (ANTI-FLICKER GERAK CEPAT) 🔥
                            # Jangan langsung reset jika skor drop sesaat (motion blur).
                            # Kita kasih toleransi 3 frame berturut-turut baru reset.
                            
                            fail_count = self.verification_counter.get(f"fail_{tid}", 0) + 1
                            self.verification_counter[f"fail_{tid}"] = fail_count
                            
                            if fail_count > 3: # Reset hanya jika sudah 3x gagal
                                print(f"[ANTI-NYANGKUT] ID {tid} drop! Skor: {raw_score:.2f} (Occluded: {is_occluded}). RESET!")
                                self.fusion.lock_real_name(tid, f"Person {tid}")
                                self.fusion.set_is_real(tid, False)
                                self.reid_skip_timer[tid] = 0 
                                if label in global_id_manager.active_identities:
                                    del global_id_manager.active_identities[label]
                                is_real_now = False 
                            else:
                                # Masih dalam masa toleransi, pertahankan status hijau
                                # Tapi jangan update score (pakai score lama)
                                pass 
                        else:
                            self.reid_skip_timer[tid] = 30
                            
                            # 🔥 LOGIKA BARU: SMART AUTO-UPDATE (BELAJAR TERUS TAPI AMAN) 🔥
                            # Syarat: Skor Tinggi (>0.80) DAN Baru saja lihat wajah (< 5 detik lalu)
                            # DAN TIDAK SEDANG OCCLUDED (Jangan belajar pas tumpang tindih!)
                            
                            time_since_face = curr_time_now - self.last_face_confirmed.get(tid, 0)
                            current_gallery_len = len(gallery)
                            
                            # 🔥 OPTIMAL BOOTSTRAPPING (Blind Learning) 🔥
                            is_bootstrapping = (current_gallery_len < 3)
                            should_save_now = False
                            if not is_occluded: # Cuma boleh save kalau bersih (tidak occluded)
                                if is_bootstrapping:
                                    should_save_now = (self.frame_idx % 5 == 0)
                                else:
                                    should_save_now = (self.frame_idx % 10 == 0)
                            
                            # TURUNIN AMBANG SKOR: 0.80 -> 0.78 (Biar lebih gampang nangkep pas muter)
                            # 🔥 LOGIKA SIDE-VIEW TANGKAP CEPAT (Agresif) 🔥
                            # Jika wajah BARU SAJA hilang (< 3.0 detik), kita terima body score rendah (0.60)
                            # Ini untuk menangkap momen saat Anda baru saja berbalik badan (Back View).
                            # 🔥 LOGIKA SIDE-VIEW TANGKAP CEPAT (Agresif) 🔥
                            score_thresh = SETTINGS.get("thresh_diff_room", 0.78)
                            if time_since_face < SETTINGS.get("time_back_view_window", 3.0):
                                score_thresh = SETTINGS.get("thresh_back_view_learn", 0.60) 

                            # 🔥 SAFETY: JANGAN BELAJAR KALAU ABIS KETUTUPAN! (Anti-Pollution) 🔥
                            # Mencegah belajar fitur orang asing yang numpang lewat.
                            is_recently_occluded = (curr_time_now - self.occlusion_cooldown.get(tid, 0) < 2.0)

                            if raw_score > score_thresh and should_save_now and not is_recently_occluded:
                                # PERPANJANG WAKTU SAFETY: 5.0 -> 8.0 detik (Biar pas muter pelan gak keburu habis)
                                if time_since_face < 8.0: 
                                    try:
                                        if current_gallery_len < 15: 
                                            body_registry.register(label, feat)
                                            print(f"[AUTO-LEARN] Menambahkan pose baru untuk {label} (Skor: {raw_score:.2f} | Total: {current_gallery_len+1})")
                                    except Exception as e: pass
                                else:
                                    # Opsional: Print debug kalau mau tau kenapa gak save
                                    pass


                # [LOGIKA 2] RECOGNITION (PINTU MASUK / HANDOVER)
                if not is_real_now:
                    # 🔥 FIX CRASH: Initialize variables first! 🔥
                    m_name = None
                    m_score = 0.0
                    
                    # Cek apakah ada Face Recognition yang valid
                    detected_face_val = current_face_map.get(tid, None)
                    if detected_face_val and detected_face_val not in ["UNKNOWN", "UNKNOWN_FACE"]:
                        m_name = detected_face_val
                        m_score = 0.95 # High confidence for Face
                        
                    # 🔥 FIX: JANGAN OVERWRITE KALAU WAJAH SUDAH IDENTIFIED! 🔥
                    # Kalau Face Rec sudah valid dan bukan 'UNKNOWN_FACE', kita pakai itu.
                    # Jangan sampai Body Rec (yang mungkin fail) menimpa jadi None/0.0.
                    
                    face_already_found = (m_name is not None and m_score > 0.60)
                    
                    if not face_already_found:
                        body_result = body_registry.match_global(feat, active_names=active_list)
                        if body_result is not None:
                            m_name, m_score = body_result
                        else:
                            m_name, m_score = None, 0.0
                    else:
                        # Kalau sudah ada wajah, kita CUMA "tambah keyakinan" pakai body (Opsional),
                        # Tapi jangan biarkan body merusak (overwrite jadi None).
                        body_result = body_registry.match_global(feat, active_names=active_list)
                        if body_result is not None:
                            b_name, b_score = body_result
                            if b_name == m_name and b_score > 0:
                                m_score = max(m_score, b_score) # Ambil yang terbaik
                    
                    detected_face = current_face_map.get(tid, None)
                    # 🔥 FIX: Jangan langsung nolkan! Beri penalti saja.
                    # Jika "UNKNOWN_FACE" (muka terlihat tapi gak kenal), mungkin cuma blur/samping.
                    # Kalau score body SANGAT TINGGI (misal 0.90), dikurangi 0.20 jadi 0.70 (Masih lolos).
                    # Ini mencegah False Negative saat Anda menoleh.
                    if detected_face == "UNKNOWN_FACE" and not face_already_found: 
                        m_score -= 0.20 
                    
                    # 🔥 2. LOGIKA JALUR VIP (SAME ROOM) 🔥
                    # Cek apakah nama yang cocok (m_name) berada di RUANGAN YANG SAMA?
                    is_same_room_handover = False
                    if m_name in global_id_manager.active_identities:
                        cur_cam = global_id_manager.active_identities[m_name][0]
                        last_seen_time = global_id_manager.active_identities[m_name][3]
                        room_curr = global_id_manager.get_room_name(cur_cam)
                        room_my = global_id_manager.get_room_name(self.camera_id)
                        
                        # 🔥 SYARAT VIP: Ruangan Sama DAN Waktu < 5 Detik
                        # Kalau lebih dari 5 detik, dianggap "New Entry" (Normal Threshold)
                        # Ini mencegah Exit Jump ke Stranger.
                        time_since_seen = curr_time_now - last_seen_time
                        if room_curr == room_my and time_since_seen < 5.0:
                            is_same_room_handover = True

                    box_height = y2 - y1
                    
                    
                    # 🔥 3. LOGIKA DETEKSI CROWDS (Dynamic Strictness) 🔥
                    # Hitung jumlah orang yang terdeteksi di frame ini
                    person_count = len(tracks)
                    
                    # Ambil threshold dasar dari Settings
                    # Ambil threshold dasar dari Settings
                    base_thresh = SETTINGS.get("thresh_same_room", 0.75) if is_same_room_handover else SETTINGS.get("thresh_diff_room", 0.81)

                    # 🔥 UPDATE v12.18: BLIND ACTIVE BOOST (SOLUSI TAMPAK BELAKANG) 🔥
                    # Jika orangnya SUDAH ADA DI GEDUNG (Active), kita harus lebih percaya diri.
                    # Dulu threshold 0.81 terlalu strict buat re-id tampak belakang (setelah track putus).
                    # Sekarang kita turunkan jadi 0.69 kalau dia 'Known Active'.
                    is_known_active = (m_name in global_id_manager.active_identities)
                    if is_known_active and not is_same_room_handover:
                        # base_thresh -= 0.12 # 🔥 SAFEGUARD: REMOVED. 0.69 terlalu rendah, bikin stranger jadi kita.
                        pass

                    
                    #  4. LOGIKA DISTANCE TIERED (Refined for CCTV v12.9) 
                    # Mengatasi Masalah #3 (Jauh salah).
                    is_tiny = (box_height < 60)
                    is_small = (box_height < 90)
                    
                    #  CONTEXT AWARENESS BOOST 
                    # Jika orang ini SUDAH AKTIF di kamera lain (misal Cam 0), dan kita lihat dia di Cam 1 (Jauh),
                    # Maka kita harus "curiga positif" bahwa itu dia. Kita BOOST skornya.
                    # Ini kunci agar CCTV blur tetap bisa ngenalin orang yang sudah dikenal sistem.

                    
                    
                    if is_tiny: # TINY (< 60px)
                         base_thresh = SETTINGS.get("thresh_blind_small", 0.60)
                         # 🔥 FIX: HAPUS BOOST. Objek Tiny terlalu berisiko. Biar murni threshold.
                         # if is_known_active: m_score += 0.05
                    elif is_small: # SMALL (< 90px)
                         base_thresh = SETTINGS.get("thresh_blind_small", 0.72) # 🔥 FIX: Hapus +0.05. 0.72 strict enough.
                         # 🔥 FIX: HAPUS BOOST JUGA.
                         # if is_known_active: m_score += 0.03
                    elif box_height < 150: # MEDIUM (< 150px)
                         #  PAKAI 0.68 (Match dengan Same Room). Jangan 0.65 (Terlalu rendah), jangan 0.72 (Terlalu tinggi).
                         base_thresh = 0.68 
                         # if is_known_active: base_thresh -= 0.05 #  SAFEGUARD: REMOVED. Tetap 0.65.
                    else: # LARGE
                         base_thresh = SETTINGS.get("thresh_blind_large", 0.75)


                    #  HIJACK GUARD (POST-MORTEM CHECK) 
                    # Mengatasi Masalah #2 (Hijau jadi orang lain).
                    # Jika ID sudah CONFIRMED (Hijau), tapi skornya jeblok di bawah 0.35 (Back View bisa rendah),
                    # Berarti itu BUKAN orang yang sama! (Mungkin orang lewat di belakang).
                    
                    #  UPDATE: RELAXED FOR SITTING POSE 
                    # Kalau orang duduk (w > h atau ratio < 1.6), skor pasti drop.
                    # Jadi jangan force detach kalau dia lagi duduk.
                    w_box = x2 - x1
                    h_box = y2 - y1
                    ratio_box = h_box / w_box if w_box > 0 else 2.0
                    
                    hijack_threshold = 0.50 # STRICTER: 0.35 -> 0.50. Kalau baju beda, langsung lepas!
                    if ratio_box < 1.8: # Sitting or Squatting
                         hijack_threshold = 0.35 # Relaksasi (jangan 0.20, terlalu rendah)
                         
                    if m_name == label and m_score < hijack_threshold:
                          print(f"[HIJACK GUARD] {label} mismatch ({m_score:.2f} < {hijack_threshold}). Ratio: {ratio_box:.2f}. FORCE DETACH.")
                          self.fusion.set_is_real(tid, False)
                          is_real_now = False


                    # ADAPTIVE LOGIC:
                    # Rame = Longgarkan dikit (-0.05). Sepi = Strict (+0.03).
                    if person_count > 3: # CROWDED (>3 Orang)
                         base_thresh -= 0.03
                    elif person_count > 1:
                        if is_same_room_handover: 
                             # 🔥 RELAX dikit (0.72 -> 0.70) biar Body Only gak mati kutu
                             # TAPI nanti kita kasih syarat STREAK lebih panjang.
                             base_thresh = max(0.68, base_thresh - 0.05) 
                    else:
                        base_thresh = min(0.90, base_thresh) # 🔥 REMOVED +0.03. 0.72 sudah cukup ketat.
                        
                    # Clipping Safety (Global Floor)
                    # Clipping Safety (Global Floor)
                    # 🔥 UPDATE v12.7: FLOOR RESTORED 0.45 (Safe Medium)
                    base_thresh = max(0.45, min(base_thresh, 0.95))

                    # ANTI-FLICKER (OCCLUSION PENALTY)
                    # Mengatasi Masalah #1 (Switch pas ketutupan).
                    # Kalau habis ketutupan, harus strict 2x lipat.
                    time_since_occlusion = curr_time_now - self.occlusion_cooldown.get(tid, 0)
                    if time_since_occlusion < 2.0:
                         # 🔥 RELAXED PENALTY: Disable kalau score lumayan (0.68)
                         if m_score < 0.68:
                             base_thresh += 0.05
                    
                    # Streak Validation (Berapa kali harus match berturut-turut?)
                    if is_tiny: 
                        required_streak = 2 if is_known_active else 5 # PERCEPAT: 5 -> 2 kalau known
                    elif is_small: 
                        required_streak = 2 if is_known_active else 3 # PERCEPAT: 3 -> 2
                    else: 
                        # 🔥 STREAK VALIDATION LOGIC 🔥
                        # Syarat: Harus konsisten N frame berturut-turut baru boleh claim.
                        # Ini untuk mencegah "One Frame Wonder" (False Positive kilat).
                        
                        if is_known_active:
                            # Kalau user sudah aktif (misal handover), lebih mudah percaya.
                            required_streak = 1
                        elif m_score > 0.85:
                            # 🔥 INSTANT CLAIM HIGH CONFIDENCE 🔥
                            # Kalau skor sangat tinggi (sangat mirip), LANGSUNG claim.
                            # Ini solusi buat "Entry Flicker" (kadang bagus kadang jelek).
                            # Sekali bagus -> LANGSUNG HIJAU.
                            required_streak = 1
                        else:
                            # Kalau baru masuk & skor standar, harus konsisten 3x.
                            required_streak = 3
                    
                    current_streak = self.verification_counter.get(tid, 0)
                    
                    if m_name and m_score > base_thresh:
                        # Potensi Match! Naikkan Counter.
                        self.verification_counter[tid] = current_streak + 1
                        
                        # Cuma boleh claim kalau streak sudah cukup
                        if self.verification_counter[tid] >= required_streak:
                            # 1. Cek Konsistensi Wajah (Kalau ada data wajah)
                            # Jangan sampai wajah A, tapi body cocok B.
                            
                            # Logika: Kalau wajahnya "UNKNOWN_FACE", kita percaya body.
                            # Tapi kalau wajahnya JELAS "Budi", tapi Body mirip "Andi", JANGAN percaya Body.
                            face_label = current_face_map.get(tid, None)
                            is_face_mismatch = (face_label and face_label != "UNKNOWN_FACE" and face_label != m_name)
                            
                            if not is_face_mismatch:
                                try_result = global_id_manager.try_claim_identity(m_name, self.camera_id, tid, m_score)
                                if try_result:
                                    print(f"[REID SUCCESS] ID {tid} -> {m_name} (Skor: {m_score:.2f})")
                                    self.fusion.lock_real_name(tid, m_name)
                                    self.reid_skip_timer[tid] = 0
                                    
                                    # 🔥 FAST-ID LEARNING 🔥
                                    # Kalau kita berhasil kenali wajah/body sebagai "Ilham",
                                    # Kita juga harus tanya: "Ilham ini Guest-berapa secara body?"
                                    # Supaya nanti kalau cuma kelihatan body-nya (Guest-X), kita tahu itu Ilham.
                                    if feat is not None:
                                        # 🔥 FIX: Use settings instead of hardcoded threshold
                                        fast_id_thresh = SETTINGS.get("thresh_guest_reid", 0.80)
                                        gid, _ = session_registry.match_or_register(feat, threshold=fast_id_thresh)
                                        if gid:
                                            self.guest_identity_map[gid] = m_name
                                            # print(f"[FAST-ID] Linked {gid} body to {m_name}")
                    else:
                        # Gagal Match -> Reset Counter (Biar harus mulai dari nol lagi)
                        # 🔥 DEBUG FLICKER 🔥
                        if self.verification_counter.get(tid, 0) > 0:
                             # print(f"[REID RESET] ID {tid} Score Drop. Name: {m_name}, Score: {m_score:.2f} (Base: {base_thresh:.2f})")
                             pass
                        
                        self.verification_counter[tid] = 0
                        
                        # 🔥 GUEST MODE (GLOBAL TRACKING FOR STRANGERS) 🔥
                        # Jika tidak dikenali sebagai 'Member', kita cek apakah dia 'Guest' yang konsisten?
                        # Syarat: Feature vector ada & Valid.
                        if feat is not None:
                             # 🔥 UPDATE: Lower threshold (0.65 -> 0.60) agar ID Guest lebih stabil (Gak gampang ganti)
                             # UPDATE: Now using Settings (0.50)
                             guest_thresh = SETTINGS.get("thresh_guest_reid", 0.50)
                             guest_id, is_new = session_registry.match_or_register(feat, threshold=guest_thresh)
                             
                             if guest_id:
                                 # print(f"[GUEST REID] Track {tid} -> {guest_id} (New? {is_new})")
                                 # Set sebagai label sementara (TAPI tetap is_real=False agar warnanya Orange)
                                 # Visualizer nanti yang akan handle display ID-nya.
                                 # Kita simpan di fusion labels tapi dengan prefix khusus biar visualizer tau.
                                 
                                 # 🔥 FIX V12.21: JANGAN PAKAI lock_real_name !!!
                                 # lock_real_name itu otomatis bikin HIJAU (is_real=True).
                                 # Kita mau Guest itu tetap ORANGE (is_real=False).
                                 
                                 # 🔥 FAST-ID CHECK 🔥
                                 # Cek apakah Guest ini sebenarnya sudah kita kenal identitasnya?
                                 if guest_id in self.guest_identity_map:
                                     known_name = self.guest_identity_map[guest_id]
                                     # [CONDITIONAL FAST-ID]
                                     # User Request: "Jika di awal sudah keidentifikasi muka, maka dianggap active"
                                     # "dan ketika jalan tanpa muka (hanya badan), langsung keidentifikasi (HIJAU)."
                                     
                                     # Syarat: Nama "known_name" harus SUDAH AKTIF (Pernah verified Face sebelumnya).
                                     is_already_active = global_id_manager.is_identity_verified(known_name)
                                     
                                     # Safety Check: Wajah tidak boleh contradict
                                     face_label = current_face_map.get(tid, None)
                                     is_face_contradiction = (face_label and face_label != "UNKNOWN_FACE" and face_label != known_name)
                                     
                                     if is_already_active and not is_face_contradiction:
                                         # AUTO-PROMOTE KE HIJAU (SAFE)!
                                         self.fusion.lock_real_name(tid, known_name)
                                     else:
                                         # Strict Mode: Kalau belum pernah aktif hari ini, atau wajah conflict:
                                         # Tahan dulu jadi Guest (Orange).
                                         pass
                                 else:
                                     # Belum kenal, tetap jadi Guest (Orange)
                                     self.fusion.labels[tid] = guest_id
                                     # self.fusion.is_real[tid] = False # Defaultnya sudah False, tapi biar aman.
                                 
                                 # Jangan set is_real=True! Biarkan False (Orange).


        # VISUALISASI
        active_names_in_frame = {}
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = bbox
            label, is_real = self.fusion.get_label(tid)

            # 🔥 UPDATE v12.17: TRUSTED BACK VIEW LEARNING 🔥
            # Masalah: Tampak belakang tidak terekam karena fitur beda jauh dengan depan.
            # Solusi: Jika wajah masih "fresh" (baru dilihat < 5 detik lalu),
            # Kita paksa sistem untuk BELAJAR fitur badan saat ini (Auto-Learn),
            # Asumsinya: Orangnya sama, cuma lagi muter badan.
            if is_real and label != f"Person {tid}":
                last_face = self.last_face_confirmed.get(tid, 0)
                if time.time() - last_face < 5.0: # 5 Detik setelah wajah hilang
                     # 🔥 FIX: IMPLEMENTASI "FORCE LEARN" (Tampak Belakang)
                     # Kita gunakan fitur yang ada di body_registry untuk memaksa update anchors.
                     try:
                         # Ambil tracks yang fiturnya available (di DeepSORT biasanya tersimpan)
                         # Tapi di loop ini kita tidak punya akses direct ke 'feat' raw.
                         # Workaround: Kita berharap 'auto-learn' di atas sudah menangani feat extraction.
                         # TAPI, kita bisa panggil extract_body_feature LAGI kalau perlu.
                         
                         feat_force = self.extract_body_feature(frame, bbox, tid)
                         if feat_force is not None:
                             # PANGGIL DENGAN FORCE!
                             body_registry.register(label, feat_force, force_replace_anchors=True)
                             print(f"[FORCE LEARN] Memaksa belajar tampak belakang untuk {label}!")
                     except Exception as e:
                         print(f"[FORCE LEARN ERROR] {e}")


            if is_real: 
                if label in active_names_in_frame:
                    prev_tid = active_names_in_frame[label]
                    curr_has_face = (tid in self.face_vote_cache) and (label in self.face_vote_cache[tid])
                    prev_has_face = (prev_tid in self.face_vote_cache) and (label in self.face_vote_cache[prev_tid])
                    if curr_has_face and not prev_has_face:
                        self.fusion.lock_real_name(prev_tid, f"Person {prev_tid}") 
                        self.fusion.set_is_real(prev_tid, False)
                        active_names_in_frame[label] = tid
                    elif prev_has_face and not curr_has_face:
                        self.fusion.lock_real_name(tid, f"Person {tid}")
                        self.fusion.set_is_real(tid, False)
                        # 🔥 UPDATE LOCAL VARS AGAR GAK DIGAMBAR HIJAU 🔥
                        label = f"Person {tid}"
                        is_real = False 
                    else:
                        # KEDUANYA PUNYA WAJAH / KEDUANYA TIDAK PUNYA WAJAH
                        # 🔥 Face Priority Switcher (Industrial Grade) 🔥
                        # Siapa yang wajahnya LEBIH BARU? Dia yang menang.
                        score_curr = self.last_face_confirmed.get(tid, 0)
                        score_prev = self.last_face_confirmed.get(prev_tid, 0)
                        
                        if score_curr > score_prev:
                             # Current TID menang (Newer Face)
                             self.fusion.lock_real_name(prev_tid, f"Person {prev_tid}")
                             self.fusion.set_is_real(prev_tid, False)
                             active_names_in_frame[label] = tid
                        else:
                             # Previous TID menang (Older but fresher Face or Stalemate)
                             self.fusion.lock_real_name(tid, f"Person {tid}")
                             self.fusion.set_is_real(tid, False)
                             # 🔥 UPDATE LOCAL VARS AGAR GAK DIGAMBAR HIJAU 🔥
                             label = f"Person {tid}"
                             is_real = False

                else:
                    active_names_in_frame[label] = tid

            # Visualisasi dipindahkan ke visualizer.draw_tracks
            pass

        # Call Visualizer (Outside Loop)
        visualizer.draw_tracks(out, tracks, self.fusion, self.face_vote_cache, self.local_pos_history)

        # Garbage Collector
        if self.frame_idx % 300 == 0:
            active_tids = [t[0] for t in tracks]
            for tid in list(self.fusion.labels.keys()):
                if tid not in active_tids:
                    self.fusion.labels.pop(tid, None)
                    self.fusion.is_real.pop(tid, None)
                    self.reid_skip_timer.pop(tid, None)
            for tid in list(self.face_vote_cache.keys()):
                if tid not in active_tids:
                    del self.face_vote_cache[tid]
            
            # 🔥 LEAK PROTECTION: BERSIHKAN DICT BARU JUGA! 🔥
            for tid in list(self.occlusion_cooldown.keys()):
                if tid not in active_tids: del self.occlusion_cooldown[tid]
            for tid in list(self.verification_counter.keys()):
                if tid not in active_tids: del self.verification_counter[tid]
            for tid in list(self.last_face_confirmed.keys()):
                if tid not in active_tids: del self.last_face_confirmed[tid]
            for tid in list(self.local_pos_history.keys()):
                 if tid not in active_tids: del self.local_pos_history[tid]

        curr_time = time.time()
        fps = 1.0 / (curr_time - self.prev_time + 1e-6)
        self.prev_time = curr_time
        # DRAW NOTIFICATIONS
        # DRAW NOTIFICATIONS
        visualizer.draw_notifications(out, self.notification_queue)
        if len(self.notification_queue) > 0:
            self.notification_queue[0]["timer"] -= 1
            if self.notification_queue[0]["timer"] <= 0:
                self.notification_queue.pop(0)

        visualizer.draw_fps(out, fps)

        # [added for dashboard integration]
        # UPDATE PRESENCE MANAGER (Live Status)
        # Kumpulkan semua ID yang 'is_real' (Hijau) di frame ini
        
        current_active_data = {} # Name -> First Seen Timestamp
        active_tids = set()
        now = time.time()
        
        for t in tracks:
            tid = t[0]
            active_tids.add(tid)
            
            # 1. Register Start Time if new
            if tid not in self.track_start_times:
                self.track_start_times[tid] = now
            
            label, is_real = self.fusion.get_label(tid)
            if is_real and "Person" not in label:
                # CLEAN ID: Remove .npy, .tmp suffix if present
                clean_label = label.replace(".npy", "").replace(".tmp", "")
                
                # Use earliest start time if multiple tracks for same person
                start_ts = self.track_start_times[tid]
                if clean_label not in current_active_data:
                    current_active_data[clean_label] = start_ts
                else:
                    if start_ts < current_active_data[clean_label]:
                        current_active_data[clean_label] = start_ts

        # 2. Cleanup Dead Tracks from Memory
        for tid in list(self.track_start_times.keys()):
            if tid not in active_tids:
                del self.track_start_times[tid]
        
        # Panggil update_presence dengan ID kamera saat ini
        # Format room_id: CAM_0, CAM_1, dst.
        from indoor.presence_manager import presence_manager
        # Pass frame original untuk snapshot (clean)
        # Params: room_id, active_data (Dict[name, start_time]), now, frame
        presence_manager.update_presence(f"CAM_{self.camera_id}", current_active_data, now, frame=frame)

        return out

    def emergency_reset(self):
        # 🔥 RESET TOTAL (TOMBOL 'x') 🔥
        print("[TRACKER] Melakukan Reset Total...")
        try: self.deepsort.tracks = [] 
        except: pass
        self.fusion.labels = {}
        self.fusion.is_real = {}
        self.face_vote_cache = {}
        global_id_manager.active_identities = {}
        
        # Bersihkan variabel baru juga
        self.last_face_confirmed = {}
        self.reid_skip_timer = {}
        self.notification_queue = []
        
        # 🔥 WIPER TAMBAHAN: HAPUS MEMORY BODY RUNTIME 🔥
        # Biar kalau ada 'salah orang' membandel, bisa langsung di-flush.
        try: body_registry.clear_memory()
        except: pass

    def extract_body_feature(self, frame, box, tid):
        x1, y1, x2, y2 = box
        h_img, w_img = frame.shape[:2]
        
        # Validasi koordinat dasar
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w_img, int(x2)), min(h_img, int(y2))
        
        # Cek validitas box
        w_box = x2 - x1
        h_box = y2 - y1
        if w_box <= 0 or h_box <= 0: return None
        
        # 🔥 SOLUSI ADAPTIVE CROP v12.16 (FINE TUNED) 🔥
        # Logika:
        # - JAUH/SEDANG (Tinggi < 180px): JANGAN CROP! (Resolusi pas-pasan, pixel sangat berharga).
        # - DEKAT/BESAR (Tinggi >= 180px): Potong pinggir 5% (Anti-Nyangkut).
        
        is_far_away = (h_box < 180) # 🔥 UPDATE v12.16: NAIKKAN BATAS (120 -> 180) biar Medium Distance juga Full Box. 

        if is_far_away:
            # MODE 1: FULL BOX (Untuk objek jauh)
            crop = frame[y1:y2, x1:x2]
        else:
            # MODE 2: CENTER CROP (Untuk objek dekat/jelas)
            # 🔥 UPDATE v12.15: KURANGI CROP WIDTH (15% -> 5%)
            # Masalah: Tampak samping/punggung itu "tipis". Kalau dipotong 15%, datanya habis.
            pad_w = int(w_box * 0.05) # Buang 5% kiri-kanan (Dulu 15%)
            pad_h = int(h_box * 0.10) # Buang 10% atas-bawah
            
            crop_x1 = x1 + pad_w
            crop_x2 = x2 - pad_w
            crop_y1 = y1 + pad_h
            crop_y2 = y2 - pad_h
            
            # Safety Check: Kalau hasil potong jadi terlalu kecil (<10px), batalkan potong.
            if (crop_x2 - crop_x1) < 10 or (crop_y2 - crop_y1) < 10:
                crop = frame[y1:y2, x1:x2]
            else:
                crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]

        # Ekstrak Fitur
        return self.osnet.extract(crop).flatten()