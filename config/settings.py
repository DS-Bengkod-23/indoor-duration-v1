# config/settings.py
SETTINGS = {
    "camera_indexes": [ 0, 
                        "http://192.168.43.173:8080/video",    
                        #"http://192.168.42.25:8080/video",
                        #"http://192.168.41.10:8080/video",
                       ], 
    "max_cameras": 4,
    "flip_camera": True,   # True = balik horizontal (hilangkan mirror webcam)

    # FACE DETECTION
    "face_conf_threshold": 0.32,   # TURUN agar mendeteksi lebih sensitif dari jauh
    "face_nms_threshold": 0.30,
    

    "face_input_size": (416, 312),  # Turun dari (480,360) untuk hemat CPU (~30% lebih sedikit pixel)

    # FACE RECOGNITION
    "face_recog_threshold": 0.60,      
    "face_recog_confirmed": 0.65,      
    "face_recog_min_frames": 1,

    # PERSON DETECTION (YOLO)
    "yolo_conf_threshold": 0.45,       # Naik dari 0.40 agar benda mati tidak disangka Guest
    "yolo_iou_threshold": 0.45,        # TURUN (dari 0.65) agar tangan merentang saat duduk tidak kepotong
    "yolo_classes": [0],

    # TRACKING
    "max_dist": 0.20,         
    "min_confidence": 0.40,     # Naikkan dari 0.30 agar track samar dibuang
    "nms_max_overlap": 0.50,    # Perlonggar (dari 0.40) agar bbox tumpang-tindih saat duduk tidak terpotong
    "max_iou_distance": 0.65,   # NAIK (dari 0.55): Toleransi sangat longgar perubahan box ekstrem (berdiri -> duduk)
    "max_age": 45,              # NAIK (dari 15): 45 Frame Tahan Tertutup/Ngumpet sebelum dianggap hilang (Anti-Nambah ID)
    "n_init": 3,                # TURUN (dari 4) agar track cepat sah dan tidak berkedip lama saat ganti ID
    "min_hits": 4,
    "body_rebind_threshold": 0.70,

    # FUSION
    "face_body_iou_match": 0.05,
    "id_lock_duration": 5.0,
    "lock_sticky": True,

    # PERFORMANCE
    "det_interval": 4,           # AI scan badan setiap 4 frame. Optimal untuk CPU-only.
    "face_interval": 10,         # Cek Wajah tiap 10 frame. Hemat CPU, Kalman Filter tetap smooth.
    "guest_memory_seconds": 1800, 
    "frame_resize": 640,
    "use_half_precision": True,
    "max_osnet_tracks": 3,       # TURUN: Hemat CPU saat rame, 3 orang diproses gantian ReID per frame

    "body_reid_threshold": 0.63,     # TURUN agar re-entry dengan baju sama mudah dikenali
    "body_profile_momentum": 0.8,
    "body_reid_margin": 0.05,
    "presence_timeout": 60.0,  
    "room_mapping": {"CAM_0": "Ruang Dosen", "CAM_1": "Ruang Dosen", "CAM_2": "Ruang Aula"},
    "cap_width": 640,
    "cap_height": 480, 
    "debug_mode": False,
    "debug_save_unknown": False,
    "show_fps": True,
    "save_logs": False,
    "unknown_to_outdoor": 10.0,
    "default_room_name": "Ruangan Tidak Dikenal",
    "cap_fps": 30, 
    "enable_registration_hotkey": True,
    "registration_key": "r",
    "save_embedding_npy": True,

    #  NEW OPTIMIZED THRESHOLDS (v2.2 - BALANCED ADAPTIVE) 
    "thresh_anti_clone": 0.75, 
    "thresh_same_room": 0.68,      
    "thresh_diff_room": 0.76,     
   
    "thresh_blind_small": 0.72, 
    "thresh_blind_large": 0.72,    
  
    "thresh_back_view_learn": 0.45, 
    "time_back_view_window": 5.0,  
    "thresh_force_learn_back_view": 0.60, 
    "thresh_guest_reid": 0.68,  
    "gate_threshold_global": 0.40, 

    # HARDCODED REPLACEMENTS
    "max_faces_to_process": 5,  
    "thresh_sitting_ratio": 1.6,
    "thresh_sitting_conf": 0.60,
    "thresh_strict_lock": 0.65,
    "thresh_cross_cam_reid": 0.62,  # Threshold body match untuk cross-camera fast-ID
}