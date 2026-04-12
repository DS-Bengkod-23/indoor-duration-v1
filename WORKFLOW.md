# Workflow Sistem: Indoor Duration Tracker v1 📹🤖

Sistem ini adalah aplikasi pelacakan durasi pengunjung dalam ruangan menggunakan Multi-Camera AI Tracking. Berdasarkan arsitektur kode saat ini, berikut adalah representasi workflow sistemnya:

## 🧭 Diagram Arsitektur (Mermaid)

```mermaid
flowchart TD
    subgraph Initialization
    A[START: Main.py] --> B[Load Config & Warming Up AI]
    B --> C[Init VideoSystem]
    end

    subgraph Video Capture (Multi-Threading)
    C --> D{Kamera Paralel: ThreadPoolExecutor}
    D -->|Cam 0| E1[SmartVideoCapture: Anti-Delay]
    D -->|Cam N| E2[SmartVideoCapture: Anti-Delay]
    end

    subgraph Tracking & Detection per Area
    E1 --> F1[MultiObjectTracker]
    E2 --> F2[MultiObjectTracker]
    
    F1 --> G1[Deteksi Wajah: YuNet]
    F1 --> G2[Deteksi Badan: YOLOv8]
    
    G1 --> H1[Tracking Frame: DeepSORT]
    G2 --> H1
    end

    subgraph Feature Extraction & Identity Matching
    H1 --> I[Ekstraksi Box & Tracking ID]
    I --> J[Face Recognizer: Ekstrak Wajah]
    I --> K[OSNet: Ekstrak Baju/Badan]
    
    J --> L[FaceBodyFusion]
    K --> L
    
    L --> M[Global Identity Manager & Registries]
    end

    subgraph Presence Logging & UI
    M --> N[PresenceManager: Cek Masuk / Keluar]
    N -->|INDOOR| O[Mulai Hitung Waktu & Simpan Foto]
    N -->|OUTDOOR| P[Stop Timer & Catat ke CSV]
    
    N --> Q[Visualizer: Gambar Bounding Box]
    Q --> R[Dashboard UI Streamlit]
    end
```

---

## 📝 Penjelasan Flow per Komponen

1. **Inisialisasi & Startup (`Main.py` & `indoor.video.VideoSystem`)**:
   - Sistem membaca pengaturan target kamera (`SETTINGS` di `config.settings.py`).
   - Melakukan "Warming Up" model AI (YOLO, OSNet, YuNet) untuk melancarkan load pipeline pada GPU/CPU menggunakan `torch` dan `cv2` dengan thread yang di-limit ke-1 (Mencegah thread contention lag).
   - `ThreadPoolExecutor` disiapkan untuk menjalankan pembacaan tiap kamera secara paralel.

2. **Pengambilan Frame Video (`indoor.smart_camera.SmartVideoCapture`)**:
   - Setiap kamera dipegang oleh thread terpisah. Buffer size diset spesifik (biasanya 1 atau minimal) untuk **menghindari delay/lag** CCTV, memastikan frame yang diproses selalu _real-time_.

3. **Deteksi Objek (`indoor.person_detector.py` & `indoor.face_detector.py`)**:
   - Frame tiap kamera diteruskan ke `MultiObjectTracker`.
   - **YuNet** digunakan khusus untuk mendeteksi wajah dengan sangat cepat, sementara **YOLOv8** digunakan untuk mendeteksi _bounding box_ seisi tubuh.

4. **Tracking Sementara (`indoor.tracker_deepsort.py`)**:
   - **DeepSORT** mengambil _bounding box_ dari YOLO/YuNet dari frame ke frame lalu memberikan UUID statis sementara untuk setiap orang supaya tidak patah-patah pergerakannya di dalam 1 kamera.

5. **Pengenalan Identitas (`indoor.fusion.py`, `indoor.osnet...`, `indoor.registry.py`)**:
   - Data visual dari tubuh (baju, dll) di-embed menjadi vektor memakai **OSNet** (`extract_body_feature`), sedangkan dataset Wajah difilter menggunakan **Face Recognizer**.
   - **FaceBodyFusion** bertugas menentukan apakah fitur yang terlihat sudah ada di _registry/database_ memori agar nama aslinya dimunculkan. Apabila ada tombol 'r' / registrasi manual ditekan (Lihat `handle_registration`), fitur akan ditambahkan ke dataset ID orang tersebut.

6. **Sinkronisasi Multi-Kamera (`indoor.id_lock.py` & `GlobalIdentityManager`)**:
   - Fitur `try_claim_identity` di GlobalIdentityManager bertugas mencegah orang yang berjalan dari Kamera A ke Kamera B dianggap "double identity" _(ping-pong hopping)_ pada waktu yang sama. Hal ini memastikan IDs stabil di seluruh ruangan.

7. **Sistem Kehadiran / Presence & Waktu (`indoor.presence_manager.py`)**:
   - State Machine yang bertugas menilai **PENDING \-\> INDOOR \-\> UNKNOWN \-\> OUTDOOR**.
   - Jika sistem mantap mengenali AI dengan konsisten, maka status menjadi INDOOR (`in_time` dimulai). Apabila identitas AI blank sebentar (karena halangan pilar, dsb), sistem menjadikannya _tentative / UNKNOWN_ sebelum akhirnya diubah OUTDOOR dan waktunya dikalkulasi, kemudian foto/log diakhiri (`_append_log` hingga ke `CSV`).

8. **Visualisasi (`indoor.visualizer.py` & `dashboard.py`)**:
   - Semua bounding box, nama, info status INDOOR ditaruh di frame lalu ditampilkan langsung ke UI baik via _Grid Layout_ CV2 atau via Dashboard web berbasis Streamlit.
