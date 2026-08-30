# Changelog

All notable changes to HYDRA-UMC-VISION-STREAMER are documented in this file.

Versioning follows the ecosystem-wide `MAJOR.MINOR.PATCH` "odometer" scheme,
applied automatically on every real build by `bump_version.py` (invoked
from build.sh/build.bat right before the compile-check): `PATCH` goes up by
1 per build; once `PATCH` would exceed 9 it resets to 0 and `MINOR` goes up
by 1 instead (e.g. `0.0.9` -> `0.1.0`), the same carry cascading into
`MAJOR` if `MINOR` also exceeds 9. `MAJOR` is otherwise only ever bumped by
hand.

## [Unreleased] - bounded, typed camera configuration

- **`config.py`** - camera-list loading now rejects non-object entries,
  boolean dimensions and configurations with more than the documented eight
  cameras. Invalid data fails before it can generate a partial pipeline or
  MediaMTX relay configuration.
- Added regression tests for each rejected input shape.

## [0.0.6] - Real HailoRT integration boundary, prepared ahead of the Hailo-8 module

- **Added `src/hydra_umc_vision_streamer/hailo_runtime.py`** (new) - a
  real HailoRT (`hailo_platform`) integration boundary, so this pipeline
  is ready to actually feed the Hailo-8 the moment a real module is
  attached, rather than starting that work from zero then.
  `open_vdevice()` and `load_hailo_detection_model()` are written against
  the real, confirmed HailoRT Python API (`VDevice`, `HEF`,
  `ConfigureParams.create_from_hef(..., interface=HailoStreamInterface.PCIe)`),
  lazily imported (same pattern as this ecosystem's other real hardware
  transports) so this development machine, which has no `hailort`
  installed, degrades to a clear `HailoNotAvailableError` instead of a
  bare `ImportError`. Also added real, hardware-independent pre-flight
  validation - `expected_input_frame_bytes()` /
  `validate_frame_matches_input()` - that catches a camera resolution
  configured in `config.py` not matching a loaded model's real input
  tensor shape before a single frame is ever pushed at the device.
  Deliberately does not parse a real detection model's NMS output byte
  layout yet - that's the next real step once a real `.hef` exists to
  verify it against, not guessed at here. `hailort` added as a new
  `[project.optional-dependencies]` extra (`pip install .[hailo]`); never
  required. 9 new tests (61 total).

## [0.0.6]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.

## [0.0.5] - Two real bugs closed from a live ecosystem bug audit

- **`src/hydra_umc_vision_streamer/main.py`** - `stream simulate` no longer
  crashes with an unhandled `ZeroDivisionError` on `--consumer-rate 0`
  (argparse only enforced `type=int`, not a minimum). `_cmd_stream_simulate`
  now rejects a non-positive `--consumer-rate` up front with a clean
  `error: --consumer-rate must be a positive integer` message and exit
  code 1, the same pattern the other `_cmd_*` handlers already use for
  bad user input.
- **`src/hydra_umc_vision_streamer/config.py`** - `_parse_camera()` only
  checked that `camera.name` was non-empty; unlike `device` (which must
  start with `/dev/`), no characters were restricted, even though
  `camera.name` is interpolated unescaped into both a hand-built YAML
  file (`mediamtx_config.build_mediamtx_paths_yaml`) and a
  `gst-launch-1.0` pipeline string (`pipeline.build_capture_pipeline`) -
  the two generators the README says must agree with this module in
  shape. A name containing a colon, space, or newline could corrupt
  either generator's output. `_parse_camera()` now restricts `name` to
  `^[A-Za-z0-9_-]+$`, rejecting an unsafe name at config-parse time -
  the earliest point in the pipeline, before either generator ever sees
  it - instead of downstream in generated YAML or gst-launch syntax.
- 4 new regression tests - `test_stream_simulate_rejects_zero_consumer_rate`
  in `test_cli.py`; `test_name_with_unsafe_characters_rejected`,
  `test_name_with_newline_rejected`, and
  `test_name_with_hyphen_and_underscore_still_parses` (a legitimate name
  still parses fine) in `test_config.py` - 49 total, all passing.

## [0.0.4] - Real bounded buffering and deterministic reconnection

- **`src/hydra_umc_vision_streamer/buffer.py`** (new) - `FrameBuffer`, a real fixed-capacity queue that drops the OLDEST item (not the newest) once full: the honest backpressure policy a live relay needs so a slow consumer (a saturated network link, an inference stage falling behind) can never make this process's own memory grow without bound. `push()` reports whether it had to drop something; `dropped_count` gives real, cumulative visibility into how much a slow consumer actually cost.
- **`src/hydra_umc_vision_streamer/reconnect.py`** (new) - `ReconnectPolicy`/`ConnectionTracker`, a real, deterministic exponential-backoff reconnect policy (no jitter, same pattern as `HYDRA-UMC-NODE-HEALING/src/watchdog/retry.go`) for a camera/relay link that drops. `ConnectionTracker` never sleeps or touches a real socket itself - it only tracks state (`connected`/`reconnecting`/`given_up`) and returns the real scheduled delay, which is what makes the whole backoff schedule (including honestly giving up after `max_attempts`, never retrying forever) exactly reproducible in a test.
- **`main.py`** - new `stream simulate` subcommand: a real, deterministic end-to-end demonstration pushing thousands of synthetic frames through a bounded `FrameBuffer` with a deliberately slow consumer, then driving a simulated disconnect through the real reconnect policy - prints the real max buffer size observed (must never exceed the declared bound), the real dropped-frame count, and the real backoff schedule.
- 21 new tests (`test_buffer.py` including a 50,000-push stress test proving the buffer's real size never exceeds its bound, `test_reconnect.py` covering the full backoff schedule and the honest give-up path, plus 3 new CLI round-trips) - 45 total. Verified live: a slow consumer (`--consumer-rate 1000`) against an 8-frame buffer over 1000 pushes never exceeds size 8 and reports 972 real drops; a fast consumer (`--consumer-rate 1`) reports 0 drops; the default reconnect policy's schedule matches `[0.5, 1.0, 2.0, 4.0]` before honestly giving up.

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
