"""Send actual device metrics; unsupported readings are reported as unknown."""
import subprocess
import time
import os
import json
import socket
import http.client
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import psutil
import HandlingEvents as events
import StartSettings


def collect_metrics():
    temperature = low_voltage = "unknown"
    try:
        temperature = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True,
            text=True, timeout=3, check=True).stdout.strip().replace("temp=", "").replace("'C", "")
        raw = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
            text=True, timeout=3, check=True).stdout.strip().split("=")[-1]
        low_voltage = "1" if int(raw, 16) & 1 else "0"
    except (OSError, ValueError, subprocess.SubprocessError):
        events.setup_logging().exception("Could not read device sensors")
    before = psutil.net_io_counters(pernic=True)
    start = time.monotonic()
    time.sleep(0.25)
    after = psutil.net_io_counters(pernic=True)
    elapsed = time.monotonic() - start
    total = sum(max(0, after[n].bytes_sent + after[n].bytes_recv - b.bytes_sent - b.bytes_recv)
                for n, b in before.items() if n in after and n in ("eth0", "wlan0"))
    return {"serialLiper": StartSettings.serialLiper, "temperature": temperature,
            "CPU": psutil.cpu_percent(), "RAM": psutil.virtual_memory().percent,
            "speedNetwork": str(round(total * 8 / elapsed / 1_000_000, 3)),
            "lowVoltage": low_voltage}


def hbGenys(metrics=None):
    from LiPER_NNP import get_token, make_api_request
    token = get_token()
    if not token:
        raise RuntimeError("Heartbeat authentication failed")
    data = {"metadata": {"url": "/MexGasStation", "service": "/postLiperStatus"},
            "payload": collect_metrics() if metrics is None else metrics}
    success, _, status = make_api_request("https://uat-genyus.ey.com/appSecServ/receiveConnect",
        {"apikey": StartSettings.genyusKey, "Authorization": "Bearer " + token,
         "Content-Type": "application/json"}, data)
    if not success:
        raise RuntimeError("Heartbeat rejected, HTTP %s" % status)
    return True


def secondary_payload(metrics):
    now = time.time()
    reader = {"status": "unknown", "last_frame_at": None, "frame_age_seconds": None}
    try:
        state = json.loads((Path(__file__).resolve().parent / ".health.json").read_text())
        age = max(0, now - float(state["last_frame"]))
        reader = {"status": "healthy" if age <= 30 else "stale",
                  "last_frame_at": datetime.fromtimestamp(state["last_frame"], timezone.utc).isoformat(),
                  "frame_age_seconds": round(age, 1)}
    except (OSError, ValueError, TypeError, KeyError):
        events.logEvent("Secondary heartbeat: reader health is unavailable")
    return {"schema_version": 1, "device_label": os.environ.get("GDF_HEALTH_LABEL", socket.gethostname()),
            "sent_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "metrics": metrics, "reader": reader}


def send_secondary(metrics):
    endpoint = os.environ.get("GDF_HEALTH_URL", "").strip()
    token = os.environ.get("GDF_HEALTH_TOKEN", "").strip()
    if not endpoint:
        return None
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Secondary heartbeat requires an HTTPS URL without embedded credentials")
    if not token:
        raise ValueError("GDF_HEALTH_TOKEN is missing")
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=8)
    try:
        conn.request("POST", target, body=json.dumps(secondary_payload(metrics)),
                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise RuntimeError("Secondary heartbeat rejected, HTTP %d" % response.status)
        # Do not follow redirects or repeat POST requests automatically.
        events.logEvent("Secondary heartbeat accepted")
        return True
    finally:
        conn.close()


def HBeat():
    metrics = collect_metrics()
    # Independent requests: a failure or slow destination cannot prevent the other attempt.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="heartbeat") as pool:
        destinations = {"genyus": pool.submit(hbGenys, metrics)}
        if os.environ.get("GDF_HEALTH_URL", "").strip():
            destinations["secondary"] = pool.submit(send_secondary, metrics)
        results = {}
        for name, future in destinations.items():
            try:
                results[name] = future.result()
            except Exception:
                results[name] = False
                events.setup_logging().exception("Heartbeat destination failed: %s", name)
    return results


if __name__ == "__main__":
    StartSettings.startVar(required=("genyusKey", "serialLiper"))
    HBeat()
