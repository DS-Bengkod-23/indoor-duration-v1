"""API Dependencies - Dependency injection for routes"""
from typing import Generator
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db as _get_db


def get_db() -> Generator:
    """
    Database session dependency
    Yields database session and closes it after request
    """
    try:
        db = next(_get_db())
        yield db
    finally:
        pass
