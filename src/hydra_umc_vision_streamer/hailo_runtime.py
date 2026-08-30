# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/hailo_runtime.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real HailoRT (hailo_platform) integration boundary for the Hailo-8
inference stage pipeline.py already reserves an appsink for
(`appsink name={camera}_hailo_sink`) but nothing in this repo has, until
now, actually known how to load a real Hailo-8 model or check a captured
frame against it. This module is that missing piece, prepared ahead of
the real Hailo-8 M.2 module landing (see this project's own README): once
it plugs in, `load_hailo_detection_model()` is the one function that
needs to actually run against real silicon - everything else here is
real, tested logic today.

The real pip package is `hailort` (not on PyPI - Hailo Developer Zone, or
`apt install hailo-all` on Raspberry Pi OS with a Hailo module attached);
its Python import name is `hailo_platform`. Real, confirmed API surface
used here: `VDevice()`, `HEF(path)`, `ConfigureParams.create_from_hef(hef,
interface=HailoStreamInterface.PCIe)`, `vdevice.configure(hef,
configure_params)` -> a list of `ConfiguredNetworkGroup`, and each vstream
info exposing real `.name`/`.shape` attributes via
`hef.get_input_vstream_infos()` / `get_output_vstream_infos()`. Actually
running inference (`InferVStreams(...)` as a context manager around an
activated network group, then parsing its own NMS output format) is the
next real step once a real detection `.hef` exists - not added here, to
avoid guessing at a byte-exact output layout this project cannot verify
without the real device in hand.

Same lazy-import + injectable-boundary pattern as every other real
hardware transport this ecosystem has added (serial_transport.py,
mavlink_transport.py, VLA-ENGINE's own hailo_runtime.py, ...):
`hailo_platform` is imported only inside the two functions that genuinely
need real HailoRT (`open_vdevice`, `load_hailo_detection_model`), each
raising a clear `HailoNotAvailableError` instead of a bare `ImportError`
when the package isn't installed - true on this development machine
today. `expected_input_frame_bytes()`/`validate_frame_matches_input()`
are real, hardware-independent pre-flight checks against `config.py`'s
existing `CameraConfig`, fully unit-testable without hailort.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import CameraConfig

HAILORT_INSTALL_HINT = (
    "hailort is not installed - get it from the Hailo Developer Zone, or "
    "`apt install hailo-all` on Raspberry Pi OS with a Hailo-8 module attached "
    "(it is not on PyPI). This module's frame-shape validation logic works "
    "and is tested without it."
)

# Real per-pixel byte counts for the raw formats a Hailo-8 input tensor is
# fed as after pipeline.py's own `videoconvert`/`jpegdec` decode stage -
# this project always decodes to a plain interleaved raw format before
# the tee, never keeps MJPG/H264 compressed bytes past that point.
_BYTES_PER_PIXEL = {"RGB": 3, "RGBA": 4}


class HailoNotAvailableError(RuntimeError):
    """Raised when hailo_platform (the hailort package) is not importable."""


class FrameShapeError(ValueError):
    """Raised when a captured frame's byte size doesn't match what a
    loaded Hailo model's real input tensor expects."""


@dataclass(frozen=True)
class HailoDetectionModel:
    """A real HailoRT network group, configured from a real .hef file -
    only ever constructed by load_hailo_detection_model() below, never by
    hand, since `network_group` is a real HailoRT object."""

    hef_path: Path
    input_name: str
    input_shape: tuple[int, ...]
    output_name: str
    output_shape: tuple[int, ...]
    network_group: object


def open_vdevice() -> object:
    """Open a real Hailo VDevice targeting whichever Hailo-8 module is
    actually attached - the only place this module imports hailo_platform
    to obtain one. Lazy, so a host without the real hailort package
    installed still gets a clear RuntimeError instead of an ImportError
    surfacing from deep inside this module.
    """
    try:
        from hailo_platform import VDevice  # type: ignore[import-not-found]
    except ImportError as error:
        raise HailoNotAvailableError(HAILORT_INSTALL_HINT) from error
    return VDevice()


def load_hailo_detection_model(vdevice: object, hef_path: Path) -> HailoDetectionModel:
    """Configure a real detection .hef onto an already-open VDevice and
    extract its real input/output vstream shapes.

    Real HailoRT flow: HEF(path) -> ConfigureParams.create_from_hef(hef,
    interface=HailoStreamInterface.PCIe) -> vdevice.configure(hef, params).
    Needs a real hailort install and a real compiled detection .hef - this
    function is the one real boundary where that dependency is
    unavoidable. Requires exactly one input vstream (this pipeline feeds
    one decoded camera frame at a time) but tolerates any number of
    output vstreams, since a real detection model's NMS-postprocessed
    output layout isn't parsed here (see this module's own header).
    """
    try:
        from hailo_platform import (  # type: ignore[import-not-found]
            HEF,
            ConfigureParams,
            HailoStreamInterface,
        )
    except ImportError as error:
        raise HailoNotAvailableError(HAILORT_INSTALL_HINT) from error

    hef = HEF(str(hef_path))
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = vdevice.configure(hef, configure_params)
    network_group = network_groups[0]

    input_infos = hef.get_input_vstream_infos()
    output_infos = hef.get_output_vstream_infos()
    if len(input_infos) != 1:
        raise HailoNotAvailableError(
            f"{hef_path}: expected exactly 1 input vstream for this pipeline's "
            f"one-frame-at-a-time feed, got {len(input_infos)}"
        )
    if not output_infos:
        raise HailoNotAvailableError(f"{hef_path}: model declares no output vstreams")

    return HailoDetectionModel(
        hef_path=hef_path,
        input_name=input_infos[0].name,
        input_shape=tuple(input_infos[0].shape),
        output_name=output_infos[0].name,
        output_shape=tuple(output_infos[0].shape),
        network_group=network_group,
    )


def expected_input_frame_bytes(input_shape: tuple[int, ...], pixel_format: str = "RGB") -> int:
    """The real raw byte count one frame at `input_shape` (a real HailoRT
    vstream shape, e.g. (height, width, channels)) must have once
    decoded to `pixel_format` - the same interleaved format
    pipeline.py's `videoconvert`/`jpegdec ! videoconvert` decode stage
    already produces before the appsink tee.
    """
    if pixel_format not in _BYTES_PER_PIXEL:
        raise FrameShapeError(f"unsupported pixel format {pixel_format!r} (known: {sorted(_BYTES_PER_PIXEL)})")
    if len(input_shape) != 3:
        raise FrameShapeError(f"expected a 3D (height, width, channels) input shape, got {input_shape}")
    height, width, channels = input_shape
    if channels != _BYTES_PER_PIXEL[pixel_format]:
        raise FrameShapeError(
            f"input tensor has {channels} channel(s), but {pixel_format} decodes to "
            f"{_BYTES_PER_PIXEL[pixel_format]} - this camera's captured frames cannot "
            f"feed this model without a resize/color-convert stage this pipeline doesn't have yet"
        )
    return height * width * channels


def validate_frame_matches_input(
    camera: CameraConfig, model: HailoDetectionModel, pixel_format: str = "RGB"
) -> None:
    """Real pre-flight check: does this camera's configured resolution
    actually match what the loaded model's real input tensor expects?
    Catching a resolution mismatch here, before a single real frame is
    ever pushed at the device, is strictly better than a real HailoRT
    call failing deep inside a live pipeline with a much less specific
    error.
    """
    expected = expected_input_frame_bytes(model.input_shape, pixel_format)
    actual = camera.width * camera.height * _BYTES_PER_PIXEL.get(pixel_format, 0)
    if expected != actual:
        height, width, _channels = model.input_shape
        raise FrameShapeError(
            f"camera {camera.name!r} is configured at {camera.width}x{camera.height}, but "
            f"model {model.hef_path} expects {width}x{height} ({expected} bytes/frame vs "
            f"{actual} bytes/frame as captured) - reconfigure the camera or resize upstream of the appsink"
        )
