"""Manual camera check, with guaranteed resource cleanup."""
from datetime import datetime
from runtime import BASE_DIR


def main():
    from picamera2 import Picamera2
    camera = Picamera2()
    try:
        camera.configure(camera.create_still_configuration(main={"size": (2560, 1440)}))
        camera.start()
        folder = BASE_DIR / "TempImages"
        folder.mkdir(exist_ok=True)
        camera.capture_file(str(folder / (datetime.now().strftime("%y%m%d%H%M%S%f") + ".jpg")))
    finally:
        camera.close()


if __name__ == "__main__":
    main()
