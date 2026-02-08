"""Camera Service - Business logic for camera management"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from app.models.camera import Camera
from app.models.room import Room
from app.schemas.camera import CameraCreate, CameraUpdate, RoomCreate


class CameraService:
    """Service for managing cameras and rooms"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========== ROOM OPERATIONS ==========
    
    def create_room(self, room_data: RoomCreate) -> Room:
        """Create new room"""
        room = Room(
            name=room_data.name,
            description=room_data.description
        )
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room
    
    def get_room_by_id(self, room_id: str) -> Optional[Room]:
        """Get room by UUID"""
        try:
            return self.db.query(Room).filter(Room.id == UUID(room_id)).first()
        except Exception as e:
            print(f"[SERVICE] Error getting room: {e}")
            return None
    
    def get_room_by_name(self, name: str) -> Optional[Room]:
        """Get room by name"""
        return self.db.query(Room).filter(Room.name == name).first()
    
    def get_all_rooms(self, is_active: Optional[bool] = None) -> List[Room]:
        """Get all rooms"""
        query = self.db.query(Room)
        
        if is_active is not None:
            query = query.filter(Room.is_active == is_active)
        
        return query.order_by(Room.name).all()
    
    def get_or_create_room(self, name: str, description: str = None) -> Room:
        """Get existing room or create if not exists"""
        room = self.get_room_by_name(name)
        if room:
            return room
        
        return self.create_room(RoomCreate(name=name, description=description))
    
    # ========== CAMERA OPERATIONS ==========
    
    def create_camera(self, camera_data: CameraCreate) -> Camera:
        """Create new camera"""
        camera = Camera(
            name=camera_data.name,
            rtsp_url=camera_data.rtsp_url,
            room_id=UUID(camera_data.room_id),
            camera_index=camera_data.camera_index,
            fps=camera_data.fps,
            resolution_width=camera_data.resolution_width,
            resolution_height=camera_data.resolution_height
        )
        
        self.db.add(camera)
        self.db.commit()
        self.db.refresh(camera)
        return camera
    
    def get_camera_by_id(self, camera_id: str) -> Optional[Camera]:
        """Get camera by UUID"""
        try:
            return self.db.query(Camera).filter(Camera.id == UUID(camera_id)).first()
        except Exception as e:
            print(f"[SERVICE] Error getting camera: {e}")
            return None
    
    def get_camera_by_name(self, name: str) -> Optional[Camera]:
        """Get camera by name"""
        return self.db.query(Camera).filter(Camera.name == name).first()
    
    def get_all_cameras(
        self, 
        is_active: Optional[bool] = None,
        room_id: Optional[str] = None
    ) -> List[Camera]:
        """Get all cameras with optional filters"""
        query = self.db.query(Camera)
        
        if is_active is not None:
            query = query.filter(Camera.is_active == is_active)
        
        if room_id:
            query = query.filter(Camera.room_id == UUID(room_id))
        
        return query.order_by(Camera.name).all()
    
    def update_camera(self, camera_id: str, camera_data: CameraUpdate) -> Optional[Camera]:
        """Update camera configuration"""
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            return None
        
        if camera_data.name is not None:
            camera.name = camera_data.name
        
        if camera_data.rtsp_url is not None:
            camera.rtsp_url = camera_data.rtsp_url
        
        if camera_data.room_id is not None:
            camera.room_id = UUID(camera_data.room_id)
        
        if camera_data.is_active is not None:
            camera.is_active = camera_data.is_active
        
        self.db.commit()
        self.db.refresh(camera)
        return camera
    
    def update_camera_status(
        self, 
        camera_id: str, 
        is_online: bool,
        last_seen: datetime = None
    ) -> Optional[Camera]:
        """Update camera online status"""
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            return None
        
        camera.is_online = is_online
        camera.last_seen = last_seen or datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(camera)
        return camera
    
    def delete_camera(self, camera_id: str) -> bool:
        """Delete camera"""
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            return False
        
        self.db.delete(camera)
        self.db.commit()
        return True
    
    def get_or_create_camera(
        self,
        name: str,
        rtsp_url: str,
        room_name: str,
        camera_index: int = None
    ) -> Camera:
        """Get existing camera or create if not exists"""
        camera = self.get_camera_by_name(name)
        if camera:
            return camera
        
        # Get or create room
        room = self.get_or_create_room(room_name)
        
        # Create camera
        camera_data = CameraCreate(
            name=name,
            rtsp_url=rtsp_url,
            room_id=str(room.id),
            camera_index=camera_index
        )
        
        return self.create_camera(camera_data)
