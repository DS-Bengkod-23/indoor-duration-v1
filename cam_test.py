# cam_test.py
import cv2
import time

cam_index = 0
cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)  # ← pakai DirectShow

# kecilin resolusi & fps biar enteng
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
cap.set(cv2.CAP_PROP_FPS, 15)

if not cap.isOpened():
    print(f"Gagal buka kamera {cam_index}")
    exit()

prev = time.time()
cnt = 0

while True:
    ok, frame = cap.read()
    if not ok:
        print("❌ Gagal grab frame")
        break

    cnt += 1
    if cnt >= 10:
        now = time.time()
        fps = cnt / (now - prev)
        prev = now
        cnt = 0
        cv2.putText(frame, f"{fps:.1f} FPS", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("TEST CAMERA", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
