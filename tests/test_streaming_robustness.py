# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_streaming_robustness.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Several viewers, a camera that never comes back, credentials in logs and
the strings written into a generated pipeline."""
import http.client
import json
import logging
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from hydra_umc_vision_streamer import mjpeg_server
from hydra_umc_vision_streamer.config import CameraConfig, ConfigError, load_cameras, redact_credentials
from hydra_umc_vision_streamer.mjpeg_server import CameraUnavailableError, Frame, MjpegCaptureSource, make_handler
from hydra_umc_vision_streamer.pipeline import build_capture_pipeline



def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "hydra_umc_vision_streamer.main", *args],
        capture_output=True, text=True,
    )


def _push(source, payload):
    with source._new_frame:
        source.frames_captured += 1
        source.last_frame_time = time.monotonic()
        source._buffer.push(Frame(payload, source.frames_captured, source.session_id, time.time()))
        source._new_frame.notify_all()


def test_two_readers_of_one_source_both_receive_every_frame():
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30)
    seen = {"a": [], "b": []}

    def reader(name):
        last = 0
        while last < 20:
            frame = source.wait_for_frame(last, timeout=2.0)
            if frame is None:
                seen[name].append(None)
                return
            seen[name].append(frame.frame_id)
            last = frame.frame_id

    threads = [threading.Thread(target=reader, args=(n,)) for n in seen]
    for t in threads:
        t.start()
    for i in range(1, 21):
        _push(source, b"x%d" % i)
        time.sleep(0.01)
    for t in threads:
        t.join(timeout=5)
    for name, ids in seen.items():
        assert None not in ids, f"viewer {name} was cut off: {ids}"
        assert ids[-1] == 20


@pytest.fixture
def http_source():
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(source, max_clients=2))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield source, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_health_is_503_without_frames_and_200_with_a_fresh_one(http_source):
    source, port = http_source
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/health")
    response = conn.getresponse()
    assert response.status == 503
    assert json.loads(response.read())["state"] == "connecting"
    _push(source, b"frame")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/health")
    response = conn.getresponse()
    assert response.status == 200
    assert json.loads(response.read())["state"] == "streaming"


def test_a_query_string_does_not_break_the_stream_path(http_source):
    source, port = http_source
    _push(source, b"\xff\xd8frame\xff\xd9")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/stream?t=123")
    response = conn.getresponse()
    assert response.status == 200
    assert "multipart/x-mixed-replace" in response.getheader("Content-Type")
    conn.close()


def test_serve_camera_fails_when_the_camera_is_given_up(monkeypatch):
    class GivenUpSource:
        display_device = "0"
        last_error = "gave up reconnecting to 0 after 5 attempts"

        def __init__(self, **_):
            self.gave_up = threading.Event()
            self.frames_captured = 0

        def start(self):
            threading.Timer(0.2, self.gave_up.set).start()

        def stop(self):
            pass

        def health(self):
            return {"healthy": False, "state": "given_up"}

        def wait_for_frame(self, last_seen, timeout=5.0):
            return None

    monkeypatch.setattr(mjpeg_server, "MjpegCaptureSource", GivenUpSource)
    with pytest.raises(CameraUnavailableError, match="gave up"):
        mjpeg_server.serve_camera("0", "127.0.0.1", 0, 640, 480, 30)


def test_credentials_are_redacted_wherever_a_device_is_shown(caplog):
    url = "rtsp://admin:s3cret@192.168.0.203:554/11"
    assert "s3cret" not in redact_credentials(f"could not open {url}")
    assert redact_credentials("rtsp://admin:p@ss@10.0.0.5/11") == "rtsp://***@10.0.0.5/11"
    source = MjpegCaptureSource(device=url, width=640, height=480, fps=30)
    assert "s3cret" not in source.display_device
    with caplog.at_level(logging.INFO):
        mjpeg_server.logger.warning("x %s", source.display_device)
    assert "s3cret" not in caplog.text


def test_device_can_come_from_the_environment(monkeypatch):
    result = run_cli("stream", "serve", "--device-env", "HYDRA_TEST_NO_SUCH_VAR", "--port", "0")
    assert result.returncode == 1
    assert "not set" in result.stderr


@pytest.mark.parametrize("device", ["/dev/video0 ! filesrc location=/etc/shadow", "/dev/../etc/passwd", "/dev/video"])
def test_a_device_with_gst_syntax_or_a_wrong_shape_is_rejected(tmp_path, device):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"name": "c", "device": device, "width": 640, "height": 480, "fps": 30, "format": "MJPG"}]))
    with pytest.raises(ConfigError):
        load_cameras(p)


@pytest.mark.parametrize("host,path", [("x ! fakesink", "/11"), ("cam.local", "/a b"), ("cam.local", "/a!b")])
def test_ip_host_and_path_cannot_carry_gst_syntax(tmp_path, host, path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"name": "c", "source_type": "ip", "host": host, "rtsp_path": path, "width": 640, "height": 480, "fps": 30, "format": "H264"}]))
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_ipv6_host_is_bracketed_and_the_path_is_normalised(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"name": "c", "source_type": "ip", "host": "fe80::1", "rtsp_path": "11", "width": 640, "height": 480, "fps": 30, "format": "H264"}]))
    camera = load_cameras(p)[0]
    assert camera.rtsp_path == "/11"
    assert camera.rtsp_url() == "rtsp://[fe80::1]:554/11"


def test_an_ip_camera_pipeline_uses_rtspsrc_and_never_prints_the_password():
    camera = CameraConfig(name="ip0", width=1920, height=1080, fps=25, format="H264", source_type="ip",
                          host="192.168.0.203", rtsp_port=554, rtsp_path="/11", username="admin", password="s3cret")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/ip0")
    assert pipeline.startswith("rtspsrc location=rtsp://192.168.0.203:554/11")
    assert "v4l2src" not in pipeline
    assert "s3cret" not in pipeline and "admin" not in pipeline


def test_both_pipeline_branches_are_leaky_and_bounded():
    camera = CameraConfig(name="cam0", device="/dev/video0", width=640, height=480, fps=30, format="MJPG")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/cam0")
    assert pipeline.count("leaky=downstream") == 2
    assert "appsink name=cam0_hailo_sink max-buffers=1 drop=true" in pipeline


def test_config_validate_shows_where_an_ip_camera_is_without_credentials(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"name": "c", "source_type": "ip", "host": "192.168.0.203", "rtsp_path": "/11", "username": "admin", "password": "s3cret", "width": 640, "height": 480, "fps": 30, "format": "H264"}]))
    result = run_cli("config", "validate", "--config", str(p))
    assert result.returncode == 0
    assert "rtsp://192.168.0.203:554/11" in result.stdout
    assert "s3cret" not in result.stdout


def test_rtsp_base_cannot_carry_gst_syntax(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([{"name": "c", "device": "/dev/video0", "width": 640, "height": 480, "fps": 30, "format": "MJPG"}]))
    result = run_cli("config", "gst", "--config", str(p), "--camera", "c", "--rtsp-base", "rtsp://h ! filesink location=/x")
    assert result.returncode == 1
