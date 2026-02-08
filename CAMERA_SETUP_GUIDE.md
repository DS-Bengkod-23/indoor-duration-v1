# Hybrid Camera Setup Guide - Windows + Docker

## Overview

Sistem ini sekarang mendukung **USB webcam DAN IP camera** di Windows:

- **USB Webcams**: Dicapture oleh native Windows service → Redis → Docker worker
- **IP/RTSP Cameras**: Diakses langsung oleh Docker worker

---

## 📋 Mendaftarkan Kamera via API

### Endpoint: `POST /api/v1/cameras`

**URL**: `http://localhost:8000/api/v1/cameras`

### Field Penjelasan

| Field | Type | Required | Deskripsi |
|-------|------|----------|-----------|
| `name` | string | ✅ Ya | Nama kamera (bebas, untuk identifikasi) |
| `rtsp_url` | string | ✅ Ya | **PENTING**: Tentukan tipe kamera di sini |
| `camera_index` | integer | ⚠️ Optional | Hanya untuk webcam (0, 1, 2, ...) |
| `room_id` | UUID | ✅ Ya | UUID ruangan (dari `GET /api/v1/cameras/rooms`) |
| `is_active` | boolean | ⚠️ Optional | Default: `true` |

### 🔑 Aturan `rtsp_url` (PENTING!)

**`rtsp_url`** menentukan **tipe kamera**:

| Tipe Kamera | Format `rtsp_url` | Contoh |
|-------------|-------------------|---------|
| **USB Webcam** | `redis://local` atau `redis://localhost` | `redis://local` |
| **IP Camera RTSP** | `rtsp://[user:pass@]ip:port/path` | `rtsp://admin:12345@192.168.1.100:554/stream1` |
| **IP Camera HTTP** | `http://ip:port/path` | `http://192.168.1.50:8080/video` |
| **Phone Camera** | `http://ip:port/...` | `http://192.168.1.50:4747/video` |

---

## 📝 Contoh Lengkap: Registrasi Kamera

### 1️⃣ USB Webcam (Laptop/PC)

#### Langkah 0: Dapatkan Room UUID
```bash
# Via browser atau curl
curl http://localhost:8000/api/v1/cameras/rooms

# Response:
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Lab Komputer",
    "location": "Lantai 2"
  }
]
```

#### Langkah 1: Cek Camera Index Yang Tersedia
```bash
# Test camera index mana yang available
python -c "import cv2; [print(f'Camera {i}: {\"OK\" if cv2.VideoCapture(i, cv2.CAP_DSHOW).isOpened() else \"NOT FOUND\"}') for i in range(3)]"

# Output contoh:
# Camera 0: OK          ← Gunakan index 0
# Camera 1: NOT FOUND
# Camera 2: NOT FOUND
```

#### Langkah 2: Register via Swagger UI

Buka: `http://localhost:8000/api/docs`

1. Expand `POST /api/v1/cameras`
2. Klik **"Try it out"**
3. Isi Request Body:

```json
{
  "name": "Webcam Laptop",
  "rtsp_url": "redis://local",
  "camera_index": 0,
  "room_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_active": true
}
```

4. Klik **"Execute"**
5. **COPY Camera UUID** dari response:

```json
{
  "id": "cam-uuid-1234-5678-90ab-cdef",  ← COPY INI!
  "name": "Webcam Laptop",
  "rtsp_url": "redis://local",
  "camera_index": 0,
  "room_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "room_name": "Lab Komputer",
  "is_active": true,
  "is_online": false,
  "created_at": "2026-02-08T06:58:00"
}
```

#### Penjelasan Field untuk Webcam:

- ✅ `"name": "Webcam Laptop"` - Nama bebas, untuk identifikasi saja
- ✅ `"rtsp_url": "redis://local"` - **WAJIB `redis://local`** untuk webcam lokal
- ✅ `"camera_index": 0` - Index webcam (0 = webcam pertama, 1 = kedua, dst)
- ✅ `"room_id": "..."` - UUID ruangan tempat kamera berada
- ✅ `"is_active": true` - Aktifkan kamera

---

### 2️⃣ IP Camera RTSP (Hikvision/Dahua/dll)

```json
{
  "name": "CCTV Perpustakaan",
  "rtsp_url": "rtsp://admin:password123@192.168.1.100:554/Streaming/Channels/101",
  "room_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_active": true
}
```

#### Penjelasan:

- ✅ `"rtsp_url"` - URL RTSP lengkap dengan username:password
- ❌ **TIDAK perlu** `camera_index` untuk IP camera
- Format umum: `rtsp://[username]:[password]@[ip]:[port]/[path]`

#### Cara Dapat RTSP URL dari IP Camera:

**Hikvision**:
```
rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101
rtsp://admin:password@192.168.1.100:554/Streaming/Channels/102  (second stream)
```

**Dahua**:
```
rtsp://admin:password@192.168.1.101:554/cam/realmonitor?channel=1&subtype=0
```

**Generic ONVIF**:
```
rtsp://admin:password@192.168.1.102:554/stream1
```

---

### 3️⃣ Mobile Phone sebagai IP Camera

#### Option A: Menggunakan IP Webcam (Android)

1. Install "IP Webcam" dari Play Store
2. Buka app, scroll ke bawah, tap **"Start server"**
3. Catat IP yang muncul, misal: `192.168.1.50:8080`
4. Register:

```json
{
  "name": "HP Android - Ruang Dosen",
  "rtsp_url": "http://192.168.1.50:8080/video",
  "room_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_active": true
}
```

#### Option B: Menggunakan DroidCam

1. Install DroidCam di HP dan PC
2. Catat IP dari app, misal: `192.168.1.50:4747`
3. Register:

```json
{
  "name": "HP DroidCam - Lab",
  "rtsp_url": "http://192.168.1.50:4747/video",
  "room_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_active": true
}
```

---

### 4️⃣ Multiple Webcams (2 atau lebih webcam USB)

```json
// Webcam pertama (built-in)
{
  "name": "Webcam Built-in",
  "rtsp_url": "redis://local",
  "camera_index": 0,
  "room_id": "room-uuid-1",
  "is_active": true
}

// Webcam kedua (external USB)
{
  "name": "Webcam External USB",
  "rtsp_url": "redis://local",
  "camera_index": 1,
  "room_id": "room-uuid-2",
  "is_active": true
}
```

**CATATAN**: Setiap webcam perlu:
- Camera UUID berbeda (otomatis dari API)
- `camera_index` berbeda (0, 1, 2, ...)
- Capture service terpisah untuk masing-masing

---

## 🚀 Workflow Lengkap Setelah Registrasi

**Option 2: IP Webcam** (Android)
1. Install "IP Webcam" from Play Store
2. Start server, note IP (e.g., `192.168.1.50:8080`)
3. Register camera:
   ```json
   {
     "name": "Phone Camera",
     "rtsp_url": "http://192.168.1.50:8080/video",
     "room_id": "YOUR-ROOM-UUID"
   }
   ```

---

## 🚀 Workflow Lengkap Setelah Registrasi

### A. Untuk USB Webcam

**Step 1**: Start Docker Infrastructure
```bash
cd e:\academic\indoorDuration\Indoorv2\indoor-duration-v1
docker-compose up -d postgres qdrant redis api

# Tunggu sampai semua healthy
docker-compose ps
```

**Step 2**: Register Camera (sudah dijelaskan di atas, dapat Camera UUID)

**Step 3**: Start Native Capture Service
```bash
# Windows
run_camera_capture.bat CAM-UUID-DARI-STEP-2 0

# Linux/Mac
./run_camera_capture.sh CAM-UUID-DARI-STEP-2 0
```

✅ **Verify capture service running**:
```
[CAPTURE] ✅ Connected to Redis
[CAPTURE] ✅ Camera 0 opened successfully
[CAPTURE]    Resolution: 640x480 @ 30 FPS
[CAPTURE] Starting capture loop for camera_id: cam-uuid-...
[CAPTURE] Frame    30 | FPS: 30.0 | Subscribers: 0
```

**Step 4**: Update `.env` (Optional, untuk auto-start worker)
```bash
# Edit .env file
notepad .env

# Tambahkan:
CAMERA_ID_1=CAM-UUID-DARI-STEP-2
```

**Step 5**: Start Docker Worker
```bash
docker-compose --profile worker up -d camera-worker-1
```

**Step 6**: Verify Everything Connected
```bash
# Check worker logs
docker-compose logs -f camera-worker-1
```

✅ **Expected logs**:
```
[WORKER] Loading camera: Webcam Laptop
[WORKER]   RTSP URL: redis://local
[WORKER]   Camera Index: 0
[WORKER] 📡 Mode: REDIS SUBSCRIPTION (local webcam)
[WORKER] ✅ Subscribed to Redis channel: camera_frames:cam-uuid-...
[WORKER] ⚠️  Make sure camera_capture_service.py is running for this camera!
[WORKER] ✅ Receiving frames from Redis
[WORKER] [REDIS] Processed frame 30, detections: 0
```

✅ **Capture service sekarang harusnya**:
```
[CAPTURE] Frame   60 | FPS: 30.0 | Subscribers: 1  ← Worker connected!
```

---

### B. Untuk IP Camera / RTSP

**Step 1**: Start Docker Infrastructure
```bash
docker-compose up -d postgres qdrant redis api
```

**Step 2**: Register IP Camera (sudah dijelaskan di atas, dapat Camera UUID)

**Step 3**: Update `.env` (Optional)
```bash
# Edit .env
CAMERA_ID_1=CAM-UUID-DARI-STEP-2
```

**Step 4**: Start Docker Worker
```bash
docker-compose --profile worker up -d camera-worker-1
```

**Step 5**: Verify Connection
```bash
docker-compose logs -f camera-worker-1
```

✅ **Expected logs**:
```
[WORKER] Loading camera: CCTV Perpustakaan
[WORKER]   RTSP URL: rtsp://admin:***@192.168.1.100:554/...
[WORKER] 📹 Mode: RTSP STREAM
[WORKER] ✅ Camera opened successfully
[WORKER] [VIDEO] Processed frame 30, detections: 1
```

---

## 🧪 Testing & Verification

### Test 1: Cek Camera Streaming

```bash
# Monitor worker logs (real-time)
docker-compose logs -f camera-worker-1

# Harusnya muncul setiap 1 detik:
# [WORKER] [REDIS/VIDEO] Processed frame XXX, detections: Y
```

### Test 2: Register Person & Test Detection

**Register diri sendiri**:
```bash
# Via Swagger UI: http://localhost:8000/api/docs
# POST /api/v1/users/register

# Upload foto wajah Anda
# Isi nama dan NIM/NIP
```

**Test detection**:
```bash
# Lihat ke kamera

# Check logs untuk detection
docker-compose logs camera-worker-1 | grep "IDENTIFIED"

# Harusnya muncul:
# [IDENTIFIED] Track T1: Nama Anda (confidence: 0.XX)
```

### Test 3: Check Database

```bash
# Connect ke PostgreSQL
docker-compose exec postgres psql -U indoor_user -d indoor_tracking

# Query active sessions
SELECT * FROM durations WHERE check_out IS NULL;

# Check registered cameras
SELECT id, name, rtsp_url, camera_index, is_online FROM cameras;

# Exit
\q
```

---

## Architecture Diagram

```
Windows Machine
├─ Docker Container
│  ├─ PostgreSQL
│  ├─ Qdrant
│  ├─ Redis ←─────────┐
│  ├─ API            │
│  └─ Camera Worker ─┘ (subscribes to Redis)
│
├─ Native Python (outside Docker)
│  └─ camera_capture_service.py
│     └─ Captures USB webcam → publishes to Redis
│
└─ Network
   └─ IP Cameras → accessed directly by Docker worker
```

---

## ⚠️ Troubleshooting

### Issue 1: "Failed to open camera" (Webcam)

**Solusi**:
```bash
# Cek camera index yang tersedia
python -c "import cv2; [print(f'Camera {i}: {\"OK\" if cv2.VideoCapture(i, cv2.CAP_DSHOW).isOpened() else \"NOT FOUND\"}') for i in range(3)]"

# Gunakan index yang "OK"
```

**Kemungkinan penyebab**:
- Webcam sedang digunakan aplikasi lain (Zoom, Teams, etc)
- Camera index salah (gunakan 0, 1, atau 2)
- Antivirus blocking camera access

---

### Issue 2: "Redis connection refused"

**Solusi**:
```bash
# Pastikan Redis running
docker-compose ps redis

# Restart kalau tidak running
docker-compose restart redis

# Test koneksi
redis-cli ping
# Harusnya: PONG
```

---

### Issue 3: Worker "Subscribers: 0" (Webcam)

**Artinya**: Worker belum subscribe ke Redis channel

**Solusi**:
```bash
# Start worker
docker-compose --profile worker up -d camera-worker-1

# Check logs
docker-compose logs -f camera-worker-1

# Harusnya muncul:
# [WORKER] ✅ Subscribed to Redis channel: camera_frames:...
```

---

### Issue 4: Worker tidak terima frame (Webcam)

**Checklist**:
1. ✅ Capture service running? (terminal masih jalan?)
2. ✅ Capture service shows "Subscribers: 1"?
3. ✅ Camera UUID sama di capture service dan worker?
4. ✅ Camera registered dengan `rtsp_url: "redis://local"`?

**Debug**:
```bash
# Monitor Redis channel manually
redis-cli
SUBSCRIBE "camera_frames:YOUR-CAMERA-UUID"

# Harusnya muncul "message" events
```

---

### Issue 5: IP Camera "Failed to open"

**Solusi**:
```bash
# Test RTSP URL dari Docker container
docker-compose exec camera-worker-1 python -c "
import cv2
cap = cv2.VideoCapture('rtsp://admin:password@192.168.1.100:554/stream1')
print(f'Connected: {cap.isOpened()}')
cap.release()
"
```

**Kemungkinan penyebab**:
- RTSP URL salah
- Username/password salah
- IP camera tidak accessible dari Docker network
- Firewall blocking

---

### Issue 6: "Camera not found in database"

**Artinya**: `CAMERA_ID` di environment tidak valid

**Solusi**:
```bash
# List semua cameras
curl http://localhost:8000/api/v1/cameras

# Update .env dengan UUID yang benar
CAMERA_ID_1=correct-uuid-from-api

# Restart worker
docker-compose restart camera-worker-1
```

---

## 📊 Performance Tips

### Optimize Frame Rate

**Untuk Webcam**:
```python
# Edit camera_capture_service.py (optional)
self.cap.set(cv2.CAP_PROP_FPS, 30)  # Adjust FPS
```

**Untuk RTSP**:
- Gunakan sub-stream (lower resolution) kalau main stream terlalu berat
- Contoh Hikvision: `/Streaming/Channels/102` (sub) vs `/101` (main)

### Monitor Resource Usage

```bash
# Docker stats
docker stats

# Expected:
# indoor_worker_cam1: ~2-3GB RAM, 30-50% CPU, 2-3GB GPU
```

---

## 🔄 Multiple Cameras Setup

### 2 USB Webcams + 1 IP Camera

```bash
# Terminal 1: Webcam 1
run_camera_capture.bat CAM-UUID-1 0

# Terminal 2: Webcam 2
run_camera_capture.bat CAM-UUID-2 1

# Terminal 3: Start all workers
docker-compose --profile worker2 --profile worker3 up -d camera-worker-1 camera-worker-2 camera-worker-3

# Monitor all
docker-compose logs -f camera-worker-1 camera-worker-2 camera-worker-3
```

**Setup `.env` untuk multiple cameras**:
```bash
# Camera 1 (auto-start dengan docker-compose up)
CAMERA_ID_1=webcam-1-uuid
CAMERA_1_TYPE=usb
CAMERA_1_INDEX=0

# Camera 2 (perlu --profile worker2)
CAMERA_ID_2=webcam-2-uuid
CAMERA_2_TYPE=usb
CAMERA_2_INDEX=1

# Camera 3 (perlu --profile worker3)
CAMERA_ID_3=ip-camera-uuid
CAMERA_3_TYPE=ip
```

---

## ➕ Menambahkan Camera Worker Baru ke docker-compose.yml

Secara default, hanya `camera-worker-1` yang auto-start saat `docker-compose up`. Untuk menambahkan worker tambahan yang ikut auto-start, ikuti langkah berikut:

### Langkah 1: Copy Service Block

Buka `docker-compose.yml` dan copy seluruh block `camera-worker-1` (sekitar baris 99-142).

### Langkah 2: Paste dan Modifikasi

Contoh untuk menambahkan `camera-worker-3` yang **auto-start**:

```yaml
  # Camera Worker 3 (AUTO-START)
  camera-worker-3:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    container_name: indoor_worker_cam3
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - DATABASE_URL=postgresql://indoor_user:indoor_pass_2026@postgres:5432/indoor_tracking
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - REDIS_URL=redis://redis:6379
      - CAMERA_ID=${CAMERA_ID_3}
    volumes:
      - ./indoor:/app/indoor
      - ./models:/app/models
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      api:
        condition: service_healthy
    networks:
      - indoor_network
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    # TIDAK ADA PROFILES = AUTO-START dengan docker-compose up
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_3}
```

### Langkah 3: Update `.env`

```env
CAMERA_ID_3=your-camera-uuid-here
CAMERA_3_TYPE=ip   # atau 'usb' untuk webcam
CAMERA_3_INDEX=2   # hanya jika usb
```

### Langkah 4: Rebuild dan Start

```bash
docker-compose build camera-worker-3
docker-compose up -d
```

---

### ⚡ Quick Template: Worker dengan Profile (Manual Start)

Jika ingin worker TIDAK auto-start (hanya start manual), tambahkan block `profiles`:

```yaml
  camera-worker-4:
    # ... (sama seperti di atas)
    profiles:
      - worker4   # <<< Tambahkan ini
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_4}
```

Untuk start manual:
```bash
docker-compose --profile worker4 up -d camera-worker-4
```

---

### 📋 Perbedaan Auto-Start vs Manual Start

| Konfigurasi | Start Command | Kapan Digunakan |
|-------------|---------------|-----------------|
| **Tanpa `profiles:`** | `docker-compose up` | Camera utama, selalu jalan |
| **Dengan `profiles: [workerX]`** | `docker-compose --profile workerX up` | Camera opsional, jarang jalan |

---

### 📝 Contoh docker-compose.yml dengan 4 Camera Workers

```yaml
services:
  # ... (postgres, qdrant, redis, api)
  
  # Worker 1 - AUTO-START (tanpa profiles)
  camera-worker-1:
    # ... config ...
    # TIDAK ADA profiles = auto-start
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_1}
  
  # Worker 2 - MANUAL START (dengan profiles)
  camera-worker-2:
    # ... config ...
    profiles:
      - worker2
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_2}
  
  # Worker 3 - AUTO-START (tanpa profiles)
  camera-worker-3:
    # ... config ...
    # TIDAK ADA profiles = auto-start
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_3}
  
  # Worker 4 - MANUAL START (dengan profiles)
  camera-worker-4:
    # ... config ...
    profiles:
      - worker4
    command: python -m ml_services.camera_worker --camera-id ${CAMERA_ID_4}
```

**Dengan konfigurasi ini:**
```bash
# Start: postgres, qdrant, redis, api, worker-1, worker-3
docker-compose up

# Start worker-2 tambahan
docker-compose --profile worker2 up -d camera-worker-2

# Start worker-4 tambahan  
docker-compose --profile worker4 up -d camera-worker-4
```

---

### 🔧 Untuk USB Webcam: Jangan Lupa Capture Service!

Jika worker baru adalah untuk USB webcam, pastikan juga update `start_webcam_captures.py` atau jalankan capture manual:

```bash
# Tambahkan ke .env
CAMERA_ID_3=new-webcam-uuid
CAMERA_3_TYPE=usb
CAMERA_3_INDEX=2

# Jalankan
python start_webcam_captures.py
# atau manual:
run_camera_capture.bat new-webcam-uuid 2
```


---

## 🎯 Best Practices

1. ✅ **Selalu test camera index** sebelum register webcam
2. ✅ **Start infrastructure dulu** sebelum workers
3. ✅ **Untuk webcam, start capture service** sebelum worker
4. ✅ **Monitor logs** untuk debugging
5. ✅ **Gunakan room yang berbeda** untuk camera yang berbeda
6. ✅ **Backup database** secara berkala

---

## 📝 Quick Reference

### USB Webcam
```json
{
  "name": "Webcam Lab",
  "rtsp_url": "redis://local",
  "camera_index": 0,
  "room_id": "ROOM-UUID"
}
```

### IP Camera RTSP
```json
{
  "name": "CCTV Perpustakaan",
  "rtsp_url": "rtsp://admin:pass@192.168.1.100:554/stream1",
  "room_id": "ROOM-UUID"
}
```

### Phone Camera
```json
{
  "name": "HP Android",
  "rtsp_url": "http://192.168.1.50:8080/video",
  "room_id": "ROOM-UUID"
}
```

---

## 🚀 Next Steps

1. ✅ Register rooms via API
2. ✅ Register cameras (webcam + IP camera)
3. ✅ Start capture services (untuk webcam)
4. ✅ Start workers
5. ✅ Register persons
6. ✅ Test face detection
7. ✅ Monitor durations
8. ✅ Build dashboard (optional)

Selamat! Sistem camera hybrid Anda sudah siap! 🎉
