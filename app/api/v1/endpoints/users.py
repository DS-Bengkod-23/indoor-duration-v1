"""Users Endpoints - Person registration and management"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
import shutil
import cv2
import numpy as np

from app.api.deps import get_db
from app.services.person_service import PersonService
from app.services.embedding_service import EmbeddingService
from app.schemas.person import (
    PersonCreate, PersonUpdate, PersonResponse, 
    PersonDetailResponse, PersonListResponse
)
from app.schemas.response import StandardResponse
from app.config import settings

# Import face recognizer from existing codebase
from indoor.face_recognizer import FaceRecognizer

router = APIRouter()

# Initialize face recognizer (singleton)
face_recognizer = None


def get_face_recognizer():
    """Get or initialize face recognizer"""
    global face_recognizer
    if face_recognizer is None:
        face_recognizer = FaceRecognizer()
    return face_recognizer


@router.post(
    "/register",
    response_model=StandardResponse[PersonResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register New Person",
    description="""
    Register a new person with face photo for recognition.
    
    **Required:**
    - name: Full name
    - nim_nip: Student/Staff ID (must be unique)
    - photo: Face photo (JPG/PNG, max 5MB)
    
    **Process:**
    1. Validates photo contains exactly one face
    2. Extracts face embedding (512D vector)
    3. Stores embedding in Qdrant vector database
    4. Saves person info in PostgreSQL
    
    **Returns:** Person object with embedding ID
    """
)
async def register_person(
    name: str = Form(..., description="Full name"),
    nim_nip: str = Form(..., description="Student/Staff ID"),
    notes: Optional[str] = Form(None, description="Optional notes"),
    photo: UploadFile = File(..., description="Face photo"),
    db: Session = Depends(get_db)
):
    """Register new person with face photo"""
    service = PersonService(db)
    recognizer = get_face_recognizer()
    
    # Validate nim_nip uniqueness
    existing = service.get_person_by_nim_nip(nim_nip)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"NIM/NIP '{nim_nip}' already exists"
        )
    
    # Validate file size
    contents = await photo.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / (1024*1024)}MB"
        )
    
    # Save photo temporarily
    temp_path = f"/tmp/{uuid.uuid4()}.jpg"
    with open(temp_path, "wb") as f:
        f.write(contents)
    
    try:
        # Read image
        image = cv2.imread(temp_path)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image file"
            )
        
        # Extract face embedding
        embedding = recognizer.extract_embedding(image)
        if embedding is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No face detected in photo. Please upload a clear face photo."
            )
        
        # Save photo permanently
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        photo_filename = f"{uuid.uuid4()}_{nim_nip}.jpg"
        photo_path = os.path.join(settings.UPLOAD_DIR, photo_filename)
        shutil.copy(temp_path, photo_path)
        
        # Create person
        person_data = PersonCreate(name=name, nim_nip=nim_nip, notes=notes)
        person = service.create_person(
            person_data=person_data,
            photo_path=photo_path,
            embedding=embedding
        )
        
        return StandardResponse(
            success=True,
            message=f"Successfully registered {name}",
            data=PersonResponse.from_orm(person)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error registering person: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register person: {str(e)}"
        )
    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get(
    "/",
    response_model=StandardResponse[PersonListResponse],
    summary="Get All Persons",
    description="Get paginated list of all registered persons with optional search"
)
def get_persons(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get list of persons"""
    service = PersonService(db)
    persons, total = service.get_all_persons(
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active
    )
    
    return StandardResponse(
        success=True,
        message="Successfully retrieved persons",
        data=PersonListResponse(
            total=total,
            persons=[PersonResponse.from_orm(p) for p in persons]
        )
    )


@router.get(
    "/{person_id}",
    response_model=StandardResponse[PersonDetailResponse],
    summary="Get Person Detail",
    description="""
    Get detailed person information including:
    - Basic info (name, nim_nip, photo)
    - Current location (room, camera)
    - Current duration (if present)
    - Total duration across all sessions
    - Session count
    """
)
def get_person(person_id: str, db: Session = Depends(get_db)):
    """Get person detail with current location and statistics"""
    service = PersonService(db)
    person_detail = service.get_person_detail(person_id)
    
    if not person_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully retrieved person detail",
        data=person_detail
    )


@router.put(
    "/{person_id}",
    response_model=StandardResponse[PersonResponse],
    summary="Update Person",
    description="Update person information (name, nim_nip, active status)"
)
def update_person(
    person_id: str,
    person_data: PersonUpdate,
    db: Session = Depends(get_db)
):
    """Update person information"""
    service = PersonService(db)
    person = service.update_person(person_id, person_data)
    
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message=f"Successfully updated person",
        data=PersonResponse.from_orm(person)
    )


@router.delete(
    "/{person_id}",
    response_model=StandardResponse[dict],
    summary="Delete Person",
    description="Delete person and their face embedding from the system"
)
def delete_person(person_id: str, db: Session = Depends(get_db)):
    """Delete person"""
    service = PersonService(db)
    success = service.delete_person(person_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person with ID '{person_id}' not found"
        )
    
    return StandardResponse(
        success=True,
        message="Successfully deleted person",
        data={"deleted": True}
    )


@router.get(
    "/search/by-name",
    response_model=StandardResponse[PersonListResponse],
    summary="Search Persons by Name",
    description="Search persons by name (case-insensitive partial match)"
)
def search_persons_by_name(
    query: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Search persons by name"""
    service = PersonService(db)
    persons, total = service.get_all_persons(search=query, limit=limit)
    
    return StandardResponse(
        success=True,
        message=f"Found {total} persons matching '{query}'",
        data=PersonListResponse(
            total=total,
            persons=[PersonResponse.from_orm(p) for p in persons]
        )
    )
