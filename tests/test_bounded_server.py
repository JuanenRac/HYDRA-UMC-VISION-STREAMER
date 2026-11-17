# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_bounded_server.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The server answers 503 to a request beyond its limit, whatever the route, instead of starting one more thread."""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler

import pytest

from hydra_umc_vision_streamer.mjpeg_server import DEFAULT_MAX_THREADS, BoundedThreadingHTTPServer


class _Slow(BaseHTTPRequestHandler):
    release = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        self.release.wait(5)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def _get(port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(b"GET /latest.jpg HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        chunks = []
        while True:
            data = connection.recv(4096)
            if not data:
                return b"".join(chunks)
            chunks.append(data)


def test_a_request_beyond_the_limit_gets_503_and_the_others_are_served() -> None:
    _Slow.release = threading.Event()
    server = BoundedThreadingHTTPServer(("127.0.0.1", 0), _Slow, max_threads=2)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    answers: list[bytes] = []
    holders = [threading.Thread(target=lambda: answers.append(_get(port))) for _ in range(2)]
    try:
        for holder in holders:
            holder.start()
        for _ in range(100):                         # wait until both are inside the handler
            if server._slots._value == 0:            # noqa: SLF001 - the two slots are taken
                break
            threading.Event().wait(0.02)
        refused = _get(port)
        assert refused.startswith(b"HTTP/1.1 503") and b"Retry-After: 1" in refused and server.refused == 1
        _Slow.release.set()
        for holder in holders:
            holder.join(5)
        assert len(answers) == 2 and all(a.startswith(b"HTTP/1.0 200") or a.startswith(b"HTTP/1.1 200") for a in answers)
        assert _get(port).endswith(b"ok")            # a slot is free again
    finally:
        _Slow.release.set()
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("bad", [0, -1, 1025, True, "8"])
def test_the_limit_is_a_whole_number_from_1_to_1024(bad: object) -> None:
    with pytest.raises(ValueError, match="max_threads"):
        BoundedThreadingHTTPServer(("127.0.0.1", 0), _Slow, max_threads=bad)  # type: ignore[arg-type]


def test_the_default_is_roomy_for_the_streams() -> None:
    assert DEFAULT_MAX_THREADS >= 32


def test_the_option_takes_a_whole_number_from_1_to_1024() -> None:
    import argparse

    from hydra_umc_vision_streamer.main import _thread_limit

    assert _thread_limit("8") == 8 and _thread_limit("1024") == 1024
    for bad in ("0", "1025", "-3", "many", ""):
        with pytest.raises(argparse.ArgumentTypeError):
            _thread_limit(bad)
