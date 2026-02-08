"""Person Model - Stores registered users"""
from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Person(Base):
    """
    Person table - stores registered users (students/staff)
    Each person has a unique ID and can have multiple duration sessions
    """
    __tablename__ = "persons"
    
    # Primary Key - UUID for global uniqueness
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User Information
    name = Column(String(255), nullable=False, index=True)
    nim_nip = Column(String(50), unique=True, nullable=False, index=True)
    
    # Photo & Embedding
    photo_path = Column(String(500))  # Path to uploaded photo
    embedding_id = Column(String(100), unique=True)  # Reference to Qdrant vector ID
    
    # Metadata
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    durations = relationship("Duration", back_populates="person", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Person(name='{self.name}', nim_nip='{self.nim_nip}')>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "name": self.name,
            "nim_nip": self.nim_nip,
            "photo_path": self.photo_path,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
