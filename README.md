# 📹 Multi-Camera AI Tracking System (Platinum Master v12.20)

**Status**: 🟢 Production Ready (Industrial Grade)
**Engine**: DeepSort + OSNet ReID + YOLOv8 + RetinaFace

## 🚀 Overview
Sistem pelacakan multi-kamera cerdas yang dirancang untuk mengenali identitas individu lintas ruangan ("Re-Identification"). Versi ini telah dioptimalkan untuk kondisi **Tampak Belakang**, **Cahaya Redup**, dan **Keamanan Identitas Tinggi**.

Fitur Unggulan (v12.20):
1.  **Back View Recognition**: Mengenali punggung orang (jika orang tersebut aktif di gedung) dengan *Blind Active Boost*.
2.  **Ambiguity Guard**: Menolak tebakan jika ada 2 orang dengan baju mirip (cegah salah orang).
3.  **Face Veto**: Koreksi otomatis jika wajah terdeteksi berbeda dengan prediksi baju.
4.  **Anti-Float**: Stabil saat subjek duduk atau diam lama.

## 🛠️ Installation

Pastikan environment Python sudah terinstall.

```bash
pip install numpy opencv-python torch torchvision ultralytics insightface -q
```

## 🎮 How to Run

1.  **Jalankan Sistem**:
    ```bash
    python Main.py
    ```

2.  **Kontrol Keyboard**:
    *   `q`: Quit (Keluar)
    *   `r`: Register (Daftar Wajah Baru - Lihat Panduan Registrasi)
    *   `x`: Hard Reset (Hapus semua tracking & mulai dari nol)
    *   `d`: Toggle Debug Info

## 📝 Registration Guide (PENTING!)
Agar sistem bekerja maksimal, ikuti cara daftar ini:
1.  Tekan `r`.
2.  **Tunjukkan Wajah** ke kamera (sampai kotak hijau muncul).
3.  **Muter Badan (360 Derajat)** pelan-pelan agar sistem merekam baju dari belakang & samping.
4.   selesai.

## 🛡️ Security Features
*   **Ambiguity Rejection**: Jika skor kemiripan antara "Ilham" dan "Fatih" beda tipis (< 5%), sistem akan melabeli "Unknown" sampai ada konfirmasi visual lebih jelas.
*   **Hijack Guard**: Jika skor drop drastis (< 0.45) saat orang berpapasan, tracking otomatis dilepas.

## ⚙️ Configuration
Pengaturan ada di `config/settings.py`.
*   `max_cameras`: Jumlah kamera.
*   `thresh_diff_room`: Sensitivitas blind lookup.
*   `camera_indexes`: Alamat IP Camera (RTSP) atau Index USB.

---
**Developed by Antigravity AI**
*Platinum Master Release v12.20*
