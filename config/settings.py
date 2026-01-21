# config/settings.py
SETTINGS = {
    "camera_indexes": [ 0, 
                       #"http://192.168.43.166:8080/video",
                       #"http://192.168.41.10:8080/video",
                        
                       ], 
    "max_cameras": 4,

    # FACE DETECTION
    "face_conf_threshold": 0.40, # 🔥 TURUNIN LAGI: 0.45 -> 0.40 (Biar wajah agak miring/gelap di Cam 1 tetap masuk)
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
    "yolo_conf_threshold": 0.40,       
    "yolo_iou_threshold": 0.65, 
    "yolo_classes": [0],

    # TRACKING
    "max_dist": 0.25,          #  RELAXED: 0.2 -> 0.25 (Biar re-id lebih toleran gerakan cepat)
    "min_confidence": 0.3,     # Min confidence deteksi YOLO
    "nms_max_overlap": 0.5,    # NMS threshold
    "max_iou_distance": 0.85,   #  UPDATE: RELAXED (0.7 -> 0.85). Biar kebal gerakan cepat/lari.
    "max_age": 15,             #  UPDATE: NAIKKAN (30 -> 55). Biar gak gampang ilang kalau ketutupan dikit.
    "n_init": 3,               # Frame minimal untuk confirm track
    "min_hits": 3,
    "body_rebind_threshold": 0.70,

    # FUSION
    "face_body_iou_match": 0.02,
    "id_lock_duration": 5.0,
    "lock_sticky": True,

    # PERFORMANCE
    "det_interval": 4, # PERCEPAT: 5 -> 4 (Tracking lebih halus)
    "face_interval": 8, # PERLAMBAT: 6 -> 12 (Face Rec berat, jangan sering-sering)
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
    "thresh_anti_clone": 0.75, # 🔥 TUNED: NAIKKAN DIKIT (0.75) untuk cegah False Positive Double Presence
    "thresh_same_room": 0.68, # 🔥 TUNED: NAIKKAN (0.60 -> 0.68). 0.60 terlalu rendah, bikin stranger jadi kita.      
    "thresh_diff_room": 0.76, # 🔥 TUNED: Relaxed (0.81 -> 0.76) for side-profile tolerance.      
    # BLIND LOOKUP: Diperketat (0.70 -> 0.75) agar stranger/noise tidak asal match.
    # Nanti diketatkan lagi via Logic Adaptive di tracker code kalau sepi.
    # BLIND LOOKUP: Diperketat (0.70 -> 0.75) agar stranger/noise tidak asal match.
    # Nanti diketatkan lagi via Logic Adaptive di tracker code kalau sepi.
    "thresh_blind_small": 0.60, # 🔥 UPDATE: NAIKKAN (0.50 -> 0.60). Biar stranger jauh gak hijack ID kita.   
    "thresh_blind_large": 0.65,    
    # 🔥 UPDATE v12.17: ENABLE BACK VIEW LEARNING (0.60 -> 0.50)
    # Ini kunci agar tampak belakang terekam otomatis saat orang muter.
    "thresh_back_view_learn": 0.45, 
    "time_back_view_window": 5.0,  # Perpanjang jendela waktu trusted (3s -> 5s)
    # GLOBAL GATE: Sedikit dilonggarkan (0.65 -> 0.62) sebagai baseline untuk crowds.
    "gate_threshold_global": 0.50  
}