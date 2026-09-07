# =============================================================================
# HYDRA-UMC-VISION-STREAMER - Container Build: Dockerfile
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
# Real image for the MJPEG capture+serve CLI (mjpeg_server.py). Deliberately
# NOT the official `python:*-slim` image: pyproject.toml's own comment
# explains why OpenCV is installed via the Debian `python3-opencv` apt
# package rather than pip's `opencv-python` - no source build on ARM
# (the real target, this ecosystem's CM5). A venv with
# --system-site-packages inherits that apt-installed cv2 while still
# isolating this project's own install - avoids Debian's PEP 668
# "externally managed environment" restriction on a bare `pip install`
# entirely, without needing --break-system-packages.
#
# `--device`/`--port` are real, per-camera, required CLI flags (see
# main.py's own `stream serve` subparser) - genuinely different for every
# real invocation (one real camera, one real container), so this image
# deliberately does not bake in a default CMD beyond --help; the real
# device/port come from `docker run`/compose at the point one specific
# camera is actually being served, matching HYDRA-UMC-VISION-NODE's own
# docker-compose.yml comment for this same service ("repeat per attached
# USB 3.0 camera"). Non-root. `/dev/video0` (or whichever real device
# node) still needs a real `--device` mapping at `docker run` time - a
# Dockerfile alone can't grant hardware access.

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-opencv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE.md ./
COPY src ./src
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .
ENV PATH="/opt/venv/bin:${PATH}"

RUN useradd --system --create-home --home-dir /home/hydra hydra
USER hydra

ENTRYPOINT ["hydra-umc-vision-streamer"]
CMD ["--help"]
