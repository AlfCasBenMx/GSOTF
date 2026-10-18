"""Capture plates; intentionally OCR only the LAST detection per image."""
import os
import json
import signal
import threading
import time
from datetime import datetime

import HandlingEvents as events
import StartSettings
from runtime import BASE_DIR, OCRWorker, PlateGate


def constrainPoint(num, minimum=1, maximum=255):
    return max(min(num, maximum), minimum)


def main():
    log = events.setup_logging()
    camera = None
    worker = OCRWorker()
    lockfile = None
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        import fcntl
        lockfile = open(BASE_DIR / ".runtime.lock", "a")
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        StartSettings.startVar(required=("ocrKey", "myOCREndpoint", "genyusKey", "serialLiper"))
        import cv2
        import numpy as np
        import tensorflow as tf
        from object_detection.utils import label_map_util, visualization_utils as viz_utils
        from picamera2 import Picamera2
        from libcamera import controls
        import LiPER_NNP

        os.chdir(BASE_DIR)
        saved, temporary, regions, errors = [BASE_DIR / name for name in
            ("SavedPlates", "TempImages", "PlateRegionImage", "ErrorOCR")]
        for folder in (saved, temporary, regions, errors, BASE_DIR / "TempSavedImages"):
            folder.mkdir(exist_ok=True)
        camera = Picamera2()
        camera.configure(camera.create_preview_configuration(main={"size": (3200, 2592)}))
        camera.start()
        camera.set_controls({"AfMode": controls.AfModeEnum.Continuous})
        time.sleep(2)
        categories = label_map_util.create_category_index_from_labelmap(str(BASE_DIR / "label_map.pbtxt"))
        detector = tf.saved_model.load(str(BASE_DIR / "saved_model"))
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gate = PlateGate()
        display = os.environ.get("GDF_DISPLAY", "1") == "1"
        last_cleanup = time.monotonic()
        log.info("Camera and model ready; last-detection-only OCR enabled")
        last_health = 0
        while not stop.is_set():
            now = time.monotonic()
            if now - last_cleanup >= 120:
                worker.clean_temporary((temporary, regions))
                events.logSytem()
                last_cleanup = now
            stamp = datetime.now().strftime("%y%m%d%H%M%S%f")
            full = temporary / (stamp + ".jpg")
            camera.capture_file(str(full))
            image = cv2.imread(str(full))
            if image is None:
                raise RuntimeError("Camera image could not be decoded")
            height, width = image.shape[:2]
            tensor = tf.convert_to_tensor(image)[tf.newaxis, ...]
            raw = detector(tensor)
            count = int(raw.pop("num_detections"))
            detections = {key: value[0, :count].numpy() for key, value in raw.items()}
            detections["detection_classes"] = detections["detection_classes"].astype(np.int64)
            if time.monotonic() - last_health >= 5:
                health = BASE_DIR / ".health.json"
                pending = health.with_suffix(".tmp")
                pending.write_text(json.dumps({"pid": os.getpid(), "last_frame": time.time(),
                                              "detections": count}), encoding="utf-8")
                pending.replace(health)
                last_health = time.monotonic()
            if display:
                preview = image.copy()
                viz_utils.visualize_boxes_and_labels_on_image_array(
                    preview, detections["detection_boxes"], detections["detection_classes"],
                    detections["detection_scores"], categories, max_boxes_to_draw=200,
                    min_score_thresh=0.45, use_normalized_coordinates=True)
                cv2.imshow("frame", cv2.resize(preview, (1200, 800)))
            selected = np.where(detections["detection_scores"] >= 0.45)[0]
            if len(selected):
                index = selected[-1]  # Deliberate last-crop-only policy.
                box = detections["detection_boxes"][index]
                x, right = [int(constrainPoint(v, 0, width)) for v in
                            (box[1]*width-5, box[3]*width+5)]
                y, bottom = [int(constrainPoint(v, 0, height)) for v in
                             (box[0]*height-5, box[2]*height+5)]
                if right <= x or bottom <= y:
                    log.warning("Skipping empty detection box")
                    continue
                crop = regions / (str(index) + "_" + stamp + ".jpg")
                region = cv2.merge([clahe.apply(channel) for channel in cv2.split(image[y:bottom, x:right])])
                if not cv2.imwrite(str(crop), region, [cv2.IMWRITE_JPEG_QUALITY, 100]):
                    raise OSError("Could not save plate crop")
                point = (int(width*(box[3]+box[1])/2), int(height*(box[2]+box[0])/2))
                if gate.candidate(point, now) and worker.submit(
                        LiPER_NNP.Predicciones_BN, str(crop), str(full), str(saved), str(errors)):
                    gate.accepted()
            else:
                gate.absent(now)
            if display and cv2.waitKey(1) & 0xFF == ord("q"):
                break
        return 0
    except Exception:
        log.exception("Plate reader stopped by an error")
        return 1
    finally:
        worker.close()
        if camera is not None:
            try:
                camera.close()
            except Exception:
                log.exception("Camera cleanup failed")
        if "cv2" in locals():
            try:
                cv2.destroyAllWindows()
            except Exception:
                log.exception("Preview cleanup failed")
        if lockfile is not None:
            lockfile.close()


if __name__ == "__main__":
    raise SystemExit(main())
