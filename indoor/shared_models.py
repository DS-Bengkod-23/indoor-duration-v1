# indoor/shared_models.py
import threading

from indoor.face_recognizer import FaceRecognizer
from indoor.osnet.reid_osnet import OSNetReID
from config.paths import get_model_paths

from ultralytics import YOLO
import torch

_face_recognizer = None
_face_lock = threading.Lock()

_osnet = None
_osnet_lock = threading.Lock()

_yolo = None
_yolo_lock = threading.Lock()
_yolo_device = "cpu"


def get_face_recognizer():
    """Singleton FaceRecognizer dipakai semua kamera."""
    global _face_recognizer
    if _face_recognizer is None:
        with _face_lock:
            if _face_recognizer is None:
                _face_recognizer = FaceRecognizer()
    return _face_recognizer


def get_osnet():
    """Singleton OSNet dipakai semua kamera."""
    global _osnet
    if _osnet is None:
        with _osnet_lock:
            if _osnet is None:
                paths = get_model_paths()
                _osnet = OSNetReID(paths["osnet"])
    return _osnet


def get_yolo_model():
    """
    Singleton YOLOv8n dipakai semua kamera.
    Dipasang di GPU kalau ada.
    """
    global _yolo, _yolo_device
    if _yolo is None:
        with _yolo_lock:
            if _yolo is None:
                paths = get_model_paths()
                device = "cuda" if torch.cuda.is_available() else "cpu"
                model = YOLO(paths["yolo"])

                # beberapa versi YOLO punya .to(), beberapa pakai arg device di predict
                try:
                    model.to(device)
                except Exception:
                    pass

                _yolo = model
                _yolo_device = device

    return _yolo, _yolo_device
