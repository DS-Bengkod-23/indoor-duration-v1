# Indoor Duration API Documentation

**Base URL**: `http://localhost:8000/api/v1`  
**Swagger UI**: `http://localhost:8000/api/docs`

---

## 📋 Table of Contents

1. [Users (Person Management)](#-users-person-management)
2. [Cameras](#-cameras)
3. [Rooms](#-rooms)
4. [Sessions (Duration Tracking)](#-sessions-duration-tracking)
5. [WebSocket Streaming](#-websocket-streaming)
6. [Workflow Examples](#-workflow-examples)

---

## 👤 Users (Person Management)

Endpoints untuk mengelola data orang yang akan dideteksi oleh sistem.

---

### Register Person
**`POST /users/register`**

**Fungsi**: Mendaftarkan orang baru ke sistem dengan foto wajah. Sistem akan:
1. Menyimpan foto ke storage
2. Ekstrak face embedding menggunakan AI model
3. Menyimpan embedding ke Qdrant vector database
4. Membuat record person di PostgreSQL

**Use Case**: Admin mendaftarkan mahasiswa/dosen baru agar bisa dikenali oleh kamera.

**Request (multipart/form-data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Nama lengkap |
| `nim_nip` | string | ✅ | NIM/NIP (identifier unik) |
| `notes` | string | ❌ | Catatan tambahan |
| `photo` | file | ✅ | Foto wajah (JPG/PNG, min 100x100px) |

**Response:**
```json
{
  "success": true,
  "message": "Successfully registered person",
  "data": {
    "id": "uuid",
    "name": "John Doe",
    "nim_nip": "A11.2023.12345",
    "photo_path": "/uploads/faces/abc123.jpg",
    "embedding_id": "emb_uuid",
    "is_active": true,
    "created_at": "2026-02-08T10:00:00"
  }
}
```

---

### Get All Persons
**`GET /users`**

**Fungsi**: Mengambil daftar semua orang yang terdaftar dengan pagination dan filter.

**Use Case**: Menampilkan daftar mahasiswa/dosen di dashboard admin.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `skip` | int | 0 | Offset untuk pagination |
| `limit` | int | 100 | Jumlah max hasil |
| `search` | string | - | Filter berdasarkan nama (partial match) |
| `is_active` | bool | - | Filter aktif/nonaktif |

---

### Get Person Detail
**`GET /users/{person_id}`**

**Fungsi**: Mengambil detail lengkap satu orang termasuk lokasi saat ini dan statistik kehadiran.

**Use Case**: Melihat profil seseorang dan mengetahui apakah sedang di ruangan mana.

**Response includes:**
- Info dasar (nama, NIM/NIP, foto)
- `current_room` - Ruangan saat ini (jika sedang hadir)
- `current_camera` - Kamera yang mendeteksi
- `total_duration_seconds` - Total waktu kehadiran sepanjang waktu
- `session_count` - Jumlah kali masuk

---

### Update Person
**`PUT /users/{person_id}`**

**Fungsi**: Mengupdate informasi orang (nama, NIM/NIP, status aktif, notes).

**Use Case**: Memperbaiki data yang salah atau menonaktifkan orang yang sudah tidak aktif.

**Request:**
```json
{
  "name": "Nama Baru",
  "nim_nip": "NEW123",
  "is_active": true,
  "notes": "Catatan terbaru"
}
```

---

### Delete Person
**`DELETE /users/{person_id}`**

**Fungsi**: Menghapus orang dari sistem (soft delete - hanya deactivate, data tetap ada).

**Use Case**: Menghapus orang yang tidak valid atau salah input.

---

### Search by Name
**`GET /users/search?query=john&limit=20`**

**Fungsi**: Mencari orang berdasarkan nama dengan fitur autocomplete/fuzzy search.

**Use Case**: Search bar di dashboard untuk mencari orang dengan cepat.

---

## 📹 Cameras

Endpoints untuk mengelola kamera yang terhubung ke sistem.

---

### Create Camera
**`POST /cameras`**

**Fungsi**: Mendaftarkan kamera baru ke sistem. Setelah didaftarkan, camera worker akan mulai memproses stream dari kamera ini.

**Use Case**: Admin menambahkan CCTV baru atau webcam ke sistem monitoring.

**Request:**
```json
{
  "name": "Webcam Laptop",
  "rtsp_url": "redis://local",
  "camera_index": 0,
  "room_id": "room-uuid",
  "fps": 30,
  "resolution_width": 640,
  "resolution_height": 480
}
```

**Jenis `rtsp_url`:**

| Camera Type | rtsp_url Value | Keterangan |
|-------------|----------------|------------|
| USB Webcam | `redis://local` | Webcam lokal, butuh capture service |
| IP Camera RTSP | `rtsp://admin:pass@192.168.1.100:554/stream` | CCTV via RTSP |
| Mobile (IP Webcam) | `http://192.168.1.50:8080/video` | HP sebagai kamera |

---

### Get All Cameras
**`GET /cameras`**

**Fungsi**: Mengambil daftar semua kamera dengan status online/offline.

**Use Case**: Dashboard monitoring untuk melihat semua kamera dan statusnya.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `is_active` | bool | Filter kamera aktif saja |
| `room_id` | string | Filter berdasarkan ruangan |

---

### Get Camera Detail
**`GET /cameras/{camera_id}`**

**Fungsi**: Mengambil detail lengkap satu kamera termasuk konfigurasi dan status.

**Use Case**: Debugging atau melihat konfigurasi spesifik kamera.

---

### Update Camera
**`PUT /cameras/{camera_id}`**

**Fungsi**: Mengupdate konfigurasi kamera (nama, URL, ruangan, status aktif).

**Use Case**: Mengubah konfigurasi tanpa harus hapus dan buat ulang.

**Request:**
```json
{
  "name": "Nama Baru",
  "rtsp_url": "rtsp://...",
  "room_id": "new-room-uuid",
  "is_active": true
}
```

---

### Delete Camera
**`DELETE /cameras/{camera_id}`**

**Fungsi**: Menghapus kamera dari sistem.

**⚠️ Warning**: Pastikan camera worker dihentikan terlebih dahulu.

---

### Get Live Streams
**`GET /cameras/live/streams`**

**Fungsi**: Mendapatkan daftar kamera aktif beserta URL WebSocket untuk streaming real-time.

**Use Case**: Frontend untuk menampilkan multi-camera view dengan streaming langsung.

**Response:**
```json
{
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

## 🏠 Rooms

Endpoints untuk mengelola ruangan tempat kamera dipasang.

---

### Create Room
**`POST /cameras/rooms`**

**Fungsi**: Membuat ruangan baru. Setiap kamera harus dikaitkan dengan satu ruangan.

**Use Case**: Setup awal sistem - buat ruangan dulu, baru tambahkan kamera.

**Request:**
```json
{
  "name": "Perpustakaan",
  "description": "Lantai 2, Gedung A"
}
```

---

### Get All Rooms
**`GET /cameras/rooms`**

**Fungsi**: Mengambil daftar semua ruangan dengan jumlah kamera di masing-masing.

**Use Case**: Dropdown pilihan ruangan saat mendaftarkan kamera baru.

---

### Get Room Detail
**`GET /cameras/rooms/{room_id}`**

**Fungsi**: Mengambil detail ruangan termasuk daftar kamera di dalamnya.

---

## ⏱️ Sessions (Duration Tracking)

Endpoints untuk tracking kehadiran/durasi orang di ruangan.

---

### Get Active Sessions
**`GET /sessions/active`**

**Fungsi**: Mendapatkan semua orang yang **sedang berada** di ruangan saat ini (check-in tapi belum check-out).

**Use Case**: Dashboard "Siapa yang ada di gedung sekarang?"

**Response:**
```json
{
  "data": [
    {
      "person_id": "uuid atau null (jika guest)",
      "person_name": "John Doe",
      "nim_nip": "A11.2023.12345",
      "room_name": "Perpustakaan",
      "camera_name": "CAM_0",
      "check_in": "2026-02-08T10:00:00",
      "current_duration_seconds": 3600,
      "confidence": 0.95,
      "is_guest": false
    }
  ]
}
```

---

### Get Person Statistics  
**`GET /sessions/person/{person_id}/stats`**

**Fungsi**: Mendapatkan statistik kehadiran seseorang: total waktu, jumlah sesi, lokasi saat ini.

**Use Case**: Laporan kehadiran individual, mengetahui berapa lama seseorang di kampus.

**Response:**
```json
{
  "data": {
    "person_id": "uuid",
    "person_name": "John Doe",
    "total_duration_seconds": 86400,
    "session_count": 15,
    "current_duration_seconds": 3600,
    "current_room": "Perpustakaan",
    "is_currently_present": true
  }
}
```

---

### Get Duration History
**`GET /sessions/history`**

**Fungsi**: Mendapatkan riwayat kehadiran dengan filter tanggal, orang, atau ruangan.

**Use Case**: Generate laporan kehadiran bulanan, analisis pola kunjungan.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `start_date` | datetime | Tanggal mulai (format ISO) |
| `end_date` | datetime | Tanggal akhir |
| `person_id` | string | Filter berdasarkan orang |
| `room_id` | string | Filter berdasarkan ruangan |

**Default**: 7 hari terakhir jika tidak ada filter tanggal.

---

### Get Person Current Location
**`GET /sessions/person/{person_id}/current`**

**Fungsi**: Mengetahui lokasi seseorang **saat ini**. Mengembalikan null jika orang tidak sedang hadir.

**Use Case**: "Di mana John Doe sekarang?"

---

### Get Room Occupants
**`GET /sessions/room/{room_id}/current`**

**Fungsi**: Mendapatkan daftar orang yang **sedang berada** di ruangan tertentu.

**Use Case**: "Siapa saja yang ada di Perpustakaan sekarang?"

---

### Assign Duration to Person
**`POST /sessions/assign/{duration_id}?person_id=uuid&confidence=0.95`**

**Fungsi**: Mengaitkan sesi guest/unknown dengan orang yang dikenali. Digunakan ketika sistem awalnya tidak mengenali seseorang, tapi kemudian berhasil mengidentifikasi.

**Use Case**: Koreksi data manual atau ketika face recognition berhasil setelah beberapa saat.

---

## 🔌 WebSocket Streaming

Real-time streaming untuk menampilkan video dan deteksi secara langsung.

---

### Camera Stream
**`WS /ws/camera/{camera_id}`**

**Fungsi**: Koneksi WebSocket untuk menerima frame video dan data deteksi secara real-time dari satu kamera.

**Use Case**: Live view kamera di dashboard dengan bounding box orang terdeteksi.

**Server → Client Message (setiap frame):**
```json
{
  "type": "frame",
  "camera_id": "uuid",
  "camera_name": "CAM_0",
  "room_name": "Perpustakaan",
  "timestamp": "2026-02-08T10:30:45",
  "detections": [
    {
      "track_id": "T1",
      "person_id": "uuid atau null",
      "person_name": "John Doe atau Guest-1",
      "nim_nip": "A11.2023.12345 atau null",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95,
      "is_guest": false
    }
  ],
  "frame_base64": "base64_encoded_jpeg"
}
```

**Client → Server Commands:**
```json
{"command": "ping"}
```

---

### All Cameras Stream
**`WS /ws/all-cameras`**

**Fungsi**: Aggregated stream dari semua kamera aktif dalam satu koneksi WebSocket.

**Use Case**: Dashboard dengan multi-camera view.

---

## 📊 Workflow Examples

### Flow 1: Setup Awal Sistem

```
1. POST /cameras/rooms         → Buat ruangan (dapat room_id)
2. POST /cameras               → Daftarkan kamera (dapat camera_id)  
3. Update .env                 → Set CAMERA_ID_1=camera_id
4. docker-compose up           → Start semua services
5. python start_webcam_captures.py → (Jika USB webcam)
```

### Flow 2: Mendaftarkan User Baru

```
1. Ambil foto wajah user (frontal, jelas, pencahayaan baik)
2. POST /users/register        → Upload foto + nama + NIM/NIP
3. Sistem otomatis akan mengenali wajah ini di kamera
```

### Flow 3: Monitor Real-time

```
1. GET /cameras/live/streams   → Dapat daftar WebSocket URL
2. Connect WS /ws/camera/{id}  → Terima frame + deteksi real-time
3. GET /sessions/active        → Dapat daftar orang yang sedang hadir
```

### Flow 4: Generate Laporan Kehadiran

```
1. GET /sessions/history?start_date=2026-02-01&end_date=2026-02-08
   → Dapat semua record kehadiran dalam rentang waktu
2. GET /sessions/person/{id}/stats   
   → Statistik individual (total waktu, jumlah sesi)
```

### Flow 5: Tracking Satu Orang

```
1. GET /users/search?query=john      → Cari orang berdasarkan nama
2. GET /users/{person_id}            → Detail + lokasi saat ini
3. GET /sessions/person/{id}/current → Sesi aktif (jika sedang hadir)
4. GET /sessions/person/{id}/stats   → Statistik total
```

---

## 📝 Response Format

**Success Response:**
```json
{
  "success": true,
  "message": "Human readable message",
  "data": { ... }
}
```

**Error Response:**
```json
{
  "detail": "Error description"
}
```

**HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad Request (validasi gagal) |
| `404` | Not Found |
| `409` | Conflict (duplikat) |
| `500` | Server Error |
