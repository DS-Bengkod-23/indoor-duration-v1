# Indoor Duration Tracking System - Backend API

Real-time presence tracking and duration monitoring system using AI face recognition and person detection.

## 🎯 Features

- **Person Management**: Register users with face photos, automatic face embedding extraction
- **Real-time Tracking**: Multi-camera support with DeepSORT tracking
- **Duration Monitoring**: Automatic calculation of time spent in rooms
- **Unknown Person Handling**: Track unidentified persons as guests with duration
- **WebSocket Streaming**: Real-time camera feeds with detection overlays
- **Statistics & Reports**: Query historical data and generate reports
- **REST API**: Comprehensive API with Swagger documentation
- **GPU Support**: CUDA-accelerated ML inference (NVIDIA GPUs)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend Dashboard                    │
│              (WebSocket + REST API Client)              │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ HTTP/WebSocket
                  │
┌─────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (Port 8000)                 │
│  - REST Endpoints  - WebSocket  - Swagger Docs          │
└──────────┬─────────────────────────────────┬────────────┘
           │                                 │
     ┌─────▼──────┐                   ┌────▼──────┐
     │ PostgreSQL │                   │  Qdrant   │
     │  Database  │                   │ Vector DB │
     └────────────┘                   └───────────┘
           │
           │
┌──────────▼─────────────────────────────────────────────┐
│          Camera Workers (GPU Enabled)                   │
│  - YOLOv8 Detection  - Face Recognition  - Tracking    │
│  - One worker per camera                               │
└────────────────────────────────────────────────────────┘
```

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 15
- **Vector DB**: Qdrant (face embeddings)
- **Cache**: Redis 7
- **ML Models**: 
  - YOLOv8 (person detection)
  - InsightFace (face recognition)
  - DeepSORT (tracking)
- **Deployment**: Docker + docker-compose
- **GPU**: CUDA 11.8 (NVIDIA)

## 📋 Requirements

### System Requirements
- **OS**: Ubuntu 22.04 / Windows 10+ / macOS
- **GPU**: NVIDIA GPU with CUDA support (tested on GTX 1650 Ti)
  - CUDA 11.8 or later
  - 4GB VRAM minimum
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 10GB free space

### Software Requirements
- Docker Engine 24.0+
- Docker Compose 2.0+
- NVIDIA Container Toolkit (for GPU support)

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone <repository-url>
cd indoor-duration-v1
```

### 2. Install NVIDIA Container Toolkit (For GPU Support)

**Ubuntu/Debian:**
```bash
# Add NVIDIA package repositories
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install nvidia-container-toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Restart Docker
sudo systemctl restart docker
```

**Windows:**
- Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Enable WSL2 backend
- Install NVIDIA drivers for Windows
- NVIDIA Container Toolkit is included in Docker Desktop for Windows

### 3. Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your settings
nano .env
```

### 4. Start Core Services
```bash
# Start PostgreSQL, Qdrant, Redis, and API
docker-compose up -d

# Check logs
docker-compose logs -f api
```

Wait for services to be healthy (check with: `docker-compose ps`)

### 5. Initialize Database
Database tables are automatically created on first run via Alembic migrations.

To manually run migrations:
```bash
docker-compose exec api alembic upgrade head
```

### 6. Register Rooms and Cameras

**Option A: Via API (Swagger UI)**
```
Open http://localhost:8000/api/docs
```

**Option B: Via Python Script**
```python
import requests

API_URL = "http://localhost:8000/api/v1"

# Create room
room_response = requests.post(f"{API_URL}/cameras/rooms", json={
    "name": "Perpustakaan",
    "description": "Ruang Perpustakaan Utama"
})
room_id = room_response.json()["data"]["id"]

# Create camera
camera_response = requests.post(f"{API_URL}/cameras", json={
    "name": "CAM_0",
    "rtsp_url": "0",  # Local camera index or RTSP URL
    "room_id": room_id,
    "camera_index": 0,
    "fps": 30
})
camera_id = camera_response.json()["data"]["id"]
print(f"Camera ID: {camera_id}")
```

Save the `camera_id` for starting workers.

### 7. Start Camera Workers

Update `.env` with camera IDs:
```bash
CAMERA_ID_1=<uuid-from-step-6>
```

Start worker:
```bash
docker-compose --profile worker up -d camera-worker-1

# Check logs
docker-compose logs -f camera-worker-1
```

### 8. Register Users

**Via API:**
```bash
curl -X POST "http://localhost:8000/api/v1/users/register" \
  -F "name=John Doe" \
  -F "nim_nip=A11.2023.12345" \
  -F "photo=@/path/to/photo.jpg"
```

**Via Swagger UI:**
```
http://localhost:8000/api/docs#/Users/register_person_api_v1_users_register_post
```

## 📚 API Documentation

### Swagger UI (Interactive)
```
http://localhost:8000/api/docs
```

### ReDoc (Documentation)
```
http://localhost:8000/api/redoc
```

### Key Endpoints

#### Users
- `POST /api/v1/users/register` - Register new person
- `GET /api/v1/users` - List all persons
- `GET /api/v1/users/{id}` - Get person detail with current location
- `PUT /api/v1/users/{id}` - Update person
- `DELETE /api/v1/users/{id}` - Delete person

#### Cameras
- `POST /api/v1/cameras` - Create camera
- `GET /api/v1/cameras` - List all cameras
- `GET /api/v1/cameras/live/streams` - Get all active streams

#### Sessions (Duration Tracking)
- `GET /api/v1/sessions/active` - Get all people currently present
- `GET /api/v1/sessions/person/{id}/stats` - Get person statistics
- `GET /api/v1/sessions/person/{id}/current` - Get current location

#### WebSocket
- `WS /api/v1/ws/camera/{id}` - Real-time camera stream
- `WS /api/v1/ws/all-cameras` - All cameras aggregated

## 🔧 Configuration

### Database Model Logic

**Duration Tracking:**
- Every person (known or unknown) gets a `Duration` record
- `person_id` is **nullable** - allows tracking unknown persons
- When unknown person is recognized → duration is assigned to person
- If person remains unknown → duration saved with `guest_label`

**Tables:**
1. **persons**: Registered users (name, nim_nip, photo, embedding_id)
2. **durations**: Presence sessions (person_id, track_id, room_id, camera_id, times)
3. **cameras**: Camera configurations (name, rtsp_url, room_id)
4. **rooms**: Physical rooms (name, description)

### Face Recognition Settings

Edit `app/config.py`:
```python
FACE_MATCH_THRESHOLD = 0.60  # Minimum similarity for recognition
FACE_HIGH_CONFIDENCE = 0.75  # High confidence threshold
```

### Camera Settings

Edit `config/settings.py` for ML model parameters:
```python
SETTINGS = {
    "face_conf_threshold": 0.40,
    "yolo_conf_threshold": 0.40,
    "max_age": 20,  # DeepSORT max age
    # ... more settings
}
```

## 🐛 Troubleshooting

### GPU Not Detected
```bash
# Verify NVIDIA driver
nvidia-smi

# Verify Docker can access GPU
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Check worker logs
docker-compose logs camera-worker-1 | grep CUDA
```

### Camera Connection Issues
```bash
# Test camera locally
docker-compose exec camera-worker-1 python -c "
import cv2
cap = cv2.VideoCapture(0)
print('Camera opened:', cap.isOpened())
cap.release()
"
```

### Database Connection Issues
```bash
# Check PostgreSQL status
docker-compose ps postgres

# Connect to database
docker-compose exec postgres psql -U indoor_user -d indoor_tracking
```

### Port Already in Use
```bash
# Change port in docker-compose.yml
# For API (default 8000):
ports:
  - "8001:8000"  # External:Internal
```

## 📊 Monitoring

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# Check all services
docker-compose ps
```

### Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f camera-worker-1

# Last 100 lines
docker-compose logs --tail=100 api
```

### Database
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U indoor_user -d indoor_tracking

# Useful queries
SELECT * FROM persons LIMIT 10;
SELECT * FROM durations WHERE check_out IS NULL;  # Active sessions
SELECT COUNT(*) FROM durations;
```

## 🔒 Security Considerations

**Production Deployment:**
1. Change database passwords in `.env` and `docker-compose.yml`
2. Set strong `SECRET_KEY` in `.env`
3. Disable `DEBUG=False` in production
4. Use HTTPS with reverse proxy (Nginx/Traefik)
5. Implement rate limiting
6. Add authentication middleware
7. Restrict CORS origins

## 📝 Development

### Local Development (Without Docker)
```bash
# Install dependencies
pip install -r requirements/api.txt
pip install -r requirements/ml.txt

# Start services manually
# PostgreSQL, Qdrant, Redis must be running

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start worker (separate terminal)
python -m ml_services.camera_worker --camera-id <uuid>
```

### Running Tests
```bash
# TODO: Add tests
pytest tests/
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is proprietary software for academic purposes.

## 👥 Support

For issues and questions:
- Create an issue on GitHub
- Contact: [your-email@domain.com]

## 🎓 Citation

If you use this system in your research, please cite:
```
@software{indoor_duration_tracking_2026,
  title={Indoor Duration Tracking System},
  author={Your Name},
  year={2026},
  url={https://github.com/your-repo}
}
```
