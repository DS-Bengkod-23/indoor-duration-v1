# API Endpoint Reference Guide

Base URL: `http://localhost:8000/api/v1`

## Authentication
Currently no authentication required. Will be added in Phase 4.

---

## Users / Persons Management

### Register New Person
**POST** `/users/register`

Register a new person with face photo.

**Form Data:**
- `name` (string, required): Full name
- `nim_nip` (string, required): Student/Staff ID
- `notes` (string, optional): Additional notes
- `photo` (file, required): Face photo (JPG/PNG, max 5MB)

**Response:**
```json
{
  "success": true,
  "message": "Successfully registered John Doe",
  "data": {
    "id": "uuid",
    "name": "John Doe",
    "nim_nip": "A11.2023.12345",
    "photo_path": "/uploads/uuid.jpg",
    "embedding_id": "uuid",
    "is_active": true,
    "created_at": "2026-02-06T10:30:00",
    "updated_at": null
  }
}
```

### Get All Persons
**GET** `/users?skip=0&limit=100&search=John&is_active=true`

**Response:**
```json
{
  "success": true,
  "message": "Successfully retrieved persons",
  "data": {
    "total": 50,
    "persons": [...]
  }
}
```

### Get Person Detail
**GET** `/users/{person_id}`

Returns person with current location and statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "name": "John Doe",
    "nim_nip": "A11.2023.12345",
    "current_room": "Perpustakaan",
    "current_camera": "CAM_0",
    "current_duration_seconds": 1800,
    "total_duration_seconds": 36000,
    "session_count": 15
  }
}
```

### Update Person
**PUT** `/users/{person_id}`

**Body:**
```json
{
  "name": "John Doe Updated",
  "is_active": true
}
```

### Delete Person
**DELETE** `/users/{person_id}`

---

## Cameras & Rooms

### Create Room
**POST** `/cameras/rooms`

**Body:**
```json
{
  "name": "Perpustakaan",
  "description": "Ruang perpustakaan utama"
}
```

### Get All Rooms
**GET** `/cameras/rooms?is_active=true`

### Create Camera
**POST** `/cameras`

**Body:**
```json
{
  "name": "CAM_0",
  "rtsp_url": "0",
  "room_id": "uuid",
  "camera_index": 0,
  "fps": 30,
  "resolution_width": 640,
  "resolution_height": 480
}
```

### Get All Cameras
**GET** `/cameras?is_active=true&room_id=uuid`

### Get Live Camera Streams
**GET** `/cameras/live/streams`

Returns all active cameras with WebSocket URLs.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "camera_id": "uuid",
      "camera_name": "CAM_0",
      "room_name": "Perpustakaan",
      "is_online": true,
      "stream_url": "/api/v1/ws/camera/uuid"
    }
  ]
}
```

---

## Sessions / Duration Tracking

### Get Active Sessions
**GET** `/sessions/active`

Get all people currently present in the building.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "person_id": "uuid",
      "person_name": "John Doe",
      "nim_nip": "A11.2023.12345",
      "room_name": "Perpustakaan",
      "camera_name": "CAM_0",
      "check_in": "2026-02-06T10:00:00",
      "current_duration_seconds": 1800,
      "confidence": 0.95,
      "is_guest": false
    }
  ]
}
```

### Get Person Statistics
**GET** `/sessions/person/{person_id}/stats`

**Response:**
```json
{
  "success": true,
  "data": {
    "person_id": "uuid",
    "person_name": "John Doe",
    "total_duration_seconds": 36000,
    "session_count": 15,
    "current_duration_seconds": 1800,
    "current_room": "Perpustakaan",
    "is_currently_present": true
  }
}
```

### Get Person Current Location
**GET** `/sessions/person/{person_id}/current`

**Response:**
```json
{
  "success": true,
  "message": "Person is currently present",
  "data": {
    "person_id": "uuid",
    "person_name": "John Doe",
    "nim_nip": "A11.2023.12345",
    "room_name": "Perpustakaan",
    "camera_name": "CAM_0",
    "check_in": "2026-02-06T10:00:00",
    "current_duration_seconds": 1800,
    "confidence": 0.95,
    "is_guest": false
  }
}
```

### Get Duration History
**GET** `/sessions/history?start_date=2026-02-01T00:00:00&end_date=2026-02-06T23:59:59&person_id=uuid`

### Assign Unknown Duration to Person
**POST** `/sessions/assign/{duration_id}?person_id=uuid&confidence=0.85`

Used when unknown person is later recognized.

---

## WebSocket Streams

### Single Camera Stream
**WS** `/ws/camera/{camera_id}`

**Server → Client (every frame):**
```json
{
  "camera_id": "uuid",
  "camera_name": "CAM_0",
  "room_name": "Perpustakaan",
  "timestamp": "2026-02-06T10:30:45",
  "detections": [
    {
      "track_id": "CAM_0_T1",
      "person_id": "uuid",
      "person_name": "John Doe",
      "nim_nip": "A11.2023.12345",
      "bbox": [100, 150, 300, 450],
      "confidence": 0.95,
      "duration_seconds": 120
    }
  ],
  "frame_base64": "base64_encoded_jpeg"
}
```

**Client → Server commands:**
```json
{"command": "request_frame"}      // Request full frame
{"command": "detections_only"}    // Stream only detections
{"command": "ping"}                // Keep-alive
```

### All Cameras Stream
**WS** `/ws/all-cameras`

Aggregated data from all cameras without frame data.

---

## Example Usage (Python)

### Register User
```python
import requests

url = "http://localhost:8000/api/v1/users/register"
files = {"photo": open("photo.jpg", "rb")}
data = {
    "name": "John Doe",
    "nim_nip": "A11.2023.12345"
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

### Get Active Sessions
```python
import requests

url = "http://localhost:8000/api/v1/sessions/active"
response = requests.get(url)
active_sessions = response.json()["data"]

for session in active_sessions:
    print(f"{session['person_name']} in {session['room_name']} for {session['current_duration_seconds']}s")
```

### WebSocket Connection (JavaScript)
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/camera/uuid');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Detections:', data.detections);
  
  // Display frame
  document.getElementById('camera-frame').src = 
    'data:image/jpeg;base64,' + data.frame_base64;
};

// Send ping
setInterval(() => {
  ws.send(JSON.stringify({command: 'ping'}));
}, 30000);
```

---

## Error Codes

- `200` - Success
- `201` - Created
- `400` - Bad Request (invalid input)
- `404` - Not Found
- `409` - Conflict (duplicate NIM/NIP)
- `413` - Payload Too Large (photo > 5MB)
- `500` - Internal Server Error

## Rate Limiting
Not implemented yet (Phase 4).

## Pagination
Default: `skip=0&limit=100`
Max limit: 1000
