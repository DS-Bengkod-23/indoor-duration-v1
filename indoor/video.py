# indoor/video.py
import cv2
import numpy as np
import threading
import time
from typing import List, Any

from indoor.tracker_deepsort import MultiObjectTracker
from indoor.presence_manager import presence_manager
from config.settings import SETTINGS


def _open_capture(source):
    """
    Buka capture robust:
      - jika source bisa di-convert ke int -> treat as webcam index
      - jika Windows & index -> use CAP_DSHOW to reduce MSMF errors
      - otherwise open with default backend (support RTSP/http)
    """
    cap = None
    try:
        # numeric index?
        idx = int(source)
        # use CAP_DSHOW on Windows to reduce MSMF errors
        backend = cv2.CAP_DSHOW
        cap = cv2.VideoCapture(idx, backend)
    except Exception:
        # treat as URL or path
        cap = cv2.VideoCapture(source)
    return cap


class CameraWorker(threading.Thread):
    def __init__(self, cam_source: Any, shared_frames: List[Any], shared_ids: List[set], buffer_idx: int):
        super().__init__()
        self.cam_source = cam_source  # int index or string (URL)
        self.buffer_idx = buffer_idx
        self.shared_frames = shared_frames
        self.shared_ids = shared_ids
        self.running = True

        self.tracker = MultiObjectTracker()

        # open capture
        self.cap = _open_capture(cam_source)
        if not self.cap or not self.cap.isOpened():
            print(f"[WORKER] Camera {cam_source} gagal dibuka.")
            self.running = False
            return

        # optional: speed settings
        cap_w = SETTINGS.get("cap_width", 640)
        cap_h = SETTINGS.get("cap_height", 360)
        cap_fps = SETTINGS.get("cap_fps", 15)
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_h)
            self.cap.set(cv2.CAP_PROP_FPS, cap_fps)
        except Exception:
            pass

        self.fail_count = 0
        self.max_fail = 200
        self.reopen_threshold = 50  # coba reopen setelah X gagal

    def _reopen(self):
        try:
            if self.cap:
                self.cap.release()
            time.sleep(0.5)
            self.cap = _open_capture(self.cam_source)
            if self.cap and self.cap.isOpened():
                print(f"[WORKER] Camera {self.cam_source} berhasil reopen.")
                self.fail_count = 0
                return True
        except Exception as e:
            print(f"[WORKER] Reopen error {self.cam_source}: {e}")
        return False

    def run(self):
        while self.running:
            if not self.cap or not self.cap.isOpened():
                # coba reopen periodik
                self.fail_count += 1
                if self.fail_count % 10 == 0:
                    print(f"[WORKER] Camera {self.cam_source} tidak terbuka, mencoba reopen ({self.fail_count})")
                if self.fail_count > self.max_fail:
                    print(f"[WORKER] Camera {self.cam_source} stop (cannot open).")
                    break
                self._reopen()
                time.sleep(0.2)
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                self.fail_count += 1
                if self.fail_count % 10 == 0:
                    print(f"[WORKER] Camera {self.cam_source} gagal grab frame ({self.fail_count})")
                time.sleep(0.05)

                # coba reopen kalau sering gagal
                if self.fail_count >= self.reopen_threshold:
                    print(f"[WORKER] Camera {self.cam_source} terlalu sering gagal, coba reopen...")
                    if self._reopen():
                        print(f"[WORKER] Camera {self.cam_source} reopened.")
                    else:
                        print(f"[WORKER] Camera {self.cam_source} reopen gagal.")
                if self.fail_count > self.max_fail:
                    print(f"[WORKER] Camera {self.cam_source} stop (too many errors).")
                    break
                continue

            self.fail_count = 0

            # resize for speed
            try:
                frame = cv2.resize(frame, (SETTINGS.get("cap_width", 640), SETTINGS.get("cap_height", 360)))
            except Exception:
                pass

            try:
                processed = self.tracker.process_frame(frame)
            except Exception as e:
                print(f"[WORKER] Error di tracker camera {self.cam_source}: {e}")
                time.sleep(0.01)
                continue

            # overlay index string supaya tahu sumbernya
            cv2.putText(
                processed,
                f"{self.cam_source}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            # tulis ke shared buffers
            self.shared_frames[self.buffer_idx] = processed

            # ambil active person IDs dari tracker dan simpan
            active_ids = self.tracker.get_active_identities()
            self.shared_ids[self.buffer_idx] = active_ids

        # cleanup sebelum keluar
        try:
            self.shared_frames[self.buffer_idx] = None
            self.shared_ids[self.buffer_idx] = set()
        except Exception:
            pass

        if self.cap:
            self.cap.release()


class VideoSystem:
    def __init__(self, max_cameras=10):
        self.max_cameras = max_cameras
        # prefer camera_indexes dari settings jika tersedia
        cams = SETTINGS.get("camera_indexes", [])
        if cams:
            self.cameras = cams[:]  # bisa berisi int atau URL string
        else:
            # fallback: scan 0..max_cameras-1 and take those that open
            self.cameras = self.detect_cameras(self.max_cameras)

        print("🎥 Active cameras (configured):", self.cameras)

        self.frames = [None] * len(self.cameras)
        self.ids = [set() for _ in self.cameras]
        self.workers = []

        self.last_rescan = time.time()
        self.rescan_interval = 5.0

    def detect_cameras(self, max_cam):
        detected = []
        for i in range(max_cam):
            try:
                cap = cv2.VideoCapture(i)
                ok, _ = cap.read()
                cap.release()
                if ok:
                    detected.append(i)
            except Exception:
                pass
        return detected

    def start_workers(self):
        for idx, cam in enumerate(self.cameras):
            worker = CameraWorker(cam, self.frames, self.ids, idx)
            if worker.running:
                worker.start()
                self.workers.append(worker)

    def add_new_cameras_if_any(self):
        # Re-scan only if using numeric scan fallback (not when camera_indexes provided)
        configured = SETTINGS.get("camera_indexes", [])
        if configured:
            return

        now = time.time()
        if now - self.last_rescan < self.rescan_interval:
            return
        self.last_rescan = now

        detected = self.detect_cameras(self.max_cameras)
        new = [c for c in detected if c not in self.cameras]
        for cam in new:
            print(f"➕ Detected new camera: {cam}")
            self.cameras.append(cam)
            self.frames.append(None)
            self.ids.append(set())
            buffer_idx = len(self.frames) - 1
            w = CameraWorker(cam, self.frames, self.ids, buffer_idx)
            if w.running:
                w.start()
                self.workers.append(w)

    def build_grid(self):
        valid_frames = [f for f in self.frames if f is not None]
        if len(valid_frames) == 0:
            return None
        if len(valid_frames) == 1:
            try:
                return cv2.resize(valid_frames[0], (1280, 720))
            except Exception:
                return valid_frames[0]

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
            # add new cameras only if using fallback scan
            self.add_new_cameras_if_any()

            # Update presence (per camera source)
            now = time.time()
            for idx, cam in enumerate(self.cameras):
                # normalize room_id as CAM_{index_in_list}
                room_id = f"CAM_{idx}"
                active_ids = self.ids[idx] if idx < len(self.ids) else set()
                # debug print (optional)
                # print(f"[DBG] update_presence {room_id} active={active_ids}")
                presence_manager.update_presence(room_id, active_ids, now)

            # show grid
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
        now = time.time()
        presence_manager.flush_all(now)
        presence_manager.print_logs()
