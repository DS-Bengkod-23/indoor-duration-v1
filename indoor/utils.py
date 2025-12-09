# indoor/utils.py
import cv2
import numpy as np
import time


def resize_frame(frame, target_height=720):
    """
    Resize frame berdasarkan tinggi (height) → menjaga aspect ratio.
    """
    h, w = frame.shape[:2]
    scale = target_height / h
    new_w = int(w * scale)
    return cv2.resize(frame, (new_w, target_height))


def draw_box(frame, x1, y1, x2, y2, color=(0,255,0), label=None):
    """
    Utility sederhana untuk menggambar bounding box + label.
    """
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    if label:
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def compute_fps(prev_time):
    """
    Hitung FPS.
    Return (fps, now_time)
    """
    now = time.time()
    fps = 1 / (now - prev_time)
    return fps, now
