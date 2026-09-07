from hydra_umc_vision_streamer.config import CameraConfig
from hydra_umc_vision_streamer.pipeline import build_capture_pipeline


def test_mjpg_pipeline_uses_jpeg_caps_and_decoder():
    camera = CameraConfig(name="cam0", device="/dev/video0", width=1920, height=1080, fps=30, format="MJPG")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/cam0")

    assert "v4l2src device=/dev/video0" in pipeline
    assert "image/jpeg,width=1920,height=1080,framerate=30/1" in pipeline
    assert "jpegdec" in pipeline
    assert "tee name=t" in pipeline
    assert "appsink name=cam0_hailo_sink" in pipeline
    assert "rtspclientsink location=rtsp://localhost:8554/cam0" in pipeline


def test_yuyv_pipeline_uses_raw_caps_no_decoder():
    camera = CameraConfig(name="cam1", device="/dev/video1", width=640, height=480, fps=15, format="YUYV")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/cam1")

    assert "video/x-raw,format=YUY2,width=640,height=480,framerate=15/1" in pipeline
    assert "jpegdec" not in pipeline


def test_h264_pipeline_uses_h264_decoder():
    camera = CameraConfig(name="cam2", device="/dev/video2", width=1280, height=720, fps=60, format="H264")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/cam2")

    assert "video/x-h264,width=1280,height=720,framerate=60/1" in pipeline
    assert "h264parse ! avdec_h264" in pipeline


def test_pipeline_is_a_single_tee_with_two_branches():
    camera = CameraConfig(name="cam0", device="/dev/video0", width=640, height=480, fps=30, format="MJPG")
    pipeline = build_capture_pipeline(camera, "rtsp://localhost:8554/cam0")

    assert pipeline.count("tee name=t") == 1
    assert pipeline.count("t. !") == 2
