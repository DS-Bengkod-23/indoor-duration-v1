"""Application Configuration"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "Indoor Duration Tracking API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql://indoor_user:indoor_pass@postgres:5432/indoor_tracking"
    
    # Qdrant Vector Database
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_FACE_COLLECTION: str = "face_embeddings"
    QDRANT_BODY_COLLECTION: str = "body_embeddings"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # File Storage
    UPLOAD_DIR: str = "./uploads"
    SNAPSHOT_DIR: str = "./logs/snapshots"
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5MB
    
    # Face Recognition Thresholds
    FACE_MATCH_THRESHOLD: float = 0.60
    FACE_HIGH_CONFIDENCE: float = 0.75
    
    # Security
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    CORS_ORIGINS: list = ["*"]
    
    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
