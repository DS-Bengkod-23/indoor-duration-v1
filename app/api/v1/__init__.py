"""API v1 Router"""
from fastapi import APIRouter
from app.api.v1.endpoints import users, cameras, sessions, websocket

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(cameras.router, prefix="/cameras", tags=["Cameras"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
