import ast
from contextlib import closing
from datetime import datetime, timedelta
import importlib
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from runtime import OCRWorker, PlateGate
import Deletefiles
import HandlingEvents
import StartSettings
import ResetControl
import LiPER_NNP


class ReliabilityTests(unittest.TestCase):
    def test_all_python_parses_on_target_interpreter(self):
        for path in ROOT.rglob("*.py"):
            if "credentials-local" not in path.parts:
                with self.subTest(path=path.name):
                    ast.parse(path.read_bytes(), filename=str(path))

    def test_stationary_limit_movement_and_absence_reset(self):
        gate = PlateGate()
        for now in (0, 1, 2):
            self.assertTrue(gate.candidate((100, 100), now))
            gate.accepted()
        self.assertFalse(gate.candidate((100, 100), 3))
        self.assertTrue(gate.candidate((200, 100), 4))
        gate.accepted()
        self.assertTrue(gate.candidate((200, 100), 5))
        gate.accepted()
        gate.absent(11)
        self.assertTrue(gate.candidate((200, 100), 12))

    def test_worker_limits_and_protects_inflight_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            crop, full = base / "crop.jpg", base / "full.jpg"
            crop.write_bytes(b"crop")
            full.write_bytes(b"full")
            old = time.time() - 1000
            for p in (crop, full):
                os.utime(p, (old, old))
            started, release = threading.Event(), threading.Event()
            def target(*args):
                started.set()
                release.wait(5)
            worker = OCRWorker()
            try:
                self.assertTrue(worker.submit(target, str(crop), str(full), str(base / "saved"), str(base / "errors")))
                self.assertTrue(started.wait(2))
                self.assertFalse(worker.submit(target, str(crop), str(full), str(base / "saved"), str(base / "errors")))
                worker.clean_temporary([base])
                self.assertTrue(crop.exists())
                self.assertTrue(full.exists())
                self.assertTrue((base / "saved" / "full.jpg").exists())
            finally:
                release.set()
                worker.close()
            worker.clean_temporary([base])
            self.assertFalse(crop.exists())

    @patch.object(HandlingEvents, "logEvent")
    def test_retention_dry_run_both_folders_and_age(self, _log):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_files, recent_files = [], []
            now = time.time()
            for name in ("SavedPlates", "ErrorOCR"):
                folder = root / name
                folder.mkdir()
                old, recent = folder / "old.jpg", folder / "recent.jpg"
                old.write_bytes(b"old")
                recent.write_bytes(b"new")
                os.utime(old, (now - 21*86400, now - 21*86400))
                old_files.append(old)
                recent_files.append(recent)
            self.assertEqual(len(Deletefiles.cleanup(root, min_free_bytes=0)), 2)
            self.assertTrue(all(p.exists() for p in old_files))
            Deletefiles.cleanup(root, min_free_bytes=0, apply=True)
            self.assertTrue(all(not p.exists() for p in old_files))
            self.assertTrue(all(p.exists() for p in recent_files))

    @patch.object(HandlingEvents, "logEvent")
    def test_low_disk_floor_prunes_oldest_but_preserves_new_capture(self, _log):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "SavedPlates"
            folder.mkdir()
            old, new = folder / "old.jpg", folder / "new.jpg"
            old.write_bytes(b"a" * 100)
            new.write_bytes(b"b")
            os.utime(old, (time.time()-300, time.time()-300))
            with patch.object(Deletefiles.shutil, "disk_usage", return_value=Mock(free=0)):
                selected = Deletefiles.cleanup(root, min_free_bytes=1, apply=True)
            self.assertEqual(selected, [str(old)])
            self.assertTrue(new.exists())

    def test_configuration_required_fields_fail_and_env_override(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "Config.xml"
            config.write_text('<Config><ocrKey>old</ocrKey></Config>')
            with patch.dict(os.environ, {"GDF_CONFIG": str(config), "GDF_OCR_KEY": "new", "GDF_SERIAL": "test"}, clear=True):
                values = StartSettings.startVar(required=("ocrKey", "serialLiper"))
                self.assertEqual(values["ocrKey"], "new")
                with self.assertRaisesRegex(ValueError, "genyusKey"):
                    StartSettings.startVar(required=("genyusKey",))

    def test_post_timeout_is_not_retried(self):
        with patch.object(LiPER_NNP.http.client, "HTTPSConnection") as factory, patch.object(HandlingEvents, "setup_logging"):
            factory.return_value.request.side_effect = TimeoutError()
            self.assertEqual(LiPER_NNP.make_api_request("https://example.invalid/api", {}), (False, None, 0))
            self.assertEqual(factory.call_count, 1)
            factory.return_value.close.assert_called_once()

    def test_ocr_constructor_failure_preserves_both_archive_copies(self):
        # Use the installed SDK type, but never create a real client or send traffic.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            full, crop = root / "full.jpg", root / "crop.jpg"
            full.write_bytes(b"photo")
            crop.write_bytes(b"crop")
            saved, errors = root / "SavedPlates", root / "ErrorOCR"
            saved.mkdir()
            (saved / full.name).write_bytes(full.read_bytes())
            with patch("azure.cognitiveservices.vision.computervision.ComputerVisionClient", side_effect=RuntimeError("client failed")), \
                 patch.object(LiPER_NNP, "validate_credentials", return_value=True), \
                 patch.object(StartSettings, "ocrKey", "test", create=True), \
                 patch.object(StartSettings, "myOCREndpoint", "https://example.invalid", create=True), \
                 patch.object(LiPER_NNP, "sendPlate") as send, \
                 patch.object(LiPER_NNP.SendEmail, "sendErrorAlert"), \
                 patch.object(HandlingEvents, "logEvent"), \
                 patch.object(HandlingEvents, "setup_logging"):
                LiPER_NNP.Predicciones_BN(str(crop), str(full), str(saved), str(errors))
            send.assert_called_once_with([], str(full))
            self.assertEqual((saved / full.name).read_bytes(), b"photo")
            self.assertEqual((errors / full.name).read_bytes(), b"photo")

    def test_ocr_closes_file_and_client_if_submission_fails(self):
        from azure.cognitiveservices.vision.computervision import ComputerVisionClient
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "image.jpg"
            image.write_bytes(b"photo")
            fake = Mock()
            fake.read_in_stream.side_effect = TimeoutError("submission timed out")
            with patch("azure.cognitiveservices.vision.computervision.ComputerVisionClient", return_value=fake), \
                 patch.object(LiPER_NNP, "validate_credentials", return_value=True), \
                 patch.object(StartSettings, "ocrKey", "test", create=True), \
                 patch.object(StartSettings, "myOCREndpoint", "https://example.invalid", create=True), \
                 patch.object(LiPER_NNP, "sendPlate"), \
                 patch.object(LiPER_NNP.SendEmail, "sendErrorAlert"), \
                 patch.object(HandlingEvents, "logEvent"), \
                 patch.object(HandlingEvents, "setup_logging"):
                LiPER_NNP.Predicciones_BN(str(image), str(image), str(root / "saved"), str(root / "errors"))
            fake.close.assert_called_once()
            self.assertTrue(fake.read_in_stream.call_args[0][0].closed)

    def test_sensor_frame_returns_millimetres(self):
        import MaxbotixTTL
        port = Mock()
        port.read.side_effect = [b'R', b'0', b'1', b'2', b'3', b'\r']
        self.assertEqual(MaxbotixTTL.measure(port), 123)
        port.close.assert_not_called()

    def test_429_retry_and_successful_empty_response(self):
        rejected = Mock(status=429, reason="limit")
        rejected.read.return_value = b"{}"
        rejected.getheader.return_value = "1"
        accepted = Mock(status=204)
        accepted.read.return_value = b""
        with patch.object(LiPER_NNP.http.client, "HTTPSConnection") as factory, patch.object(LiPER_NNP.time, "sleep"):
            factory.return_value.getresponse.side_effect = [rejected, accepted]
            self.assertEqual(LiPER_NNP.make_api_request("https://example.invalid/api", {}), (True, {}, 204))
            self.assertEqual(factory.call_count, 2)

    def test_reboot_window_counts_across_hour_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "state.db"
            with closing(sqlite3.connect(db)) as c, c:
                c.execute("CREATE TABLE LogEventsLiper (id INTEGER PRIMARY KEY, eventType INTEGER, timeEvent TEXT DEFAULT CURRENT_TIMESTAMP)")
                c.execute("CREATE TABLE LastEventsLiper (id INTEGER PRIMARY KEY, timeEvent TEXT)")
                for minutes in (5, 15, 25, 65):
                    c.execute("INSERT INTO LogEventsLiper(eventType,timeEvent) VALUES(2,?)",
                        ((datetime.utcnow()-timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S'),))
            with patch.object(ResetControl, "DB_PATH", db), patch.object(HandlingEvents, "logException"), patch.object(HandlingEvents, "rebootDevice") as reboot:
                self.assertEqual(ResetControl.readDBTest(2), 3)
                self.assertFalse(ResetControl.ValidateReset(4, "test"))
                reboot.assert_not_called()

    def test_safe_formatter_redacts_traceback(self):
        with patch.object(StartSettings, "ocrKey", "private-value", create=True):
            try:
                raise ValueError("private-value")
            except ValueError:
                record = logging.LogRecord("test", logging.ERROR, "", 1, "failed private-value", (), sys.exc_info())
            formatted = HandlingEvents.SafeFormatter().format(record)
            self.assertNotIn("private-value", formatted)
            self.assertIn("ValueError", formatted)


if __name__ == "__main__":
    unittest.main()
