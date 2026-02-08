"""Duration Schemas - Session tracking"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import datetime
from uuid import UUID


class DurationBase(BaseModel):
    """Base duration schema"""
    track_id: str = Field(..., description="Tracking ID from camera")
    room_id: UUID = Field(..., description="Room UUID")
    camera_id: UUID = Field(..., description="Camera UUID")
    
    @field_serializer('room_id', 'camera_id')
    def serialize_uuids(self, v: UUID) -> str:
        return str(v) if v else None


class DurationCreate(DurationBase):
    """Schema for creating duration record"""
    person_id: Optional[UUID] = None
    check_in: datetime
    confidence: Optional[float] = 0.0
    status: str = "UNKNOWN"
    guest_label: Optional[str] = None
    
    @field_serializer('person_id')
    def serialize_person_id(self, v: UUID) -> str:
        return str(v) if v else None


class DurationUpdate(BaseModel):
    """Schema for updating duration record"""
    person_id: Optional[str] = None
    check_out: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    confidence: Optional[float] = None
    status: Optional[str] = None


class DurationResponse(BaseModel):
    """Schema for duration response"""
    id: UUID
    track_id: str
    room_id: UUID
    camera_id: UUID
    person_id: Optional[UUID] = None
    person_name: Optional[str] = None
    check_in: datetime
    check_out: Optional[datetime] = None
    duration_seconds: int
    confidence: float
    status: str
    is_guest: bool = False
    guest_label: Optional[str] = None
    snapshot_path: Optional[str] = None
    created_at: datetime
    
    @field_serializer('id', 'room_id', 'camera_id', 'person_id')
    def serialize_uuids(self, v: UUID) -> str:
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class ActiveDurationResponse(BaseModel):
    """Response for currently active sessions"""
    person_id: Optional[UUID] = None
    person_name: str
    nim_nip: Optional[str] = None
    room_name: str
    camera_name: str
    check_in: datetime
    current_duration_seconds: int
    confidence: float
    is_guest: bool
    
    @field_serializer('person_id')
    def serialize_person_id(self, v: UUID) -> str:
        return str(v) if v else None


class DurationStatsResponse(BaseModel):
    """Statistics for a person's durations"""
    person_id: Optional[UUID] = None
    person_name: str
    total_duration_seconds: int
    session_count: int
    current_duration_seconds: Optional[int] = None
    current_room: Optional[str] = None
    is_currently_present: bool
    
    @field_serializer('person_id')
    def serialize_person_id(self, v: UUID) -> str:
        return str(v) if v else None
