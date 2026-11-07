# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_publisher_fuzz.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Fixed-seed fuzzing of the publishing file, the command line it builds and the JPEG header reader: only the error of the module may come out, never another."""
import random
import string

from hydra_umc_vision_streamer.publisher import (
    PublishError,
    build_feed_command,
    jpeg_subsampling,
    parse_publish_config,
    rtsp_location,
)

SEED = 20260707
ALPHABET = string.ascii_letters + string.digits + " ;|&$`'\"\\/\n\t-_.:@%#"


def random_value(rng: random.Random, depth: int = 0):
    kind = rng.randrange(9 if depth < 2 else 6)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice([True, False])
    if kind == 2:
        return rng.choice([0, 1, -1, 22, 8554, 65535, 65536, 10**12, 2**63])
    if kind == 3:
        return rng.choice([0.0, 0.5, -3.25, float("nan"), float("inf")])
    if kind == 4:
        return "".join(rng.choice(ALPHABET) for _ in range(rng.randrange(0, 40)))
    if kind == 5:
        return rng.choice(["h264", "mjpeg", "h265", "", "H264", "rtsp://127.0.0.1:8554", "rtsp://[::1]:8554/live", "http://127.0.0.1:9997", "rtsp://evil.example.invalid:8554"])
    if kind == 6:
        return [random_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    return {rng.choice(["enabled", "gstLaunch", "rtspBase", "codec", "bitrateKbps", "mediamtxApi", "allowRemote", "restart", "x"]): random_value(rng, depth + 1) for _ in range(rng.randrange(0, 5))}


def test_a_random_publishing_block_is_accepted_or_refused_with_the_module_error() -> None:
    rng = random.Random(SEED)
    accepted = refused = 0
    for _ in range(3000):
        block = random_value(rng)
        try:
            config = parse_publish_config(block)
        except PublishError:
            refused += 1
            continue
        accepted += 1
        assert config.codec in ("h264", "mjpeg")
        assert config.describe()["codec"] == config.codec
    assert refused > 2000
    assert accepted >= 1


def test_random_valid_looking_blocks_build_commands_made_only_of_plain_tokens() -> None:
    rng = random.Random(SEED + 1)
    built = 0
    for _ in range(1500):
        block = {
            "enabled": True,
            "codec": rng.choice(["h264", "mjpeg"]),
            "bitrateKbps": rng.choice([100, 500, 4000, 20000, rng.randrange(-5, 100000)]),
            "rtspBase": rng.choice(["rtsp://127.0.0.1:8554", "rtsp://localhost:9000/live", "rtsp://192.168.0.180:8554/cams"]),
            "allowRemote": rng.choice([True, False]),
        }
        try:
            config = parse_publish_config(block)
        except PublishError:
            continue
        camera = "".join(rng.choice(ALPHABET) for _ in range(rng.randrange(0, 70))) if rng.random() < 0.4 else "".join(rng.choice(string.ascii_letters + string.digits + "_-") for _ in range(rng.randrange(1, 60)))
        fps = rng.choice([1, 10, 30, 240, 241, 0, -1, rng.randrange(-10, 400), True, 2.5, "10", None])
        try:
            command = build_feed_command(config, camera, fps)  # type: ignore[arg-type]
        except PublishError:
            continue
        built += 1
        for token in command[len(config.gst_launch):]:
            assert token == "!" or all(ch in string.ascii_letters + string.digits + "._/:=+,-" for ch in token), token
        assert rtsp_location(config, camera) in " ".join(command)
    assert built > 50


def test_the_address_of_a_camera_with_anything_but_plain_characters_is_never_built() -> None:
    rng = random.Random(SEED + 2)
    config = parse_publish_config({"enabled": True})
    for _ in range(2000):
        name = "".join(rng.choice(ALPHABET) for _ in range(rng.randrange(0, 90)))
        plain = bool(name) and len(name) <= 64 and all(ch in string.ascii_letters + string.digits + "_-" for ch in name)
        try:
            address = rtsp_location(config, name)
        except PublishError:
            assert not plain
            continue
        assert plain and address.endswith("/" + name)


def test_the_jpeg_header_reader_never_fails_on_random_or_truncated_bytes() -> None:
    rng = random.Random(SEED + 3)
    real = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\xf0\x01\x40\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xda"
    for _ in range(4000):
        size = rng.randrange(0, 40)
        data = bytes(rng.randrange(256) for _ in range(size))
        if rng.random() < 0.5:
            data = b"\xff\xd8" + data
        result = jpeg_subsampling(data)
        assert result in (None, "4:2:0", "4:2:2", "4:4:4", "gray", "other")
    assert jpeg_subsampling(real) == "4:2:0"
    for cut in range(len(real)):
        assert jpeg_subsampling(real[:cut]) in (None, "4:2:0")
    for position in range(len(real)):
        for value in (0x00, 0xFF, 0x7F):
            mutated = real[:position] + bytes([value]) + real[position + 1:]
            assert jpeg_subsampling(mutated) in (None, "4:2:0", "4:2:2", "4:4:4", "gray", "other")
