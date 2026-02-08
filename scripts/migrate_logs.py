"""Migration Script: Import historical logs to PostgreSQL"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime
import re
from app.database import SessionLocal
from app.models import Duration, Camera, Room
from app.services.camera_service import CameraService
import uuid

def parse_log_line(line: str) -> dict:
    """
    Parse log line from old format
    Example: "1. John Doe_A11.2023.12345 | CAM_0 | 10:30:45 → 11:45:30 | Perpustakaan | OUTDOOR"
    """
    try:
        # Extract components using regex
        pattern = r"(\d+)\.\s+([^|]+)\s+\|\s+([^|]+)\s+\|\s+([^→]+)→([^|]+)\|\s+([^|]+)\|\s+(\w+)"
        match = re.match(pattern, line)
        
        if not match:
            return None
        
        index, person_info, camera, time_in, time_out, room, status = match.groups()
        
        # Parse person info
        person_parts = person_info.strip().rsplit("_", 1)
        if len(person_parts) == 2:
            name, nim_nip = person_parts
        else:
            name = person_info.strip()
            nim_nip = None
        
        return {
            "person_name": name.strip(),
            "nim_nip": nim_nip.strip() if nim_nip else None,
            "camera": camera.strip(),
            "time_in": time_in.strip(),
            "time_out": time_out.strip(),
            "room": room.strip(),
            "status": status.strip()
        }
    except Exception as e:
        print(f"Error parsing line: {e}")
        return None


def migrate_logs():
    """Migrate historical logs to PostgreSQL"""
    print("[MIGRATION] Starting log migration...")
    
    db = SessionLocal()
    camera_service = CameraService(db)
    
    # Source directory
    log_dir = Path("logs")
    log_files = list(log_dir.glob("system.log.*"))
    
    if not log_files:
        print(f"[ERROR] No log files found in {log_dir}")
        return
    
    migrated_count = 0
    
    for log_file in log_files:
        print(f"\n[MIGRATION] Processing {log_file.name}...")
        
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                
                # Parse log line
                data = parse_log_line(line)
                if not data:
                    continue
                
                try:
                    # Get or create camera and room
                    camera = camera_service.get_camera_by_name(data["camera"])
                    if not camera:
                        # Create room first
                        room = camera_service.get_or_create_room(data["room"])
                        # Create camera
                        camera = camera_service.get_or_create_camera(
                            name=data["camera"],
                            rtsp_url="0",  # Unknown
                            room_name=data["room"]
                        )
                    
                    # Parse times (assuming same date as log file)
                    log_date = log_file.stem.split(".")[-1]  # e.g., "2026-01-20"
                    
                    check_in_str = f"{log_date} {data['time_in']}"
                    check_out_str = f"{log_date} {data['time_out']}"
                    
                    check_in = datetime.strptime(check_in_str, "%Y-%m-%d %H:%M:%S")
                    
                    if data['time_out'] != "--:--:--":
                        check_out = datetime.strptime(check_out_str, "%Y-%m-%d %H:%M:%S")
                        duration_seconds = int((check_out - check_in).total_seconds())
                    else:
                        check_out = None
                        duration_seconds = 0
                    
                    # Create duration record
                    duration = Duration(
                        id=uuid.uuid4(),
                        person_id=None,  # Will be filled when persons are migrated
                        track_id=f"MIGRATED_{uuid.uuid4().hex[:8]}",
                        room_id=camera.room_id,
                        camera_id=camera.id,
                        check_in=check_in,
                        check_out=check_out,
                        duration_seconds=duration_seconds,
                        confidence=0.0,
                        status=data["status"],
                        is_guest="Y",  # Assume guest until matched
                        guest_label=data["person_name"]
                    )
                    
                    db.add(duration)
                    migrated_count += 1
                    
                    if migrated_count % 100 == 0:
                        db.commit()
                        print(f"  Migrated {migrated_count} records...")
                
                except Exception as e:
                    print(f"❌ Error migrating record: {e}")
                    continue
    
    # Final commit
    db.commit()
    db.close()
    
    print(f"\n[MIGRATION] Completed! Migrated {migrated_count} duration records.")


if __name__ == "__main__":
    migrate_logs()
