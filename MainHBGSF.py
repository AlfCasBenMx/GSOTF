"""Independent heartbeat process, with graceful shutdown."""
import signal
import threading
import time
import HandlingEvents as events
import StartSettings


def main():
    log = events.setup_logging()
    StartSettings.startVar(required=("genyusKey", "serialLiper"))
    import Send_HB as heartbeat
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        started = time.monotonic()
        try:
            events.logSytem()
            heartbeat.HBeat()
        except Exception:
            log.exception("Heartbeat failed")
        stop.wait(max(0, 30 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
