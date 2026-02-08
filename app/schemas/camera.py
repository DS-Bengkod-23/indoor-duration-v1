"""Camera & Room Schemas"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import datetime
from uuid import UUID


class RoomBase(BaseModel):
    """Base room schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class RoomCreate(RoomBase):
    """Schema for creating room"""
    pass


class RoomResponse(RoomBase):
    """Schema for room response"""
    id: UUID
    is_active: bool
    camera_count: int = 0
    
    @field_serializer('id')
    def serialize_id(self, v: UUID) -> str:
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class CameraBase(BaseModel):
    """Base camera schema"""
    name: str = Field(..., min_length=1, max_length=100)
    rtsp_url: str = Field(..., description="RTSP URL or camera index (0, 1, 2)")
    room_id: str  # Keep as str for input (accepts both str and UUID)


class CameraCreate(CameraBase):
    """Schema for creating camera"""
    camera_index: Optional[int] = None
    fps: int = 30
    resolution_width: int = 640
    resolution_height: int = 480


class CameraUpdate(BaseModel):
    """Schema for updating camera"""
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    room_id: Optional[str] = None
    is_active: Optional[bool] = None


class CameraResponse(BaseModel):
    """Schema for camera response"""
    id: UUID
    name: str
    rtsp_url: str
    room_id: UUID
    room_name: Optional[str] = None
    is_active: bool
    is_online: bool
    last_seen: Optional[datetime] = None
    created_at: datetime
    
    @field_serializer('id', 'room_id')
    def serialize_uuids(self, v: UUID) -> str:
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class CameraStreamResponse(BaseModel):
    """Response for camera stream info"""
    camera_id: str
    camera_name: str
    room_name: str
    is_online: bool
    stream_url: str  # WebSocket URL for live stream


class LiveCameraData(BaseModel):
    """Real-time data from camera"""
    camera_id: str
    camera_name: str
    room_name: str
    timestamp: datetime
    detections: list[dict]  # List of detected persons with bounding boxes
    frame_base64: Optional[str] = None  # Optional frame data
