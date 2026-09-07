# =============================================================================
# HYDRA-UMC-VISION-STREAMER - package init: src/hydra_umc_vision_streamer/__init__.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""HYDRA-UMC-VISION-STREAMER - GStreamer capture/pre-processing pipeline for
up to 8x USB 3.0 camera streams, feeding the Hailo-8 NPU on
HYDRA-UMC-VISION-NODE (the integration parent of this project).

No `hardware/`, `firmware/`, `os/` or `models/` folder here: CM5 + Hailo-8
is off-the-shelf hardware with no board of its own to design, and the
shared OS image / compiled models this pipeline runs alongside live only
in the integration parent, HYDRA-UMC-VISION-NODE - carrying copies here
would just be two places to keep in sync for no benefit.

The installed package version is the single source of truth in
pyproject.toml (read at runtime via importlib.metadata), never duplicated
here, so bump_version.py only ever has one place to edit.
"""
