# Changelog

All notable changes to HYDRA-UMC-VISION-STREAMER are documented in this file.

Versioning follows the ecosystem-wide `MAJOR.MINOR.PATCH` "odometer" scheme,
applied automatically on every real build by `bump_version.py` (invoked
from build.sh/build.bat right before the compile-check): `PATCH` goes up by
1 per build; once `PATCH` would exceed 9 it resets to 0 and `MINOR` goes up
by 1 instead (e.g. `0.0.9` -> `0.1.0`), the same carry cascading into
`MAJOR` if `MINOR` also exceeds 9. `MAJOR` is otherwise only ever bumped by
hand.

## [0.0.3]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.

## [0.0.3] - Real v0: camera config, GStreamer pipeline, and MediaMTX generation

- **`src/hydra_umc_vision_streamer/config.py`** - `CameraConfig` (name,
  device, width, height, fps, format) and `load_cameras()`, which
  schema-validates a JSON camera list: device must start with `/dev/`,
  dimensions/fps must be positive integers, format must be one of
  `MJPG`/`YUYV`/`H264`, and camera names/devices must be unique.
- **`src/hydra_umc_vision_streamer/pipeline.py`** - `build_capture_pipeline()`
  generates the exact `gst-launch-1.0` description this project intends
  to run for a camera: `v4l2src` with format-appropriate caps and
  decoder, a `tee` splitting into an `appsink` branch (for the future
  Hailo-8 inference process) and an `rtspclientsink` branch (pushing to
  the future MediaMTX relay).
- **`src/hydra_umc_vision_streamer/mediamtx_config.py`** - `build_mediamtx_paths_yaml()`
  generates the `paths:` section of a `mediamtx.yml`, one
  `source: publisher` entry per camera, hand-rolled rather than pulling
  in PyYAML for a shape this simple; `rtsp_url_for()` derives the single
  RTSP path both the pipeline and the MediaMTX config need to agree on.
- **`main.py`** - new `config validate --config PATH`, `config gst
  --config PATH --camera NAME [--rtsp-base URL]`, and `config mediamtx
  --config PATH [--out PATH]` subcommands.
- 24 tests (`test_config.py`, `test_pipeline.py`, `test_mediamtx_config.py`,
  `test_cli.py`).
- `pyproject.toml` - added a `dev` extra (`pytest`).
- `build.sh`/`build.bat` - fixed the version-bump step ordering, added
  the real test-suite step, and the no-autoclose-on-double-click
  behavior common to the rest of the ecosystem's scripts.
- `run.sh`/`run.bat` - now forward CLI arguments through to the entry
  point instead of ignoring them.
- Still out of scope: actually opening a V4L2 device, running the
  generated pipeline through real GStreamer, and driving the Hailo-8
  runtime - all of that needs physical USB cameras and hardware this
  environment doesn't have.

## [0.0.2]

Polish pass: copyright headers normalized across `main.py`, `__init__.py`,
`bump_version.py` and `build.sh`/`build.bat`/`run.sh`/`run.bat`; "why"
comments added; this `CHANGELOG.md` added; README (5 languages) expanded
with an Advanced Technical Information section, a detailed Build & Run
walkthrough with troubleshooting, a dateless "Current Status & Next
Steps" section replacing the previous dated roadmap, and a full Related
Projects section. No behavior change - the bump is this verification
build.

## [0.0.1]

Real build verification. `build.sh`/`build.bat` run end-to-end for real:
odometer bump, `.venv` creation, editable install, `python -m compileall`
clean across `src/`. `run.sh`/`run.bat` executed the entry point for real,
printing name + version + role. No business-logic change - the bump is the
recorded event.

## [0.0.0]

Initial skeleton: `pyproject.toml` (package metadata, no runtime
dependencies yet), `src/hydra_umc_vision_streamer/` (`__init__.py` +
`main.py` entry point reading its version from installed package
metadata), `bump_version.py` (odometer-style version bump),
`build.sh`/`build.bat` (venv + editable install + compile-check) and
`run.sh`/`run.bat`.
