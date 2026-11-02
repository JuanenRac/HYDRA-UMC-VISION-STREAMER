# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/recorder.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A ring of the last seconds of each camera that is written to disk when an event asks for it (the "black box" of an incident).

Each camera keeps its newest JPEG frames in memory, bounded by time (`seconds`) and by size (`maxBytes`): older frames fall out as new ones come in.
Nothing touches the disk until a trigger arrives (`POST /<camera>/record/trigger`, which a safety service sends when it stops the machine). Then the frames
of the ring are copied, the frames that arrive during `postSeconds` are added, and the lot is written to one folder of `outDir`: the JPEG files in capture
order and an `incident.json` with the reason, the instant of the trigger and, for every frame, its identity and SHA-256. The folder is built under a temporary
name and renamed when complete, so a folder that exists is a whole one. A new trigger inside `minGapSeconds` of the last accepted one is not written (one
incident is not a hundred), at most `maxPending` incidents wait for their post-roll, and only the newest `maxIncidents` folders are kept.

The whole thing is off unless the recording file says `"enabled": true` and the server is started with `--recording`. It stores video of a workplace, so
the folder is the operator's to protect: it is created with the permissions of the process and nothing here sends a frame anywhere.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

MAX_RING_SECONDS = 600.0
MAX_RING_BYTES = 512 * 1024 * 1024
MIN_RING_BYTES = 1024 * 1024
MAX_POST_SECONDS = 120.0
MAX_INCIDENTS = 100
MAX_GAP_SECONDS = 3600.0
MAX_PENDING = 4
REASON_LIMIT = 120
LIST_LIMIT = 100
_KEYS = {"enabled", "seconds", "maxBytes", "postSeconds", "outDir", "maxIncidents", "minGapSeconds"}
_SOURCE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_REASON = re.compile(r"[\x20-\x7e]{1,%d}" % REASON_LIMIT)
_FOLDER = re.compile(r"\d{8}T\d{9}Z-\d{4}")


class RecordingError(ValueError):
    """The recording file or a trigger cannot be used."""


class FrameLike(Protocol):
    @property
    def payload(self) -> bytes: ...
    @property
    def frame_id(self) -> int: ...
    @property
    def session_id(self) -> str: ...
    @property
    def capture_ts(self) -> float: ...


@dataclass(frozen=True)
class RecordingConfig:
    enabled: bool
    seconds: float
    max_bytes: int
    post_seconds: float
    out_dir: Path
    max_incidents: int
    min_gap_seconds: float

    def describe(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "seconds": self.seconds, "maxBytes": self.max_bytes, "postSeconds": self.post_seconds,
                "maxIncidents": self.max_incidents, "minGapSeconds": self.min_gap_seconds}


def _number(block: dict, key: str, default: float, low: float, high: float) -> float:
    value = block.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise RecordingError(f"{key} must be a number from {low:g} to {high:g}")
    return float(value)


def parse_recording_config(block: object, base: Path) -> RecordingConfig:
    """The recording file. `enabled` is false unless it says true; `outDir` is relative to the folder of the file or absolute, never with `..`."""
    if not isinstance(block, dict) or set(block) - _KEYS:
        raise RecordingError(f"the recording file is an object with the keys {sorted(_KEYS)}")
    enabled = block.get("enabled", False)
    if not isinstance(enabled, bool):
        raise RecordingError("enabled must be true or false")
    raw = block.get("outDir")
    if not isinstance(raw, str) or not raw or len(raw) > 400 or ".." in Path(raw).parts or "\x00" in raw:
        raise RecordingError("outDir must be a folder, relative to the file or absolute, without '..'")
    out_dir = Path(raw) if Path(raw).is_absolute() else base / raw
    max_bytes = block.get("maxBytes", 64 * 1024 * 1024)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not MIN_RING_BYTES <= max_bytes <= MAX_RING_BYTES:
        raise RecordingError(f"maxBytes must be an integer from {MIN_RING_BYTES} to {MAX_RING_BYTES}")
    keep = block.get("maxIncidents", 5)
    if isinstance(keep, bool) or not isinstance(keep, int) or not 1 <= keep <= MAX_INCIDENTS:
        raise RecordingError(f"maxIncidents must be an integer from 1 to {MAX_INCIDENTS}")
    return RecordingConfig(
        enabled, _number(block, "seconds", 10.0, 1.0, MAX_RING_SECONDS), max_bytes, _number(block, "postSeconds", 5.0, 0.0, MAX_POST_SECONDS),
        out_dir, keep, _number(block, "minGapSeconds", 30.0, 0.0, MAX_GAP_SECONDS),
    )


def load_recording_config(path: str | Path) -> RecordingConfig:
    file = Path(path)
    try:
        if file.stat().st_size > 64 * 1024:
            raise RecordingError("the recording file is larger than 65536 bytes")
        block = json.loads(file.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except OSError as error:
        raise RecordingError(f"the recording file cannot be read: {error.strerror}") from None
    except ValueError as error:
        if isinstance(error, RecordingError):
            raise
        raise RecordingError(f"the recording file is not valid JSON: {error}") from None
    return parse_recording_config(block, file.resolve().parent)


def _reject_constant(name: str) -> float:
    raise ValueError(f"{name} is not a valid JSON number")


def parse_trigger(body: object) -> tuple[str, str | None]:
    """The reason (printable ASCII, 1 to 120 characters) and the optional source of a trigger body."""
    if not isinstance(body, dict) or set(body) - {"reason", "source"}:
        raise RecordingError("the trigger is an object with reason and (optional) source")
    reason = body.get("reason")
    if not isinstance(reason, str) or not _REASON.fullmatch(reason):
        raise RecordingError(f"reason must be 1 to {REASON_LIMIT} printable ASCII characters")
    source = body.get("source")
    if source is not None and (not isinstance(source, str) or not _SOURCE.fullmatch(source)):
        raise RecordingError("source is 1 to 64 characters of letters, digits and _ . : -")
    return reason, source


@dataclass
class _Pending:
    incident: str
    reason: str
    source: str | None
    triggered_at: float
    deadline: float
    pre: list[Any]
    post: list[Any]
    ring_seconds: float
    post_bytes: int = 0


class RingRecorder:
    def __init__(self, camera: str, config: RecordingConfig, clock: Callable[[], float] = time.time, schedule: Callable[[float, Callable[[], object]], Any] | None = None) -> None:
        self.camera = camera
        self.config = config
        self._clock = clock
        self._schedule = schedule or self._timer
        self._lock = threading.Lock()
        self._ring: deque[Any] = deque()
        self._bytes = 0
        self._pending: dict[str, _Pending] = {}
        self._last_accepted: float | None = None
        self._sequence = 0
        self.written = 0
        self.last_error: str | None = None
        self._folder = config.out_dir / camera

    @staticmethod
    def _timer(delay: float, action: Callable[[], object]) -> threading.Timer:
        timer = threading.Timer(delay, action)
        timer.daemon = True
        timer.start()
        return timer

    # the capture loop calls this for every frame: it must be quick and must never raise
    def add(self, frame: FrameLike) -> None:
        try:
            size = len(frame.payload)
            with self._lock:
                self._ring.append(frame)
                self._bytes += size
                newest = frame.capture_ts
                while len(self._ring) > 1 and (self._bytes > self.config.max_bytes or self._ring[0].capture_ts < newest - self.config.seconds):
                    self._bytes -= len(self._ring.popleft().payload)
                for pending in self._pending.values():
                    # the post-roll is bounded by the same size as the ring: a long wait cannot fill the memory
                    if pending.post_bytes + size <= self.config.max_bytes:
                        pending.post.append(frame)
                        pending.post_bytes += size
        except Exception as error:  # noqa: BLE001 - the capture must go on whatever the recorder does
            self.last_error = type(error).__name__

    def trigger(self, reason: str, source: str | None = None) -> dict[str, Any]:
        """Ask for the ring to be written. Returns {"accepted": bool, "incident": id or None, "detail": ...}."""
        now = self._clock()
        with self._lock:
            if self._last_accepted is not None and now - self._last_accepted < self.config.min_gap_seconds:
                return {"accepted": False, "incident": None, "detail": "debounced: an incident was accepted less than minGapSeconds ago"}
            if len(self._pending) >= MAX_PENDING:
                return {"accepted": False, "incident": None, "detail": f"{MAX_PENDING} incidents are already waiting for their post-roll"}
            if not self._ring:
                return {"accepted": False, "incident": None, "detail": "the ring is empty: no frame has been captured yet"}
            self._sequence += 1
            self._last_accepted = now
            stamp = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]
            incident = f"{stamp}Z-{self._sequence % 10000:04d}"
            pre = list(self._ring)
            ring_seconds = pre[-1].capture_ts - pre[0].capture_ts
            pending = _Pending(incident, reason, source, now, now + self.config.post_seconds, pre, [], ring_seconds)
            wait = self.config.post_seconds > 0
            if wait:
                self._pending[incident] = pending
        if wait:
            self._schedule(self.config.post_seconds, lambda: self.finalize(incident))
        else:
            self._write(pending)
        return {"accepted": True, "incident": incident, "detail": "written" if not wait else f"waiting {self.config.post_seconds:g} s for the post-roll"}

    def finalize(self, incident: str) -> bool:
        """Write the incident that waits for its post-roll (the timer calls this; so does `flush`)."""
        with self._lock:
            pending = self._pending.pop(incident, None)
        if pending is None:
            return False
        self._write(pending)
        return True

    def flush(self) -> int:
        """Write every incident that is still waiting, now (at shutdown)."""
        with self._lock:
            names = list(self._pending)
        return sum(1 for name in names if self.finalize(name))

    def _write(self, pending: _Pending) -> None:
        try:
            frames = pending.pre + pending.post
            self._folder.mkdir(parents=True, exist_ok=True)
            temp = self._folder / f".{pending.incident}.tmp"
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir()
            entries = []
            for number, frame in enumerate(frames, start=1):
                name = f"{number:05d}.jpg"
                (temp / name).write_bytes(frame.payload)
                entries.append({"file": name, "frame_id": frame.frame_id, "session_id": frame.session_id, "capture_ts_ms": int(frame.capture_ts * 1000),
                                "bytes": len(frame.payload), "sha256": hashlib.sha256(frame.payload).hexdigest()})
            manifest = {
                "camera": self.camera, "incident": pending.incident, "reason": pending.reason, "source": pending.source,
                "triggered_at_ms": int(pending.triggered_at * 1000), "pre_frames": len(pending.pre), "post_frames": len(frames) - len(pending.pre),
                "ring_seconds": round(pending.ring_seconds, 3), "frames": entries,
            }
            (temp / "incident.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            os.replace(temp, self._folder / pending.incident)
            self.written += 1
            self._prune()
        except OSError as error:
            self.last_error = f"cannot write the incident: {error.strerror or type(error).__name__}"

    def _folders(self) -> list[Path]:
        try:
            return sorted(p for p in self._folder.iterdir() if p.is_dir() and _FOLDER.fullmatch(p.name))
        except OSError:
            return []

    def _prune(self) -> None:
        folders = self._folders()
        for old in folders[:-self.config.max_incidents]:
            shutil.rmtree(old, ignore_errors=True)

    def list_incidents(self) -> list[dict[str, Any]]:
        """The newest incidents on disk (at most LIST_LIMIT), newest first, read from their manifests."""
        found = []
        for folder in reversed(self._folders()[-LIST_LIMIT:]):
            try:
                manifest = json.loads((folder / "incident.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            found.append({"incident": folder.name, "reason": manifest.get("reason"), "source": manifest.get("source"),
                          "triggeredAtMs": manifest.get("triggered_at_ms"), "frames": len(manifest.get("frames", [])),
                          "bytes": sum(e.get("bytes", 0) for e in manifest.get("frames", []))})
        return found

    def status(self) -> dict[str, Any]:
        with self._lock:
            frames, size, pending = len(self._ring), self._bytes, len(self._pending)
            span = self._ring[-1].capture_ts - self._ring[0].capture_ts if frames > 1 else 0.0
        return {"enabled": True, "camera": self.camera, "ringFrames": frames, "ringBytes": size, "ringSeconds": round(span, 3), "pending": pending,
                "incidentsWritten": self.written, "incidentsOnDisk": len(self._folders()), "lastError": self.last_error, **{"limits": self.config.describe()}}
