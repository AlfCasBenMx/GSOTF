"""Thread-safe rotating logs; no log handler mutation for each event."""
import logging
import os
from logging.handlers import RotatingFileHandler
import re
import socket
import subprocess
import threading
from pathlib import Path

import psutil

BASE_DIR = Path(__file__).resolve().parent
_lock = threading.Lock()


class RedactSecrets(logging.Filter):
    def filter(self, record):
        import StartSettings
        message = record.getMessage()
        for name in ("ocrKey", "genyusKey", "accountKey"):
            value = getattr(StartSettings, name, "")
            if value:
                message = message.replace(value, "[REDACTED]")
        message = re.sub(r"([?&]code=)[^\s&]+", r"\1[REDACTED]", message)
        record.msg, record.args = message, ()
        return True


class SafeFormatter(logging.Formatter):
    def format(self, record):
        import StartSettings
        text = super().format(record)
        values = [getattr(StartSettings, name, "") for name in ("ocrKey", "genyusKey", "accountKey")]
        values += [value for key, value in os.environ.items()
                   if key.startswith("GDF_") and any(word in key for word in ("KEY", "PASSWORD", "TOKEN", "URL"))]
        for value in values:
            if value:
                text = text.replace(value, "[REDACTED]")
        return re.sub(r"([?&]code=)[^\s&]+", r"\1[REDACTED]", text)


def setup_logging():
    logger = logging.getLogger("gdf")
    with _lock:
        if not logger.handlers:
            folder = BASE_DIR / "Logs"
            folder.mkdir(exist_ok=True)
            handler = RotatingFileHandler(folder / "runtime.log", maxBytes=5*1024*1024,
                                          backupCount=5, encoding="utf-8")
            handler.setFormatter(SafeFormatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
            handler.addFilter(RedactSecrets())
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    return logger


def logEvent(description):
    setup_logging().info("%s", description)


def logException(description):
    setup_logging().error("%s", description)


def logPlates(plate, imagefull):
    logEvent("Plate accepted by API: %s image=%s" % (plate, imagefull))


def logPlatesPattern(imagefull, plate, pattern):
    logEvent("Plate pattern: %s %s %s" % (plate, pattern, imagefull))


def connect(host="8.8.8.8"):
    try:
        with socket.create_connection((host, 53), timeout=2):
            return True
    except OSError:
        return False


def logInternt(status):
    logEvent("Internet: %s" % status)


def detailSystem():
    result = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True,
                            text=True, timeout=3, check=True)
    return "%s CPU=%s RAM=%s" % (result.stdout.strip(), psutil.cpu_percent(), psutil.virtual_memory().percent)


def logSytem():
    try:
        logEvent(detailSystem() + " Internet: " + str(connect()))
    except Exception:
        setup_logging().exception("Could not collect system metrics")


def rebootDevice():
    subprocess.run(["sudo", "-n", "systemctl", "reboot"], check=True, timeout=10)
