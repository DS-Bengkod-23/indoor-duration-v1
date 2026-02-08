"""Duration Model - Tracks presence sessions"""
from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Index, column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Duration(Base):
    """
    Duration table - tracks presence sessions for both known and unknown persons
    Key feature: person_id is nullable to support unknown person tracking
    """
    __tablename__ = "durations"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Person Reference (NULLABLE - for unknown persons)
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL"), 
                      nullable=True, index=True)
    
    # Tracking Information
    track_id = Column(String(100), nullable=False, index=True)  # Camera tracking ID (e.g., "CAM_0_T1")
    
    # Location Information
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    
    # Time Tracking
    check_in = Column(DateTime, nullable=False, index=True)
    check_out = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    
    # Recognition Information
    confidence = Column(Float, default=0.0)  # Recognition confidence (0-1)
    status = Column(String(20), default="UNKNOWN")  # INDOOR, OUTDOOR, UNKNOWN, PENDING
    
    # Guest/Unknown handling
    is_guest = Column(String(10), default="Y")  # Y=unknown/guest, N=recognized
    guest_label = Column(String(50), nullable=True)  # e.g., "Guest-1", "Guest-2"
    
    # Snapshot for verification
    snapshot_path = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    person = relationship("Person", back_populates="durations")
    room = relationship("Room", back_populates="durations")
    camera = relationship("Camera", back_populates="durations")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_duration_track', 'track_id', 'camera_id'),
        Index('idx_duration_time', 'check_in', 'check_out'),
        Index('idx_duration_active', 'check_out', postgresql_where=(column('check_out').is_(None))),
    )
    
    def __repr__(self):
        person_name = self.person.name if self.person else self.guest_label or "Unknown"
        return f"<Duration(person='{person_name}', room='{self.room_id}', duration={self.duration_seconds}s)>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "person_id": str(self.person_id) if self.person_id else None,
            "person_name": self.person.name if self.person else self.guest_label,
            "track_id": self.track_id,
            "room_id": str(self.room_id),
            "camera_id": str(self.camera_id),
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "duration_seconds": self.duration_seconds,
            "confidence": self.confidence,
            "status": self.status,
            "is_guest": self.is_guest,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
