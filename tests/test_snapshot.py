# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_snapshot.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The synchronized snapshot of several cameras: skew, flags, archive and routes."""
import http.client
import io
import json
import threading
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from hydra_umc_vision_streamer.mjpeg_server import Frame, make_multi_handler
from hydra_umc_vision_streamer.snapshot import SnapshotError, build_zip, check_max_skew_ms, describe

NOW = 1_000_000.0


def _frame(name: str, capture_ts: float, frame_id: int = 1) -> Frame:
    return Frame(b"\xff\xd8" + name.encode() + b"\xff\xd9", frame_id, "sess-" + name, capture_ts)


def test_skew_is_the_gap_between_the_earliest_and_the_latest_capture() -> None:
    frames = {"left": _frame("left", NOW - 0.100), "right": _frame("right", NOW - 0.140)}
    manifest = describe(frames, 50.0, now=NOW)
    assert manifest["skew_ms"] == pytest.approx(40.0)
    assert manifest["complete"] and manifest["synchronized"]
    assert manifest["cameras"]["left"]["data_age_ms"] in (99, 100) and manifest["cameras"]["right"]["capture_ts_ms"] == int((NOW - 0.140) * 1000)


def test_too_far_apart_is_returned_but_not_synchronized() -> None:
    frames = {"a": _frame("a", NOW), "b": _frame("b", NOW - 0.5)}
    manifest = describe(frames, 50.0, now=NOW)
    assert manifest["complete"] and not manifest["synchronized"] and manifest["skew_ms"] == pytest.approx(500.0)


def test_a_camera_without_a_frame_makes_it_incomplete() -> None:
    manifest = describe({"a": _frame("a", NOW), "b": None}, 50.0, now=NOW)
    assert not manifest["complete"] and not manifest["synchronized"]
    assert manifest["cameras"]["b"] == {"available": False}


def test_no_cameras_is_never_synchronized() -> None:
    manifest = describe({}, 50.0, now=NOW)
    assert not manifest["complete"] and not manifest["synchronized"] and manifest["skew_ms"] == 0.0


def test_session_id_is_header_safe() -> None:
    frame = Frame(b"x", 1, "bad\r\nid", NOW)
    assert describe({"a": frame}, 50.0, now=NOW)["cameras"]["a"]["session_id"] == "badid"


def test_archive_holds_one_jpeg_per_camera_and_the_manifest() -> None:
    frames = {"left": _frame("left", NOW), "right": _frame("right", NOW)}
    manifest = describe(frames, 50.0, now=NOW)
    with zipfile.ZipFile(io.BytesIO(build_zip(frames, manifest))) as archive:
        assert sorted(archive.namelist()) == ["left.jpg", "right.jpg", "snapshot.json"]
        assert archive.read("left.jpg") == frames["left"].payload
        assert json.loads(archive.read("snapshot.json"))["synchronized"] is True


@pytest.mark.parametrize("bad", [0, -1, 60_001, float("nan"), float("inf"), True, "50"])
def test_refuses_a_bad_skew_limit(bad: object) -> None:
    with pytest.raises(SnapshotError):
        check_max_skew_ms(bad)
    with pytest.raises(SnapshotError):
        make_multi_handler({"a": object()}, snapshot_max_skew_ms=bad)  # type: ignore[arg-type]


class _Source:
    def __init__(self, frame: Frame | None) -> None:
        self._frame = frame

    def latest_frame(self) -> Frame | None:
        return self._frame

    def health(self) -> dict:
        return {"state": "streaming", "healthy": True}


class _Server:
    def __init__(self, handler: type) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]

    def get(self, path: str) -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def test_routes_answer_404_while_off() -> None:
    server = _Server(make_multi_handler({"a": _Source(_frame("a", NOW))}))
    try:
        assert server.get("/snapshot.json")[0] == 404
        assert server.get("/snapshot.zip")[0] == 404
    finally:
        server.stop()


def test_routes_answer_the_snapshot_when_on() -> None:
    import time

    now = time.time()
    server = _Server(make_multi_handler({"a": _Source(_frame("a", now)), "b": _Source(_frame("b", now - 0.01))}, snapshot_max_skew_ms=50))
    try:
        status, _, body = server.get("/snapshot.json")
        assert status == 200 and json.loads(body)["synchronized"] is True
        status, headers, body = server.get("/snapshot.zip")
        assert status == 200 and headers["Content-Type"] == "application/zip" and headers["X-Synchronized"] == "1"
        assert sorted(zipfile.ZipFile(io.BytesIO(body)).namelist()) == ["a.jpg", "b.jpg", "snapshot.json"]
    finally:
        server.stop()


def test_zip_is_refused_while_a_camera_has_no_frame() -> None:
    server = _Server(make_multi_handler({"a": _Source(_frame("a", NOW)), "b": _Source(None)}, snapshot_max_skew_ms=50))
    try:
        assert server.get("/snapshot.zip")[0] == 503
        status, _, body = server.get("/snapshot.json")
        assert status == 200 and json.loads(body)["cameras"]["b"] == {"available": False}
    finally:
        server.stop()


def test_snapshot_needs_the_token_when_there_is_one() -> None:
    server = _Server(make_multi_handler({"a": _Source(_frame("a", NOW))}, token="0123456789abcdef-token", snapshot_max_skew_ms=50))
    try:
        assert server.get("/snapshot.json")[0] == 401
    finally:
        server.stop()
