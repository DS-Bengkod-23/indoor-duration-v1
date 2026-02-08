"""WebSocket Endpoints - Real-time camera streaming"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import Dict, Set
import asyncio
import json
from datetime import datetime
import base64

from app.api.deps import get_db
from app.services.camera_service import CameraService

router = APIRouter()

# Connection manager for WebSocket clients
class ConnectionManager:
    """Manages WebSocket connections for camera streams"""
    
    def __init__(self):
        # camera_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
        # Store latest frame data for each camera
        # camera_id -> {frame_base64, detections, timestamp}
        self.latest_frames: Dict[str, dict] = {}
    
    async def connect(self, websocket: WebSocket, camera_id: str):
        """Accept new WebSocket connection"""
        await websocket.accept()
        
        if camera_id not in self.active_connections:
            self.active_connections[camera_id] = set()
        
        self.active_connections[camera_id].add(websocket)
        print(f"[WS] Client connected to camera {camera_id}. Total: {len(self.active_connections[camera_id])}")
    
    def disconnect(self, websocket: WebSocket, camera_id: str):
        """Remove WebSocket connection"""
        if camera_id in self.active_connections:
            self.active_connections[camera_id].discard(websocket)
            print(f"[WS] Client disconnected from camera {camera_id}. Remaining: {len(self.active_connections[camera_id])}")
            
            # Clean up empty sets
            if not self.active_connections[camera_id]:
                del self.active_connections[camera_id]
    
    async def broadcast_to_camera(self, camera_id: str, message: dict):
        """Broadcast message to all clients watching a camera"""
        if camera_id not in self.active_connections:
            return
        
        # Store as latest frame
        self.latest_frames[camera_id] = message
        
        # Broadcast to all connected clients
        disconnected = set()
        for connection in self.active_connections[camera_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WS] Error sending to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn, camera_id)
    
    def update_camera_frame(self, camera_id: str, frame_data: dict):
        """
        Update latest frame data for a camera (called by camera worker)
        
        frame_data should contain:
        - frame_base64: Base64 encoded JPEG frame
        - detections: List of detected persons with bounding boxes
        - timestamp: ISO timestamp
        """
        self.latest_frames[camera_id] = frame_data
    
    def get_active_camera_count(self) -> int:
        """Get number of cameras with active connections"""
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/camera/{camera_id}")
async def camera_stream_websocket(
    websocket: WebSocket,
    camera_id: str
):
    """
    WebSocket endpoint for real-time camera streaming
    
    **Protocol:**
    Server -> Client (every frame):
    ```json
    {
        "type": "frame",
        "camera_id": "uuid",
        "camera_name": "CAM_0",
        "room_name": "Perpustakaan",
        "timestamp": "2026-02-06T10:30:45",
        "detections": [
            {
                "track_id": "T1",
                "person_id": "uuid or null",
                "person_name": "John Doe or Guest-1",
                "nim_nip": "A11.2023.12345 or null",
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.95,
                "duration_seconds": 120
            }
        ],
        "frame_base64": "base64_encoded_jpeg"
    }
    ```
    """
    import redis
    import os
    
    try:
        await manager.connect(websocket, camera_id)
        
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection",
            "message": f"Connected to camera {camera_id}",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Connect to Redis for frame subscription
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        
        # Subscribe to processed frames channel
        ws_channel = f"ws_frames:{camera_id}"
        pubsub.subscribe(ws_channel)
        print(f"[WS] Subscribed to Redis channel: {ws_channel}")
        
        # Forward frames from Redis to WebSocket
        while True:
            try:
                # Check for new frame from Redis (non-blocking)
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                
                if message and message['type'] == 'message':
                    # Parse and forward frame
                    frame_data = json.loads(message['data'])
                    await websocket.send_json(frame_data)
                    
                    # Store as latest frame
                    manager.latest_frames[camera_id] = frame_data
                
                # Also check for client commands (with short timeout)
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=0.05
                    )
                    
                    # Handle commands
                    try:
                        command = json.loads(data)
                        if command.get("command") == "ping":
                            await websocket.send_json({
                                "type": "pong",
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    except json.JSONDecodeError:
                        pass
                        
                except asyncio.TimeoutError:
                    pass  # No command received, continue
                    
            except WebSocketDisconnect:
                # Client disconnected - exit loop cleanly
                break
            except Exception as e:
                error_msg = str(e).lower()
                # Check for disconnect-related errors and exit silently
                if "disconnect" in error_msg or "not connected" in error_msg or "accept" in error_msg:
                    break
                # Only log unexpected errors (and limit frequency)
                print(f"[WS] Unexpected error: {e}")
                break
            
    except WebSocketDisconnect:
        pass  # Normal disconnect, no need to log
    except Exception as e:
        error_msg = str(e).lower()
        if "disconnect" not in error_msg and "not connected" not in error_msg:
            print(f"[WS] Error in WebSocket connection: {e}")
    finally:
        manager.disconnect(websocket, camera_id)
        try:
            pubsub.unsubscribe(ws_channel)
            pubsub.close()
        except:
            pass


@router.websocket("/all-cameras")
async def all_cameras_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for monitoring all cameras simultaneously
    
    Receives aggregated data from all active cameras
    """
    await websocket.accept()
    
    try:
        while True:
            # Collect data from all cameras
            all_camera_data = {
                "type": "all_cameras",
                "timestamp": datetime.utcnow().isoformat(),
                "cameras": []
            }
            
            for camera_id, frame_data in manager.latest_frames.items():
                # Send without frame data to reduce bandwidth
                camera_summary = {
                    "camera_id": camera_id,
                    "camera_name": frame_data.get("camera_name"),
                    "room_name": frame_data.get("room_name"),
                    "detections": frame_data.get("detections", []),
                    "timestamp": frame_data.get("timestamp")
                }
                all_camera_data["cameras"].append(camera_summary)
            
            await websocket.send_json(all_camera_data)
            
            # Wait before next update
            await asyncio.sleep(1.0)  # Update every second
            
    except WebSocketDisconnect:
        print("[WS] Client disconnected from all-cameras stream")
    except Exception as e:
        print(f"[WS] Error in all-cameras WebSocket: {e}")


# Export manager for use by camera workers
def get_websocket_manager() -> ConnectionManager:
    """Get global WebSocket connection manager"""
    return manager
