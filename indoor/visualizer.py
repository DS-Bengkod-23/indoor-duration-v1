import cv2
import numpy as np
import threading

class Visualizer:
    def __init__(self):
        self.font   = cv2.FONT_HERSHEY_SIMPLEX
        self.green  = (0, 255, 0)
        self.orange = (0, 165, 255)
        self.white  = (255, 255, 255)
        self.black  = (0, 0, 0)
        self.red    = (0, 0, 255)

        # 🔥 STABLE PERSISTENT ID MAPPING 🔥
        # Key: label string (name or Guest-X) → stable display PID
        # Key: (cam_id, DeepSORT_tid)         → stable display PID  (per-camera!)
        self._pid_lock  = threading.Lock()   # Hanya lock saat assign PID baru
        self.name_to_id = {}
        self.tid_to_pid = {}                 # Key: (cam_id, tid)
        self.next_pid   = 1

        self.active_pids_cycle = set()

    def start_new_cycle(self):
        self.active_pids_cycle = set()

    def _assign_pid(self, label, cam_tid_key):
        """Thread-safe PID assignment. Return (pid, updated)."""
        with self._pid_lock:
            if label in self.name_to_id and "Person " not in label:
                pid = self.name_to_id[label]
                self.tid_to_pid[cam_tid_key] = pid
                return pid

            if cam_tid_key in self.tid_to_pid:
                pid = self.tid_to_pid[cam_tid_key]
                if "Person " not in label and label not in self.name_to_id:
                    self.name_to_id[label] = pid
                return pid

            # Brand new: assign next available PID
            if "Person " not in label:
                used = set(self.name_to_id.values()) | set(self.tid_to_pid.values())
                while self.next_pid in used:
                    self.next_pid += 1
                pid = self.next_pid
                self.next_pid += 1
                self.name_to_id[label] = pid
                self.tid_to_pid[cam_tid_key] = pid
                return pid

            return None

    def _safe_bbox(self, bbox):
        """Return (x1,y1,x2,y2) int, atau None jika koordinat tidak valid."""
        try:
            x1, y1, x2, y2 = [float(v) for v in bbox]
            if any(v != v or abs(v) == float('inf') for v in (x1, y1, x2, y2)):
                return None
            return int(x1), int(y1), int(x2), int(y2)
        except Exception:
            return None

    def draw_tracks(self, frame, tracks, fusion_manager, face_vote_cache, local_pos_history, cam_id=0):
        """
        Menggambar semua track.
        Proses is_real (hijau) dahulu agar mendapat PID lebih kecil.
        cam_id dipakai sebagai bagian key tid_to_pid agar tidak collision antar kamera.
        """
        # 🔥 SORT: registered (is_real=True) diproses duluan → dapat PID rendah dulu
        def priority(t):
            _, is_real = fusion_manager.get_label(t[0])
            return 0 if is_real else 1
        sorted_tracks = sorted(tracks, key=priority)

        for t in sorted_tracks:
            tid, bbox = t[0], t[1]

            # 🔥 Safety: skip bbox dengan nilai infinity
            coords = self._safe_bbox(bbox)
            if coords is None:
                continue
            x1, y1, x2, y2 = coords

            label, is_real = fusion_manager.get_label(tid)
            cam_tid_key    = (cam_id, tid)

            # Assign stable PID (thread-safe)
            pid = self._assign_pid(label, cam_tid_key)

            # --- GAMBAR ---
            if is_real:
                # HIJAU: orang terdaftar & terverifikasi
                color = self.green
                with self._pid_lock:
                    display = f"{label} (ID: {self.name_to_id.get(label, pid)})"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                (tw, th), _ = cv2.getTextSize(display, self.font, 0.6, 2)
                cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
                cv2.putText(frame, display, (x1, y1 - 5), self.font, 0.6, self.black, 1)

            elif "Guest-" in label:
                # ORANGE: orang asing yang sudah punya Guest label
                color = self.orange
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
                show = f"ID: {pid}" if pid is not None else label
                cv2.putText(frame, show, (x1, y1 - 5), self.font, 0.6, color, 2)

            else:
                # ORANGE TIPIS: raw tracker / track baru belum teridentifikasi
                color = self.orange
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

                if "Person " in label:
                    # 🔥 FIX: Track baru dapat PID stabil langsung, bukan "?"
                    # Hapus stale mapping dulu (jika pernah punya Guest label sebelumnya)
                    with self._pid_lock:
                        # Clear jika pernah punya mapping lama dari Guest → reset ke fresh PID
                        old = self.tid_to_pid.get(cam_tid_key)
                        if old is not None and old in set(self.name_to_id.values()):
                            # Stale dari Guest mapping → hapus
                            del self.tid_to_pid[cam_tid_key]
                        if cam_tid_key not in self.tid_to_pid:
                            used = set(self.name_to_id.values()) | set(self.tid_to_pid.values())
                            while self.next_pid in used:
                                self.next_pid += 1
                            self.tid_to_pid[cam_tid_key] = self.next_pid
                            self.next_pid += 1
                        p = self.tid_to_pid[cam_tid_key]
                    cv2.putText(frame, f"ID: {p}",
                                (x1, y1 - 5), self.font, 0.6, color, 1)

                elif pid is not None:
                    # Known name tapi belum verified (is_real=False)
                    cv2.putText(frame, f"{label}? ({pid})",
                                (x1, y1 - 5), self.font, 0.5, color, 1)
                else:
                    # Fallback: assign PID baru
                    with self._pid_lock:
                        if cam_tid_key not in self.tid_to_pid:
                            used = set(self.name_to_id.values()) | set(self.tid_to_pid.values())
                            while self.next_pid in used:
                                self.next_pid += 1
                            self.tid_to_pid[cam_tid_key] = self.next_pid
                            self.next_pid += 1
                        p = self.tid_to_pid[cam_tid_key]
                    cv2.putText(frame, f"ID: {p}",
                                (x1, y1 - 5), self.font, 0.6, color, 1)

    def draw_fps(self, frame, fps):
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 40), self.font, 1.0, self.green, 2)

    def draw_notifications(self, frame, notification_queue):
        if len(notification_queue) > 0:
            notif = notification_queue[0]
            text  = notif["text"]
            color = notif["color"]
            (tw, th), _ = cv2.getTextSize(text, self.font, 1.0, 3)
            cv2.rectangle(frame, (50, 100 - th - 10), (50 + tw + 20, 110), self.black, -1)
            cv2.putText(frame, text, (60, 100), self.font, 1.0, color, 3)

    def draw_cam_id(self, frame, cam_id):
        cv2.putText(frame, f"CAM {cam_id}", (10, 20),
                    self.font, 0.6, (0, 255, 255), 2)

visualizer = Visualizer()
