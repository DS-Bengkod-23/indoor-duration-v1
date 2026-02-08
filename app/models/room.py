"""Room Model - Defines physical rooms"""
from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Room(Base):
    """
    Room table - defines physical rooms being monitored
    Each room can have multiple cameras
    """
    __tablename__ = "rooms"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Room Information
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    cameras = relationship("Camera", back_populates="room", cascade="all, delete-orphan")
    durations = relationship("Duration", back_populates="room")
    
    def __repr__(self):
        return f"<Room(name='{self.name}')>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "camera_count": len(self.cameras) if self.cameras else 0
        }
