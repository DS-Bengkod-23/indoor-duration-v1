# indoor/video.py
import cv2
import numpy as np
import threading
import time

from indoor.tracker_deepsort import MultiObjectTracker
from config.settings import SETTINGS


class CameraWorker(threading.Thread):
    def __init__(self, cam_index, shared_frames, buffer_idx):
        super().__init__()
        self.cam_index = cam_index
        self.buffer_idx = buffer_idx
        self.shared_frames = shared_frames
        self.running = True

        # Tracker per kamera
        self.tracker = MultiObjectTracker()

        self.cap = cv2.VideoCapture(cam_index)
        if not self.cap.isOpened():
            print(f"[WORKER] Camera {cam_index} gagal dibuka.")
            self.running = False

        # counter error grab frame
        self.fail_count = 0
        self.max_fail = 50

    def run(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                self.fail_count += 1
                if self.fail_count % 50 == 0:
                    print(f"[WORKER] Camera {self.cam_index} gagal grab frame ({self.fail_count})")
                if self.fail_count >= self.max_fail:
                    print(f"[WORKER] Stop camera {self.cam_index}, terlalu banyak error grab frame.")
                    break
                time.sleep(0.01)
                continue

            self.fail_count = 0  # reset kalau berhasil

            # kecilkan resolusi kamera
            frame = cv2.resize(frame, (640, 360))

            try:
                processed = self.tracker.process_frame(frame)
            except Exception as e:
                print(f"[WORKER] Error di tracker camera {self.cam_index}: {e}")
                # kalau tracking error, jangan matikan kamera; lanjut baca frame berikutnya
                continue

            # overlay index kamera → supaya tahu ini camera berapa
            cv2.putText(
                processed,
                f"CAM {self.cam_index}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            self.shared_frames[self.buffer_idx] = processed

        self.cap.release()


class VideoSystem:
    def __init__(self, max_cameras=10):
        self.max_cameras = max_cameras

        # auto scan awal
        self.cameras = self.detect_cameras(self.max_cameras)
        print("🎥 Active cameras (auto scan):", self.cameras)

        # satu slot frame per kamera
        self.frames = [None] * len(self.cameras)
        self.workers = []

        # untuk auto-rescan kamera baru
        self.last_rescan = time.time()
        self.rescan_interval = 5.0  # detik

    def detect_cameras(self, max_cam):
        """Scan awal: cari kamera yang benar-benar bisa dibuka."""
        detected = []
        for i in range(max_cam):
            cap = cv2.VideoCapture(i)
            ok, _ = cap.read()
            cap.release()
            if ok:
                detected.append(i)
        return detected

    def start_workers(self):
        for idx, cam_id in enumerate(self.cameras):
            worker = CameraWorker(cam_id, self.frames, idx)
            if worker.running:
                worker.start()
                self.workers.append(worker)

    def add_new_cameras_if_any(self):
        """
        Re-scan index yang BELUM dipakai.
        Tidak akan menyentuh kamera yang sudah aktif di self.cameras,
        supaya tidak bentrok dengan worker yang sedang jalan.
        """
        # kalau sudah mencapai limit, jangan scan lagi
        if len(self.cameras) >= self.max_cameras:
            return

        now = time.time()
        if now - self.last_rescan < self.rescan_interval:
            return
        self.last_rescan = now

        # kandidat index baru = yang belum ada di self.cameras
        candidate_indices = [i for i in range(self.max_cameras) if i not in self.cameras]

        for cam_id in candidate_indices:
            cap = cv2.VideoCapture(cam_id)
            ok, _ = cap.read()
            cap.release()
            if ok:
                print(f"➕ Detected new camera: {cam_id}")
                self.cameras.append(cam_id)
                self.frames.append(None)  # slot frame baru
                buffer_idx = len(self.frames) - 1

                worker = CameraWorker(cam_id, self.frames, buffer_idx)
                if worker.running:
                    worker.start()
                    self.workers.append(worker)

    def build_grid(self):
        valid_frames = [f for f in self.frames if f is not None]
        if len(valid_frames) == 0:
            return None

        if len(valid_frames) == 1:
            return cv2.resize(valid_frames[0], (1280, 720))

        n = len(valid_frames)
        rows = int(np.ceil(np.sqrt(n)))
        cols = int(np.ceil(n / rows))

        target_h = 360
        resized = []

        for f in valid_frames:
            h, w = f.shape[:2]
            scale = target_h / h
            resized.append(cv2.resize(f, (int(w * scale), target_h)))

        blank = np.zeros_like(resized[0])
        while len(resized) < rows * cols:
            resized.append(blank)

        rows_list = []
        k = 0
        for r in range(rows):
            rows_list.append(np.hstack(resized[k:k + cols]))
            k += cols

        return np.vstack(rows_list)

    def run(self):
        self.start_workers()
        print("🚀 Multi-camera tracking berjalan...")

        while True:
            # cek apakah ada kamera baru tiap beberapa detik
            self.add_new_cameras_if_any()

            grid = self.build_grid()
            if grid is not None:
                cv2.imshow("Multi-Camera Grid View", grid)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.stop()

    def stop(self):
        for w in self.workers:
            w.running = False
            w.join()
        cv2.destroyAllWindows()
