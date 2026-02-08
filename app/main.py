"""FastAPI Main Application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.api.v1.router import api_router
from app.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print("[APP] Starting Indoor Duration Tracking API...")
    print(f"[APP] Version: {settings.APP_VERSION}")
    print(f"[APP] Database: {settings.DATABASE_URL.split('@')[0]}@***")  # Hide password
    print(f"[APP] Qdrant: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    
    # Create database tables
    try:
        print("[APP] Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("[APP] Database tables ready")
    except Exception as e:
        print(f"[APP] Warning: Could not create tables: {e}")
    
    yield
    
    # Shutdown
    print("[APP] Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    # Indoor Duration Tracking System API
    
    Real-time presence tracking and duration monitoring system using AI face recognition and person detection.
    
    ## Features
    
    - **Person Management**: Register users with face photos
    - **Real-time Tracking**: Track people across multiple cameras
    - **Duration Monitoring**: Automatic calculation of time spent in rooms
    - **Unknown Person Handling**: Track unidentified persons as guests
    - **WebSocket Streaming**: Real-time camera feeds with detection overlays
    - **Statistics & Reports**: Query historical data and generate reports
    
    ## Architecture
    
    - **Backend**: FastAPI (Python 3.11)
    - **Database**: PostgreSQL + Qdrant Vector DB
    - **ML Models**: YOLOv8, InsightFace, DeepSORT
    - **Deployment**: Docker with GPU support (NVIDIA)
    
    ## Workflow
    
    1. **Registration**: User uploads photo → Face embedding extracted → Stored in Qdrant
    2. **Detection**: Camera detects person → Extracts embedding → Searches Qdrant
    3. **Tracking**: Assigns ID (known or guest) → Tracks duration → Updates PostgreSQL
    4. **Real-time**: Streams data via WebSocket → Frontend displays live
    
    ## Important Endpoints
    
    - `POST /api/v1/users/register` - Register new person
    - `GET /api/v1/users/{id}` - Get person detail with current location
    - `GET /api/v1/sessions/active` - Get all people currently present
    - `WS /api/v1/ws/camera/{id}` - WebSocket for live camera stream
    """,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routers
app.include_router(api_router, prefix="/api/v1")


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "message": "Indoor Duration Tracking API",
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "redoc": "/api/redoc",
        "status": "operational"
    }


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": "connected",  # TODO: Add actual DB check
        "qdrant": "connected"     # TODO: Add actual Qdrant check
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    print(f"[ERROR] Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
