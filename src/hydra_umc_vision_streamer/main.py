# =============================================================================
# HYDRA-UMC-VISION-STREAMER - entry point: src/hydra_umc_vision_streamer/main.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Entry point for HYDRA-UMC-VISION-STREAMER.

Skeleton stage: prints identity and exits 0. Real pipeline logic (GStreamer
graph construction, V4L2 capture, hardware ISP resize/format conversion,
zero-copy handoff to the Hailo-8 runtime) lands when this project's turn
comes up in SONNET/5.PLAN_EJECUCION_32_PROYECTOS_NUEVOS.txt.
"""
from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

PROJECT_NAME = "HYDRA-UMC-VISION-STREAMER"
DIST_NAME = "hydra-umc-vision-streamer"
ROLE = (
    "Optimized GStreamer capture/pre-processing pipeline for up to 8x USB "
    "3.0 camera streams feeding the Hailo-8 NPU."
)


def get_version() -> str:
    """Read the running version from installed package metadata, which is
    sourced from pyproject.toml - the single place bump_version.py edits.

    Why not a hardcoded __version__ string here instead? That would give
    this project two places to keep in sync on every build (pyproject.toml
    AND this module). Reading it back from installed metadata means this
    function can never drift out of sync with the number bump_version.py
    actually wrote."""
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        return "0.0.0-dev (package not installed - run build.sh/build.bat first)"


def main() -> int:
    # Skeleton stage on purpose: this is the whole entry point today. It
    # confirms the package installs, imports and runs cleanly end to end
    # before the real GStreamer/V4L2/ISP pipeline is built on top of it.
    print(f"{PROJECT_NAME} v{get_version()}")
    print(ROLE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
