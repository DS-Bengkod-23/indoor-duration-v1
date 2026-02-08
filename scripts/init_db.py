"""Initialize Database with Sample Data"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models import Person, Room, Camera
from app.services.camera_service import CameraService
import uuid

def init_database():
    """Initialize database with sample rooms and cameras"""
    print("[INIT] Creating database tables...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("[INIT] Tables created successfully")
    
    # Create session
    db = SessionLocal()
    camera_service = CameraService(db)
    
    try:
        # Check if already initialized
        existing_rooms = camera_service.get_all_rooms()
        if existing_rooms:
            print("[INIT] Database already initialized. Skipping...")
            return
        
        print("[INIT] Adding sample rooms and cameras...")
        
        # Create sample rooms
        rooms = [
            {"name": "Ruang Dosen", "description": "Ruangan untuk dosen"},
            {"name": "Perpustakaan", "description": "Ruang perpustakaan utama"},
            {"name": "Ruang Kuliah", "description": "Ruangan untuk kuliah"},
            {"name": "Lab Komputer", "description": "Laboratorium komputer"},
        ]
        
        created_rooms = []
        for room_data in rooms:
            room = Room(
                id=uuid.uuid4(),
                name=room_data["name"],
                description=room_data["description"],
                is_active=True
            )
            db.add(room)
            created_rooms.append(room)
            print(f"  ✅ Created room: {room.name}")
        
        db.commit()
        
        # Create sample cameras
        cameras = [
            {"name": "CAM_0", "rtsp_url": "0", "room": created_rooms[0], "index": 0},
            {"name": "CAM_1", "rtsp_url": "http://192.168.41.141:8080/video", "room": created_rooms[0], "index": None},
        ]
        
        for cam_data in cameras:
            camera = Camera(
                id=uuid.uuid4(),
                name=cam_data["name"],
                rtsp_url=cam_data["rtsp_url"],
                room_id=cam_data["room"].id,
                camera_index=cam_data["index"],
                fps=30,
                resolution_width=640,
                resolution_height=480,
                is_active=True,
                is_online=False
            )
            db.add(camera)
            print(f"  ✅ Created camera: {camera.name} in {cam_data['room'].name}")
            print(f"     Camera ID: {camera.id}")
        
        db.commit()
        
        print("\n[INIT] Database initialized successfully!")
        print("\n[INFO] Copy these Camera IDs to your .env file:")
        print(f"CAMERA_ID_1={cameras[0].id if hasattr(cameras[0], 'id') else 'N/A'}")
        print(f"CAMERA_ID_2={cameras[1].id if len(cameras) > 1 and hasattr(cameras[1], 'id') else 'N/A'}")
        
    except Exception as e:
        print(f"[ERROR] Failed to initialize database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
