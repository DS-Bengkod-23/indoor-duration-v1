# config/settings.py
SETTINGS = {
    "camera_indexes": [ 0, 
                       "http://192.168.18.3:8080/video",
                       #"http://192.168.41.10:8080/video",
                        
                       ], 
    "max_cameras": 4,

    # FACE DETECTION
    "face_conf_threshold": 0.45,
    "face_nms_threshold": 0.30,
    
    # 🔥 UBAH KE INI: Resolusi 'Sweet Spot' (Tengah-tengah)
    # 320x240 = Terlalu Kecil (Kotak ilang saat duduk)
    # 640x480 = Terlalu Berat (Laptop panas/lag)
    # 480x360 = PAS (Tajam & Ringan)
    "face_input_size": (480, 360), 

    # FACE RECOGNITION
    "face_recog_threshold": 0.60,      
    "face_recog_confirmed": 0.65,      
    "face_recog_min_frames": 1,

    # PERSON DETECTION (YOLO)
    "yolo_conf_threshold": 0.45,       
    "yolo_iou_threshold": 0.65, 
    "yolo_classes": [0],

    # TRACKING
    "max_dist": 0.25,          # 🔥 RELAXED: 0.2 -> 0.25 (Biar re-id lebih toleran gerakan cepat)
    "min_confidence": 0.3,     # Min confidence deteksi YOLO
    "nms_max_overlap": 0.5,    # NMS threshold
    "max_iou_distance": 1.1,   # 🔥 ULTRA RELAXED: 0.9 -> 1.1 (Boleh loncat jauh banget, gerakan Ninja OK)
    "max_age": 70,             # Umur track sebelum dihapus
    "n_init": 3,               # Frame minimal untuk confirm track
    "min_hits": 3,
    "body_rebind_threshold": 0.70,

    # FUSION
    "face_body_iou_match": 0.02,
    "id_lock_duration": 5.0,
    "lock_sticky": True,

    # PERFORMANCE
    "det_interval": 4, # PERCEPAT: 5 -> 4 (Tracking lebih halus)
    "face_interval": 12, # PERLAMBAT: 6 -> 12 (Face Rec berat, jangan sering-sering)
    "frame_resize": 640,
    "use_half_precision": True,

    "body_reid_threshold": 0.70,
    "body_profile_momentum": 0.8,
    "body_reid_margin": 0.05,

    "presence_timeout": 2.0, 
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

    # 🔥 NEW OPTIMIZED THRESHOLDS (v2.2 - BALANCED ADAPTIVE) 🔥
    "thresh_anti_clone": 0.82,     
    "thresh_same_room": 0.79, # 🔥 UPDATE: NAIKKAN DIKIT (0.72 -> 0.75) biar Stranger di satu ruangan gak gampang masuk.      
    "thresh_diff_room": 0.81, # 🔥 UPDATE: LEBIH KETAT (0.78 -> 0.81) untuk cegah False Positive di kamera lain.      
    # BLIND LOOKUP: Sedikit dilonggarkan (0.75 -> 0.70) biar crowds detection lebih mulus
    # Nanti diketatkan lagi via Logic Adaptive di tracker code kalau sepi.
    "thresh_blind_small": 0.70,    
    "thresh_blind_large": 0.82,    
    "thresh_back_view_learn": 0.60, 
    "time_back_view_window": 3.0,  
    # GLOBAL GATE: Sedikit dilonggarkan (0.65 -> 0.62) sebagai baseline untuk crowds.
    "gate_threshold_global": 0.62  
}