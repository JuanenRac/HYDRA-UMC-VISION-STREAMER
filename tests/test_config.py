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


def test_name_with_unsafe_characters_rejected(tmp_path):
    # camera.name is written unescaped into generated YAML and gst-launch
    # pipeline strings - a colon or newline would corrupt either one.
    p = tmp_path / "cameras.json"
    _write(p, [_cam(name="cam0: evil")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_name_with_newline_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(name="cam0\nsource: publisher")])
    with pytest.raises(ConfigError):
        load_cameras(p)


def test_name_with_hyphen_and_underscore_still_parses(tmp_path):
    # A legitimate name using the allowed safe characters must not regress.
    p = tmp_path / "cameras.json"
    _write(p, [_cam(name="cam-0_front")])
    cameras = load_cameras(p)
    assert cameras[0].name == "cam-0_front"


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


def test_non_object_camera_entry_is_rejected_cleanly(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, ["not-a-camera"])
    with pytest.raises(ConfigError, match="entry must be an object"):
        load_cameras(p)


def test_boolean_capture_dimension_is_not_an_integer(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(width=True)])
    with pytest.raises(ConfigError, match="width must be a positive integer"):
        load_cameras(p)


def test_more_than_eight_cameras_is_rejected_before_generation(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(name=f"cam{i}", device=f"/dev/video{i}") for i in range(9)])
    with pytest.raises(ConfigError, match="maximum is 8"):
        load_cameras(p)


def test_malformed_json(tmp_path):
    p = tmp_path / "cameras.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_cameras(p)


# --- IP camera (source_type="ip") - real RTSP config, verified end to end
# against 2 real local-network IP cameras (see config.py's own header for
# the real firmware/paths this was tested against). ------------------------


def _ip_cam(name="cam0", host="192.168.0.210", rtsp_path="/11", rtsp_port=554, username="admin", password="Admin123456", width=1920, height=1080, fps=30, fmt="H264"):
    return {
        "name": name, "source_type": "ip", "host": host, "rtsp_path": rtsp_path, "rtsp_port": rtsp_port,
        "username": username, "password": password, "width": width, "height": height, "fps": fps, "format": fmt,
    }


def test_load_valid_ip_camera(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_ip_cam()])
    cameras = load_cameras(p)
    assert len(cameras) == 1
    cam = cameras[0]
    assert cam.source_type == "ip"
    assert cam.device == ""
    assert cam.rtsp_url() == "rtsp://admin:Admin123456@192.168.0.210:554/11"


def test_ip_camera_missing_host_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    cam = _ip_cam()
    del cam["host"]
    _write(p, [cam])
    with pytest.raises(ConfigError, match="host is required"):
        load_cameras(p)


def test_ip_camera_missing_rtsp_path_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    cam = _ip_cam()
    del cam["rtsp_path"]
    _write(p, [cam])
    with pytest.raises(ConfigError, match="rtsp_path is required"):
        load_cameras(p)


def test_ip_camera_invalid_port_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_ip_cam(rtsp_port=70000)])
    with pytest.raises(ConfigError, match="rtsp_port must be a valid port"):
        load_cameras(p)


def test_ip_camera_without_credentials_omits_userinfo(tmp_path):
    # A real camera with RTSP auth disabled - rtsp_url() must not emit a
    # bare "@" with nothing in front of it.
    p = tmp_path / "cameras.json"
    _write(p, [_ip_cam(username="", password="")])
    cameras = load_cameras(p)
    assert cameras[0].rtsp_url() == "rtsp://192.168.0.210:554/11"


def test_ip_camera_password_with_special_characters_percent_encoded(tmp_path):
    # A real password containing "@"/":" must not be misparsed as a second
    # userinfo delimiter in the built RTSP URL.
    p = tmp_path / "cameras.json"
    _write(p, [_ip_cam(password="p@ss:word/1")])
    cameras = load_cameras(p)
    url = cameras[0].rtsp_url()
    assert url == "rtsp://admin:p%40ss%3Aword%2F1@192.168.0.210:554/11"


def test_invalid_source_type_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    cam = _ip_cam()
    cam["source_type"] = "bluetooth"
    _write(p, [cam])
    with pytest.raises(ConfigError, match="source_type"):
        load_cameras(p)


def test_usb_and_ip_cameras_coexist_in_one_config(tmp_path):
    p = tmp_path / "cameras.json"
    _write(p, [_cam(name="usb0"), _ip_cam(name="ip0")])
    cameras = load_cameras(p)
    assert len(cameras) == 2
    assert cameras[0].source_type == "usb"
    assert cameras[1].source_type == "ip"


def test_duplicate_ip_camera_host_and_path_rejected(tmp_path):
    p = tmp_path / "cameras.json"
    # Different credentials, same real connection - still a real duplicate.
    _write(p, [_ip_cam(name="cam0", password="Admin123456"), _ip_cam(name="cam1", password="different")])
    with pytest.raises(ConfigError, match="duplicate camera connection"):
        load_cameras(p)


def test_ip_cameras_on_same_host_different_path_are_not_duplicates(tmp_path):
    # A real, common case: one physical camera's own main (/11) and sub
    # (/12) streams configured as two separate CameraConfig entries.
    p = tmp_path / "cameras.json"
    _write(p, [_ip_cam(name="cam0_main", rtsp_path="/11"), _ip_cam(name="cam0_sub", rtsp_path="/12")])
    cameras = load_cameras(p)
    assert len(cameras) == 2
