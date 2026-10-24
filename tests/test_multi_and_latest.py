# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_multi_and_latest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The identity of a frame on the wire, /latest.jpg and /latest.json, several cameras in one process, and a camera chosen from the list."""
import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from hydra_umc_vision_streamer import main as streamer_main
from hydra_umc_vision_streamer.mjpeg_server import Frame, _latest_info, _part_header, make_handler, make_multi_handler

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


class FakeSource:
    def __init__(self, session="sess-1", healthy=True, frame_id=7, capture_ts=None):
        self.session_id = session
        self.frames_captured = frame_id
        self._frame = Frame(JPEG, frame_id, session, time.time() if capture_ts is None else capture_ts)
        self._healthy = healthy
        self.has_frame = True
        self.release = threading.Event()  # a stream that has sent its frame waits for this, like a live camera waits for the next frame

    def latest_frame(self):
        return self._frame if self.has_frame else None

    def wait_for_frame(self, last_seen, timeout=5.0):
        if last_seen >= self._frame.frame_id:
            self.release.wait(timeout)
            return None
        return self._frame

    def health(self):
        return {"state": "streaming" if self._healthy else "stalled", "healthy": self._healthy}


class Server:
    def __init__(self, handler_cls):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def get(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        result = (response.status, dict(response.getheaders()), body)
        conn.close()
        return result


@pytest.fixture
def single():
    source = FakeSource()
    server = Server(make_handler(source, max_clients=2))
    yield server
    source.release.set()
    server.close()


def test_every_part_of_the_stream_carries_the_identity_of_its_frame(single):
    conn = http.client.HTTPConnection("127.0.0.1", single.port, timeout=5)
    conn.request("GET", "/stream")
    response = conn.getresponse()
    assert response.status == 200
    raw = b""
    while JPEG not in raw:
        raw += response.fp.read1(4096)
    conn.close()
    head = raw.split(b"\r\n\r\n", 1)[0].decode("ascii")
    lines = head.splitlines()
    assert lines[0] == "--hydraumcframe"
    assert "Content-Type: image/jpeg" in lines
    assert f"Content-Length: {len(JPEG)}" in lines
    assert "X-Frame-Id: 7" in lines
    assert "X-Session-Id: sess-1" in lines
    stamp = [l for l in lines if l.startswith("X-Capture-Ts: ")][0]
    assert abs(int(stamp.split(": ")[1]) - time.time() * 1000) < 5000


def test_the_jpeg_markers_are_the_only_ff_bytes_a_marker_scanner_can_trip_on():
    # MjpegPlayer.kt scans the bytes for FF D8 ... FF D9: the headers are ASCII, so they can never contain those markers
    header = _part_header(Frame(JPEG, 1, "s" * 100 + "\xff\r\n", 1_800_000_000.0))
    assert header.isascii()
    assert b"\xff" not in header
    assert b"\r\n\r\n" == header[-4:]
    assert header.count(b"\r\n") == 7, "the boundary, five headers and the blank line: nothing in a value can end a line early"


def test_a_session_id_cannot_break_the_header():
    header = _part_header(Frame(JPEG, 1, "a\r\nX-Evil: 1\r\n", 1.0)).decode("ascii")
    assert "X-Evil" in header  # the letters stay, but never as a header of their own
    assert "\r\nX-Evil" not in header


def test_latest_jpg_answers_the_newest_frame_with_its_identity(single):
    status, headers, body = single.get("/latest.jpg")
    assert status == 200
    assert body == JPEG
    assert headers["Content-Type"] == "image/jpeg"
    assert headers["X-Frame-Id"] == "7"
    assert headers["X-Session-Id"] == "sess-1"
    assert int(headers["X-Capture-Ts"]) > 0


def test_latest_json_says_how_old_the_frame_is(single):
    status, _headers, body = single.get("/latest.json")
    info = json.loads(body)
    assert status == 200
    assert info["available"] is True
    assert info["frame_id"] == 7 and info["session_id"] == "sess-1" and info["bytes"] == len(JPEG)
    assert 0 <= info["data_age_ms"] < 5000


def test_latest_info_age_never_goes_negative_and_is_measured_from_the_capture():
    frame = Frame(JPEG, 1, "s", 1000.0)
    assert _latest_info(frame, now=1000.25)["data_age_ms"] == 250
    assert _latest_info(frame, now=999.0)["data_age_ms"] == 0
    assert _latest_info(None) == {"available": False}


def test_before_the_first_frame_latest_is_a_503_with_a_retry_hint():
    source = FakeSource()
    source.has_frame = False
    server = Server(make_handler(source))
    try:
        status, headers, _ = server.get("/latest.jpg")
        assert status == 503 and headers["Retry-After"] == "1"
        status, _, body = server.get("/latest.json")
        assert status == 503 and json.loads(body) == {"available": False}
    finally:
        server.close()


def test_latest_needs_the_token_like_the_stream():
    server = Server(make_handler(FakeSource(), token="0123456789abcdef"))
    try:
        assert server.get("/latest.jpg")[0] == 401
        assert server.get("/latest.json")[0] == 401
        assert server.get("/latest.jpg", {"Authorization": "Bearer 0123456789abcdef"})[0] == 200
        assert server.get("/health")[0] == 200
    finally:
        server.close()


def test_unknown_paths_are_404(single):
    assert single.get("/nope")[0] == 404
    assert single.get("/latest.png")[0] == 404


@pytest.fixture
def several():
    cameras = {"left": FakeSource("left-session", frame_id=3), "right": FakeSource("right-session", frame_id=9)}
    server = Server(make_multi_handler(cameras, max_clients=1))
    yield server, cameras
    for source in cameras.values():
        source.release.set()
    server.close()


def test_each_camera_has_its_own_address_and_its_own_frames(several):
    server, _ = several
    status, headers, body = server.get("/left/latest.jpg")
    assert (status, headers["X-Session-Id"], headers["X-Frame-Id"]) == (200, "left-session", "3")
    status, headers, _ = server.get("/right/latest.jpg")
    assert (status, headers["X-Session-Id"], headers["X-Frame-Id"]) == (200, "right-session", "9")
    assert json.loads(server.get("/right/latest.json")[2])["frame_id"] == 9


def test_the_stream_of_a_camera_is_served_under_its_name(several):
    server, _ = several
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/right/stream")
    response = conn.getresponse()
    assert response.status == 200
    raw = b""
    while JPEG not in raw:
        raw += response.fp.read1(4096)
    conn.close()
    assert b"X-Session-Id: right-session" in raw


def test_a_name_that_is_not_a_camera_and_the_bare_root_are_404(several):
    server, _ = several
    assert server.get("/middle/stream")[0] == 404
    assert server.get("/stream")[0] == 404
    assert server.get("/left/nope")[0] == 404


def test_the_client_limit_is_per_camera(several):
    server, _ = several
    held = []
    try:
        for name in ("left", "right"):
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            conn.request("GET", f"/{name}/stream")
            response = conn.getresponse()
            assert response.status == 200, name
            response.fp.readline()
            held.append(conn)
        # the second viewer of a camera is over its limit of one; the other camera is not affected
        over = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        over.request("GET", "/left/stream")
        assert over.getresponse().status == 503
        over.close()
    finally:
        for conn in held:
            conn.close()


def test_health_of_the_process_is_healthy_only_while_every_camera_is(several):
    server, cameras = several
    status, _, body = server.get("/health")
    assert status == 200 and json.loads(body)["healthy"] is True
    cameras["right"]._healthy = False
    status, _, body = server.get("/health")
    report = json.loads(body)
    assert status == 503 and report["healthy"] is False
    assert report["cameras"]["left"]["healthy"] is True and report["cameras"]["right"]["healthy"] is False
    assert server.get("/left/health")[0] == 200
    assert server.get("/right/health")[0] == 503


def test_the_multi_handler_refuses_no_cameras_and_names_that_cannot_be_addresses():
    with pytest.raises(ValueError):
        make_multi_handler({})
    for bad in ("", "a/b", "a b", "../x", "x?y"):
        with pytest.raises(ValueError):
            make_multi_handler({bad: FakeSource()})


# ---- choosing a camera from the list ----

LIST = [
    {"name": "bench", "source_type": "usb", "device": "/dev/video2", "width": 800, "height": 600, "fps": 15, "format": "MJPG"},
    {"name": "door", "source_type": "ip", "host": "10.0.0.50", "rtsp_path": "/11", "username": "u", "password": "p@ss:word",
     "width": 1280, "height": 720, "fps": 20, "format": "MJPG"},
]


def _write_list(tmp_path):
    path = tmp_path / "cams.json"
    path.write_text(json.dumps(LIST), encoding="utf-8")
    return str(path)


def _serve(monkeypatch, argv):
    calls = []
    monkeypatch.setattr(streamer_main, "serve_camera", lambda *args: calls.append(args))
    monkeypatch.setattr("sys.argv", ["hydra-umc-vision-streamer", *argv])
    return streamer_main.main(), calls


def test_a_usb_camera_is_served_from_the_list_with_its_own_size_and_rate(tmp_path, monkeypatch):
    code, calls = _serve(monkeypatch, ["stream", "serve", "--config", _write_list(tmp_path), "--camera", "bench", "--port", "9001"])
    assert code == 0
    device, addr, port, width, height, fps, *_ = calls[0]
    assert (device, addr, port, width, height, fps) == ("/dev/video2", "127.0.0.1", 9001, 800, 600, 15)


def test_an_ip_camera_gets_its_address_built_from_the_list_and_it_is_not_on_the_command_line(tmp_path, monkeypatch):
    argv = ["stream", "serve", "--config", _write_list(tmp_path), "--camera", "door", "--port", "9002"]
    code, calls = _serve(monkeypatch, argv)
    assert code == 0
    assert calls[0][0] == "rtsp://u:p%40ss%3Aword@10.0.0.50:554/11"
    assert not any("p@ss" in a or "password" in a for a in argv)


@pytest.mark.parametrize(
    "extra",
    [
        ["--camera", "bench"],  # a camera without a list
        ["--config", "LIST"],  # a list without a camera
        ["--config", "LIST", "--camera", "nobody"],
        ["--config", "LIST", "--camera", "bench", "--device", "0"],
        ["--config", "LIST", "--camera", "bench", "--device-env", "X"],
    ],
)
def test_a_camera_chosen_wrongly_stops_before_anything_is_opened(tmp_path, monkeypatch, capsys, extra):
    listing = _write_list(tmp_path)
    argv = ["stream", "serve", "--port", "9003", *[listing if a == "LIST" else a for a in extra]]
    code, calls = _serve(monkeypatch, argv)
    assert code == 1
    assert calls == []
    assert capsys.readouterr().err.startswith("error:")


def test_serve_all_serves_every_camera_or_the_ones_asked_for(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(streamer_main, "serve_cameras", lambda cameras, *rest: seen.append((cameras, rest)))
    monkeypatch.setattr("sys.argv", ["x", "stream", "serve-all", "--config", _write_list(tmp_path), "--port", "9010"])
    assert streamer_main.main() == 0
    assert set(seen[0][0]) == {"bench", "door"}
    assert seen[0][0]["bench"] == ("/dev/video2", 800, 600, 15)
    assert seen[0][0]["door"][0].startswith("rtsp://u:")
    seen.clear()
    monkeypatch.setattr("sys.argv", ["x", "stream", "serve-all", "--config", _write_list(tmp_path), "--camera", "door", "--port", "9010"])
    assert streamer_main.main() == 0
    assert set(seen[0][0]) == {"door"}


def test_serve_all_refuses_an_unknown_camera_and_an_open_network_port(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(streamer_main, "serve_cameras", lambda *a: pytest.fail("must not start"))
    monkeypatch.setattr("sys.argv", ["x", "stream", "serve-all", "--config", _write_list(tmp_path), "--camera", "ghost", "--port", "9010"])
    assert streamer_main.main() == 1
    monkeypatch.setattr("sys.argv", ["x", "stream", "serve-all", "--config", _write_list(tmp_path), "--addr", "0.0.0.0", "--port", "9010"])
    monkeypatch.delenv("HYDRA_UMC_VISION_STREAMER_TOKEN", raising=False)
    assert streamer_main.main() == 2
    assert "token" in capsys.readouterr().err.lower()
