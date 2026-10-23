"""The shared redaction passes the cases every implementation of it must pass."""
import json
import unittest
from pathlib import Path

from hydra_umc_vision_streamer.log_redaction import redact_json, redact_lines, redact_secrets

VECTORS = json.loads((Path(__file__).resolve().parent / "redaction_vectors.json").read_text(encoding="utf-8"))


class SharedRedactionVectorsTest(unittest.TestCase):
    def test_text_cases(self):
        for case in VECTORS["text"]:
            with self.subTest(case["name"]):
                self.assertEqual(redact_secrets(case["input"]), case["expected"])

    def test_json_cases(self):
        for case in VECTORS["json"]:
            with self.subTest(case["name"]):
                self.assertEqual(redact_json(case["input"]), case["expected"])

    def test_line_cases(self):
        for case in VECTORS["lines"]:
            with self.subTest(case["name"]):
                self.assertEqual(redact_lines(case["input"]), case["expected"])


class StreamerLogTest(unittest.TestCase):
    def test_a_logged_line_never_carries_a_camera_password_or_a_token(self):
        import logging

        from hydra_umc_vision_streamer import mjpeg_server

        records = []

        class Catch(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Catch()
        mjpeg_server.logger.addHandler(handler)
        previous = mjpeg_server.logger.level
        mjpeg_server.logger.setLevel(logging.INFO)
        try:
            mjpeg_server.logger.warning("could not open %s with token=%s", "rtsp://admin:hunter2@10.0.0.5/11", "abc123secretvalue")
        finally:
            mjpeg_server.logger.removeHandler(handler)
            mjpeg_server.logger.setLevel(previous)
        self.assertEqual(len(records), 1)
        self.assertNotIn("hunter2", records[0])
        self.assertNotIn("abc123secretvalue", records[0])


if __name__ == "__main__":
    unittest.main()
