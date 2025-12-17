# config/settings.py
# ==========================================================
#  SETTINGS – Multi-camera (webcam / IP cam) + Presence rules
# ==========================================================

SETTINGS = {

    # CAMERA:
    "camera_indexes": [
        "http://192.168.42.155:8080/video",
        0
    ],

    "max_cameras": 4,

    # FACE DETECTION – YuNet (long range)
    "face_conf_threshold": 0.60,
    "face_nms_threshold": 0.30,
    "face_input_size": (640, 480),

    # FACE RECOGNITION – InsightFace (ArcFace)
    # set rendah supaya mirip project lama (recog threshold sekitar 0.38)
    "face_recog_threshold": 0.25,
    "face_recog_strict": 0.30,
    "face_recog_min_frames": 1,

    # PERSON DETECTION – YOLOv8n
    "yolo_conf_threshold": 0.45,
    "yolo_iou_threshold": 0.45,
    "yolo_classes": [0],  # 0 = person

    # TRACKING – DeepSORT
    "max_age": 30,
    "min_hits": 3,
    "max_iou_distance": 0.70,

    # FUSION
    "face_body_iou_match": 0.02,
    "id_lock_duration": 2.0,
    "lock_sticky": True,

    # REGISTRATION
    "enable_registration_hotkey": True,
    "registration_key": "r",
    "save_embedding_npy": True,

    # PERFORMANCE / INTERVAL
    # urgent: face interval lebih sering daripada sebelumnya supaya pengenal cepat
    "det_interval": 3,
    "face_interval": 3,
    "frame_resize": 720,
    "skip_frames": 0,
    "use_half_precision": False,
    "async_mode": True,

    # BODY ReID GLOBAL (OSNet)
    "body_reid_threshold": 0.60,
    "body_reid_strict": 0.70,
    "body_reid_min_frames": 7,
    "body_profile_momentum": 0.7,
    "body_reid_margin": 0.06,

    # LOG
    "show_fps": True,
    "save_logs": False,

    # PRESENCE MANAGER (INDOOR / UNKNOWN / OUTDOOR)
    "presence_timeout": 10.0,
    "unknown_to_outdoor": 10.0,

    "room_mapping": {
        "CAM_0": "Ruang Dosen",
        "CAM_1": "Ruang Dosen",
        "CAM_2": "Ruang H2.1",
        "CAM_3": "Ruang Rapat",
    },

    "default_room_name": "Ruangan Tidak Dikenal",

    # Kamera reader settings
    "cap_width": 640,
    "cap_height": 360,
    "cap_fps": 10,

    # DEBUG FLAGS (opsional)
    "debug_mode": False,
    "debug_save_unknown": False,
}
