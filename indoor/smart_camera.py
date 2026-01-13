
import cv2
import time
import threading

class SmartVideoCapture:
    def __init__(self, source, name="Cam"):
        self.source = source
        self.name = name
        self.cap = cv2.VideoCapture(self.source)
        self.q = []
        self.status = self.cap.isOpened()
        self.running = True
        self.lock = threading.Lock()
        
        # Simpan preferensi resolusi agar tidak reset saat reconnect
        self.target_width = None
        self.target_height = None
        
        # Buffer reader thread
        self.thread = threading.Thread(target=self._reader)
        self.thread.daemon = True
        self.thread.start()

    def _reader(self):
        while self.running:
            if not self.status:
                # 🔥 LOGIKA AUTO-RECONNECT 🔥
                # print(f"[{self.name}] Koneksi putus/init... Reconnect dalam 2 detik...")
                time.sleep(2.0)
                try:
                    with self.lock:
                        self.cap.release()
                        self.cap = cv2.VideoCapture(self.source)
                        if self.cap.isOpened():
                            print(f"[{self.name}] ✅ Berhasil Terhubung/Reconnect!")
                            # Set buffer size agar real-time (PENTING untuk RTSP)
                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            
                            # 🔥 TERAPKAN ULANG SETTING SETELAH RECONNECT 🔥
                            if self.target_width: 
                                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
                            if self.target_height:
                                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
                                
                            self.status = True
                except:
                    pass
                continue

            with self.lock:
                ret = False
                frame = None
                if self.cap.isOpened():
                    ret, frame = self.cap.read()
            
            if not ret:
                # print(f"[{self.name}] ⚠️ Gagal baca frame/Stream habis.")
                self.status = False
                continue
            
            # Simpan frame terbaru saja (buang yang lama biar real-time)
            self.q = [frame]
            time.sleep(0.005) # Yield cpu dikit

    def read(self):
        if self.q:
            return True, self.q[-1]
        return False, None

    def set(self, propId, value):
        with self.lock:
            if self.cap.isOpened():
                self.cap.set(propId, value)
            
            # 🔥 SIMPAN PREFERENSI AGAR TIDAK HILANG SAAT RECONNECT 🔥
            if propId == cv2.CAP_PROP_FRAME_WIDTH:
                self.target_width = value
            elif propId == cv2.CAP_PROP_FRAME_HEIGHT:
                self.target_height = value

    def release(self):
        self.running = False
        with self.lock:
            if self.cap: self.cap.release()
