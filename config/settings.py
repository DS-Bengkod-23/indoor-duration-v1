# config/settings.py
SETTINGS = {
    "camera_indexes": [ 0, 
                       #"http://192.168.32.135:8080/video",
                       #"http://192.168.41.10:8080/video",
                        
                       ], 
    "max_cameras": 4,

    # FACE DETECTION
    "face_conf_threshold": 0.40,
    "face_nms_threshold": 0.30,
    

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
    "max_dist": 0.20,         
    "min_confidence": 0.3,     
    "nms_max_overlap": 0.5,   
    "max_iou_distance": 0.70,  
    "max_age": 30,             
    "n_init": 3,               
    "min_hits": 3,
    "body_rebind_threshold": 0.70,

    # FUSION
    "face_body_iou_match": 0.02,
    "id_lock_duration": 5.0,
    "lock_sticky": True,

    # PERFORMANCE
    "det_interval": 4, 
    "face_interval": 5, 
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

    #  NEW OPTIMIZED THRESHOLDS (v2.2 - BALANCED ADAPTIVE) 
    "thresh_anti_clone": 0.75, 
    "thresh_same_room": 0.68,      
    "thresh_diff_room": 0.76,      
   
    "thresh_blind_small": 0.72, 
    "thresh_blind_large": 0.72,    
  
    "thresh_back_view_learn": 0.45, 
    "time_back_view_window": 5.0,  
    
    "gate_threshold_global": 0.65
}