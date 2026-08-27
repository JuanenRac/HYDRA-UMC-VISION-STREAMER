import json

import pytest

from hydra_umc_vision_streamer.config import ConfigError, load_cameras


def _cam(name="cam0", device="/dev/video0", width=1920, height=1080, fps=30, fmt="MJPG"):
    return {"name": name, "device": device, "width": width, "height": height, "fps": fps, "format": fmt}


def _write(path, cameras):
    path.write_text(json.dumps(cameras), encoding="utf-8")


def test_load_valid_cameras(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(), _cam(name="cam1", device="/dev/video1")])
    cameras = load_cameras(p)
    assert len(cameras) == 2
    assert cameras[0].name == "cam0"
    assert cameras[1].device == "/dev/video1"


def test_missing_field(tmp_path):
    p = tmp_path / "cameras.json"
    bad = _cam()
    del bad["fps"]
    _write(p, [bad])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_device_must_start_with_dev(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(device="video0")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_negative_dimension_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(width=-1)])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_invalid_format_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(fmt="RAW")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_duplicate_name_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(), _cam(device="/dev/video1")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_duplicate_device_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(), _cam(name="cam1")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_not_a_list(tmp_path):
    p = tmp_path / "cameras.json"
    p.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_malformed_json(tmp_path):
    p = tmp_path / "cameras.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_cameras(p)
