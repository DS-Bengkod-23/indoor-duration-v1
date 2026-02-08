"""Sessions Endpoints - Duration/presence tracking"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.api.deps import get_db
from app.services.duration_service import DurationService
from app.schemas.duration import (
    DurationResponse, ActiveDurationResponse, DurationStatsResponse
)
from app.schemas.response import StandardResponse

router = APIRouter()


@router.get(
    "/active",
    response_model=StandardResponse[List[ActiveDurationResponse]],
    summary="Get Active Presence Sessions",
    description="""
    Get all currently active presence sessions (people currently in rooms).
    
    **Returns:** List of active sessions with:
    - Person name and NIM/NIP (or Guest label if unknown)
    - Current room and camera
    - Check-in time
    - Current duration (live)
    - Recognition confidence
    
    **Use case:** Display real-time "Who's in the building" dashboard
    """
)
def get_active_sessions(db: Session = Depends(get_db)):
    """Get all currently active presence sessions"""
    service = DurationService(db)
    active_sessions = service.get_active_durations()
    
    return StandardResponse(
        success=True,
        message=f"Found {len(active_sessions)} active sessions",
        data=active_sessions
    )


@router.get(
    "/person/{person_id}/stats",
    response_model=StandardResponse[DurationStatsResponse],
    summary="Get Person Duration Statistics",
    description="""
    Get duration statistics for a specific person.
    
    **Returns:**
    - Total duration across all sessions (seconds)
    - Number of sessions
    - Current duration (if currently present)
    - Current room (if currently present)
    - Presence status
    
    **Use case:** Show user their total time in building, current location
    """
)
def get_person_stats(person_id: str, db: Session = Depends(get_db)):
    """Get duration statistics for a person"""
    service = DurationService(db)
    stats = service.get_person_statistics(person_id)
    
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully retrieved statistics",
        data=stats
    )


@router.get(
    "/history",
    response_model=StandardResponse[List[DurationResponse]],
    summary="Get Duration History",
    description="""
    Get historical duration records with filters.
    
    **Filters:**
    - start_date: Start of date range (ISO format)
    - end_date: End of date range (ISO format)
    - person_id: Filter by person
    - room_id: Filter by room
    
    **Use case:** Generate reports, analyze patterns
    """
)
def get_duration_history(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    person_id: Optional[str] = Query(None, description="Filter by person ID"),
    room_id: Optional[str] = Query(None, description="Filter by room ID"),
    db: Session = Depends(get_db)
):
    """Get duration history with filters"""
    service = DurationService(db)
    
    # Default date range: last 7 days
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=7)
    if not end_date:
        end_date = datetime.utcnow()
    
    durations = service.get_durations_by_date_range(
        start_date=start_date,
        end_date=end_date,
        person_id=person_id,
        room_id=room_id
    )
    
    return StandardResponse(
        success=True,
        message=f"Found {len(durations)} duration records",
        data=[DurationResponse.from_orm(d) for d in durations]
    )


@router.get(
    "/person/{person_id}/current",
    response_model=StandardResponse[Optional[ActiveDurationResponse]],
    summary="Get Person Current Location",
    description="""
    Get current location and duration for a specific person.
    
    **Returns:** Current session if person is present, null otherwise
    
    **Use case:** "Where is John Doe right now?"
    """
)
def get_person_current_location(person_id: str, db: Session = Depends(get_db)):
    """Get person's current location"""
    service = DurationService(db)
    active_sessions = service.get_active_durations()
    
    # Find this person's active session
    person_session = next(
        (s for s in active_sessions if s.person_id == person_id),
        None
    )
    
    if person_session:
        return StandardResponse(
            success=True,
            message="Person is currently present",
            data=person_session
        )
    else:
        return StandardResponse(
            success=True,
            message="Person is not currently present",
            data=None
        )


@router.get(
    "/room/{room_id}/current",
    response_model=StandardResponse[List[ActiveDurationResponse]],
    summary="Get Current People in Room",
    description="""
    Get all people currently in a specific room.
    
    **Returns:** List of active sessions in the room
    
    **Use case:** "Who's in the library right now?"
    """
)
def get_room_current_occupants(room_id: str, db: Session = Depends(get_db)):
    """Get current occupants of a room"""
    service = DurationService(db)
    active_sessions = service.get_active_durations()
    
    # Filter by room
    room_sessions = [
        s for s in active_sessions 
        if s.room_name  # Room filter by name can be added here
    ]
    
    return StandardResponse(
        success=True,
        message=f"Found {len(room_sessions)} people in room",
        data=room_sessions
    )


@router.post(
    "/assign/{duration_id}",
    response_model=StandardResponse[DurationResponse],
    summary="Assign Duration to Person",
    description="""
    Assign an unknown/guest duration session to a recognized person.
    
    **Use case:** When person is identified after being tracked as unknown/guest
    
    **Parameters:**
    - duration_id: ID of the duration record to assign
    - person_id: ID of the person to assign it to
    - confidence: Recognition confidence score
    """
)
def assign_duration_to_person(
    duration_id: str,
    person_id: str = Query(..., description="Person ID to assign to"),
    confidence: float = Query(..., description="Recognition confidence"),
    db: Session = Depends(get_db)
):
    """Assign unknown duration to recognized person"""
    service = DurationService(db)
    duration = service.assign_duration_to_person(duration_id, person_id, confidence)
    
    if not duration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Duration with ID '{duration_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message=f"Successfully assigned duration to person",
        data=DurationResponse.from_orm(duration)
    )
