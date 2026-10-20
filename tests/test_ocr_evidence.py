import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import ocr_evidence

class EvidenceTests(unittest.TestCase):
    def test_exact_bytes_unique_events_and_results(self):
        with tempfile.TemporaryDirectory() as root:
            saved = Path(root) / "SavedPlates"
            data = bytes(range(256)) * 3
            path, record = ocr_evidence.preserve(data, "capture.jpg", saved)
            self.assertEqual((path.parent / record["crop"]).read_bytes(), data)
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
            ocr_evidence.finish(path, record, "succeeded", ["ABC-123"], ["ABC123"])
            result = json.loads(path.read_text())
            self.assertEqual(result["raw_lines"], ["ABC-123"])
            self.assertEqual(result["genyus_eligible_candidates"], ["ABC123"])
            second, _ = ocr_evidence.preserve(data, "capture.jpg", saved)
            self.assertNotEqual(path, second)
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_pipeline_submits_preserved_bytes_once_without_real_network(self):
        from unittest.mock import Mock, patch
        import LiPER_NNP
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            crop, full = base / "crop.jpg", base / "full.jpg"
            data = b"exact-jpeg-payload-for-mocked-ocr"
            crop.write_bytes(data)
            full.write_bytes(b"full-photo")
            client = Mock()
            received = []
            def submit(stream, raw):
                received.append(stream.read())
                return Mock(headers={"Operation-Location": "https://example.invalid/op/id"})
            client.read_in_stream.side_effect = submit
            client.get_read_result.return_value = Mock(status="succeeded", analyze_result=Mock(read_results=[Mock(lines=[Mock(text="ABC-123")])]))
            with patch.object(LiPER_NNP.StartSettings, "ocrKey", "fake", create=True), patch.object(LiPER_NNP.StartSettings, "myOCREndpoint", "https://example.invalid", create=True), patch.object(LiPER_NNP, "validate_credentials", return_value=True), patch("azure.cognitiveservices.vision.computervision.ComputerVisionClient", return_value=client), patch("msrest.authentication.CognitiveServicesCredentials"), patch.object(LiPER_NNP, "sendPlate") as send, patch("local_dashboard.record_reading") as panel, patch.object(LiPER_NNP.myEvent, "logEvent"):
                LiPER_NNP.Predicciones_BN(str(crop), str(full), str(base / "SavedPlates"), str(base / "ErrorOCR"))
            panel.assert_called_once_with(["ABC123"], data)
            self.assertEqual(received, [data])
            evidence = base / "OCREvidence"
            self.assertEqual(next(evidence.glob("*.jpg")).read_bytes(), data)
            result = json.loads(next(evidence.glob("*.json")).read_text())
            self.assertEqual(result["raw_lines"], ["ABC-123"])
            self.assertEqual(result["normalized_candidates"], ["ABC123"])
            self.assertEqual(result["ocr_status"], "succeeded")
            send.assert_called_once_with(["ABC123"], str(full))
