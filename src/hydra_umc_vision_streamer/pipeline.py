# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/pipeline.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""GStreamer pipeline description generation.

Deciding the pipeline *topology* - which elements, in which order, with
which caps - is a design/string-building problem, separate from actually
running it (which needs GStreamer/PyGObject installed and a real camera
at the device path). This module produces the exact `gst-launch-1.0`
description this project intends to execute once that runtime lands; it
does not open a device or import GStreamer itself.
"""
from __future__ import annotations

from .config import CameraConfig

_CAPS_BY_FORMAT = {
    "MJPG": "image/jpeg,width={width},height={height},framerate={fps}/1",
    "YUYV": "video/x-raw,format=YUY2,width={width},height={height},framerate={fps}/1",
    "H264": "video/x-h264,width={width},height={height},framerate={fps}/1",
}

_DECODE_BY_FORMAT = {
    "MJPG": "jpegdec ! videoconvert",
    "YUYV": "videoconvert",
    "H264": "h264parse ! avdec_h264 ! videoconvert",
}


_IP_DEPAY_BY_FORMAT = {
    "H264": "rtph264depay ! h264parse ! avdec_h264 ! videoconvert",
    "MJPG": "rtpjpegdepay ! jpegdec ! videoconvert",
}


def build_capture_pipeline(camera: CameraConfig, rtsp_url: str) -> str:
    """The gst-launch-1.0 description for one camera's capture pipeline.

    Splits the decoded stream with a `tee`: one branch into an `appsink`
    for the (future) Hailo-8 inference process to pull frames from, one
    branch pushed out over RTSP via `rtspclientsink` to the (future)
    MediaMTX relay, at the URL `build_mediamtx_paths()`/the caller
    already agreed this camera's path maps to.

    Both branches are leaky and bounded: a slow consumer drops frames
    instead of accumulating them or stalling the other branch. An IP camera
    is read with `rtspsrc` (never `v4l2src`), and its credentials are not
    printed - they are expected in `$CAMERA_USER` / `$CAMERA_PASSWORD`.
    """
    if camera.source_type == "ip":
        depay = _IP_DEPAY_BY_FORMAT.get(camera.format)
        if depay is None:
            raise ValueError(f"an IP camera streams H264 or MJPG, not {camera.format!r}")
        credentials = " user-id=$CAMERA_USER user-pw=$CAMERA_PASSWORD" if camera.username or camera.password else ""
        source = f"rtspsrc location={camera.display_target()} latency=0{credentials} ! {depay}"
    else:
        caps = _CAPS_BY_FORMAT[camera.format].format(
            width=camera.width, height=camera.height, fps=camera.fps
        )
        decode = _DECODE_BY_FORMAT[camera.format]
        source = f"v4l2src device={camera.device} ! {caps} ! {decode}"

    return (
        f"{source} ! "
        f"tee name=t "
        f"t. ! queue leaky=downstream max-size-buffers=1 ! appsink name={camera.name}_hailo_sink max-buffers=1 drop=true sync=false "
        f"t. ! queue leaky=downstream max-size-buffers=2 ! rtspclientsink location={rtsp_url}"
    )
