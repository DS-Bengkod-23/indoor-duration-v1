"""
Native Windows Camera Capture Service (Optimized)
Captures frames from local USB webcams and publishes to Redis
Uses JPEG compression to reduce bandwidth (~30KB vs ~1MB per frame)

Usage:
    python camera_capture_service.py --camera-id YOUR-CAMERA-UUID --camera-index 0
    python camera_capture_service.py --camera-id YOUR-CAMERA-UUID --camera-index 0 --redis-url redis://localhost:6379
"""
# python camera_capture_service.py --camera-id 5b184d0f-983d-4759-acbd-9742e7241562 --camera-index 0

import cv2
import redis
import time
import base64
import json
import argparse
from datetime import datetime
import sys


class CameraCaptureService:
    """Captures frames from local camera and publishes to Redis (JPEG optimized)"""
    
    def __init__(self, camera_id: str, camera_index: int, redis_url: str = "redis://localhost:6379"):
        self.camera_id = camera_id
        self.camera_index = camera_index
        self.redis_url = redis_url
        self.redis_client = None
        self.cap = None
        self.running = False
        self.target_fps = 25  # Lowered for USB webcams
        self.jpeg_quality = 70  # Good balance of quality/size
        
    def connect_redis(self):
        """Connect to Redis"""
        print(f"[CAPTURE] Connecting to Redis at {self.redis_url}...")
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            print(f"[CAPTURE] ✅ Connected to Redis")
        except Exception as e:
            print(f"[CAPTURE] ❌ Failed to connect to Redis: {e}")
            print(f"[CAPTURE] Make sure Redis is running: docker-compose ps redis")
            sys.exit(1)
    
    def open_camera(self):
        """Open camera with DirectShow backend (Windows)"""
        print(f"[CAPTURE] Opening camera index {self.camera_index}...")
        
        # Use DirectShow for Windows webcams (more reliable than default)
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            print(f"[CAPTURE] ❌ Failed to open camera {self.camera_index}")
            print(f"[CAPTURE] Available camera indices:")
            # Try to detect available cameras
            for i in range(3):
                test_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if test_cap.isOpened():
                    print(f"[CAPTURE]   - Camera index {i} is available")
                    test_cap.release()
                else:
                    print(f"[CAPTURE]   - Camera index {i} is NOT available")
            sys.exit(1)
        
        # Set camera properties for better performance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # Get actual camera properties
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        
        print(f"[CAPTURE] ✅ Camera {self.camera_index} opened successfully")
        print(f"[CAPTURE]    Resolution: {width}x{height} @ {fps} FPS")
        
    def start(self):
        """Start capturing and publishing frames"""
        self.connect_redis()
        self.open_camera()
        
        # Channel for camera worker to subscribe to
        channel = f"camera_frames:{self.camera_id}"
        
        print(f"[CAPTURE] Starting capture loop for camera_id: {self.camera_id}")
        print(f"[CAPTURE] Publishing to Redis channel: {channel}")
        print(f"[CAPTURE] Target FPS: {self.target_fps} | JPEG Quality: {self.jpeg_quality}")
        print(f"[CAPTURE] Press Ctrl+C to stop")
        print("-" * 60)
        
        self.running = True
        frame_count = 0
        last_report_time = time.time()
        frames_since_report = 0
        frame_interval = 1.0 / self.target_fps
        
        try:
            while self.running:
                start_time = time.time()
                
                ret, frame = self.cap.read()
                if not ret:
                    print("[CAPTURE] ⚠️ Failed to read frame, retrying...")
                    time.sleep(1)
                    continue
                
                # Resize if needed (target 640x480)
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    frame = cv2.resize(frame, (640, int(h * scale)))
                
                # Encode frame as JPEG (much smaller than raw pickle)
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                frame_size_kb = len(frame_base64) / 1024
                
                # Prepare frame data as JSON (compatible with camera_worker)
                frame_data = {
                    "camera_id": self.camera_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "frame_jpeg": frame_base64,  # JPEG base64 instead of pickle
                    "frame_count": frame_count,
                    "width": frame.shape[1],
                    "height": frame.shape[0]
                }
                
                # Publish to Redis channel
                try:
                    subscribers = self.redis_client.publish(channel, json.dumps(frame_data))
                    
                    frame_count += 1
                    frames_since_report += 1
                    
                    # Report stats every second
                    current_time = time.time()
                    if current_time - last_report_time >= 1.0:
                        actual_fps = frames_since_report / (current_time - last_report_time)
                        status = "🟢" if subscribers > 0 else "🔴"
                        print(f"[CAPTURE] {status} Frame {frame_count:5d} | FPS: {actual_fps:4.1f} | Size: {frame_size_kb:5.1f}KB | Subs: {subscribers}")
                        last_report_time = current_time
                        frames_since_report = 0
                    
                except redis.RedisError as e:
                    print(f"[CAPTURE] ❌ Redis error: {e}")
                    time.sleep(1)
                
                # Control FPS
                elapsed = time.time() - start_time
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                
        except KeyboardInterrupt:
            print("\n[CAPTURE] Received stop signal...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop capture and cleanup"""
        self.running = False
        if self.cap:
            self.cap.release()
            print("[CAPTURE] ✅ Camera released")
        if self.redis_client:
            self.redis_client.close()
            print("[CAPTURE] ✅ Redis connection closed")
        print("[CAPTURE] Service stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Native Windows camera capture service for indoor-duration-v1 (JPEG optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture from webcam (index 0) for camera UUID abc-123
  python camera_capture_service.py --camera-id abc-123 --camera-index 0
  
  # Use different Redis URL
  python camera_capture_service.py --camera-id abc-123 --camera-index 0 --redis-url redis://localhost:6379
  
  # Capture from second webcam
  python camera_capture_service.py --camera-id xyz-789 --camera-index 1
        """
    )
    
    parser.add_argument(
        "--camera-id",
        required=True,
        help="Camera UUID from database (from API: GET /api/v1/cameras)"
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Camera index (0 for first webcam, 1 for second, etc.)"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis URL (default: redis://localhost:6379)"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=8,
        help="Target FPS (default: 8, lower = less CPU)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Indoor Duration - Camera Capture Service (JPEG)")
    print("=" * 60)
    print(f"Camera ID:    {args.camera_id}")
    print(f"Camera Index: {args.camera_index}")
    print(f"Redis URL:    {args.redis_url}")
    print(f"Target FPS:   {args.fps}")
    print("=" * 60)
    
    service = CameraCaptureService(
        camera_id=args.camera_id,
        camera_index=args.camera_index,
        redis_url=args.redis_url
    )
    service.target_fps = args.fps
    
    service.start()


if __name__ == "__main__":
    main()
