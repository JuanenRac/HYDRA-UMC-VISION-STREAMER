# =============================================================================
# HYDRA-UMC-VISION-STREAMER - entry point: src/hydra_umc_vision_streamer/main.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Entry point for HYDRA-UMC-VISION-STREAMER.

Real v0: the per-camera configuration layer (config.py) and the two
things it drives - the GStreamer pipeline description (pipeline.py) and
the MediaMTX relay config (mediamtx_config.py) - independent of the
V4L2/GStreamer/Hailo-8 runtime and physical USB cameras this project
doesn't have in this environment. Actually opening a device and running
the generated pipeline is still future work.
"""
from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import ConfigError, load_cameras
from .mediamtx_config import build_mediamtx_paths_yaml, rtsp_url_for
from .pipeline import build_capture_pipeline

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


def _cmd_config_validate(args: argparse.Namespace) -> int:
    try:
        cameras = load_cameras(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{len(cameras)} camera(s) in {args.config}")
    for camera in cameras:
        print(f"  {camera.name}: {camera.device} {camera.width}x{camera.height}@{camera.fps} {camera.format}")
    print("config OK")
    return 0


def _cmd_config_gst(args: argparse.Namespace) -> int:
    try:
        cameras = load_cameras(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    matches = [c for c in cameras if c.name == args.camera]
    if not matches:
        print(f"no camera named {args.camera!r} in {args.config}", file=sys.stderr)
        return 1
    camera = matches[0]

    rtsp_url = rtsp_url_for(camera, args.rtsp_base)
    print(build_capture_pipeline(camera, rtsp_url))
    return 0


def _cmd_config_mediamtx(args: argparse.Namespace) -> int:
    try:
        cameras = load_cameras(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    yaml_text = build_mediamtx_paths_yaml(cameras)
    if args.out:
        Path(args.out).write_text(yaml_text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(yaml_text, end="")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydra-umc-vision-streamer")
    subparsers = parser.add_subparsers(dest="command")

    config = subparsers.add_parser("config", help="Inspect and generate config from the camera list.")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    validate = config_sub.add_parser("validate", help="Validate a camera config file.")
    validate.add_argument("--config", required=True, help="Path to the camera list JSON file")
    validate.set_defaults(func=_cmd_config_validate)

    gst = config_sub.add_parser("gst", help="Print the GStreamer pipeline description for one camera.")
    gst.add_argument("--config", required=True, help="Path to the camera list JSON file")
    gst.add_argument("--camera", required=True, help="Camera name to build the pipeline for")
    gst.add_argument("--rtsp-base", default="rtsp://localhost:8554", dest="rtsp_base",
                      help="MediaMTX RTSP base URL (default: rtsp://localhost:8554)")
    gst.set_defaults(func=_cmd_config_gst)

    mediamtx = config_sub.add_parser("mediamtx", help="Generate the MediaMTX paths.yml section for all cameras.")
    mediamtx.add_argument("--config", required=True, help="Path to the camera list JSON file")
    mediamtx.add_argument("--out", default=None, help="Write to this file instead of stdout")
    mediamtx.set_defaults(func=_cmd_config_mediamtx)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        # Skeleton stage identity print, still the default bare invocation:
        # confirms the package installs, imports and runs cleanly end to
        # end before/alongside the real GStreamer/V4L2/ISP pipeline.
        print(f"{PROJECT_NAME} v{get_version()}")
        print(ROLE)
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
