# main.py
import os
import warnings
import sys

# 1. Sembunyikan Warning Sampah (InsightFace / Numpy FutureWarnings)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Redirect stderr sementara untuk suppress log library yang berisik (Opsional)
# sys.stderr = open(os.devnull, 'w') 

from indoor.video import VideoSystem
from indoor.utils import logger # 🔥 IMPOR LOGGER INDUSTRIAL

def main():
    print("==========================================")
    print("   MULTI-CAMERA AI TRACKING SYSTEM")
    print("   STATUS: READY (INDUSTRIAL GRADE v10.0)")
    print("==========================================")
    
    logger.info("========== [SYSTEM STARTUP] ==========")
    logger.info("Menginisialisasi Sistem Kamera...")

    from config.settings import SETTINGS
    from indoor.utils import validate_settings
    
    if not validate_settings(SETTINGS):
        logger.critical("[STOP] Konfigurasi Invalid. Periksa settings.py.")
        return # Exit graceful

    # Ambil max_cameras langsung dari Settings
    target_cam_count = SETTINGS.get("max_cameras", 1)
    logger.info(f"Target Kamera dari Config: {target_cam_count}")
    
    system = VideoSystem(max_cameras=target_cam_count) 

    try:
        logger.info("Sistem berjalan (Main Loop Active).")
        system.run()
    except KeyboardInterrupt:
        print("\n[STOP] Menghentikan sistem...")
        logger.warning("[SYSTEM SHUTDOWN] User menekan Ctrl+C.")
        # system.stop() # Main run loop will exit naturally via KeyboardInterrupt typically, or handled internally
    except Exception as e:
        print(f"\n[ERROR] Terjadi kesalahan fatal: {e}")
        logger.critical(f"[FATAL ERROR] System Crash: {e}", exc_info=True)
        # system.stop()
    finally:
        logger.info("========== [SYSTEM OFFLINE] ==========")

if __name__ == "__main__":
    main()