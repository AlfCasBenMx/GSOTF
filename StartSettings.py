"""Configuration is local XML plus environment overrides, never source secrets."""
import logging
import os
from pathlib import Path
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent
FIELDS = {
    "myClient": ("Cliente", "GDF_CLIENT"),
    "myStation": ("Estacion", "GDF_STATION"),
    "myPump": ("Bomba", "GDF_PUMP"),
    "myOCREndpoint": ("ocrendpoint", "GDF_OCR_ENDPOINT"),
    "ocrKey": ("ocrKey", "GDF_OCR_KEY"),
    "genyusKey": ("genyusKey", "GDF_GENYUS_KEY"),
    "accountName": ("accountName", "GDF_STORAGE_ACCOUNT"),
    "accountKey": ("accountKey", "GDF_STORAGE_KEY"),
    "containerName": ("containerName", "GDF_STORAGE_CONTAINER"),
}


def startVar(required=()):
    path = Path(os.environ.get("GDF_CONFIG", str(BASE_DIR / "Config.xml")))
    values = {}
    if path.exists():
        root = ET.parse(path).getroot()
        values = {node.tag: (node.text or "").strip() for node in root.iter()}
    settings = {name: os.environ.get(env, values.get(tag, "")).strip()
                for name, (tag, env) in FIELDS.items()}
    serial = os.environ.get("GDF_SERIAL", "").strip()
    if not serial:
        serial_path = Path("/sys/firmware/devicetree/base/serial-number")
        if serial_path.exists():
            serial = serial_path.read_text().strip("\x00\r\n ")[:16]
    settings["serialLiper"] = serial
    missing = [name for name in required if not settings.get(name)]
    if missing:
        raise ValueError("Missing configuration fields: " + ", ".join(missing))
    globals().update(settings)
    return settings


def SetMyLocalTime():
    # Time is managed by the OS (NTP), not unauthenticated HTTP responses.
    logging.getLogger("gdf").info("System time is managed by NTP; no manual clock change")
