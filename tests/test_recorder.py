# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_recorder.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The ring recorder: what it keeps, when it writes, what it refuses, and the routes that reach it."""
import hashlib
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from hydra_umc_vision_streamer.mjpeg_server import Frame, make_handler, make_multi_handler
from hydra_umc_vision_streamer.recorder import (
    RecordingConfig,
    RecordingError,
    RingRecorder,
    load_recording_config,
    parse_recording_config,
    parse_trigger,
)


def _config(tmp_path: Path, **change) -> RecordingConfig:
    block = {"enabled": True, "seconds": 2, "maxBytes": 1024 * 1024, "postSeconds": 0, "outDir": "out", "minGapSeconds": 0, **change}
    return parse_recording_config(block, tmp_path)


def _frame(number: int, size: int = 100, at: float | None = None) -> Frame:
    return Frame(bytes([number % 256]) * size, number, "sess-1", 1000.0 + number * 0.5 if at is None else at)


class Clock:
    def __init__(self, now: float = 5000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_the_ring_keeps_only_the_last_seconds(tmp_path: Path) -> None:
    recorder = RingRecorder("cam", _config(tmp_path, seconds=2))
    for number in range(20):
        recorder.add(_frame(number))
    status = recorder.status()
    assert status["ringFrames"] == 5 and status["ringSeconds"] == 2.0  # frames 15..19, half a second apart


def test_the_ring_is_bounded_by_size_too_and_keeps_the_newest_frame(tmp_path: Path) -> None:
    recorder = RingRecorder("cam", _config(tmp_path, seconds=600, maxBytes=1024 * 1024))
    for number in range(30):
        recorder.add(_frame(number, size=100_000, at=1000.0 + number * 0.01))
    status = recorder.status()
    assert status["ringBytes"] <= 1024 * 1024 and 9 <= status["ringFrames"] <= 10
    recorder.add(_frame(99, size=2_000_000))
    assert recorder.status()["ringFrames"] == 1  # a frame larger than the ring is still the newest one


def test_nothing_is_written_until_a_trigger(tmp_path: Path) -> None:
    recorder = RingRecorder("cam", _config(tmp_path))
    for number in range(5):
        recorder.add(_frame(number))
    assert not (tmp_path / "out").exists()
    assert recorder.status()["incidentsOnDisk"] == 0


def test_a_trigger_writes_the_ring_in_order_with_a_manifest(tmp_path: Path) -> None:
    clock = Clock()
    recorder = RingRecorder("cam", _config(tmp_path), clock=clock)
    frames = [_frame(n) for n in range(4)]
    for frame in frames:
        recorder.add(frame)
    result = recorder.trigger("e-stop of the cell", "safety-zones")
    assert result["accepted"] is True and result["detail"] == "written"
    folder = tmp_path / "out" / "cam" / result["incident"]
    assert sorted(p.name for p in folder.iterdir()) == ["00001.jpg", "00002.jpg", "00003.jpg", "00004.jpg", "incident.json"]
    manifest = json.loads((folder / "incident.json").read_text(encoding="utf-8"))
    assert manifest["reason"] == "e-stop of the cell" and manifest["source"] == "safety-zones" and manifest["camera"] == "cam"
    assert manifest["pre_frames"] == 4 and manifest["post_frames"] == 0 and manifest["triggered_at_ms"] == 5_000_000
    for entry, frame in zip(manifest["frames"], frames, strict=True):
        assert (folder / entry["file"]).read_bytes() == frame.payload
        assert entry["sha256"] == hashlib.sha256(frame.payload).hexdigest() and entry["frame_id"] == frame.frame_id
    assert not list((tmp_path / "out" / "cam").glob(".*.tmp"))


def test_the_post_roll_adds_the_frames_that_come_after_the_trigger(tmp_path: Path) -> None:
    clock = Clock()
    waiting: list = []
    recorder = RingRecorder("cam", _config(tmp_path, postSeconds=3), clock=clock, schedule=lambda delay, action: waiting.append((delay, action)))
    for number in range(3):
        recorder.add(_frame(number))
    result = recorder.trigger("door opened")
    assert result["accepted"] is True and "waiting 3 s" in result["detail"] and waiting[0][0] == 3
    assert recorder.status()["pending"] == 1 and recorder.status()["incidentsOnDisk"] == 0
    for number in range(3, 6):
        recorder.add(_frame(number))
    waiting[0][1]()
    manifest = json.loads((tmp_path / "out" / "cam" / result["incident"] / "incident.json").read_text(encoding="utf-8"))
    assert manifest["pre_frames"] == 3 and manifest["post_frames"] == 3 and [e["frame_id"] for e in manifest["frames"]] == [0, 1, 2, 3, 4, 5]
    assert recorder.status()["pending"] == 0
    assert recorder.finalize(result["incident"]) is False  # already written


def test_flush_writes_what_is_still_waiting(tmp_path: Path) -> None:
    recorder = RingRecorder("cam", _config(tmp_path, postSeconds=30), schedule=lambda delay, action: None)
    recorder.add(_frame(1))
    recorder.trigger("a")
    assert recorder.flush() == 1 and recorder.status()["incidentsOnDisk"] == 1


def test_a_second_trigger_inside_the_gap_is_not_written(tmp_path: Path) -> None:
    clock = Clock()
    recorder = RingRecorder("cam", _config(tmp_path, minGapSeconds=30), clock=clock)
    recorder.add(_frame(1))
    assert recorder.trigger("first")["accepted"] is True
    clock.now += 29
    refused = recorder.trigger("second")
    assert refused["accepted"] is False and "debounced" in refused["detail"]
    clock.now += 2
    assert recorder.trigger("third")["accepted"] is True
    assert recorder.status()["incidentsOnDisk"] == 2


def test_an_empty_ring_and_too_many_waiting_incidents_are_refused(tmp_path: Path) -> None:
    recorder = RingRecorder("cam", _config(tmp_path, postSeconds=10), schedule=lambda delay, action: None)
    assert "empty" in recorder.trigger("x")["detail"]
    recorder.add(_frame(1))
    results = [recorder.trigger(f"r{n}") for n in range(6)]
    assert [r["accepted"] for r in results] == [True, True, True, True, False, False]
    assert "already waiting" in results[-1]["detail"]


def test_only_the_newest_incidents_stay_on_disk(tmp_path: Path) -> None:
    clock = Clock()
    recorder = RingRecorder("cam", _config(tmp_path, maxIncidents=2), clock=clock)
    recorder.add(_frame(1))
    made = []
    for n in range(4):
        clock.now += 1
        made.append(recorder.trigger(f"r{n}")["incident"])
    on_disk = sorted(p.name for p in (tmp_path / "out" / "cam").iterdir())
    assert on_disk == sorted(made[-2:])
    listed = recorder.list_incidents()
    assert [i["incident"] for i in listed] == sorted(made[-2:], reverse=True) and listed[0]["frames"] == 1 and listed[0]["reason"] == "r3"


def test_a_folder_that_cannot_be_written_is_reported_and_the_capture_goes_on(tmp_path: Path) -> None:
    (tmp_path / "out").write_text("a file where the folder should be", encoding="utf-8")
    recorder = RingRecorder("cam", _config(tmp_path))
    recorder.add(_frame(1))
    assert recorder.trigger("x")["accepted"] is True
    assert "cannot write" in recorder.status()["lastError"]
    recorder.add(object())  # type: ignore[arg-type]  # a bad frame must not raise into the capture loop
    assert recorder.status()["lastError"] == "AttributeError"


@pytest.mark.parametrize("block", [
    "text", {"outDir": "x", "extra": 1}, {}, {"outDir": ""}, {"outDir": "../up"}, {"outDir": "a/../b"}, {"outDir": "x", "enabled": "yes"},
    {"outDir": "x", "seconds": 0}, {"outDir": "x", "seconds": 601}, {"outDir": "x", "seconds": True}, {"outDir": "x", "maxBytes": 10},
    {"outDir": "x", "maxBytes": 10**10}, {"outDir": "x", "postSeconds": -1}, {"outDir": "x", "postSeconds": 121}, {"outDir": "x", "maxIncidents": 0},
    {"outDir": "x", "maxIncidents": 101}, {"outDir": "x", "minGapSeconds": 3601}, {"outDir": "x", "seconds": float("nan")},
])
def test_a_bad_recording_file_is_refused(tmp_path: Path, block: object) -> None:
    with pytest.raises(RecordingError):
        parse_recording_config(block, tmp_path)


def test_the_file_is_off_unless_it_says_so_and_relative_folders_hang_from_the_file(tmp_path: Path) -> None:
    (tmp_path / "rec.json").write_text(json.dumps({"outDir": "incidents"}), encoding="utf-8")
    config = load_recording_config(tmp_path / "rec.json")
    assert config.enabled is False and config.out_dir == tmp_path.resolve() / "incidents"
    assert config.seconds == 10 and config.post_seconds == 5 and config.min_gap_seconds == 30 and config.max_incidents == 5
    (tmp_path / "bad.json").write_text("{nan", encoding="utf-8")
    with pytest.raises(RecordingError, match="not valid JSON"):
        load_recording_config(tmp_path / "bad.json")
    (tmp_path / "const.json").write_text('{"outDir": "x", "seconds": NaN}', encoding="utf-8")
    with pytest.raises(RecordingError, match="not a valid JSON number"):
        load_recording_config(tmp_path / "const.json")
    with pytest.raises(RecordingError, match="cannot be read"):
        load_recording_config(tmp_path / "missing.json")


@pytest.mark.parametrize("body", [[], {"source": "x"}, {"reason": ""}, {"reason": "é"}, {"reason": "x" * 121}, {"reason": 5}, {"reason": "ok", "source": "a b"},
                                  {"reason": "ok", "extra": 1}])
def test_a_bad_trigger_is_refused(body: object) -> None:
    with pytest.raises(RecordingError):
        parse_trigger(body)


def test_a_good_trigger() -> None:
    assert parse_trigger({"reason": "e-stop: zone 3", "source": "safety-zones"}) == ("e-stop: zone 3", "safety-zones")
    assert parse_trigger({"reason": "manual"}) == ("manual", None)


# ------------------------------------------------------------------------------------------------------ the routes


class FakeSource:
    def __init__(self) -> None:
        self.release = threading.Event()
        self._frame = Frame(b"\xff\xd8x\xff\xd9", 1, "s", 1.0)

    def latest_frame(self) -> Frame:
        return self._frame

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0) -> None:
        self.release.wait(0.05)
        return None

    def health(self) -> dict:
        return {"state": "streaming", "healthy": True}


class Served:
    def __init__(self, handler: type) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.server_address[1]

    def call(self, method: str, path: str, body: object = None, token: str = "") -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw) if raw else {}

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def served(tmp_path: Path):
    recorder = RingRecorder("front", _config(tmp_path))
    recorder.add(_frame(1))
    handler = make_multi_handler({"front": FakeSource(), "back": FakeSource()}, token="t" * 16, recorders={"front": recorder})  # type: ignore[dict-item]
    server = Served(handler)
    yield server, recorder, tmp_path
    server.close()


def test_the_trigger_route_writes_the_incident(served) -> None:
    server, recorder, tmp_path = served
    status, answer = server.call("POST", "/front/record/trigger", {"reason": "e-stop", "source": "safety-zones"}, "t" * 16)
    assert status == 202 and answer["accepted"] is True
    assert (tmp_path / "out" / "front" / answer["incident"] / "incident.json").is_file()
    status, listed = server.call("GET", "/front/record/incidents", token="t" * 16)
    assert status == 200 and listed["incidents"][0]["incident"] == answer["incident"]
    status, state = server.call("GET", "/front/record", token="t" * 16)
    assert status == 200 and state["enabled"] is True and state["incidentsWritten"] == 1


def test_the_trigger_route_needs_the_token_and_a_good_body(served) -> None:
    server, _recorder, _ = served
    assert server.call("POST", "/front/record/trigger", {"reason": "x"})[0] == 401
    assert server.call("GET", "/front/record")[0] == 401
    for body in (b"", b"not json", b'{"reason": ""}', b'{"reason": "x", "bogus": 1}', b'{"reason": NaN}', b"x" * 2000):
        assert server.call("POST", "/front/record/trigger", body, "t" * 16)[0] == 400
    assert server.call("POST", "/back/record/trigger", {"reason": "x"}, "t" * 16)[0] == 404  # this camera does not record
    assert server.call("GET", "/back/record", token="t" * 16)[0] == 404
    assert server.call("POST", "/nowhere/record/trigger", {"reason": "x"}, "t" * 16)[0] == 404
    assert server.call("POST", "/front/stream", {"reason": "x"}, "t" * 16)[0] == 404


def test_a_second_trigger_gets_429(tmp_path: Path) -> None:
    recorder = RingRecorder("front", _config(tmp_path, minGapSeconds=60))
    recorder.add(_frame(1))
    server = Served(make_multi_handler({"front": FakeSource()}, recorders={"front": recorder}))  # type: ignore[dict-item]
    try:
        assert server.call("POST", "/front/record/trigger", {"reason": "a"})[0] == 202
        status, answer = server.call("POST", "/front/record/trigger", {"reason": "b"})
        assert status == 429 and answer["accepted"] is False
    finally:
        server.close()


def test_without_a_recorder_the_routes_do_not_exist() -> None:
    server = Served(make_handler(FakeSource()))  # type: ignore[arg-type]
    try:
        assert server.call("POST", "/record/trigger", {"reason": "x"})[0] == 404
        assert server.call("GET", "/record")[0] == 404
    finally:
        server.close()


def test_the_single_camera_handler_has_the_routes_without_a_name(tmp_path: Path) -> None:
    recorder = RingRecorder("camera", _config(tmp_path))
    recorder.add(_frame(1))
    server = Served(make_handler(FakeSource(), recorder=recorder))  # type: ignore[arg-type]
    try:
        status, answer = server.call("POST", "/record/trigger", {"reason": "x"})
        assert status == 202 and (tmp_path / "out" / "camera" / answer["incident"]).is_dir()
    finally:
        server.close()
