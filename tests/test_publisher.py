# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_publisher.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Publishing to MediaMTX: the file, the command, the child process (a stand-in for gst-launch-1.0) and the status."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hydra_umc_vision_streamer.mjpeg_server import Frame, make_multi_handler
from hydra_umc_vision_streamer.publisher import (
    Address,
    FeedPublisher,
    PublishError,
    build_feed_command,
    load_publish_config,
    parse_publish_config,
    probe_ready,
    rtsp_location,
)

FAKE = str(Path(__file__).with_name("fake_gst.py"))
JPEG = b"\xff\xd8" + b"j" * 60 + b"\xff\xd9"


def _config(**change):
    block = {"enabled": True, "gstLaunch": [sys.executable, FAKE], "restart": {"maxAttempts": 2, "baseDelaySeconds": 0.05, "maxDelaySeconds": 0.1}, **change}
    return parse_publish_config(block)


class LiveSource:
    """A source that hands out a new frame every few milliseconds, like a camera."""

    fps = 25

    def __init__(self) -> None:
        self.number = 0

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0):
        time.sleep(0.005)
        self.number += 1
        return Frame(JPEG, self.number, "s", time.time())


def _wait(predicate, seconds: float = 8.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_the_command_has_plain_arguments_and_the_address_of_the_camera() -> None:
    command = build_feed_command(_config(), "front", 25)
    assert command[:2] == [sys.executable, FAKE]
    arguments = command[2:]
    assert arguments[:5] == ["-q", "-e", "fdsrc", "fd=0", "do-timestamp=true"]
    assert "image/jpeg,framerate=25/1" in arguments and "x264enc" in arguments and "bitrate=2000" in arguments
    assert arguments[-2:] == ["rtspclientsink", "location=rtsp://127.0.0.1:8554/front"]
    assert not any(" " in a or ";" in a or "$" in a for a in arguments)


def test_the_mjpeg_codec_sends_the_frames_on_without_encoding() -> None:
    arguments = build_feed_command(_config(codec="mjpeg", rtspBase="rtsp://localhost:9000/live"), "front", 10)[2:]
    assert "rtpjpegpay" not in arguments and "jpegparse" in arguments and arguments[-1].startswith("location=") and "x264enc" not in arguments and "jpegdec" not in arguments
    assert arguments[-1] == "location=rtsp://localhost:9000/live/front"


def test_a_camera_name_or_a_frame_rate_that_is_not_plain_is_refused() -> None:
    config = _config()
    for name in ("a b", "x;y", "a/b", "", "$HOME"):
        with pytest.raises(PublishError):
            rtsp_location(config, name)
    for fps in (0, 241, True, "30"):
        with pytest.raises(PublishError):
            build_feed_command(config, "front", fps)  # type: ignore[arg-type]


@pytest.mark.parametrize("block", [
    "text", {"extra": 1}, {"enabled": "yes"}, {"gstLaunch": []}, {"gstLaunch": "gst-launch-1.0"}, {"gstLaunch": ["a", "b", "c", "d", "e"]}, {"gstLaunch": [""]},
    {"codec": "vp9"}, {"bitrateKbps": 10}, {"bitrateKbps": 99999}, {"bitrateKbps": True}, {"rtspBase": "http://127.0.0.1"}, {"rtspBase": "rtsp://user:pw@127.0.0.1"},
    {"rtspBase": "rtsp://example.com:8554"}, {"rtspBase": "rtsp://127.0.0.1:8554?x=1"}, {"rtspBase": "rtsp://127.0.0.1/a/../b"}, {"rtspBase": 5},
    {"mediamtxApi": "https://127.0.0.1:9997"}, {"mediamtxApi": "http://example.com:9997"}, {"allowRemote": 1}, {"restart": {"maxAttempts": 0}},
    {"restart": {"maxAttempts": 101}}, {"restart": {"baseDelaySeconds": 0}}, {"restart": {"baseDelaySeconds": 5, "maxDelaySeconds": 1}}, {"restart": {"x": 1}},
    {"restart": {"maxAttempts": "3"}}, {"restart": {"maxDelaySeconds": 99999}},
])
def test_a_bad_publishing_file_is_refused(block: object) -> None:
    with pytest.raises(PublishError):
        parse_publish_config(block)


def test_the_file_is_off_by_default_and_remote_addresses_need_allow_remote(tmp_path: Path) -> None:
    config = parse_publish_config({})
    assert config.enabled is False and config.gst_launch == ("gst-launch-1.0",) and config.codec == "h264" and config.api is None
    remote = parse_publish_config({"rtspBase": "rtsp://cm5.local:8554/base", "mediamtxApi": "http://cm5.local:9997", "allowRemote": True})
    assert remote.rtsp.host == "cm5.local" and remote.rtsp.path == "/base" and remote.api == Address("http", "cm5.local", 9997, "")
    (tmp_path / "pub.json").write_text(json.dumps({"enabled": True, "codec": "mjpeg"}), encoding="utf-8")
    assert load_publish_config(tmp_path / "pub.json").codec == "mjpeg"
    (tmp_path / "bad.json").write_text('{"bitrateKbps": NaN}', encoding="utf-8")
    with pytest.raises(PublishError, match="not a valid JSON number"):
        load_publish_config(tmp_path / "bad.json")
    with pytest.raises(PublishError, match="cannot be read"):
        load_publish_config(tmp_path / "missing.json")
    assert "gst-launch-1.0" in json.dumps(config.describe())


def test_the_frames_of_the_camera_reach_the_child_and_it_is_stopped_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "gst.log"
    monkeypatch.setenv("FAKE_GST_OUT", str(out))
    publisher = FeedPublisher("front", LiveSource(), _config())
    publisher.start()
    try:
        assert _wait(lambda: publisher.status()["framesSent"] >= 5)
        status = publisher.status()
        assert status["state"] == "publishing" and status["url"] == "rtsp://127.0.0.1:8554/front" and status["codec"] == "h264" and status["ready"] is None
    finally:
        publisher.stop()
    assert publisher.status()["state"] == "stopped"
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["event"] == "start" and lines[0]["args"][-1] == "location=rtsp://127.0.0.1:8554/front"
    assert lines[-1]["event"] == "end" and lines[-1]["bytes"] >= 5 * len(JPEG) and lines[-1]["code"] == 0


def test_a_child_that_ends_is_started_again_and_after_the_last_attempt_the_state_stays_given_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "gst.log"
    monkeypatch.setenv("FAKE_GST_OUT", str(out))
    monkeypatch.setenv("FAKE_GST_EXIT_AFTER", str(len(JPEG)))
    monkeypatch.setenv("FAKE_GST_ERROR", "no element rtspclientsink password=hunter2")
    publisher = FeedPublisher("front", LiveSource(), _config())
    publisher.start()
    try:
        assert _wait(lambda: publisher.status()["state"] == "given_up")
        status = publisher.status()
        assert status["restarts"] == 2
        assert "exit code 3" in status["lastError"] and "no element rtspclientsink" in status["lastError"]
        assert "hunter2" not in status["lastError"]  # the redaction of the family applies to what the child says
    finally:
        publisher.stop()
    starts = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if '"start"' in line]
    assert len(starts) == 3  # the first run and two restarts


def test_a_machine_without_the_program_ends_in_unavailable_without_retrying(tmp_path: Path) -> None:
    publisher = FeedPublisher("front", LiveSource(), _config(gstLaunch=[str(tmp_path / "no-such-gst-launch")]))
    publisher.start()
    try:
        assert _wait(lambda: publisher.status()["state"] == "unavailable")
        assert "not installed" in publisher.status()["lastError"] and publisher.status()["restarts"] == 0
    finally:
        publisher.stop()


def test_a_program_that_cannot_be_started_is_unavailable_too(tmp_path: Path) -> None:
    def broken(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    publisher = FeedPublisher("front", LiveSource(), _config(), spawn=broken)
    publisher.start()
    try:
        assert _wait(lambda: publisher.status()["state"] == "unavailable")
        assert "Permission denied" in publisher.status()["lastError"]
    finally:
        publisher.stop()


class FakeMediaMtx(BaseHTTPRequestHandler):
    answers: dict[str, tuple[int, bytes]] = {}

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        status, body = self.answers.get(self.path, (404, b"{}"))
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def mediamtx():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMediaMtx)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Address("http", "127.0.0.1", server.server_address[1], "")
    server.shutdown()
    server.server_close()


def test_the_probe_asks_mediamtx_whether_the_path_has_a_publisher(mediamtx: Address) -> None:
    FakeMediaMtx.answers = {"/v3/paths/get/front": (200, b'{"name": "front", "ready": true}'), "/v3/paths/get/back": (200, b'{"ready": false}'),
                            "/v3/paths/get/odd": (200, b'{"ready": "yes"}'), "/v3/paths/get/bad": (500, b"{}"), "/v3/paths/get/junk": (200, b"<html>")}
    assert probe_ready(mediamtx, "front") is True
    assert probe_ready(mediamtx, "back") is False
    assert probe_ready(mediamtx, "missing") is False  # MediaMTX answers 404 for a path that does not exist
    for name in ("odd", "bad", "junk"):
        assert probe_ready(mediamtx, name) is None
    assert probe_ready(Address("http", "127.0.0.1", 1, ""), "front", timeout=0.5) is None


def test_the_status_carries_the_answer_of_mediamtx_while_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mediamtx: Address) -> None:
    FakeMediaMtx.answers = {"/v3/paths/get/front": (200, b'{"ready": true}')}
    monkeypatch.setenv("FAKE_GST_OUT", str(tmp_path / "gst.log"))
    publisher = FeedPublisher("front", LiveSource(), _config(mediamtxApi=f"http://127.0.0.1:{mediamtx.port}"))
    publisher.start()
    try:
        assert _wait(lambda: publisher.status()["state"] == "publishing")
        assert publisher.status()["ready"] is True
    finally:
        publisher.stop()
    assert publisher.status()["ready"] is None  # not asked when nothing is published


def test_the_publish_route_reports_the_state_of_each_camera(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import http.client

    monkeypatch.setenv("FAKE_GST_OUT", str(tmp_path / "gst.log"))
    source = LiveSource()
    publisher = FeedPublisher("front", source, _config())
    handler = make_multi_handler({"front": source, "back": source}, publishers={"front": publisher})  # type: ignore[dict-item]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        publisher.start()
        assert _wait(lambda: publisher.status()["state"] == "publishing")
        for path, expected in (("/front/publish", 200), ("/back/publish", 404)):
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            conn.close()
            assert response.status == expected
            if expected == 200:
                assert json.loads(body)["state"] == "publishing"
    finally:
        publisher.stop()
        httpd.shutdown()
        httpd.server_close()
