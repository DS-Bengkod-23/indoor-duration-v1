# cam_test_ip.py
import cv2, time, sys, requests

base = "http://192.168.42.245:8080"   # ganti kalau perlu
candidates = [base, base + "/video", base + "/shot.jpg", base + "/mjpeg", base + "/cam.mjpeg"]

print("Trying endpoints:", candidates)
for url in candidates:
    try:
        print("→ trying", url)
        # quick HEAD to check reachable (not all endpoints support HEAD)
        try:
            r = requests.get(url, timeout=2, stream=True)
            print("  HTTP status:", r.status_code)
            r.close()
        except Exception as e:
            print("  HTTP check failed:", repr(e))

        cap = cv2.VideoCapture(url)
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            print("  SUCCESS on:", url)
            # show briefly
            cv2.imshow("TEST", cv2.resize(frame, (640,360)))
            cv2.waitKey(2000)
            cv2.destroyAllWindows()
            sys.exit(0)
        else:
            print("  no frame from", url)
    except Exception as e:
        print("  error:", repr(e))

print("No working endpoint found. Try checking app docs or use VLC to find URL.")
