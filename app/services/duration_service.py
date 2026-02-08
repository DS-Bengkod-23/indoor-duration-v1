"""Duration Service - Business logic for presence tracking"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from app.models.duration import Duration
from app.models.person import Person
from app.models.camera import Camera
from app.models.room import Room
from app.schemas.duration import (
    DurationCreate, DurationUpdate, DurationResponse,
    ActiveDurationResponse, DurationStatsResponse
)


class DurationService:
    """Service for managing presence duration tracking"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_duration(self, duration_data: DurationCreate) -> Duration:
        """
        Create new duration record (for both known and unknown persons)
        """
        duration = Duration(
            person_id=UUID(duration_data.person_id) if duration_data.person_id else None,
            track_id=duration_data.track_id,
            room_id=UUID(duration_data.room_id),
            camera_id=UUID(duration_data.camera_id),
            check_in=duration_data.check_in,
            confidence=duration_data.confidence,
            status=duration_data.status,
            is_guest="N" if duration_data.person_id else "Y",
            guest_label=duration_data.guest_label
        )
        
        self.db.add(duration)
        self.db.commit()
        self.db.refresh(duration)
        return duration
    
    def update_duration(self, duration_id: str, duration_data: DurationUpdate) -> Optional[Duration]:
        """Update existing duration record"""
        try:
            duration = self.db.query(Duration).filter(Duration.id == UUID(duration_id)).first()
            if not duration:
                return None
            
            # Update fields
            if duration_data.person_id is not None:
                duration.person_id = UUID(duration_data.person_id) if duration_data.person_id else None
                duration.is_guest = "N" if duration_data.person_id else "Y"
            
            if duration_data.check_out is not None:
                duration.check_out = duration_data.check_out
                
                # Calculate duration
                if duration.check_in and duration.check_out:
                    duration.duration_seconds = int(
                        (duration.check_out - duration.check_in).total_seconds()
                    )
            
            if duration_data.duration_seconds is not None:
                duration.duration_seconds = duration_data.duration_seconds
            
            if duration_data.confidence is not None:
                duration.confidence = duration_data.confidence
            
            if duration_data.status is not None:
                duration.status = duration_data.status
            
            self.db.commit()
            self.db.refresh(duration)
            return duration
            
        except Exception as e:
            print(f"[SERVICE] Error updating duration: {e}")
            self.db.rollback()
            return None
    
    def get_or_create_active_duration(
        self,
        track_id: str,
        camera_id: str,
        room_id: str,
        person_id: Optional[str] = None,
        guest_label: Optional[str] = None,
        confidence: float = 0.0
    ) -> Duration:
        """
        Get existing active duration or create new one
        Used by camera worker to track ongoing sessions
        """
        # Look for active duration with same track_id and camera
        duration = self.db.query(Duration).filter(
            Duration.track_id == track_id,
            Duration.camera_id == UUID(camera_id),
            Duration.check_out.is_(None)
        ).first()
        
        if duration:
            # Update ongoing duration
            duration.duration_seconds = int(
                (datetime.utcnow() - duration.check_in).total_seconds()
            )
            
            # Update person_id if recognized (unknown -> known)
            if person_id and not duration.person_id:
                duration.person_id = UUID(person_id)
                duration.is_guest = "N"
                duration.confidence = confidence
            
            self.db.commit()
            self.db.refresh(duration)
            return duration
        
        # Create new duration
        new_duration = Duration(
            person_id=UUID(person_id) if person_id else None,
            track_id=track_id,
            room_id=UUID(room_id),
            camera_id=UUID(camera_id),
            check_in=datetime.utcnow(),
            confidence=confidence,
            status="INDOOR",
            is_guest="N" if person_id else "Y",
            guest_label=guest_label
        )
        
        self.db.add(new_duration)
        self.db.commit()
        self.db.refresh(new_duration)
        return new_duration
    
    def close_duration(self, track_id: str, camera_id: str) -> Optional[Duration]:
        """Close active duration when person leaves"""
        duration = self.db.query(Duration).filter(
            Duration.track_id == track_id,
            Duration.camera_id == UUID(camera_id),
            Duration.check_out.is_(None)
        ).first()
        
        if duration:
            duration.check_out = datetime.utcnow()
            duration.status = "OUTDOOR"
            duration.duration_seconds = int(
                (duration.check_out - duration.check_in).total_seconds()
            )
            self.db.commit()
            self.db.refresh(duration)
            return duration
        
        return None
    
    def get_active_durations(self) -> List[ActiveDurationResponse]:
        """Get all currently active presence sessions"""
        active_sessions = self.db.query(
            Duration, Person, Room, Camera
        ).outerjoin(
            Person, Duration.person_id == Person.id
        ).join(
            Room, Duration.room_id == Room.id
        ).join(
            Camera, Duration.camera_id == Camera.id
        ).filter(
            Duration.check_out.is_(None)
        ).all()
        
        results = []
        for duration, person, room, camera in active_sessions:
            # Calculate current duration
            current_seconds = int(
                (datetime.utcnow() - duration.check_in).total_seconds()
            )
            
            results.append(ActiveDurationResponse(
                person_id=str(duration.person_id) if duration.person_id else None,
                person_name=person.name if person else duration.guest_label or "Unknown",
                nim_nip=person.nim_nip if person else None,
                room_name=room.name,
                camera_name=camera.name,
                check_in=duration.check_in,
                current_duration_seconds=current_seconds,
                confidence=duration.confidence,
                is_guest=(duration.is_guest == "Y")
            ))
        
        return results
    
    def get_person_statistics(self, person_id: str) -> Optional[DurationStatsResponse]:
        """Get duration statistics for a person"""
        person = self.db.query(Person).filter(Person.id == UUID(person_id)).first()
        if not person:
            return None
        
        # Get total duration and session count
        stats = self.db.query(
            func.sum(Duration.duration_seconds).label("total_duration"),
            func.count(Duration.id).label("session_count")
        ).filter(
            Duration.person_id == UUID(person_id)
        ).first()
        
        # Get current active session
        active = self.db.query(Duration, Room).join(
            Room, Duration.room_id == Room.id
        ).filter(
            Duration.person_id == UUID(person_id),
            Duration.check_out.is_(None)
        ).first()
        
        current_duration = None
        current_room = None
        if active:
            duration, room = active
            current_duration = int(
                (datetime.utcnow() - duration.check_in).total_seconds()
            )
            current_room = room.name
        
        return DurationStatsResponse(
            person_id=str(person.id),
            person_name=person.name,
            total_duration_seconds=int(stats.total_duration) if stats.total_duration else 0,
            session_count=stats.session_count or 0,
            current_duration_seconds=current_duration,
            current_room=current_room,
            is_currently_present=(active is not None)
        )
    
    def assign_duration_to_person(
        self, 
        duration_id: str, 
        person_id: str,
        confidence: float
    ) -> Optional[Duration]:
        """
        Assign unknown duration to a recognized person
        Used when person is identified after being tracked as unknown
        """
        duration = self.db.query(Duration).filter(Duration.id == UUID(duration_id)).first()
        if not duration:
            return None
        
        duration.person_id = UUID(person_id)
        duration.is_guest = "N"
        duration.confidence = confidence
        
        self.db.commit()
        self.db.refresh(duration)
        return duration
    
    def get_durations_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        person_id: Optional[str] = None,
        room_id: Optional[str] = None
    ) -> List[Duration]:
        """Get durations within date range with optional filters"""
        query = self.db.query(Duration).filter(
            Duration.check_in >= start_date,
            Duration.check_in <= end_date
        )
        
        if person_id:
            query = query.filter(Duration.person_id == UUID(person_id))
        
        if room_id:
            query = query.filter(Duration.room_id == UUID(room_id))
        
        return query.order_by(Duration.check_in.desc()).all()
