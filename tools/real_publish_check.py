# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tools/real_publish_check.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Publishes frames to a real MediaMTX through a real GStreamer and reads them back with a second GStreamer (what the publish workflow runs).

The frames are a test pattern encoded to JPEG by `gst-launch-1.0` itself; the publisher is the one of the service (`FeedPublisher`), so the command line it builds, the
feeding through the standard input and the readiness question to the MediaMTX API are all exercised for real, once per codec. Prints `REAL_PUBLISH=PASS` or
`REAL_PUBLISH=FAIL <why>`. It needs `gst-launch-1.0` with the good, bad and ugly plugin sets and `rtspclientsink`, and a MediaMTX that accepts publishers on
127.0.0.1:8554 with its API on 127.0.0.1:9997.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hydra_umc_vision_streamer.publisher import FeedPublisher, parse_publish_config  # noqa: E402


@dataclass
class _Frame:
    frame_id: int
    payload: bytes


class _Camera:
    """The same JPEG at 10 frames per second, numbered."""

    fps = 10

    def __init__(self, jpeg: bytes) -> None:
        self._jpeg = jpeg
        self._count = 0

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0) -> _Frame:
        time.sleep(1.0 / self.fps)
        self._count += 1
        return _Frame(self._count, self._jpeg)


def make_jpeg(folder: Path) -> bytes:
    target = folder / "pattern.jpg"
    subprocess.run(["gst-launch-1.0", "-q", "videotestsrc", "num-buffers=1", "!", "video/x-raw,format=I420,width=320,height=240", "!", "jpegenc", "!", "filesink", f"location={target}"], check=True, timeout=60)
    data = target.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        raise RuntimeError("gst-launch did not write a JPEG")
    return data


def check_codec(codec: str, jpeg: bytes) -> str | None:
    """None when the frames reached MediaMTX and a reader got buffers; otherwise what went wrong."""
    camera = f"real-{codec}"
    config = parse_publish_config({"enabled": True, "codec": codec, "rtspBase": "rtsp://127.0.0.1:8554", "mediamtxApi": "http://127.0.0.1:9997", "restart": {"maxAttempts": 1}})
    publisher = FeedPublisher(camera, _Camera(jpeg), config)
    publisher.start()
    try:
        deadline = time.monotonic() + 45
        status = publisher.status()
        while time.monotonic() < deadline and not (status["state"] == "publishing" and status["ready"] is True):
            if status["state"] in ("unavailable", "given_up"):
                return f"{codec}: the publisher ended as {status['state']}: {status['lastError']}"
            time.sleep(1)
            status = publisher.status()
        if status["ready"] is not True:
            return f"{codec}: MediaMTX never said the path is ready (state {status['state']}, last error {status['lastError']})"
        reader = subprocess.run(["gst-launch-1.0", "-q", "rtspsrc", f"location=rtsp://127.0.0.1:8554/{camera}", "latency=200", "!", "fakesink", "num-buffers=5"], capture_output=True, timeout=60)
        if reader.returncode != 0:
            return f"{codec}: the reader failed ({reader.returncode}): {reader.stderr.decode('utf-8', 'replace')[-300:]}"
        if publisher.status()["framesSent"] < 5:
            return f"{codec}: fewer than 5 frames were sent"
        return None
    finally:
        publisher.stop()


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        jpeg = make_jpeg(Path(folder))
    problems = []
    for codec in ("h264", "mjpeg"):
        problem = check_codec(codec, jpeg)
        if problem:
            print(f"REAL_PUBLISH_PROBLEM {problem}")
            problems.append(problem)
        else:
            print(f"codec {codec}: published, ready on MediaMTX and read back")
    if problems:
        print(f"REAL_PUBLISH=FAIL {len(problems)} codec(s) failed")
        return 1
    print("REAL_PUBLISH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
