# indoor/video.py
import cv2
import time
import os
import numpy as np
from threading import Thread
from config.settings import SETTINGS
from config.paths import get_data_paths
from indoor.tracker_deepsort import MultiObjectTracker
from indoor.body_registry import body_registry
from indoor.smart_camera import SmartVideoCapture # 🔥 MODUL BARU

class VideoSystem:
    def __init__(self, max_cameras=1):
        self.sources = SETTINGS["camera_indexes"][:max_cameras]
        self.trackers = []
        for i in range(len(self.sources)):
            trk = MultiObjectTracker()
            trk.set_camera_id(i) 
            self.trackers.append(trk)
            
        self.caps = []
        self.running = True
        
        for src in self.sources:
            # 🔥 PAKAI SMART CAPTURE (Auto Reconnect)
            cap = SmartVideoCapture(src, name=f"Cam_{self.sources.index(src)}")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, SETTINGS["cap_width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SETTINGS["cap_height"])
            
            # 🔥 WAJIB ADA: ANTI-DELAY 🔥
            # Ini memerintahkan kamera untuk tidak menumpuk frame lama.
            # Tanpa ini, video akan telat (delay) walau FPS tinggi.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.caps.append(cap)
            
        print(f"[SYSTEM] {len(self.caps)} Kamera aktif.")
        print("[SYSTEM] Tekan 'q' untuk keluar.")
        print("[SYSTEM] Tekan 'r' untuk REGISTRASI WAJAH & BADAN.")
        print("[SYSTEM] Tekan 'x' untuk RESET DARURAT.") 

    def run(self):
        while self.running:
            frames = []
            raw_frames = [] 
            
            for i, cap in enumerate(self.caps):
                try:
                    ret, frame = cap.read()
                    
                    if not ret:
                        time.sleep(0.1)
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    
                    # 🔥 FIX LIGHTING (REAL-LIFE CCTV) 🔥
                    # Gunakan CLAHE untuk perbaiki kontras di lorong gelap/silau.
                    try:
                        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                        l, a, b = cv2.split(lab)
                        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                        cl = clahe.apply(l)
                        limg = cv2.merge((cl, a, b))
                        frame = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
                    except: pass # Safety kalau format pixel aneh

                    # Resize ringan (Kunci FPS Tinggi)
                    frame = cv2.resize(frame, SETTINGS["face_input_size"])
                    
                    # Simpan RAW
                    raw_frames.append(frame.copy()) 
                    
                    # PROSES TRACKING
                    processed_frame = self.trackers[i].process_frame(frame)
                    
                    cv2.putText(processed_frame, f"CAM {i}", (10, 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
                    frames.append(processed_frame)
                except Exception as e:
                    from indoor.utils import logger
                    logger.error(f"[CRASH GUARD] Error di Cam {i}: {e}. Skipping frame.")
                    
                    # 🔥 FIX: Gunakan ukuran dari Settings agar Grid tidak Crash
                    target_w, target_h = SETTINGS["face_input_size"]
                    # Ingat: Numpy shape itu (Height, Width, Channel)
                    frames.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))

            # Tampilkan Grid
            if len(frames) == 1:
                grid = frames[0]
            elif len(frames) == 2:
                grid = np.hstack(frames)
            else:
                top = np.hstack(frames[:2])
                if len(frames) == 3:
                    bottom = np.hstack([frames[2], np.zeros_like(frames[0])])
                else:
                    bottom = np.hstack(frames[2:4])
                grid = np.vstack([top, bottom])

            cv2.imshow("Multi-Camera Grid View", grid)

            # KEYBOARD HANDLER
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                self.stop()
            
            elif key == ord('r'):
                # Tidak perlu pause di sini, biar handle_registration yang ngatur
                if len(raw_frames) > 0:
                    self.handle_registration(raw_frames[0], self.trackers[0])

            elif key == ord('x'):
                print("\n[USER COMMAND] Melakukan Reset Darurat...")
                for tracker in self.trackers:
                    tracker.emergency_reset()

    def handle_registration(self, raw_frame, tracker):
        # --- LANGKAH 1: Cari Track Aktif Terbesar ---
        tracks = tracker.deepsort.get_active_tracks(with_feature=False)
        best_track = None
        max_area = 0
        
        for t in tracks:
            tid = t[0]
            bbox = t[1]
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area > max_area:
                max_area = area
                best_track = t
        
        # --- LANGKAH 2: Cek Apakah Sudah Hijau (Auto-Update) ---
        if best_track is not None:
            tid = best_track[0]
            bbox = best_track[1]
            name, is_real = tracker.fusion.get_label(tid)
            
            # 🔥 DEBUG: Tampilkan status di Terminal biar jelas
            print(f"[DEBUG] Tombol R Ditekan. Track ID: {tid}, Nama: {name}, Status Hijau: {is_real}")

            if is_real and "Person" not in name:
                print("\n" + "="*40)
                print(f"   AUTO-UPDATE: {name}")
                print("="*40)
                
                h, w = raw_frame.shape[:2]
                x1, y1, x2, y2 = bbox
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(w, int(x2)), min(h, int(y2))
                
                crop_body = raw_frame[y1:y2, x1:x2]
                
                if crop_body.size > 0:
                    feat = tracker.osnet.extract(crop_body)
                    if feat is not None:
                        body_registry.register(name, feat.flatten())
                        print(f"✅ Data Punggung ditambahkan ke {name}.")
                        
                        # POP-UP KONFIRMASI VISUAL
                        preview_save = crop_body.copy()
                        cv2.rectangle(preview_save, (0,0), (preview_save.shape[1], preview_save.shape[0]), (0,255,0), 4)
                        cv2.putText(preview_save, "SAVED!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,255,0), 3)
                        
                        cv2.imshow("SYSTEM NOTIFICATION", preview_save)
                        cv2.waitKey(800) 
                        cv2.destroyWindow("SYSTEM NOTIFICATION")
                        
                        return
                    else:
                        print("⚠️ Gagal ekstrak fitur.")
                return

        # --- LANGKAH 3: Manual Mode (Jika Belum Kenal/Tracker Putus) ---
        print("\n[PAUSE] Memulai registrasi MANUAL... (TRACKER ORANGE/PUTUS)")
        
        clean_frame = raw_frame.copy()
        faces = tracker.face_detector.detect(clean_frame)
        
        crop_body = None
        face_emb = None
        mode = "FACE"
        
        # ... (Kode ke bawah sama seperti sebelumnya) ...
        # Copy paste sisa fungsi handle_registration yang lama di sini
        # (Bagian if len(faces) > 0 dst...)
        if len(faces) > 0:
            best_face = max(faces, key=lambda f: f[2] * f[3]) 
            x, y, w, h = best_face
            
            preview = clean_frame.copy()
            cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 0), 3)
            cv2.putText(preview, "WAJAH TERDETEKSI", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("Multi-Camera Grid View", preview)
            cv2.waitKey(1)

            crop_face = clean_frame[y:y+h, x:x+w]
            face_emb = tracker.face_recognizer.get_embedding(cv2.cvtColor(crop_face, cv2.COLOR_BGR2RGB))
            
            h_img, w_img = clean_frame.shape[:2]
            bx1 = max(0, x - int(w * 0.5))
            by1 = max(0, y) 
            bx2 = min(w_img, x + w + int(w * 0.5))
            by2 = min(h_img, y + h * 4) 
            crop_body = clean_frame[by1:by2, bx1:bx2]
            
        else:
            dets = tracker.person_detector.detect(clean_frame)
            if len(dets) == 0:
                print("\n❌ Gagal: Tidak ada orang. Mundur sedikit.")
                return

            best_det = max(dets, key=lambda d: (d[2]-d[0]) * (d[3]-d[1]))
            x1, y1, x2, y2 = int(best_det[0]), int(best_det[1]), int(best_det[2]), int(best_det[3])
            
            preview = clean_frame.copy()
            cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 165, 255), 3)
            cv2.putText(preview, "PUNGGUNG (MANUAL)", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
            cv2.imshow("Multi-Camera Grid View", preview)
            cv2.waitKey(1)
            
            crop_body = clean_frame[y1:y2, x1:x2]
            mode = "BODY_ONLY"

        print("\n" + "="*40)
        print(f"   REGISTRASI MANUAL ({mode})")
        print("="*40)
        
        try:
            print("⚠️ TRACKER BELUM HIJAU / PUTUS.")
            print("👉 Masukkan Nama Manual di Terminal >> ")
            name = input(f"Nama >> ").strip()
        except EOFError:
            return

        if not name: return

        paths = get_data_paths()
        
        if face_emb is not None:
            save_path = os.path.join(paths["embeddings_dir"], f"{name}.npy")
            np.save(save_path, face_emb)
            print(f"✅ Wajah tersimpan.")
            tracker.face_recognizer.load_embeddings(paths["embeddings_dir"])

        try:
            if crop_body is not None and crop_body.size > 0:
                body_emb = tracker.osnet.extract(crop_body)
                if body_emb is not None:
                    body_registry.register(name, body_emb.flatten()) 
                    print(f"✅ Data Badan berhasil ditambahkan.")
        except Exception as e:
            print(f"⚠️ Error: {e}")

        print("\n[INFO] Selesai.")

    def stop(self):
        self.running = False
        for cap in self.caps:
            cap.release()
        cv2.destroyAllWindows()