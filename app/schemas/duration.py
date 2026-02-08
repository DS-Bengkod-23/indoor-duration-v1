"""Duration Schemas - Session tracking"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DurationBase(BaseModel):
    """Base duration schema"""
    track_id: str = Field(..., description="Tracking ID from camera")
    room_id: str = Field(..., description="Room UUID")
    camera_id: str = Field(..., description="Camera UUID")


class DurationCreate(DurationBase):
    """Schema for creating duration record"""
    person_id: Optional[str] = None
    check_in: datetime
    confidence: Optional[float] = 0.0
    status: str = "UNKNOWN"
    guest_label: Optional[str] = None


class DurationUpdate(BaseModel):
    """Schema for updating duration record"""
    person_id: Optional[str] = None
    check_out: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    confidence: Optional[float] = None
    status: Optional[str] = None


class DurationResponse(DurationBase):
    """Schema for duration response"""
    id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    check_in: datetime
    check_out: Optional[datetime] = None
    duration_seconds: int
    confidence: float
    status: str
    is_guest: str
    guest_label: Optional[str] = None
    snapshot_path: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ActiveDurationResponse(BaseModel):
    """Response for currently active sessions"""
    person_id: Optional[str] = None
    person_name: str
    nim_nip: Optional[str] = None
    room_name: str
    camera_name: str
    check_in: datetime
    current_duration_seconds: int
    confidence: float
    is_guest: bool


class DurationStatsResponse(BaseModel):
    """Statistics for a person's durations"""
    person_id: Optional[str] = None
    person_name: str
    total_duration_seconds: int
    session_count: int
    current_duration_seconds: Optional[int] = None
    current_room: Optional[str] = None
    is_currently_present: bool
