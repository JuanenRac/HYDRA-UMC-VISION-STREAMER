from hydra_umc_vision_streamer.config import CameraConfig
from hydra_umc_vision_streamer.mediamtx_config import build_mediamtx_paths_yaml, rtsp_url_for


def _cam(name="cam0"):
    return CameraConfig(name=name, device="/dev/video0", width=1920, height=1080, fps=30, format="MJPG")


def test_rtsp_url_for_strips_trailing_slash():
    camera = _cam("cam0")
    assert rtsp_url_for(camera, "rtsp://localhost:8554/") == "rtsp://localhost:8554/cam0"
    assert rtsp_url_for(camera, "rtsp://localhost:8554") == "rtsp://localhost:8554/cam0"


def test_empty_camera_list_produces_empty_paths():
    assert build_mediamtx_paths_yaml([]) == "paths: {}\n"


def test_single_camera_yaml_shape():
    yaml_text = build_mediamtx_paths_yaml([_cam("cam0")])
    assert yaml_text == "paths:\n  cam0:\n    source: publisher\n"


def test_multiple_cameras_each_get_an_entry():
    yaml_text = build_mediamtx_paths_yaml([_cam("cam0"), _cam("cam1")])
    lines = yaml_text.splitlines()
    assert lines[0] == "paths:"
    assert "  cam0:" in lines
    assert "  cam1:" in lines
    assert lines.count("    source: publisher") == 2
