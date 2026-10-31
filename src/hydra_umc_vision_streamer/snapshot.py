# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/snapshot.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A snapshot of all the cameras at once: the newest frame of each, and how far apart in time they were taken.

Stereo and extrinsic calibration and 3D safety zones need frames of several cameras that were
captured at nearly the same moment. A snapshot carries the identity of each frame (session,
frame id, capture instant) and the skew: the gap between the earliest and the latest capture.
`synchronized` is true only when every camera has a frame and the skew is within `max_skew_ms`;
a snapshot that is not synchronized is still returned, flagged, so the caller decides.

Frames are duck-typed (`payload`, `frame_id`, `session_id`, `capture_ts`), as in mjpeg_server.
"""
from __future__ import annotations

import io
import json
import math
import time
import zipfile

MAX_SKEW_LIMIT_MS = 60_000.0


class SnapshotError(ValueError):
    """The skew limit cannot be used."""


def check_max_skew_ms(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= MAX_SKEW_LIMIT_MS:
        raise SnapshotError(f"max skew must be a number above 0 and at most {MAX_SKEW_LIMIT_MS:g} ms, got {value!r}")
    return float(value)


def _safe(text: object) -> str:
    return "".join(c for c in str(text) if 32 < ord(c) < 127)[:64]


def describe(frames: dict, max_skew_ms: float, now: float | None = None) -> dict:
    """The manifest of a snapshot: `frames` maps a camera name to its newest frame, or None when it has none."""
    seen = time.time() if now is None else now
    cameras: dict[str, dict] = {}
    stamps: list[float] = []
    for name in sorted(frames):
        frame = frames[name]
        if frame is None:
            cameras[name] = {"available": False}
            continue
        stamps.append(frame.capture_ts)
        cameras[name] = {
            "available": True,
            "frame_id": frame.frame_id,
            "session_id": _safe(frame.session_id),
            "capture_ts_ms": int(frame.capture_ts * 1000),
            "data_age_ms": max(0, int((seen - frame.capture_ts) * 1000)),
            "bytes": len(frame.payload),
        }
    skew_ms = (max(stamps) - min(stamps)) * 1000.0 if stamps else 0.0
    complete = bool(frames) and len(stamps) == len(frames)
    return {
        "complete": complete,
        "synchronized": complete and skew_ms <= max_skew_ms,
        "skew_ms": round(skew_ms, 3),
        "max_skew_ms": max_skew_ms,
        "cameras": cameras,
    }


def build_zip(frames: dict, manifest: dict) -> bytes:
    """The JPEG of each camera (`<name>.jpg`) and `snapshot.json`, in one stored (uncompressed) archive."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("snapshot.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name in sorted(frames):
            if frames[name] is not None:
                archive.writestr(f"{name}.jpg", frames[name].payload)
    return out.getvalue()
