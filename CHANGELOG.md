# Changelog

All notable changes to HYDRA-UMC-VISION-STREAMER are documented in this file.

Versioning follows the ecosystem-wide `MAJOR.MINOR.PATCH` "odometer" scheme,
applied automatically on every real build by `bump_version.py` (invoked
from build.sh/build.bat right before the compile-check): `PATCH` goes up by
1 per build; once `PATCH` would exceed 9 it resets to 0 and `MINOR` goes up
by 1 instead (e.g. `0.0.9` -> `0.1.0`), the same carry cascading into
`MAJOR` if `MINOR` also exceeds 9. `MAJOR` is otherwise only ever bumped by
hand.

## [Unreleased]

- **New `discover-usb` CLI subcommand** (`main.py`/`mjpeg_server.py`'s new
  `discover_usb_devices()`) - real USB/V4L2 device enumeration for
  `HYDRA-UMC-SERVER`'s new "Discover USB Devices" camera-config button
  (that project's own `GET /api/camera/discover-usb-devices` shells out
  to this exact subcommand). Probes indices `0..max-1` with the same
  real `cv2.VideoCapture`/backend-selection logic `stream serve` already
  uses (`CAP_V4L2` on Linux/CM5, `CAP_ANY` elsewhere) - an index this
  reports as available is genuinely the same one `stream serve --device
  <index>` would open. Reads a real frame per candidate, not just
  `isOpened()` (some backends report a device as open even with nothing
  attached - the first real read is the honest check), and always
  releases every probed device immediately. Prints a plain JSON array
  to stdout: `[{"index": 0, "available": true, "width":.., "height":..}]`.
  Verified live against this dev machine's own real integrated camera
  (found at index 0, 1280x720). Real test coverage
  (`tests/test_mjpeg_server.py`: only real working indices returned, an
  empty scan when none are available, every probed device released, and
  the real "opencv-python not installed" degradation path) - also fixed
  a real, pre-existing gap in that same test file while there:
  `test_start_raises_clear_error_without_opencv` assumed cv2 is never
  installed wherever this suite runs, which is false on this same dev
  machine - now forces the import to fail via `sys.modules` instead of
  relying on the environment.
- **Documentation: the 2nd pair of real IP cameras is now also verified end
  to end.** `[0.1.0]`'s own entry below documented 2 of 4 real cameras
  working; the other 2 needed their own real RTSP path (`profile0`, found
  on the camera's own config screen) rather than the first pair's `/11` -
  not a credential or firmware issue as that entry's own wording implied.
  Verified for real: `stream serve --device
  "rtsp://admin:admin123456@192.168.0.204:8554/profile0"` (and the same for
  `.203`) opens the real camera and serves real MJPEG frames over HTTP.
  README (all 7 languages) and `docs/CLI_REFERENCE.md` updated to state
  4 of 4, not 2 of 4.

## [0.1.1]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.

## [0.1.0] - real RTSP IP camera support

- **`config.py`** - `CameraConfig` now has a real `source_type` field
  (`"usb"`, the default matching every existing config file unchanged, or
  `"ip"`), with `host`/`rtsp_port`/`rtsp_path`/`username`/`password` for
  the `"ip"` case and a real `rtsp_url()` builder (userinfo
  percent-encoded via `urllib.parse.quote`, so a real password containing
  `@`/`:`/`/` can never be misparsed as a second URL delimiter). The
  duplicate-connection check now compares `host:port+path` for IP cameras
  instead of the always-empty `device` field, so a real second IP camera
  is never falsely flagged as a duplicate of the first, while the same
  physical camera's own main/sub streams (same host, different
  `rtsp_path`) correctly are not treated as duplicates either.
- **`mjpeg_server.py`** - `MjpegCaptureSource`/`stream serve` now open a
  real RTSP IP camera the same way they already open a real USB/V4L2
  device: a `device` string starting with `rtsp://` picks
  `cv2.CAP_FFMPEG` (OpenCV's own bundled RTSP support, no new
  dependency) instead of the V4L2/CAP_ANY logic that only applies to a
  local device. Also fixed a real, live-reproduced gap in the same
  handler: a client disconnecting mid-stream on Windows raises
  `ConnectionAbortedError`, which the existing
  `except (BrokenPipeError, ConnectionResetError)` didn't cover -
  printed an unhandled traceback to stderr for a perfectly normal
  disconnect (never a crash risk the way `HYDRA-UMC-SERVER`'s own
  equivalent gap was - `ThreadingHTTPServer` isolates it to one request
  thread - just noisy).
- **Verified end to end against real hardware:** 2 of 4 real
  IP cameras on the local network opened and streamed real H.264 frames
  through the complete real path - `config.py`'s `rtsp_url()` ->
  `mjpeg_server.py`'s new RTSP capture path -> `stream serve`'s own HTTP
  MJPEG server -> `HYDRA-UMC-SERVER`'s real `GET /api/camera/:id/stream`
  proxy (8.5MB of real frames over 4s). Both real cameras share
  `Hipcam RealServer/V1.0` RTSP firmware, main stream on `/11`, sub
  stream on `/12`. The other 2 (different RTSP/HTTP firmware,
  `H264DVR 1.0`) rejected every credential/path combination tried
  (401 Unauthorized) - real, not-yet-resolved; needs either the real
  admin-panel credentials for that specific camera or RTSP explicitly
  enabled there first, not something to guess further at.
- Real test coverage added to `tests/test_config.py` (10 new cases:
  valid IP camera parsing, `rtsp_url()` with and without credentials,
  percent-encoding a password with special characters, missing
  host/rtsp_path, invalid port, invalid source_type, USB+IP cameras
  coexisting in one config file, and the corrected duplicate-connection
  check both firing on a real duplicate and NOT firing on the same
  camera's own main/sub streams).

## [0.0.9] - bounded, typed camera configuration + cross-platform capture backend

- **`config.py`** - camera-list loading now rejects non-object entries,
  boolean dimensions and configurations with more than the documented eight
  cameras. Invalid data fails before it can generate a partial pipeline or
  MediaMTX relay configuration.
- Added regression tests for each rejected input shape.
- **`mjpeg_server.py`** - `stream serve`'s real V4L2 capture no longer
  hardcodes `cv2.CAP_V4L2` unconditionally. That backend only exists on
  Linux, so `MjpegCaptureSource.start()` failed to open any camera at all
  on a non-Linux dev machine - not a hardware problem, a backend that
  can't exist there. The real Linux/CM5 deployment target is unchanged
  (still pins `CAP_V4L2` there); off Linux it now lets OpenCV pick that
  platform's own real backend (`CAP_ANY`, e.g. DirectShow/MSMF on
  Windows), which is what let a real laptop webcam be captured and
  proxied through HYDRA-UMC-SERVER's own `/api/camera/:id/stream` for
  the first time outside the CM5 itself.

## [0.0.9]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.

## [0.0.8] - Real CM5 deployment for `stream serve`

- **`systemd/hydra-umc-vision-streamer@.service`** (new) - templated unit,
  one instance per admin-assigned camera slot (`hydra-umc-vision-streamer@N`,
  N matching the same `cameraId` HYDRA-UMC-STUDIO's admin panel already
  assigns). Recomputes the exact `8100 + cameraId - 1` port
  HYDRA-UMC-SERVER's own `GET /api/camera/:id/stream` proxy already expects,
  runs as an unprivileged system account granted only the `video` group
  (real Debian default ownership of `/dev/video*`), no `PrivateDevices`
  (that would hide the camera from the unit entirely).
- **`systemd/cameras.env.example`** (new) - the one thing this unit needs
  per slot: `DEVICE=/dev/videoN`, deliberately a manual admin assignment
  (see the file's own header for why an automatic guess isn't attempted -
  a machine with more than one USB camera has no reliable way to know
  which node is which slot without a person deciding).
- **`HYDRA-UMC-OS/provisioning/install_vision_streamer.sh`** (new, that
  repo) - installs the real `python3-opencv`/`v4l-utils` apt packages,
  copies `src/` the same way `install_datalake.sh` already does, installs
  the unit above. Installs the capability only; enabling a specific camera
  slot is a printed manual follow-up, on purpose.
- Real gap still open: not yet verified against a physically-connected USB
  camera - `tests/test_mjpeg_server.py` mocks `cv2.VideoCapture` at the
  module boundary; real hardware verification is still pending.

## [0.0.7] - Real v0 capture+serve: `stream serve` (mjpeg_server.py)

- **`mjpeg_server.py`** (new) - opens a real V4L2 device via OpenCV,
  JPEG-encodes real captured frames, and serves them as a real HTTP MJPEG
  multipart stream, reusing this project's own already-real, already-
  tested `FrameBuffer` (`buffer.py`) for the exact bounded-backpressure
  reasoning that module already documents. Closes the exact gap this
  project's own `main.py` docstring already named as future work
  ("Actually running the generated pipeline... against physical USB
  cameras... is still future work") for the one thing needed today -
  real live video from a real USB webcam - deliberately not the full
  GStreamer/Hailo-8 tee/inference pipeline `pipeline.py` still describes
  for tomorrow (see that module's own docstring for why OpenCV, not
  GStreamer, for this v0). New `stream serve` CLI subcommand
  (`--device`/`--addr`/`--port`/`--width`/`--height`/`--fps`).
- **`tools/build_test.py`** now actually runs this repo's own real
  `tests/` pytest suite (65 tests) - real gap found live: it only ever
  syntax-checked Python sources before, so a real regression could pass
  `build_test.py` cleanly.

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
