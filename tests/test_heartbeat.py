import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import Send_HB

METRICS = {"serialLiper": "device1", "temperature": "65.0", "CPU": 20,
           "RAM": 30, "speedNetwork": "0.1", "lowVoltage": "0"}
CONFIG = {"GDF_HEALTH_URL": "https://example.invalid/api/heartbeat", "GDF_HEALTH_TOKEN": "private-token"}


class HeartbeatTests(unittest.TestCase):
    def test_secondary_disabled_without_url(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Send_HB.http.client, "HTTPSConnection") as connection:
            self.assertIsNone(Send_HB.send_secondary(METRICS))
            connection.assert_not_called()

    def test_https_and_token_required(self):
        for config in ({"GDF_HEALTH_URL": "http://example.invalid", "GDF_HEALTH_TOKEN": "x"},
                       {"GDF_HEALTH_URL": "https://example.invalid"},
                       {"GDF_HEALTH_URL": "https://user:pass@example.invalid", "GDF_HEALTH_TOKEN": "x"}):
            with self.subTest(config=config), patch.dict(os.environ, config, clear=True):
                with self.assertRaises(ValueError):
                    Send_HB.send_secondary(METRICS)

    def test_secondary_posts_health_without_genyus_key(self):
        with patch.dict(os.environ, CONFIG, clear=True), patch.object(Send_HB.http.client, "HTTPSConnection") as factory, patch.object(Send_HB.events, "logEvent"):
            factory.return_value.getresponse.return_value.status = 200
            with patch.object(Path, "read_text", return_value=json.dumps({"last_frame": time.time()})):
                self.assertTrue(Send_HB.send_secondary(METRICS))
            args, kwargs = factory.return_value.request.call_args
            self.assertEqual(args, ("POST", "/api/heartbeat"))
            payload = json.loads(kwargs["body"])
            self.assertEqual(payload["reader"]["status"], "healthy")
            self.assertEqual(payload["metrics"], METRICS)
            self.assertNotIn("genyusKey", kwargs["body"])
            self.assertNotIn("private-token", kwargs["body"])
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer private-token")
            factory.return_value.close.assert_called_once()

    def test_rejected_secondary_is_not_retried(self):
        with patch.dict(os.environ, CONFIG, clear=True), patch.object(Send_HB.http.client, "HTTPSConnection") as factory, patch.object(Send_HB, "secondary_payload", return_value={}):
            factory.return_value.getresponse.return_value.status = 302
            with self.assertRaises(RuntimeError):
                Send_HB.send_secondary(METRICS)
            self.assertEqual(factory.call_count, 1)
            factory.return_value.close.assert_called_once()

    def test_genyus_failure_does_not_block_secondary(self):
        with patch.dict(os.environ, CONFIG), patch.object(Send_HB, "collect_metrics", return_value=METRICS), patch.object(Send_HB, "hbGenys", side_effect=RuntimeError()), patch.object(Send_HB, "send_secondary", return_value=True) as secondary, patch.object(Send_HB.events, "setup_logging"):
            self.assertEqual(Send_HB.HBeat(), {"genyus": False, "secondary": True})
            secondary.assert_called_once_with(METRICS)

    def test_secondary_failure_does_not_block_genyus(self):
        with patch.dict(os.environ, CONFIG), patch.object(Send_HB, "collect_metrics", return_value=METRICS), patch.object(Send_HB, "hbGenys", return_value=True) as primary, patch.object(Send_HB, "send_secondary", side_effect=TimeoutError()), patch.object(Send_HB.events, "setup_logging"):
            self.assertEqual(Send_HB.HBeat(), {"genyus": True, "secondary": False})
            primary.assert_called_once_with(METRICS)

    def test_requests_run_independently(self):
        secondary_started = threading.Event()
        def primary(_):
            return secondary_started.wait(2)
        def secondary(_):
            secondary_started.set()
            return True
        with patch.dict(os.environ, CONFIG), patch.object(Send_HB, "collect_metrics", return_value=METRICS), patch.object(Send_HB, "hbGenys", side_effect=primary), patch.object(Send_HB, "send_secondary", side_effect=secondary):
            self.assertEqual(Send_HB.HBeat(), {"genyus": True, "secondary": True})

    def test_missing_reader_health_is_unknown(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError()), patch.object(Send_HB.events, "logEvent"):
            self.assertEqual(Send_HB.secondary_payload(METRICS)["reader"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
