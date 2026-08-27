#!/usr/bin/env bash
# HYDRA-UMC-VISION-STREAMER - run.sh: runs the entry point from the local venv
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
#
# Runs the project entry point from the local venv created by build.sh.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f ".venv/Scripts/python.exe" ]; then
  VENV_PY=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
  VENV_PY=".venv/bin/python"
else
  echo "No .venv found - run build.sh first." >&2
  exit 1
fi

exec "$VENV_PY" -m hydra_umc_vision_streamer.main "$@"
