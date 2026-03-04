# indoor/video.py
import cv2
import time
import os
import numpy as np
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from config.settings import SETTINGS
from config.paths import get_data_paths
from indoor.tracker_deepsort import MultiObjectTracker
from indoor.body_registry import body_registry
from indoor.smart_camera import SmartVideoCapture # 🔥 MODUL BARU
from indoor.visualizer import visualizer

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
        
        # 🔥 MULTI-THREADING EXECUTOR UNTUK PARALELISASI KAMERA 🔥
        self.executor = ThreadPoolExecutor(max_workers=max_cameras if max_cameras > 0 else 1)
        
        # 🔥 PENTING: WARMUP AI MODELS UNTUK THREAD SAFETY 🔥
        # Jika YOLO/OSNet dipanggil berbarengan pertama kali oleh beberapa thread,
        # PyTorch bisa crash ("Conv object has no attribute 'bn'"). Kita harus warmup dulu!
        try:
            from indoor.shared_models import get_yolo_model, get_osnet
            print("[SYSTEM] Warming up AI Models for Thread Safety...")
            yolo_model, _ = get_yolo_model()
            osnet_model = get_osnet()
            dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
            yolo_model(dummy_img, verbose=False)
            osnet_model.extract(dummy_img)
            print("[SYSTEM] AI Models Warmup Complete.")
        except Exception as e:
            print(f"[SYSTEM] Warning during AI warmup: {e}")
        
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

    def find_user_cameras(self, target_name):
        """
        Mengembalikan daftar index kamera di mana user tersebut terdeteksi.
        """
        active_cams = []
        for i, tracker in enumerate(self.trackers):
            tracks = tracker.deepsort.get_active_tracks(with_feature=False)
            for t in tracks:
                tid = t[0]
                name, is_real = tracker.fusion.get_label(tid)
                if is_real and name == target_name:
                    active_cams.append(i)
                    break 
        return active_cams

    def run(self):
        try:
            while self.running:
                loop_start = time.time()  # 🔥 FIX STUTTER: Timer untuk adaptive sleep
                # 🔥 GLOBAL SYNC: Reset active PIDs for this cycle
                visualizer.start_new_cycle()
                
                frames = [None] * len(self.caps)
                raw_frames = [None] * len(self.caps)
                
                def process_camera(index, cap):
                    try:
                        ret, img = cap.read()
                        
                        if not ret or img is None:
                            time.sleep(0.01) # Kurangi sleep delay jika gagal baca
                            img = np.zeros((480, 640, 3), dtype=np.uint8)
                        
                     
                        if SETTINGS.get("flip_camera", False):
                            img = cv2.flip(img, 1)  # flipCode=1 → horizontal flip
                        
                        # 🔥 OPTIMALISASI LIGHTING (LEBIH RINGAN DARI CLAHE) 🔥
                        # CLAHE terlalu berat untuk dijalankan di Multi-Threading untuk 2 kamera
                        # Kita ganti dengan Brightness/Contrast linear dasar.
                        try:
                            # Tambah brightness 20, contrast 1.1x (Cukup untuk CCTV)
                            img = cv2.convertScaleAbs(img, alpha=1.1, beta=20)
                        except: pass

                        # Resize ringan (Kunci FPS Tinggi)
                        img = cv2.resize(img, SETTINGS["face_input_size"])
                        raw_img = img.copy()
                        
                        # PROSES TRACKING
                        proc_img = self.trackers[index].process_frame(img)
                        visualizer.draw_cam_id(proc_img, index)
                        
                        return index, proc_img, raw_img
                    except Exception as e:
                        from indoor.utils import logger
                        logger.error(f"[CRASH GUARD] Error di Cam {index}: {e}. Skipping frame.")
                        target_w, target_h = SETTINGS["face_input_size"]
                        placeholder = np.zeros((target_h, target_w, 3), dtype=np.uint8)
                        return index, placeholder, placeholder

                # Jalankan semua kamera secara paralel (MULTI-THREADING)
                futures = [self.executor.submit(process_camera, i, cap) for i, cap in enumerate(self.caps)]
                
                for future in futures:
                    idx, processed, raw = future.result()
                    frames[idx] = processed
                    raw_frames[idx] = raw

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

                # Callback Hook for Web Dashboard
                if hasattr(self, "on_frame_callback") and self.on_frame_callback:
                    # Update signature to pass frames (annotated) list too
                    self.on_frame_callback(grid, frames)

                # 🔥 FIX STUTTER: ADAPTIVE SLEEP (Ganti fixed sleep 15ms) 🔥
                # Hitung berapa waktu yang sudah terpakai di iterasi ini.
                # Kalau AI sudah lambat (CPU spike), jangan tidur lagi — langsung lanjut.
                # Target ~30 FPS = 33ms per frame.
                loop_elapsed = time.time() - loop_start
                sleep_time = max(0.001, 0.033 - loop_elapsed)
                time.sleep(sleep_time)

                cv2.imshow("Multi-Camera Grid View", grid)

                # KEYBOARD HANDLER
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    self.running = False
                
                elif key == ord('r'):
                    # Tidak perlu pause di sini, biar handle_registration yang ngatur
                    if len(raw_frames) > 0:
                        self.handle_registration(raw_frames[0], self.trackers[0])

                elif key == ord('x'):
                    print("\n[USER COMMAND] Melakukan Reset Darurat...")
                    for tracker in self.trackers:
                        tracker.emergency_reset()
        finally:
            self.stop()

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
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        for cap in self.caps:
            cap.release()
        cv2.destroyAllWindows()