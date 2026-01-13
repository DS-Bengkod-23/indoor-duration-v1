# indoor/tracker_deepsort.py
import cv2, time, numpy as np
from indoor.face_detector import FaceDetectorYuNet
from indoor.person_detector import PersonDetectorYOLO
from indoor.fusion import FaceBodyFusion
from indoor.deepsort.deep_sort import DeepSort
from indoor.body_registry import body_registry
from indoor.shared_models import get_face_recognizer, get_osnet
from config.settings import SETTINGS

class GlobalIdentityManager:
    def __init__(self):
        self.active_identities = {} 
        self.room_mapping = SETTINGS.get("room_mapping", {})

    def get_room_name(self, cam_index):
        key = f"CAM_{cam_index}"
        # 🔥 UPDATE: USER CONFIRM "MASIH SATU RUANGAN" 🔥
        # Jadi default-nya kita anggap SATU RUANGAN BESAR (Shared).
        # Ini mengaktifkan logika "Same Room Handover" (bukan Diff Room).
        return self.room_mapping.get(key, "Shared_Room_Alpha")

    def get_active_names_list(self):
        now = time.time()
        active = []
        for name, data in self.active_identities.items():
            last_seen = data[3]
            # Ingatan global 15 detik biar handover antar kamera santai
            if now - last_seen < 15.0: 
                active.append(name)
        return active

    def try_claim_identity(self, name, cam_index, track_id, score, claim_type='BODY'):
        now = time.time()
        
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
                # Kita Izinkan "Double Presence" HANYA jika kemiripan TINGGI (> 0.82).
                # Ini biar Anda bisa muncul di 2 kamera sekaligus (sudut beda),
                # TAPI orang lain (kemiripan rendah) tetap DITOLAK.
                # Jika time_diff < frame_count (Target masih aktif di kamera lain):
                # Kita Izinkan "Double Presence" HANYA jika kemiripan TINGGI.
                time_diff = now - last_seen
                if time_diff < SETTINGS.get("time_back_view_window", 3.0):
                    if score > SETTINGS.get("thresh_anti_clone", 0.82):
                        # IOZIN: Double Presence Valid (Skor Tinggi)
                        self.active_identities[name] = (cam_index, track_id, score, now)
                        return True
                    else:
                        # print(f"[ANTI-CLONE] TOLAK {name} ID {track_id} (Skor: {score:.2f}) - Masih aktif di Cam {curr_cam}")
                        return False 
                
                # Normal Handover (Sudah > 3 detik menghilang)
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True
            else:
                # BEDA RUANGAN: Pakai logika anti-teleport
                time_diff = now - last_seen
                if time_diff < 1.5: 
                    # Jika ada di tempat lain, CUMA BOLEH CLAIM kalau skor SANGAT TINGGI (0.82)
                    # Ini mengizinkan "Double Presence" untuk Fatih asli,
                    # Tapi menolak False Positive (Stranger) yang skornya nanggung.
                    if score < SETTINGS.get("thresh_anti_clone", 0.82):
                        return False 
                
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True

        # Anti-Hijack dalam satu kamera
        if curr_cam == cam_index and curr_id != track_id:
            time_gap = now - last_seen
            if time_gap < 5.0:
                if score > 0.85: 
                    self.active_identities[name] = (cam_index, track_id, score, now)
                    return True
                return False 
            
            if claim_type == 'FACE': 
                self.active_identities[name] = (cam_index, track_id, score, now)
                return True
            else: return False

        if score > (curr_score - 0.1): 
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
                    if ratio < 1.6 and conf < 0.60:
                        continue 
                    
                filtered_dets.append([x1, y1, x2, y2, conf])

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
                if faces_processed_count >= 2: break 
                
                search_y1 = max(0, y1 - 40) 
                face_search_area = frame[search_y1:min(frame.shape[0], y1 + int((y2-y1)/1.5)), max(0, x1):x2]
                
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
                                should_replace = (raw_score < 0.50) # Cuma replace kalau bedanya jauh banget
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
                            print(f"[ANTI-NYANGKUT] ID {tid} drop! Skor: {raw_score:.2f} (Occluded: {is_occluded}). RESET!")
                            self.fusion.lock_real_name(tid, f"Person {tid}")
                            self.fusion.set_is_real(tid, False)
                            self.reid_skip_timer[tid] = 0 
                            if label in global_id_manager.active_identities:
                                del global_id_manager.active_identities[label]
                            is_real_now = False 
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
                    m_name, m_score = body_registry.match_global(feat, active_names=active_list)
                    
                    detected_face = current_face_map.get(tid, None)
                    if detected_face == "UNKNOWN_FACE": m_score = 0.0 
                    
                    # 🔥 2. LOGIKA JALUR VIP (SAME ROOM) 🔥
                    # Cek apakah nama yang cocok (m_name) berada di RUANGAN YANG SAMA?
                    is_same_room_handover = False
                    if m_name in global_id_manager.active_identities:
                        cur_cam = global_id_manager.active_identities[m_name][0]
                        room_curr = global_id_manager.get_room_name(cur_cam)
                        room_my = global_id_manager.get_room_name(self.camera_id)
                        if room_curr == room_my:
                            is_same_room_handover = True

                    box_height = y2 - y1
                    
                    
                    # 🔥 3. LOGIKA DETEKSI CROWDS (Dynamic Strictness) 🔥
                    # Hitung jumlah orang yang terdeteksi di frame ini
                    person_count = len(tracks)
                    
                    # Ambil threshold dasar dari Settings
                    base_thresh = SETTINGS.get("thresh_same_room", 0.75) if is_same_room_handover else SETTINGS.get("thresh_diff_room", 0.81)

                    
                    # 🔥 4. LOGIKA DISTANCE TIERED (Refined for CCTV) 🔥
                    # Mengatasi Masalah #3 (Jauh salah).
                    is_tiny = (box_height < 60)
                    is_small = (box_height < 90)
                    
                    if is_tiny: # TINY
                         base_thresh = 0.82 # Sangat Ketat
                         m_score -= 0.15    # Penalti Jauh
                    elif is_small: # SMALL
                         base_thresh = 0.79 # Ketat
                         m_score -= 0.05
                    elif box_height < 140: # MEDIUM
                         base_thresh -= 0.05 # Sedikit Longgar (Aman)
                    else: # LARGE
                         base_thresh -= 0.08 # Longgar (Sangat Jelas)


                    # 🔥 5. HIJACK GUARD (POST-MORTEM CHECK) 🔥
                    # Mengatasi Masalah #2 (Hijau jadi orang lain).
                    # Jika ID sudah CONFIRMED (Hijau), tapi skornya jeblok di bawah 0.45,
                    # Berarti itu BUKAN orang yang sama! (Mungkin orang lewat di belakang).
                    if m_name == label and m_score < 0.45:
                          print(f"[HIJACK GUARD] {label} appearance mismatch ({m_score:.2f}). FORCE DETACH.")
                          self.fusion.set_is_real(tid, False)
                          is_real_now = False


                    # ADAPTIVE LOGIC:
                    # Rame = Longgarkan dikit (-0.05). Sepi = Strict (+0.03).
                    if person_count > 1:
                        if is_same_room_handover: 
                             base_thresh = max(0.60, base_thresh - 0.05)
                    else:
                        base_thresh = min(0.90, base_thresh + 0.03)
                        
                    # Clipping
                    base_thresh = max(0.60, min(base_thresh, 0.90))

                    # ANTI-FLICKER (OCCLUSION PENALTY)
                    # Mengatasi Masalah #1 (Switch pas ketutupan).
                    # Kalau habis ketutupan, harus strict 2x lipat.
                    time_since_occlusion = curr_time_now - self.occlusion_cooldown.get(tid, 0)
                    if time_since_occlusion < 2.0:
                         base_thresh += 0.15
                    
                    # Streak Validation (Berapa kali harus match berturut-turut?)
                    if is_tiny: required_streak = 5
                    elif is_small: required_streak = 2
                    else: required_streak = 1
                    
                    current_streak = self.verification_counter.get(tid, 0)
                    
                    if m_name and m_score > base_thresh:
                        # Potensi Match! Naikkan Counter.
                        self.verification_counter[tid] = current_streak + 1
                        
                        # Cuma boleh claim kalau streak sudah cukup
                        if self.verification_counter[tid] >= required_streak:
                             is_hijack_attempt = False
                             # ... (Anti hijack logic) ...
                             if not is_hijack_attempt:
                                  if global_id_manager.try_claim_identity(m_name, self.camera_id, tid, m_score, 'BODY'):
                                      self.fusion.lock_real_name(tid, m_name)
                                      self.reid_skip_timer[tid] = 0
                    else:
                        # Gagal Match -> Reset Counter (Biar harus mulai dari nol lagi)
                        self.verification_counter[tid] = 0

        # VISUALISASI
        active_names_in_frame = {}
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = bbox
            label, is_real = self.fusion.get_label(tid)

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
                else:
                    active_names_in_frame[label] = tid

                # HIJAU: TEBAL + NAMA
                color = (0, 255, 0)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                cv2.putText(out, f"{label}", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            else:
                # ORANGE: TIPIS + POLOS (Bersih)
                color = (0, 165, 255)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)

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
        # Tampilkan notifikasi dari queue (paling atas)
        if len(self.notification_queue) > 0:
            notif = self.notification_queue[0]
            text = notif["text"]
            color = notif["color"]
            timer = notif["timer"]
            
            # Draw Background Box
            (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)
            cv2.rectangle(out, (50, 100 - text_h - 10), (50 + text_w + 20, 100 + 10), (0,0,0), -1)
            cv2.putText(out, text, (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 3)
            
            # Decrement Timer
            notif["timer"] -= 1
            if notif["timer"] <= 0:
                self.notification_queue.pop(0)

        cv2.putText(out, f"FPS: {fps:.1f}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

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
        h, w = frame.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 <= x1 or y2 <= y1: return None
        crop = frame[y1:y2, x1:x2]
        return self.osnet.extract(crop).flatten()