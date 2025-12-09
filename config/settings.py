# config/settings.py
# ==========================================================
#  SETTINGS – LONG RANGE + HIGH FPS (UPDATED + BODY REID SAFE)
# ==========================================================

SETTINGS = {

    # CAMERA
    "camera_indexes": [0],
    "max_cameras": 2,

    # FACE DETECTION – YuNet (long range)
    "face_conf_threshold": 0.65,
    "face_nms_threshold": 0.30,
    "face_input_size": (640, 480),

    # FACE RECOGNITION – InsightFace (long-range)
    "face_recog_threshold": 0.40,

    # PERSON DETECTION – YOLOv8n
    "yolo_conf_threshold": 0.45,
    "yolo_iou_threshold": 0.45,
    "yolo_classes": [0],  # 0 = person

    # TRACKING – DeepSORT
    "max_age": 20,
    "min_hits": 3,
    "max_iou_distance": 0.55,

    # FUSION – Face→Body
    "face_body_iou_match": 0.05,
    "id_lock_duration": 3.0,
    "lock_sticky": True,

    # REGISTRATION
    "enable_registration_hotkey": True,
    "registration_key": "r",
    "save_embedding_npy": True,

    # ======================================================
    # PERFORMANCE / INTERVAL
    # ======================================================
    "det_interval": 3,   # YOLO tiap 3 frame
    "face_interval": 6,  # face detect+recog tiap 6 frame

    "frame_resize": 720,
    "skip_frames": 0,
    "use_half_precision": False,
    "async_mode": True,

    # ======================================================
    # BODY ReID GLOBAL
    # ======================================================
    "body_reid_threshold": 0.50,
    "body_reid_strict": 0.75,
    "body_reid_min_frames": 2,
    "body_profile_momentum": 0.6,

    # LOG
    "show_fps": True,
    "save_logs": False,
}
