# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_access.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional Bearer token: none needed on loopback, mandatory away from it, constant-time comparison, /stream guarded, /health open."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from hydra_umc_vision_streamer.access import TOKEN_ENV, authorized, bind_problem, is_loopback, load_token
from http.server import ThreadingHTTPServer

from hydra_umc_vision_streamer.mjpeg_server import make_handler

TOKEN = "a-long-random-token-1234"


def test_loopback_detection() -> None:
    for addr in ("127.0.0.1", "127.9.9.9", "::1", "[::1]", "localhost"):
        assert is_loopback(addr), addr
    for addr in ("0.0.0.0", "::", "192.168.0.180", "example.com", "127.0.0.1.evil.example", ""):
        assert not is_loopback(addr), addr


def test_bind_problem_demands_a_token_away_from_loopback() -> None:
    assert bind_problem("127.0.0.1", "") is None
    assert bind_problem("0.0.0.0", TOKEN) is None
    assert "not loopback" in (bind_problem("0.0.0.0", "") or "")
    assert bind_problem("192.168.0.180", "") is not None


def test_load_token_from_file_environment_and_nothing(tmp_path: Path) -> None:
    assert load_token(None, {}) == ""
    assert load_token(None, {TOKEN_ENV: " " + TOKEN + " "}) == TOKEN
    file = tmp_path / "token"
    file.write_text(TOKEN + "  ", encoding="utf-8")
    # the file wins over the environment
    assert load_token(file, {TOKEN_ENV: "an-environment-token-9999"}) == TOKEN


def test_load_token_rejects_a_short_or_unreadable_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 16"):
        load_token(None, {TOKEN_ENV: "short"})
    with pytest.raises(ValueError, match="cannot read"):
        load_token(tmp_path / "missing", {})


class _Headers(dict):
    def get(self, key, default=""):  # type: ignore[override]
        return super().get(key, default)


class _Handler:
    def __init__(self, header: str | None) -> None:
        self.headers = _Headers({"Authorization": header} if header is not None else {})


def test_authorized_logic() -> None:
    assert authorized(_Handler(None), "")  # no token configured
    assert authorized(_Handler(f"Bearer {TOKEN}"), TOKEN)
    assert not authorized(_Handler(None), TOKEN)
    assert not authorized(_Handler("Bearer wrong-token-0000000"), TOKEN)
    assert not authorized(_Handler(f"Basic {TOKEN}"), TOKEN)
    assert not authorized(_Handler(TOKEN), TOKEN)
    assert not authorized(_Handler("Bearer "), TOKEN)


class _NoFrames:
    """A capture source that never produces a frame: /stream ends at once, which is all these tests need."""

    def wait_for_frame(self, last_seen: int, timeout: float = 0.0):
        return None


def _status(url: str, token: str | None) -> int:
    request = urllib.request.Request(url)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


@contextmanager
def _running(token: str):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(_NoFrames(), 2, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stream_needs_the_token_when_one_is_set() -> None:
    with _running(TOKEN) as base:
        assert _status(f"{base}/stream", None) == 401
        assert _status(f"{base}/stream", "wrong-token-0000000") == 401
        assert _status(f"{base}/", None) == 401
        assert _status(f"{base}/nothing", None) == 401
        assert _status(f"{base}/stream", TOKEN) == 200
        assert _status(f"{base}/nothing", TOKEN) == 404


def test_health_stays_open_for_the_service_registry() -> None:
    with _running(TOKEN) as base:
        assert _status(f"{base}/health", None) == 200


def test_no_token_configured_keeps_the_open_loopback_behaviour() -> None:
    with _running("") as base:
        assert _status(f"{base}/stream", None) == 200


def test_serve_refuses_a_non_loopback_address_without_a_token(capsys: pytest.CaptureFixture[str]) -> None:
    from hydra_umc_vision_streamer.main import _build_parser, _cmd_stream_serve

    args = _build_parser().parse_args(["stream", "serve", "--device", "0", "--addr", "0.0.0.0", "--port", "0"])
    assert _cmd_stream_serve(args) == 2
    assert "not loopback" in capsys.readouterr().err
