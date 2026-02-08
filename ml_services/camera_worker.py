"""Camera Worker - Main processing loop for camera streams"""
import cv2
import asyncio
import base64
import json
import numpy as np
from datetime import datetime
from typing import Optional
import sys
import os
import redis

# Add parent directory to path  
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ml_services.processor import FrameProcessor
from app.config import settings
from app.services.camera_service import CameraService
from app.services.duration_service import DurationService
from app.services.person_service import PersonService


class CameraWorker:
    """
    Camera worker process - handles video stream processing
    One worker per camera, runs in separate container
    """
    
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.processor: Optional[FrameProcessor] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.room_id: Optional[str] = None  # Store room_id for duration tracking
        
        # Redis support for local cameras
        self.use_redis = False
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        
        # Database connection
        engine = create_engine(settings.DATABASE_URL)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        print(f"[WORKER] Initialized for camera {camera_id}")
    
    def initialize_camera(self):
        """Initialize camera and processor"""
        db = self.SessionLocal()
        try:
            # Get camera info from database
            camera_service = CameraService(db)
            camera = camera_service.get_camera_by_id(self.camera_id)
            
            if not camera:
                raise ValueError(f"Camera {self.camera_id} not found in database")
            
            print(f"[WORKER] Loading camera: {camera.name}")
            print(f"[WORKER]   RTSP URL: {camera.rtsp_url}")
            print(f"[WORKER]   Camera Index: {camera.camera_index}")
            
            # Determine camera source type
            # Redis-based (local webcam): rtsp_url contains "redis://"
            # RTSP: rtsp_url starts with "rtsp://"
            # Direct: camera_index is set and rtsp_url doesn't contain "redis://"
            
            if "redis://" in camera.rtsp_url.lower():
                # Local camera captured by native service, frames via Redis
                print(f"[WORKER] 📡 Mode: REDIS SUBSCRIPTION (local webcam)")
                self.use_redis = True
                
                # Connect to Redis
                self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
                self.pubsub = self.redis_client.pubsub()
                
                # Subscribe to camera frames channel
                channel = f"camera_frames:{self.camera_id}"
                self.pubsub.subscribe(channel)
                print(f"[WORKER] ✅ Subscribed to Redis channel: {channel}")
                print(f"[WORKER] ⚠️  Make sure camera_capture_service.py is running for this camera!")
                
            else:
                # Traditional video capture (RTSP or local camera index)
                self.use_redis = False
                
                # Still need Redis for publishing processed frames to WebSocket
                try:
                    self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
                    print(f"[WORKER] ✅ Redis connected for WebSocket publishing")
                except Exception as e:
                    print(f"[WORKER] ⚠️  Redis not available for WebSocket: {e}")
                    self.redis_client = None
                
                if camera.rtsp_url.startswith("rtsp://"):
                    print(f"[WORKER] 📹 Mode: RTSP STREAM")
                    self.cap = cv2.VideoCapture(camera.rtsp_url)
                elif camera.camera_index is not None:
                    print(f"[WORKER] 📹 Mode: DIRECT CAMERA (index {camera.camera_index})")
                    self.cap = cv2.VideoCapture(camera.camera_index)
                else:
                    raise ValueError(f"Invalid camera configuration: no valid source")
                
                if not self.cap.isOpened():
                    raise RuntimeError(f"Failed to open camera {camera.name}")
                
                print(f"[WORKER] ✅ Camera opened successfully")

            
            # Store room_id for duration tracking
            self.room_id = str(camera.room.id) if camera.room else None
            
            # Initialize processor
            self.processor = FrameProcessor(
                camera_id=str(camera.id),
                camera_name=camera.name,
                room_name=camera.room.name if camera.room else "Unknown"
            )
            
            # Set room_id on processor for easy access
            self.processor.room_id = self.room_id
            
            # Update camera status
            camera_service.update_camera_status(
                camera_id=self.camera_id,
                is_online=True,
                last_seen=datetime.utcnow()
            )
            
            print(f"[WORKER] Camera {camera.name} initialized successfully")
            
        except Exception as e:
            print(f"[WORKER] Error initializing camera: {e}")
            raise
        finally:
            db.close()
    
    async def process_loop(self):
        """Main processing loop"""
        self.is_running = True
        frame_count = 0
        
        db = self.SessionLocal()
        duration_service = DurationService(db)
        person_service = PersonService(db)
        
        try:
            while self.is_running:
                # Get frame from Redis or VideoCapture
                frame = None
                
                if self.use_redis:
                    # Get frame from Redis subscription
                    try:
                        message = self.pubsub.get_message(timeout=1.0)
                    except Exception as e:
                        print(f"[WORKER] Redis pubsub error: {e}")
                        await asyncio.sleep(1)
                        continue
                    
                    if message is None:
                        await asyncio.sleep(0.01)
                        continue
                    
                    if message['type'] != 'message':
                        # Skip non-message types (subscribe confirmations, etc.)
                        continue
                    
                    try:
                        # Parse JSON frame data (JPEG compressed)
                        frame_data = json.loads(message['data'])
                        
                        # Decode JPEG from base64
                        if 'frame_jpeg' in frame_data:
                            img_bytes = base64.b64decode(frame_data['frame_jpeg'])
                            nparr = np.frombuffer(img_bytes, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        else:
                            # Legacy pickle support (skip for now)
                            print(f"[WORKER] ⚠️ Received non-JPEG frame, skipping")
                            continue
                        
                        if frame is None:
                            print(f"[WORKER] ⚠️ Failed to decode JPEG frame")
                            continue
                        
                        # Log first frame
                        if frame_count == 0:
                            print(f"[WORKER] ✅ Receiving JPEG frames from Redis")
                        
                    except json.JSONDecodeError as e:
                        print(f"[WORKER] Error parsing JSON: {e}")
                        await asyncio.sleep(0.1)
                        continue
                    except Exception as e:
                        print(f"[WORKER] Error decoding frame: {e}")
                        await asyncio.sleep(0.1)
                        continue
                else:
                    # Get frame from VideoCapture (RTSP or direct)
                    ret, frame = self.cap.read()
                    if not ret:
                        print(f"[WORKER] Failed to read frame, attempting reconnect...")
                        await asyncio.sleep(1)
                        continue
                
                if frame is None:
                    continue
                
                frame_count += 1
                
                # Frame skipping for FPS optimization:
                # Run full ML detection every N frames
                # Skip ML on intermediate frames (use tracker predictions only)
                ML_EVERY_N_FRAMES = 3  # Run ML every 3rd frame
                skip_ml = (frame_count % ML_EVERY_N_FRAMES != 0)
                
                # Process frame (with or without ML)
                result = self.processor.process_frame(frame, skip_ml=skip_ml)
                
                # Update database with detections
                for detection in result["detections"]:
                    track_id = detection["track_id"]
                    person_id = detection["person_id"]
                    guest_label = detection["person_name"] if detection["is_guest"] else None
                    
                    # Get or create duration record (skip if no room_id)
                    if self.room_id:
                        try:
                            duration = duration_service.get_or_create_active_duration(
                                track_id=track_id,
                                camera_id=self.camera_id,
                                room_id=self.room_id,
                                person_id=person_id,
                                guest_label=guest_label,
                                confidence=detection["confidence"]
                            )
                        except Exception as e:
                            print(f"[WORKER] Error updating duration: {e}")
                
                # Encode frame for WebSocket
                _, buffer = cv2.imencode('.jpg', result["annotated_frame"], 
                                        [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # Prepare WebSocket message
                ws_message = {
                    "type": "frame",
                    "camera_id": result["camera_id"],
                    "camera_name": result["camera_name"],
                    "room_name": result["room_name"],
                    "timestamp": result["timestamp"],
                    "detections": result["detections"],
                    "frame_base64": frame_base64
                }
                
                # Publish to Redis for WebSocket streaming
                try:
                    ws_channel = f"ws_frames:{self.camera_id}"
                    self.redis_client.publish(ws_channel, json.dumps(ws_message))
                except Exception as e:
                    if frame_count % 100 == 0:
                        print(f"[WORKER] Error publishing to WebSocket channel: {e}")
                
                # Log progress
                if frame_count % 30 == 0:  # Every second at 30fps
                    mode = "REDIS" if self.use_redis else "VIDEO"
                    print(f"[WORKER] [{mode}] Processed frame {frame_count}, detections: {len(result['detections'])}")
                
                # Small delay to control FPS (only for non-Redis mode)
                if not self.use_redis:
                    await asyncio.sleep(0.033)  # ~30 FPS
                else:
                    # Redis mode: frames come at their own rate
                    await asyncio.sleep(0.001)

                
        except Exception as e:
            print(f"[WORKER] Error in processing loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()
            self.stop()
    
    def stop(self):
        """Stop worker"""
        self.is_running = False
        if self.cap:
            self.cap.release()
            print(f"[WORKER] VideoCapture released")
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.pubsub.close()
            print(f"[WORKER] Redis pubsub closed")
        if self.redis_client:
            self.redis_client.close()
            print(f"[WORKER] Redis client closed")
        print(f"[WORKER] Stopped")
    
    async def run(self):
        """Run worker"""
        print(f"[WORKER] Starting camera worker...")
        self.initialize_camera()
        await self.process_loop()


async def main():
    """Main entry point for camera worker"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Camera Worker Process")
    parser.add_argument("--camera-id", required=True, help="Camera UUID from database")
    args = parser.parse_args()
    
    worker = CameraWorker(camera_id=args.camera_id)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
