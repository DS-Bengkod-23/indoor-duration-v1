"""Camera Model - Defines cameras and their configurations"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Camera(Base):
    """
    Camera table - stores camera configurations and RTSP URLs
    Each camera belongs to one room
    """
    __tablename__ = "cameras"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Camera Information
    name = Column(String(100), nullable=False, unique=True, index=True)  # e.g., "CAM_0", "Perpustakaan_Cam1"
    rtsp_url = Column(String(500), nullable=False)  # RTSP stream URL or camera index
    
    # Room Reference
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    
    # Camera Configuration
    camera_index = Column(Integer, nullable=True)  # For local cameras (0, 1, 2, etc.)
    fps = Column(Integer, default=30)
    resolution_width = Column(Integer, default=640)
    resolution_height = Column(Integer, default=480)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    room = relationship("Room", back_populates="cameras")
    durations = relationship("Duration", back_populates="camera")
    
    def __repr__(self):
        return f"<Camera(name='{self.name}', room='{self.room.name if self.room else 'N/A'}')>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "name": self.name,
            "rtsp_url": self.rtsp_url,
            "room_id": str(self.room_id),
            "room_name": self.room.name if self.room else None,
            "is_active": self.is_active,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
