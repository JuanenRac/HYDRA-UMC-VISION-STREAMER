import json
import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "hydra_umc_vision_streamer.main", *args],
        capture_output=True, text=True,
    )


def _write_config(path, cameras=None):
    if cameras is None:
        cameras = [{"name": "cam0", "device": "/dev/video0", "width": 1920, "height": 1080, "fps": 30, "format": "MJPG"}]
    path.write_text(json.dumps(cameras), encoding="utf-8")


def test_bare_invocation_prints_identity():
    result = run_cli()
    assert result.returncode == 0
    assert "HYDRA-UMC-VISION-STREAMER" in result.stdout


def test_config_validate(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p)
    result = run_cli("config", "validate", "--config", str(p))
    assert result.returncode == 0
    assert "config OK" in result.stdout


def test_config_validate_bad_config(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p, cameras=[{"name": "cam0"}])
    result = run_cli("config", "validate", "--config", str(p))
    assert result.returncode == 1
    assert "error" in result.stderr


def test_config_gst(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p)
    result = run_cli("config", "gst", "--config", str(p), "--camera", "cam0")
    assert result.returncode == 0
    assert "v4l2src device=/dev/video0" in result.stdout
    assert "rtspclientsink location=rtsp://localhost:8554/cam0" in result.stdout


def test_config_gst_unknown_camera(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p)
    result = run_cli("config", "gst", "--config", str(p), "--camera", "nope")
    assert result.returncode == 1


def test_config_mediamtx_stdout(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p)
    result = run_cli("config", "mediamtx", "--config", str(p))
    assert result.returncode == 0
    assert "paths:" in result.stdout
    assert "cam0:" in result.stdout


def test_config_mediamtx_to_file(tmp_path):
    p = tmp_path / "cameras.json"
    _write_config(p)
    out = tmp_path / "mediamtx_paths.yml"
    result = run_cli("config", "mediamtx", "--config", str(p), "--out", str(out))
    assert result.returncode == 0
    assert out.exists()
    assert "source: publisher" in out.read_text(encoding="utf-8")


def test_stream_simulate_default_run_stays_within_bound():
    result = run_cli("stream", "simulate")
    assert result.returncode == 0
    assert "Max buffer size observed: 8 (must never exceed 8)" in result.stdout
    assert "Frames dropped by backpressure:" in result.stdout


def test_stream_simulate_reports_a_real_dropped_frame_count_with_a_slow_consumer():
    # A tiny buffer and a very slow consumer (rate=1000, i.e. essentially
    # never pops during a 500-frame run) must drop real frames.
    result = run_cli(
        "stream", "simulate", "--buffer-size", "4", "--frames", "500", "--consumer-rate", "1000",
    )
    assert result.returncode == 0
    assert "Max buffer size observed: 4 (must never exceed 4)" in result.stdout
    # Roughly frames - buffer_size frames must have been dropped (minus
    # the one real pop at i == 0).
    assert "Frames dropped by backpressure: 495" in result.stdout


def test_stream_simulate_rejects_zero_consumer_rate():
    # --consumer-rate 0 would be `i % 0`, an unhandled ZeroDivisionError -
    # this must be a clean CLI error instead.
    result = run_cli("stream", "simulate", "--consumer-rate", "0")
    assert result.returncode == 1
    assert "error" in result.stderr
    assert "ZeroDivisionError" not in result.stderr


def test_stream_simulate_prints_the_real_reconnect_schedule():
    # max_reconnect_attempts=3 means attempts 1 and 2 each produce a
    # real scheduled delay; the 3rd call exhausts the budget and gives
    # up honestly instead of retrying forever.
    result = run_cli(
        "stream", "simulate", "--frames", "100", "--max-reconnect-attempts", "3",
        "--base-delay", "1.0", "--max-delay", "100.0",
    )
    assert result.returncode == 0
    assert "Reconnect backoff schedule (s): [1.0, 2.0]" in result.stdout
    assert "Final connection state: given_up" in result.stdout
