"""Isolated heavy probes. No credentials, network, OCR calls or persisted photos."""
import os
from pathlib import Path
import sys
import time


def main():
    kind, folder = sys.argv[1:]
    root = Path(folder)
    os.chdir(str(root))
    sys.path.insert(0, str(root))
    if kind in ('imports', 'environment'):
        import cv2
        import tensorflow
        import psutil
        import LiPER_NNP
        import Send_HB
        from object_detection.utils import label_map_util, visualization_utils
        from picamera2 import Picamera2
        from libcamera import controls
        from azure.cognitiveservices.vision.computervision import ComputerVisionClient
        import serial
        import requests
        import msrest
        if kind == 'environment':
            import tkinter
            import json
            import numpy
            import google.protobuf
            assert sys.version_info[:2] == (3, 9)
            assert tensorflow.__version__.startswith('2.12.')
            assert numpy.__version__ == '1.23.5'
            assert google.protobuf.__version__.startswith('3.20.')
            print(json.dumps({'compatible': True, 'python': sys.version.split()[0],
                              'tensorflow': tensorflow.__version__, 'numpy': numpy.__version__}))
    elif kind == 'model':
        import tensorflow as tf
        from object_detection.utils import label_map_util
        label_map_util.create_category_index_from_labelmap(str(root / 'label_map.pbtxt'))
        detector = tf.saved_model.load(str(root / 'saved_model'))
        result = detector(tf.zeros((1, 2592, 3200, 3), dtype=tf.uint8))
        assert all(k in result for k in ('num_detections', 'detection_boxes', 'detection_classes', 'detection_scores'))
    elif kind == 'camera':
        from picamera2 import Picamera2
        from libcamera import controls
        camera = Picamera2()
        try:
            camera.configure(camera.create_preview_configuration(main={'size': (3200, 2592)}))
            camera.start()
            camera.set_controls({'AfMode': controls.AfModeEnum.Continuous})
            time.sleep(2)
            frame = camera.capture_array()
            assert frame is not None and frame.size > 0
        finally:
            camera.close()
    else:
        raise ValueError('Unknown probe')


if __name__ == '__main__':
    main()
