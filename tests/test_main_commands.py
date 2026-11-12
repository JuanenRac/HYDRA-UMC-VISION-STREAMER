# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_main_commands.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The command line in this process (the other CLI tests run it in a child process, which a coverage run does not see): every refusal
of `stream serve` and `stream serve-all` before the port is bound, the simulation, the USB discovery and the version text.
Nothing here opens a camera or a socket: the two serving functions are replaced by recorders."""
import json
import sys

import pytest

from hydra_umc_vision_streamer import main as streamer_main
from hydra_umc_vision_streamer.mjpeg_server import CameraUnavailableError

USB = {"name": "cam0", "device": "/dev/video0", "width": 640, "height": 480, "fps": 15, "format": "MJPG"}
IP = {"name": "door", "source_type": "ip", "host": "192.168.0.50", "rtsp_path": "/11", "width": 1280, "height": 720, "fps": 10, "format": "H264"}
GOOD_TOKEN = "t" * 20


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["hydra-umc-vision-streamer", *argv])
    return streamer_main.main()


@pytest.fixture
def cameras(tmp_path):
    path = tmp_path / "cameras.json"
    path.write_text(json.dumps([USB, IP]), encoding="utf-8")
    return str(path)


@pytest.fixture
def served(monkeypatch):
    """Replaces the two blocking servers by recorders; `calls` lists what each was asked to serve."""
    calls = []
    monkeypatch.setattr(streamer_main, "serve_camera", lambda *a: calls.append(("one", a)))
    monkeypatch.setattr(streamer_main, "serve_cameras", lambda *a: calls.append(("all", a)))
    return calls


def test_version_text_falls_back_when_not_installed(monkeypatch):
    def missing(_name):
        raise streamer_main.PackageNotFoundError()
    monkeypatch.setattr(streamer_main, "version", missing)
    assert "not installed" in streamer_main.get_version()
    monkeypatch.setattr(streamer_main, "version", lambda _name: "9.9.9")
    assert streamer_main.get_version() == "9.9.9"


def test_bare_invocation_prints_the_role(monkeypatch, capsys):
    assert run(monkeypatch) == 0
    out = capsys.readouterr().out
    assert streamer_main.PROJECT_NAME in out and streamer_main.ROLE in out


def test_config_validate_lists_the_cameras(monkeypatch, capsys, cameras):
    assert run(monkeypatch, "config", "validate", "--config", cameras) == 0
    out = capsys.readouterr().out
    assert "2 camera(s)" in out and "cam0" in out and "config OK" in out


def test_config_commands_refuse_a_missing_file(monkeypatch, capsys, tmp_path):
    missing = str(tmp_path / "nope.json")
    for argv in (("validate",), ("gst", "--camera", "cam0"), ("mediamtx",)):
        assert run(monkeypatch, "config", argv[0], "--config", missing, *argv[1:]) == 1
        assert "error" in capsys.readouterr().err


def test_config_gst_refuses_a_base_that_is_not_a_plain_rtsp_url(monkeypatch, capsys, cameras):
    for base in ("http://host", "rtsp://user:pw@host", "rtsp://host/a b", "rtsp://host;rm"):
        assert run(monkeypatch, "config", "gst", "--config", cameras, "--camera", "cam0", "--rtsp-base", base) == 1
        assert "not a plain rtsp" in capsys.readouterr().err
    assert run(monkeypatch, "config", "gst", "--config", cameras, "--camera", "nope") == 1
    assert "no camera named" in capsys.readouterr().err


def test_config_gst_and_mediamtx_print_to_the_screen(monkeypatch, capsys, cameras):
    assert run(monkeypatch, "config", "gst", "--config", cameras, "--camera", "cam0", "--rtsp-base", "rtsp://localhost:8554") == 0
    assert "rtspclientsink" in capsys.readouterr().out
    assert run(monkeypatch, "config", "mediamtx", "--config", cameras) == 0
    assert "cam0" in capsys.readouterr().out


def test_config_mediamtx_to_a_file(monkeypatch, capsys, cameras, tmp_path):
    out = tmp_path / "paths.yml"
    assert run(monkeypatch, "config", "mediamtx", "--config", cameras, "--out", str(out)) == 0
    assert out.read_text(encoding="utf-8").strip() and "wrote" in capsys.readouterr().out


def test_simulate_refuses_a_consumer_rate_that_is_not_positive(monkeypatch, capsys):
    for rate in ("0", "-3"):
        assert run(monkeypatch, "stream", "simulate", "--consumer-rate", rate) == 1
        assert "positive" in capsys.readouterr().err


def test_simulate_keeps_the_buffer_inside_its_bound(monkeypatch, capsys):
    assert run(monkeypatch, "stream", "simulate", "--frames", "40", "--buffer-size", "4", "--consumer-rate", "10") == 0
    out = capsys.readouterr().out
    assert "Max buffer size observed: 4" in out and "Frames dropped by backpressure" in out
    assert "Reconnect backoff schedule" in out and "Final connection state" in out


def test_simulate_reports_a_buffer_that_exceeds_its_bound(monkeypatch, capsys):
    class Leaky:
        size = 99
        dropped_count = 0

        def __init__(self, max_size):
            pass

        def push(self, _item):
            pass

        def pop(self):
            pass

    monkeypatch.setattr(streamer_main, "FrameBuffer", Leaky)
    assert run(monkeypatch, "stream", "simulate", "--frames", "4", "--buffer-size", "2") == 1
    assert "FAIL" in capsys.readouterr().err


# ---- stream serve ----

def test_serve_needs_the_camera_flags_together(monkeypatch, capsys, cameras, served):
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--config", cameras) == 1
    assert "go together" in capsys.readouterr().err
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--camera", "cam0") == 1
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--config", cameras, "--camera", "cam0", "--device", "0") == 1
    assert "not both" in capsys.readouterr().err
    assert served == []


def test_serve_refuses_an_unreadable_list_and_an_unknown_camera(monkeypatch, capsys, cameras, tmp_path, served):
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--config", str(tmp_path / "x.json"), "--camera", "cam0") == 1
    assert "error" in capsys.readouterr().err
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--config", cameras, "--camera", "ghost") == 1
    assert "no camera named" in capsys.readouterr().err
    assert served == []


def test_serve_takes_the_size_and_device_from_the_list(monkeypatch, cameras, served):
    assert run(monkeypatch, "stream", "serve", "--port", "8081", "--config", cameras, "--camera", "cam0") == 0
    kind, args = served[0]
    assert kind == "one" and args[0] == "/dev/video0" and args[3:6] == (640, 480, 15)
    # an IP camera is opened by the address built from its file, which is never on the command line
    served.clear()
    assert run(monkeypatch, "stream", "serve", "--port", "8081", "--config", cameras, "--camera", "door") == 0
    assert served[0][1][0].startswith("rtsp://192.168.0.50") and served[0][1][0].endswith("/11")


def test_serve_reads_the_device_from_the_environment(monkeypatch, capsys, served):
    monkeypatch.delenv("HYDRA_TEST_CAM", raising=False)
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device-env", "HYDRA_TEST_CAM") == 1
    assert "is not set" in capsys.readouterr().err
    monkeypatch.setenv("HYDRA_TEST_CAM", "rtsp://u:p@10.0.0.2/x")
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device-env", "HYDRA_TEST_CAM") == 0
    assert served[0][1][0] == "rtsp://u:p@10.0.0.2/x"


def test_serve_needs_a_device(monkeypatch, capsys, served):
    assert run(monkeypatch, "stream", "serve", "--port", "1") == 1
    assert "--device" in capsys.readouterr().err
    assert served == []


def test_serve_refuses_a_bad_token_and_an_open_address_without_one(monkeypatch, capsys, tmp_path, served):
    monkeypatch.delenv("HYDRA_UMC_VISION_STREAMER_TOKEN", raising=False)
    short = tmp_path / "short.txt"
    short.write_text("abc", encoding="utf-8")
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0", "--token-file", str(short)) == 2
    assert "at least" in capsys.readouterr().err
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0", "--token-file", str(tmp_path / "none.txt")) == 2
    assert "cannot read the token file" in capsys.readouterr().err
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0", "--addr", "0.0.0.0") == 2
    assert "not loopback" in capsys.readouterr().err
    assert served == []


def test_serve_refuses_broken_optional_files(monkeypatch, capsys, tmp_path, served):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    for flag in ("--recording", "--publish", "--capture-tuning"):
        assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0", flag, str(bad)) == 2
        assert "error" in capsys.readouterr().err
    assert served == []


def test_serve_passes_the_optional_files_and_the_token_on(monkeypatch, tmp_path, served):
    token = tmp_path / "token.txt"
    token.write_text(GOOD_TOKEN, encoding="utf-8")
    tuning = tmp_path / "tuning.json"
    tuning.write_text(json.dumps({"rtspOpenTimeoutMs": 3000}), encoding="utf-8")
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0", "--addr", "0.0.0.0",
               "--token-file", str(token), "--capture-tuning", str(tuning)) == 0
    args = served[0][1]
    assert args[7] == GOOD_TOKEN and args[10].rtsp_open_timeout_ms == 3000


def test_serve_reports_a_camera_that_does_not_open_and_a_ctrl_c(monkeypatch, capsys):
    def unavailable(*_a):
        raise CameraUnavailableError("cannot open")

    monkeypatch.setattr(streamer_main, "serve_camera", unavailable)
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0") == 1
    assert "cannot open" in capsys.readouterr().err

    def interrupted(*_a):
        raise KeyboardInterrupt

    monkeypatch.setattr(streamer_main, "serve_camera", interrupted)
    assert run(monkeypatch, "stream", "serve", "--port", "1", "--device", "0") == 0


# ---- stream serve-all ----

def test_serve_all_refuses_a_missing_list_and_unknown_cameras(monkeypatch, capsys, cameras, tmp_path, served):
    assert run(monkeypatch, "stream", "serve-all", "--port", "1", "--config", str(tmp_path / "x.json")) == 1
    assert "error" in capsys.readouterr().err
    assert run(monkeypatch, "stream", "serve-all", "--port", "1", "--config", cameras, "--camera", "cam0", "--camera", "ghost") == 1
    assert "'ghost'" in capsys.readouterr().err
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    code = run(monkeypatch, "stream", "serve-all", "--port", "1", "--config", str(empty))
    assert code == 1
    assert served == []


def test_serve_all_refuses_a_bad_token_a_bad_skew_and_broken_files(monkeypatch, capsys, cameras, tmp_path, served):
    monkeypatch.delenv("HYDRA_UMC_VISION_STREAMER_TOKEN", raising=False)
    base = ("stream", "serve-all", "--port", "1", "--config", cameras)
    short = tmp_path / "short.txt"
    short.write_text("abc", encoding="utf-8")
    assert run(monkeypatch, *base, "--token-file", str(short)) == 2
    capsys.readouterr()
    assert run(monkeypatch, *base, "--addr", "0.0.0.0") == 2
    assert "not loopback" in capsys.readouterr().err
    assert run(monkeypatch, *base, "--snapshot-max-skew-ms", "-5") == 2
    assert "--snapshot-max-skew-ms" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    for flag in ("--recording", "--publish", "--capture-tuning"):
        assert run(monkeypatch, *base, flag, str(bad)) == 2
        assert "error" in capsys.readouterr().err
    assert served == []


def test_serve_all_serves_the_chosen_cameras(monkeypatch, cameras, served):
    assert run(monkeypatch, "stream", "serve-all", "--port", "9", "--config", cameras, "--camera", "door", "--snapshot-max-skew-ms", "40") == 0
    kind, args = served[0]
    assert kind == "all" and list(args[0]) == ["door"] and args[0]["door"][0].startswith("rtsp://")
    assert args[4] == "" and args[5] == 40.0  # no token on loopback; the skew limit passed on
    served.clear()
    assert run(monkeypatch, "stream", "serve-all", "--port", "9", "--config", cameras) == 0
    assert sorted(served[0][1][0]) == ["cam0", "door"]


def test_serve_all_reports_an_unavailable_camera_and_a_ctrl_c(monkeypatch, capsys, cameras):
    def unavailable(*_a):
        raise CameraUnavailableError("busy")

    monkeypatch.setattr(streamer_main, "serve_cameras", unavailable)
    assert run(monkeypatch, "stream", "serve-all", "--port", "1", "--config", cameras) == 1
    assert "busy" in capsys.readouterr().err

    def interrupted(*_a):
        raise KeyboardInterrupt

    monkeypatch.setattr(streamer_main, "serve_cameras", interrupted)
    assert run(monkeypatch, "stream", "serve-all", "--port", "1", "--config", cameras) == 0


# ---- discover-usb ----

def test_discover_usb_prints_the_devices_or_the_reason(monkeypatch, capsys):
    monkeypatch.setattr(streamer_main, "discover_usb_devices", lambda max_index=10: [{"index": 0, "max": max_index}])
    assert run(monkeypatch, "discover-usb", "--max", "3") == 0
    assert json.loads(capsys.readouterr().out) == [{"index": 0, "max": 3}]

    def no_opencv(max_index=10):
        raise RuntimeError("opencv-python (cv2) is not installed")

    monkeypatch.setattr(streamer_main, "discover_usb_devices", no_opencv)
    assert run(monkeypatch, "discover-usb") == 1
    assert "not installed" in capsys.readouterr().err
