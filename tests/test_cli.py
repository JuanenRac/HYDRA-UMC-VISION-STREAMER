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
