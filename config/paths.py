import os

# Root project directory
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Model directory
MODEL_DIR = os.path.join(ROOT, "models")

# Data directories
EMBED_DIR      = os.path.join(ROOT, "data", "embeddings")        # face
BODY_EMB_DIR   = os.path.join(ROOT, "data", "body_embeddings")   # body (OSNet)
LOG_DIR        = os.path.join(ROOT, "data", "logs")

# Model files (YuNet + YOLO + OSNet)
YUNET_ONNX = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
YOLOV8N_PT = os.path.join(MODEL_DIR, "yolov8n.pt")
OSNET_ONNX = os.path.join(MODEL_DIR, "osnet_x1_0.onnx")

# Ensure folders exist
os.makedirs(MODEL_DIR,    exist_ok=True)
os.makedirs(EMBED_DIR,    exist_ok=True)
os.makedirs(BODY_EMB_DIR, exist_ok=True)
os.makedirs(LOG_DIR,      exist_ok=True)

# -------------------------------------------------------------
#  MODEL PATHS  (dipakai face detector, YOLO, dll)
# -------------------------------------------------------------
def get_model_paths():
    return {
        "yunet": YUNET_ONNX,
        "yolo": YOLOV8N_PT,
        "osnet": OSNET_ONNX,
        "embeddings_dir": EMBED_DIR,
        "body_embeddings_dir": BODY_EMB_DIR,
        "logs_dir": LOG_DIR,
    }

# -------------------------------------------------------------
#  DATA PATHS (dipakai logging / database)
# -------------------------------------------------------------
def get_data_paths():
    return {
        "embeddings_dir": EMBED_DIR,
        "body_embeddings_dir": BODY_EMB_DIR,
        "logs_dir": LOG_DIR,
    }
