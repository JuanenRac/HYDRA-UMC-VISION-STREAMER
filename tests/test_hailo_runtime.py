from pathlib import Path

import pytest

from hydra_umc_vision_streamer.config import CameraConfig
from hydra_umc_vision_streamer.hailo_runtime import (
    FrameShapeError,
    HailoDetectionModel,
    HailoNotAvailableError,
    expected_input_frame_bytes,
    load_hailo_detection_model,
    open_vdevice,
    validate_frame_matches_input,
)


def _cam(name="cam0", width=1920, height=1080):
    return CameraConfig(name=name, device="/dev/video0", width=width, height=height, fps=30, format="MJPG")


def _model(input_shape=(1080, 1920, 3)):
    # Constructed directly (never via load_hailo_detection_model, which
    # needs real hailort) - proves the frame-validation logic works
    # against any object with the real HailoDetectionModel shape,
    # hailort installed or not.
    return HailoDetectionModel(
        hef_path=Path("yolo-detector.hef"),
        input_name="yolo_input",
        input_shape=input_shape,
        output_name="yolo_nms",
        output_shape=(100, 5),
        network_group=object(),
    )


def test_open_vdevice_raises_clear_error_without_hailort():
    # hailort is not installed on this development machine - the real,
    # honest state this module must degrade to cleanly.
    with pytest.raises(HailoNotAvailableError, match="hailort is not installed"):
        open_vdevice()


def test_load_hailo_detection_model_raises_clear_error_without_hailort():
    with pytest.raises(HailoNotAvailableError, match="hailort is not installed"):
        load_hailo_detection_model(vdevice=object(), hef_path=Path("yolo-detector.hef"))


def test_expected_input_frame_bytes_rgb():
    assert expected_input_frame_bytes((1080, 1920, 3), "RGB") == 1080 * 1920 * 3


def test_expected_input_frame_bytes_rgba():
    assert expected_input_frame_bytes((480, 640, 4), "RGBA") == 480 * 640 * 4


def test_expected_input_frame_bytes_unsupported_format():
    with pytest.raises(FrameShapeError, match="unsupported pixel format"):
        expected_input_frame_bytes((1080, 1920, 3), "YUYV")


def test_expected_input_frame_bytes_wrong_rank():
    with pytest.raises(FrameShapeError, match="3D"):
        expected_input_frame_bytes((1080, 1920), "RGB")


def test_expected_input_frame_bytes_channel_mismatch():
    with pytest.raises(FrameShapeError, match="channel"):
        expected_input_frame_bytes((1080, 1920, 4), "RGB")


def test_validate_frame_matches_input_ok():
    camera = _cam(width=1920, height=1080)
    model = _model(input_shape=(1080, 1920, 3))
    # Must not raise.
    validate_frame_matches_input(camera, model)


def test_validate_frame_matches_input_resolution_mismatch():
    camera = _cam(width=640, height=480)
    model = _model(input_shape=(1080, 1920, 3))
    with pytest.raises(FrameShapeError, match="cam0.*configured at 640x480"):
        validate_frame_matches_input(camera, model)


def test_validate_frame_matches_input_rejects_a_transposed_resolution():
    # Real bug found in audit: a camera configured 1080x1920 (portrait)
    # against a model expecting 1920x1080 (landscape) has the exact same
    # total byte count (1920*1080*3 either way) - a check that only
    # compared byte totals let this through silently even though the
    # frame is genuinely transposed relative to what the model expects.
    camera = _cam(width=1080, height=1920)
    model = _model(input_shape=(1080, 1920, 3))  # expects height=1080, width=1920
    with pytest.raises(FrameShapeError, match="cam0.*configured at 1080x1920"):
        validate_frame_matches_input(camera, model)
