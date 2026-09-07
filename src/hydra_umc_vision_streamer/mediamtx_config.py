# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/mediamtx_config.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""MediaMTX `paths` section generation.

Hand-rolled rather than built on PyYAML: the shape this project needs
(one flat `paths:` map, one `source: publisher` entry per camera) is
simple and fixed enough that a real dependency isn't justified yet - see
pyproject.toml. If per-camera config grows nested/list-valued fields,
revisit this and pull in PyYAML then, not before.
"""
from __future__ import annotations

from .config import CameraConfig


def rtsp_url_for(camera: CameraConfig, rtsp_base: str) -> str:
    """The RTSP URL this camera's GStreamer branch publishes to, and
    that MediaMTX exposes it back out on. Both sides must agree on this
    path, so it's derived here from the camera name rather than
    duplicated in each caller."""
    return f"{rtsp_base.rstrip('/')}/{camera.name}"


def build_mediamtx_paths_yaml(cameras: list[CameraConfig]) -> str:
    """The `paths:` section of a mediamtx.yml, one entry per camera.

    `source: publisher` means MediaMTX expects a client (this project's
    own `rtspclientsink` branch) to push the stream in, rather than
    MediaMTX pulling from an external source - matching the pipeline
    `build_capture_pipeline()` generates.
    """
    if not cameras:
        return "paths: {}\n"

    lines = ["paths:"]
    for camera in cameras:
        lines.append(f"  {camera.name}:")
        lines.append("    source: publisher")
    return "\n".join(lines) + "\n"
