# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/fake_gst.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A stand-in for gst-launch-1.0 used by the tests of the publisher: it records its arguments and the bytes it is fed.

Environment: FAKE_GST_OUT (a file that receives one JSON line per start with the arguments, and one per end with the byte count),
FAKE_GST_EXIT_AFTER (leave with exit code 3 after this many bytes), FAKE_GST_ERROR (a line written on the error output).
"""
import json
import os
import sys

out = os.environ["FAKE_GST_OUT"]
with open(out, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"event": "start", "args": sys.argv[1:]}) + "\n")
limit = int(os.environ.get("FAKE_GST_EXIT_AFTER", "0"))
if os.environ.get("FAKE_GST_ERROR"):
    sys.stderr.write(os.environ["FAKE_GST_ERROR"] + "\n")
    sys.stderr.flush()
total = 0
while True:
    chunk = sys.stdin.buffer.read1(4096) if hasattr(sys.stdin.buffer, "read1") else sys.stdin.buffer.read(4096)
    if not chunk:
        break
    total += len(chunk)
    if limit and total >= limit:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "end", "bytes": total, "code": 3}) + "\n")
        sys.exit(3)
with open(out, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"event": "end", "bytes": total, "code": 0}) + "\n")
