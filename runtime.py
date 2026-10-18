"""Small, hardware-independent helpers for the capture loop."""
import logging
import math
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("gdf")


class PlateGate:
    """Keep the original moving capture plus two stationary OCR attempts."""
    def __init__(self):
        self.previous = None
        self.stationary = 0
        self.last_seen = None
        self.moved = False

    def candidate(self, point, now=None):
        now = time.monotonic() if now is None else now
        if self.last_seen is not None and now - self.last_seen >= 5:
            self.previous = None
            self.stationary = 0
        moved = self.previous is None or math.dist(point, self.previous) >= 60
        self.moved = moved
        self.previous = point
        self.last_seen = now
        if moved:
            self.stationary = 0
        return moved or self.stationary < 2

    def accepted(self):
        if not self.moved:
            self.stationary += 1

    def absent(self, now=None):
        now = time.monotonic() if now is None else now
        if self.last_seen is not None and now - self.last_seen >= 5:
            self.previous = None
            self.stationary = 0


class OCRWorker:
    """One OCR request at a time, no unbounded pending queue."""
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self.slot = threading.BoundedSemaphore(1)
        self.lock = threading.Lock()
        self.active = set()

    def submit(self, target, crop, full, saved, errors):
        if not self.slot.acquire(blocking=False):
            return False
        paths = {Path(crop).resolve(), Path(full).resolve()}
        try:
            # Protect inputs before another thread can clean them.
            with self.lock:
                self.active.update(paths)
            Path(saved).mkdir(parents=True, exist_ok=True)
            shutil.copy2(full, Path(saved) / Path(full).name)
            self.pool.submit(self._run, target, paths, crop, full, saved, errors)
            return True
        except Exception:
            with self.lock:
                self.active.difference_update(paths)
            self.slot.release()
            log.exception("Could not queue OCR capture")
            return False

    def _run(self, target, paths, *args):
        try:
            target(*args)
        except Exception:
            log.exception("OCR worker failed")
        finally:
            with self.lock:
                self.active.difference_update(paths)
            self.slot.release()

    def clean_temporary(self, folders, age=120):
        cutoff = time.time() - age
        with self.lock:
            for folder in folders:
                for path in Path(folder).glob("*.jpg"):
                    try:
                        if path.resolve() not in self.active and path.stat().st_mtime < cutoff:
                            path.unlink()
                    except OSError:
                        log.exception("Temporary image cleanup failed")

    def close(self):
        self.pool.shutdown(wait=True)
