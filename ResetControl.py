from contextlib import closing
"""Rate-limited reboot requests with persistent SQLite event history."""
from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import HandlingEvents as events
import SendNotifications

DB_PATH = Path(os.environ.get("GDF_STATE_DB", "/home/pi/LifeLiper.db"))


def readDBTest(NumberEvent=3):
    cutoff = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    with closing(sqlite3.connect(str(DB_PATH), timeout=5)) as conn, conn:
        return conn.execute("SELECT COUNT(*) FROM LogEventsLiper WHERE eventType=? AND datetime(timeEvent)>=?",
                            (NumberEvent, cutoff)).fetchone()[0]


def WriteEvent(NumberEvent):
    with closing(sqlite3.connect(str(DB_PATH), timeout=5)) as conn, conn:
        conn.execute("UPDATE LastEventsLiper SET timeEvent=datetime('now') WHERE id=?", (NumberEvent,))
        conn.execute("INSERT INTO LogEventsLiper(eventType) VALUES (?)", (NumberEvent,))


def ValidateReset(NumberEvent, ReasonReset):
    cutoff = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with closing(sqlite3.connect(str(DB_PATH), timeout=5)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM LogEventsLiper WHERE eventType=2 AND datetime(timeEvent)>=?",
                                 (cutoff,)).fetchone()[0]
            if count >= 3:
                events.logException("Reboot suppressed: three requests in 30 minutes")
                return False
            if os.environ.get("GDF_ALLOW_REBOOT") != "1":
                events.logException("Reboot disabled; request logged only")
                return False
            for event in dict.fromkeys((NumberEvent, 2)):
                conn.execute("UPDATE LastEventsLiper SET timeEvent=datetime('now') WHERE id=?", (event,))
                conn.execute("INSERT INTO LogEventsLiper(eventType) VALUES (?)", (event,))
        SendNotifications.sendResetWarning(ReasonReset)
        events.rebootDevice()
        return True
    except Exception:
        events.setup_logging().exception("Reboot request failed")
        return False
