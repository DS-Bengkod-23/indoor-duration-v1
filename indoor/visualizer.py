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
        
    def draw_tracks(self, frame, tracks, fusion_manager, face_vote_cache, local_pos_history):
        """
        Menggambar kotak bounding box dan label untuk setiap track.
        """
        active_names_in_frame = {}
        
        # Pre-pass untuk logika visual (siapa yang hijau, siapa yang orange)
        # Sebenarnya logika ini agak hybrid, tapi kita coba visualkan saja hasil dari fusion.
        
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = map(int, bbox) # Pastikan int
            
            # Ambil label dari Fusion
            label, is_real = fusion_manager.get_label(tid)
            
            # Tentukan Warna dan Ketebalan
            if is_real:
                # HIJAU: TEBAL + NAMA
                color = self.green
                thickness = 2
                
                # Gambar Kotak
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Gambar Label Background biar jelas
                display_text = f"{label} (ID: {tid})"
                (text_w, text_h), baseline = cv2.getTextSize(display_text, self.font, 0.6, 2)
                cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w, y1), color, -1)
                cv2.putText(frame, display_text, (x1, y1 - 5), self.font, 0.6, self.black, 2)
            elif "Guest-" in label:
                # CYAN: GUEST MODE (Unknown but Linked)
                color = (255, 255, 0) # Cyan
                thickness = 2
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Label Guest
                cv2.putText(frame, f"{label}", (x1, y1 - 5), self.font, 0.6, self.black, 2)
                cv2.putText(frame, f"{label}", (x1, y1 - 5), self.font, 0.6, color, 1)

            else:
                # ORANGE: TIPIS + POLOS (Bersih)
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
