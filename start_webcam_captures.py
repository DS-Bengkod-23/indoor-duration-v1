"""
Start All USB Webcam Capture Services
Reads camera configuration from .env and starts capture services for all USB webcams

Usage:
    python start_webcam_captures.py
    
Requirements:
    - Redis must be running (docker-compose up redis)
    - Camera UUIDs must be configured in .env file
"""
import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_usb_cameras():
    """
    Get list of USB webcams configured in .env
    Returns list of camera configs
    """
    cameras = []
    
    # Read camera configuration from environment
    for i in range(1, 10):  # Support up to 9 cameras
        camera_id = os.environ.get(f"CAMERA_ID_{i}", "").strip()
        camera_type = os.environ.get(f"CAMERA_{i}_TYPE", "").lower().strip()
        camera_index = os.environ.get(f"CAMERA_{i}_INDEX", str(i-1)).strip()
        
        # Skip empty camera IDs
        if not camera_id:
            continue
            
        # Only process USB cameras
        if camera_type == "usb":
            cameras.append({
                "id": camera_id,
                "index": int(camera_index),
                "name": f"Camera {i}"
            })
    
    return cameras


def start_capture_service(camera_id: str, camera_index: int, camera_name: str):
    """Start a capture service for a USB webcam"""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    
    cmd = [
        sys.executable,  # Use same Python interpreter
        "camera_capture_service.py",
        "--camera-id", camera_id,
        "--camera-index", str(camera_index),
        "--redis-url", redis_url
    ]
    
    print(f"\n{'='*60}")
    print(f"Starting {camera_name}")
    print(f"  UUID:  {camera_id}")
    print(f"  Index: {camera_index}")
    print(f"{'='*60}")
    
    # Start subprocess
    process = subprocess.Popen(
        cmd,
        stdout=sys.stdout,  # Direct output to main stdout
        stderr=sys.stderr,  # Direct errors to main stderr
    )
    
    return process


def main():
    print("\n" + "="*60)
    print("  Indoor Duration - USB Webcam Capture Manager")
    print("="*60)
    
    # Check if camera_capture_service.py exists
    if not Path("camera_capture_service.py").exists():
        print("[ERROR] camera_capture_service.py not found!")
        print("        Make sure you're running from the project root directory")
        sys.exit(1)
    
    # Get configured USB cameras
    cameras = get_usb_cameras()
    
    if not cameras:
        print("\n[WARNING] No USB cameras configured in .env")
        print("")
        print("To configure USB cameras, add to your .env file:")
        print("  CAMERA_ID_1=your-camera-uuid-here")
        print("  CAMERA_1_TYPE=usb")
        print("  CAMERA_1_INDEX=0")
        print("")
        print("For multiple cameras:")
        print("  CAMERA_ID_2=second-camera-uuid")
        print("  CAMERA_2_TYPE=usb")
        print("  CAMERA_2_INDEX=1")
        sys.exit(1)
    
    print(f"\nFound {len(cameras)} USB webcam(s) to start:")
    for cam in cameras:
        print(f"  - {cam['name']}: Index {cam['index']} -> {cam['id'][:8]}...")
    
    print("\n[INFO] Starting capture services...")
    print("[INFO] Press Ctrl+C to stop all captures\n")
    
    # Start all capture services
    processes = []
    for cam in cameras:
        proc = start_capture_service(cam['id'], cam['index'], cam['name'])
        processes.append((cam['name'], proc))
        time.sleep(1)  # Wait for camera to initialize
    
    # Wait for all processes
    try:
        while True:
            # Check if any process died
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n[WARNING] {name} exited with code {proc.returncode}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopping all capture services...")
        for name, proc in processes:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"  Stopped {name}")
        
        print("\n[INFO] All capture services stopped")


if __name__ == "__main__":
    main()
