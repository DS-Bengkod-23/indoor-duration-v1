# main.py
from indoor.video import VideoSystem

def main():
    print("=== MULTI CAMERA AI-TRACKING ===")
    system = VideoSystem(max_cameras=1)

    try:
        system.run()
    except KeyboardInterrupt:
        system.stop()

if __name__ == "__main__":
    main()
