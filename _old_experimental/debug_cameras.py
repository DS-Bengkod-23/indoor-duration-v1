
import cv2
import sys
import os

# Adds current directory to python path to import config
sys.path.append(os.getcwd())


try:
    with open("camera_log.txt", "w") as log:
        def log_print(msg):
            print(msg)
            log.write(str(msg) + "\n")

        from config.settings import SETTINGS
        log_print("\n[INFO] Loaded settings successfully.")
        log_print(f"[INFO] Max Cameras: {SETTINGS.get('max_cameras')}")
        log_print(f"[INFO] Camera Indexes: {SETTINGS.get('camera_indexes')}")
        
        sources = SETTINGS["camera_indexes"][:SETTINGS.get("max_cameras", 1)]
        log_print(f"[INFO] Active Sources to Try: {sources}")
        
        for i, src in enumerate(sources):
            log_print(f"\nScanning Source {i}: {src}")
            cap = cv2.VideoCapture(src)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    log_print(f"  [SUCCESS] Camera {i} is OPEN and reading frames.")
                    log_print(f"  Resolution: {frame.shape[1]}x{frame.shape[0]}")
                else:
                    log_print(f"  [WARNING] Camera {i} is OPEN but returned NO frame (ret=False).")
                cap.release()
            else:
                log_print(f"  [FAILURE] Camera {i} FAILED to open.")
                if isinstance(src, str) and src.startswith("http"):
                    log_print("    -> Check IP address, network connection, or if URL is correct.")

except Exception as e:
    with open("camera_log.txt", "a") as log:
        log.write(f"[ERROR] Exception during check: {e}\n")
    import traceback
    traceback.print_exc()

print("\n[DONE] Check complete.")
