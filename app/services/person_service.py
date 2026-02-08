"""Person Service - Business logic for person management"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import shutil
from uuid import UUID
import numpy as np

from app.models.person import Person
from app.models.duration import Duration
from app.schemas.person import PersonCreate, PersonUpdate, PersonDetailResponse
from app.services.embedding_service import EmbeddingService
from app.config import settings


class PersonService:
    """Service for managing persons (students/staff)"""
    
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
    
    def create_person(
        self, 
        person_data: PersonCreate, 
        photo_path: str,
        embedding: np.ndarray
    ) -> Person:
        """
        Create new person with photo and face embedding
        
        Args:
            person_data: Person information (name, nim_nip)
            photo_path: Path to saved photo
            embedding: Face embedding vector
            
        Returns:
            Created Person object
        """
        # Create person in PostgreSQL
        person = Person(
            name=person_data.name,
            nim_nip=person_data.nim_nip,
            photo_path=photo_path,
            notes=person_data.notes
        )
        
        self.db.add(person)
        self.db.flush()  # Get person.id before committing
        
        # Add embedding to Qdrant
        embedding_id = self.embedding_service.add_embedding(
            embedding=embedding,
            person_id=str(person.id),
            person_name=person.name,
            nim_nip=person.nim_nip
        )
        
        # Update person with embedding_id
        person.embedding_id = embedding_id
        self.db.commit()
        self.db.refresh(person)
        
        return person
    
    def get_person_by_id(self, person_id: str) -> Optional[Person]:
        """Get person by UUID"""
        try:
            return self.db.query(Person).filter(Person.id == UUID(person_id)).first()
        except Exception as e:
            print(f"[SERVICE] Error getting person: {e}")
            return None
    
    def get_person_by_nim_nip(self, nim_nip: str) -> Optional[Person]:
        """Get person by NIM/NIP"""
        return self.db.query(Person).filter(Person.nim_nip == nim_nip).first()
    
    def get_all_persons(
        self, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> tuple[List[Person], int]:
        """Get list of persons with pagination and search"""
        query = self.db.query(Person)
        
        # Filter by active status
        if is_active is not None:
            query = query.filter(Person.is_active == is_active)
        
        # Search by name or nim_nip
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Person.name.ilike(search_term)) |
                (Person.nim_nip.ilike(search_term))
            )
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        persons = query.order_by(Person.name).offset(skip).limit(limit).all()
        
        return persons, total
    
    def update_person(self, person_id: str, person_data: PersonUpdate) -> Optional[Person]:
        """Update person information"""
        person = self.get_person_by_id(person_id)
        if not person:
            return None
        
        # Update fields
        if person_data.name is not None:
            person.name = person_data.name
            # Update Qdrant metadata
            if person.embedding_id:
                self.embedding_service.update_embedding_metadata(
                    embedding_id=person.embedding_id,
                    person_name=person_data.name
                )
        
        if person_data.nim_nip is not None:
            person.nim_nip = person_data.nim_nip
        
        if person_data.is_active is not None:
            person.is_active = person_data.is_active
            # Update Qdrant metadata
            if person.embedding_id:
                self.embedding_service.update_embedding_metadata(
                    embedding_id=person.embedding_id,
                    is_active=person_data.is_active
                )
        
        if person_data.notes is not None:
            person.notes = person_data.notes
        
        self.db.commit()
        self.db.refresh(person)
        return person
    
    def delete_person(self, person_id: str) -> bool:
        """Delete person and their embedding"""
        person = self.get_person_by_id(person_id)
        if not person:
            return False
        
        # Delete embedding from Qdrant
        if person.embedding_id:
            self.embedding_service.delete_embedding(person.embedding_id)
        
        # Delete photo file
        if person.photo_path and os.path.exists(person.photo_path):
            try:
                os.remove(person.photo_path)
            except Exception as e:
                print(f"[SERVICE] Error deleting photo: {e}")
        
        # Delete from database
        self.db.delete(person)
        self.db.commit()
        return True
    
    def get_person_detail(self, person_id: str) -> Optional[PersonDetailResponse]:
        """Get person with current location and duration statistics"""
        person = self.get_person_by_id(person_id)
        if not person:
            return None
        
        # Get current active session
        active_session = self.db.query(Duration).filter(
            Duration.person_id == UUID(person_id),
            Duration.check_out.is_(None)
        ).first()
        
        # Get total duration and session count
        stats = self.db.query(
            func.sum(Duration.duration_seconds).label("total_duration"),
            func.count(Duration.id).label("session_count")
        ).filter(
            Duration.person_id == UUID(person_id)
        ).first()
        
        # Build response
        detail = PersonDetailResponse(
            id=str(person.id),
            name=person.name,
            nim_nip=person.nim_nip,
            photo_path=person.photo_path,
            embedding_id=person.embedding_id,
            is_active=person.is_active,
            created_at=person.created_at,
            updated_at=person.updated_at,
            current_room=active_session.room.name if active_session and active_session.room else None,
            current_camera=active_session.camera.name if active_session and active_session.camera else None,
            current_duration_seconds=active_session.duration_seconds if active_session else None,
            total_duration_seconds=int(stats.total_duration) if stats.total_duration else 0,
            session_count=stats.session_count or 0
        )
        
        return detail
    
    def search_person_by_embedding(
        self, 
        embedding: np.ndarray,
        threshold: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person by face embedding
        Returns best match if above threshold
        """
        matches = self.embedding_service.search_similar(
            embedding=embedding,
            limit=1,
            threshold=threshold or settings.FACE_MATCH_THRESHOLD
        )
        
        if matches:
            return matches[0]
        return None
