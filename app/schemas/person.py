"""Person Schemas - Request/Response validation"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import datetime
from uuid import UUID


class PersonBase(BaseModel):
    """Base person schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Full name")
    nim_nip: str = Field(..., min_length=1, max_length=50, description="Student/Staff ID")


class PersonCreate(PersonBase):
    """Schema for creating a new person"""
    # Photo will be handled separately as UploadFile
    notes: Optional[str] = None


class PersonUpdate(BaseModel):
    """Schema for updating person information"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    nim_nip: Optional[str] = Field(None, min_length=1, max_length=50)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PersonResponse(PersonBase):
    """Schema for person response"""
    id: UUID
    photo_path: Optional[str] = None
    embedding_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('id')
    def serialize_id(self, v: UUID) -> str:
        return str(v)
    
    class Config:
        from_attributes = True


class PersonDetailResponse(PersonResponse):
    """Extended person response with current location"""
    current_room: Optional[str] = None
    current_camera: Optional[str] = None
    current_duration_seconds: Optional[int] = None
    total_duration_seconds: Optional[int] = None
    session_count: Optional[int] = None


class PersonListResponse(BaseModel):
    """Response for list of persons"""
    total: int
    persons: list[PersonResponse]
