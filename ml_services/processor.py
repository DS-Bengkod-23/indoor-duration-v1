"""Frame Processor - Thin wrapper around MultiObjectTracker for camera worker"""
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indoor.tracker_deepsort import MultiObjectTracker
from indoor.visualizer import visualizer
from config.settings import SETTINGS


class FrameProcessor:
    """
    Wraps MultiObjectTracker for camera worker usage.
    
    This is a thin wrapper that:
    1. Delegates all ML processing to MultiObjectTracker.process_frame()
    2. Extracts detection data from tracker's internal state
    3. Returns structured data for camera_worker.py
    """
    
    def __init__(self, camera_id: str, camera_name: str, room_name: str):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.room_name = room_name
        self.room_id: Optional[str] = None  # Can be set by worker if needed
        
        print(f"[PROCESSOR] Initializing for {camera_name} ({room_name})...")
        
        # Use the proven MultiObjectTracker directly
        # This is the same tracker used by indoor/video.py
        self.tracker = MultiObjectTracker()
        self.tracker.set_camera_id(0)  # Default to cam index 0
        
        self.frame_count = 0
        print(f"[PROCESSOR] Initialized successfully")
    
    def process_frame(self, frame: np.ndarray, skip_ml: bool = False) -> Dict[str, Any]:
        """
        Process a single frame through the ML pipeline.
        
        Args:
            frame: BGR image as numpy array
            skip_ml: If True, skip detection and only use tracker predictions (faster)
            
        Returns:
            Dict containing:
                - camera_id: Camera UUID
                - camera_name: Camera display name
                - room_name: Room name
                - timestamp: ISO format timestamp
                - frame_count: Current frame number
                - detections: List of detected persons
                - annotated_frame: Frame with bounding boxes drawn
                - raw_frame: Original unmodified frame
        """
        self.frame_count += 1
        
        # Apply CLAHE for lighting normalization (same as video.py)
        try:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=1.1, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            frame = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        except Exception:
            pass  # Skip if format issues
        
        # Resize to standard input size
        target_size = SETTINGS.get("face_input_size", (640, 480))
        frame = cv2.resize(frame, target_size)
        
        # Store raw frame before annotation
        raw_frame = frame.copy()
        
        if skip_ml:
            # Skip ML detection - only use tracker predictions (fast path)
            # Just draw existing tracks without new detection
            annotated_frame = self._tracking_only(frame)
        else:
            # Full ML pipeline - detection + tracking + identification
            annotated_frame = self.tracker.process_frame(frame)
        
        # Extract detection data from tracker's internal state
        detections = self._extract_detections()
        
        return {
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "room_name": self.room_name,
            "timestamp": datetime.utcnow().isoformat(),
            "frame_count": self.frame_count,
            "detections": detections,
            "annotated_frame": annotated_frame,
            "raw_frame": raw_frame
        }
    
    def _tracking_only(self, frame: np.ndarray) -> np.ndarray:
        """
        Fast path: Only update tracker predictions without running ML detection.
        Used for intermediate frames to boost FPS.
        """
        annotated_frame = frame.copy()
        
        try:
            # Get existing tracks and predict new positions
            tracks = self.tracker.deepsort.get_active_tracks(with_feature=False)
            
            for t in tracks:
                tid, bbox = t[0], t[1]
                x1, y1, x2, y2 = map(int, bbox)
                
                # Get identity from fusion manager
                label, is_real = self.tracker.fusion.get_label(tid)
                
                # Draw bounding box
                color = (0, 255, 0) if is_real else (0, 165, 255)  # Green for known, orange for guest
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label
                label_text = label if is_real else f"Guest-{tid}"
                cv2.putText(annotated_frame, label_text, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
        except Exception as e:
            pass  # Return frame as-is on error
        
        return annotated_frame

    
    def _extract_detections(self) -> list:
        """
        Extract detection data from tracker's internal state.
        
        Maps tracker's internal data to the format expected by camera_worker.py
        """
        detections = []
        
        # Get active tracks from DeepSORT
        try:
            tracks = self.tracker.deepsort.get_active_tracks(with_feature=False)
        except Exception as e:
            print(f"[PROCESSOR] Error getting tracks: {e}")
            return detections
        
        for t in tracks:
            tid, bbox = t[0], t[1]
            x1, y1, x2, y2 = map(int, bbox)
            
            # Get identity from fusion manager
            label, is_real = self.tracker.fusion.get_label(tid)
            
            # Determine if this is a guest (unknown person)
            is_guest = not is_real or "Guest" in label or "Person" in label
            
            # Set person name based on identification status
            if is_guest:
                person_name = f"Guest-{tid}"
                person_id = None
                confidence = 0.0
            else:
                person_name = label
                person_id = label  # Using name as ID for now
                confidence = 1.0
            
            detections.append({
                "track_id": f"{self.camera_name}_T{tid}",
                "person_id": person_id,
                "person_name": person_name,
                "nim_nip": None,  # Will be filled by backend lookup
                "bbox": [x1, y1, x2, y2],
                "confidence": confidence,
                "duration_seconds": 0,  # Managed by duration_service
                "is_guest": is_guest
            })
        
        return detections
    
    def set_camera_index(self, index: int):
        """Set the camera index for the tracker (for multi-camera setups)"""
        self.tracker.set_camera_id(index)
