"""Cameras Endpoints - Camera and room management"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_db
from app.services.camera_service import CameraService
from app.schemas.camera import (
    CameraCreate, CameraUpdate, CameraResponse,
    RoomCreate, RoomResponse, CameraStreamResponse
)
from app.schemas.response import StandardResponse

router = APIRouter()


# ========== ROOM ENDPOINTS ==========

@router.post(
    "/rooms",
    response_model=StandardResponse[RoomResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Room"
)
def create_room(room_data: RoomCreate, db: Session = Depends(get_db)):
    """Create new room"""
    service = CameraService(db)
    
    # Check if room already exists
    existing = service.get_room_by_name(room_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Room '{room_data.name}' already exists"
        )
    
    room = service.create_room(room_data)
    return StandardResponse(
        success=True,
        message=f"Successfully created room '{room.name}'",
        data=RoomResponse.from_orm(room)
    )


@router.get(
    "/rooms",
    response_model=StandardResponse[List[RoomResponse]],
    summary="Get All Rooms"
)
def get_rooms(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get list of all rooms"""
    service = CameraService(db)
    rooms = service.get_all_rooms(is_active=is_active)
    
    return StandardResponse(
        success=True,
        message=f"Found {len(rooms)} rooms",
        data=[RoomResponse.from_orm(r) for r in rooms]
    )


@router.get(
    "/rooms/{room_id}",
    response_model=StandardResponse[RoomResponse],
    summary="Get Room Detail"
)
def get_room(room_id: str, db: Session = Depends(get_db)):
    """Get room by ID"""
    service = CameraService(db)
    room = service.get_room_by_id(room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room with ID '{room_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully retrieved room",
        data=RoomResponse.from_orm(room)
    )


# ========== CAMERA ENDPOINTS ==========

@router.post(
    "/",
    response_model=StandardResponse[CameraResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Camera",
    description="""
    Register a new camera in the system.
    
    **Required:**
    - name: Unique camera name (e.g., "CAM_0", "Perpustakaan_Cam1")
    - rtsp_url: RTSP stream URL or local camera index (e.g., "0", "1", "rtsp://...")
    - room_id: UUID of the room where camera is located
    
    **Optional:**
    - camera_index: For local cameras (0, 1, 2, etc.)
    - fps: Frame rate (default: 30)
    - resolution: Width and height (default: 640x480)
    """
)
def create_camera(camera_data: CameraCreate, db: Session = Depends(get_db)):
    """Create new camera"""
    service = CameraService(db)
    
    # Check if camera name already exists
    existing = service.get_camera_by_name(camera_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Camera '{camera_data.name}' already exists"
        )
    
    # Verify room exists
    room = service.get_room_by_id(camera_data.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room with ID '{camera_data.room_id}' not found"
        )
    
    camera = service.create_camera(camera_data)
    return StandardResponse(
        success=True,
        message=f"Successfully created camera '{camera.name}'",
        data=CameraResponse.from_orm(camera)
    )


@router.get(
    "/",
    response_model=StandardResponse[List[CameraResponse]],
    summary="Get All Cameras",
    description="""
    Get list of all cameras with optional filters.
    
    **Filters:**
    - is_active: Filter by active status
    - room_id: Filter by room
    
    **Returns:** List of cameras with their current online status
    """
)
def get_cameras(
    is_active: Optional[bool] = None,
    room_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of all cameras"""
    service = CameraService(db)
    cameras = service.get_all_cameras(is_active=is_active, room_id=room_id)
    
    return StandardResponse(
        success=True,
        message=f"Found {len(cameras)} cameras",
        data=[CameraResponse.from_orm(c) for c in cameras]
    )


@router.get(
    "/{camera_id}",
    response_model=StandardResponse[CameraResponse],
    summary="Get Camera Detail"
)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    """Get camera by ID"""
    service = CameraService(db)
    camera = service.get_camera_by_id(camera_id)
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully retrieved camera",
        data=CameraResponse.from_orm(camera)
    )


@router.put(
    "/{camera_id}",
    response_model=StandardResponse[CameraResponse],
    summary="Update Camera"
)
def update_camera(
    camera_id: str,
    camera_data: CameraUpdate,
    db: Session = Depends(get_db)
):
    """Update camera configuration"""
    service = CameraService(db)
    camera = service.update_camera(camera_id, camera_data)
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message=f"Successfully updated camera",
        data=CameraResponse.from_orm(camera)
    )


@router.delete(
    "/{camera_id}",
    response_model=StandardResponse[dict],
    summary="Delete Camera"
)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    """Delete camera"""
    service = CameraService(db)
    success = service.delete_camera(camera_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully deleted camera",
        data={"deleted": True}
    )


@router.get(
    "/live/streams",
    response_model=StandardResponse[List[CameraStreamResponse]],
    summary="Get All Live Camera Streams",
    description="""
    Get information about all active camera streams for frontend display.
    
    **Returns:** List of cameras with:
    - Camera ID and name
    - Room name
    - Online status
    - WebSocket URL for live stream
    
    Use the stream_url to connect via WebSocket for real-time video and detection data.
    """
)
def get_live_streams(db: Session = Depends(get_db)):
    """Get all active camera live streams"""
    service = CameraService(db)
    cameras = service.get_all_cameras(is_active=True)
    
    streams = []
    for camera in cameras:
        streams.append(CameraStreamResponse(
            camera_id=str(camera.id),
            camera_name=camera.name,
            room_name=camera.room.name if camera.room else "Unknown",
            is_online=camera.is_online,
            stream_url=f"/api/v1/ws/camera/{camera.id}"
        ))
    
    return StandardResponse(
        success=True,
        message=f"Found {len(streams)} active streams",
        data=streams
    )
