# HYDRA-UMC-VISION-STREAMER — CLI Reference

`hydra-umc-vision-streamer` is a Python console script
(`src/hydra_umc_vision_streamer/main.py`, installed as an entry point via
`pyproject.toml`). What's real in v0: per-camera configuration parsing
and validation (including a real `"ip"` `source_type` for RTSP cameras,
alongside the default `"usb"`), generating the GStreamer pipeline
description and the MediaMTX relay config from that configuration, the
actual backpressure/reconnection policy a live relay needs, and a real
MJPEG capture+serve path (`stream serve`) that actually opens a USB/V4L2
device or a real RTSP IP camera via OpenCV and serves the picture over
HTTP — tested with the simulator only; verification against real IP cameras is pending on the bench.
Still not implemented: the full GStreamer/PyGObject pipeline
`config gst`/`config mediamtx` describe, and real Hailo-8 inference.
Every example below was captured from a real run of the installed CLI —
not written from memory.

## Usage

```
$ hydra-umc-vision-streamer -h
usage: hydra-umc-vision-streamer [-h] {config,stream} ...

positional arguments:
  {config,stream}
    config         Inspect and generate config from the camera list.
    stream         Real buffer/reconnect policy, independent of hardware.

options:
  -h, --help       show this help message and exit
```

Bare invocation (no subcommand) prints identity/version/role and exits `0`:

```
$ hydra-umc-vision-streamer
HYDRA-UMC-VISION-STREAMER v0.1.0
Optimized GStreamer capture/pre-processing pipeline for up to 8x USB 3.0 camera streams feeding the Hailo-8 NPU.
```

All examples below use a real 2-camera config fixture:

```json
// cameras.json
[
  {"name": "cam0", "device": "/dev/video0", "width": 1920, "height": 1080, "fps": 30, "format": "MJPG"},
  {"name": "cam1", "device": "/dev/video1", "width": 1280, "height": 720, "fps": 60, "format": "YUYV"}
]
```

## Commands

### `config validate --config PATH`

```
$ hydra-umc-vision-streamer config validate -h
usage: hydra-umc-vision-streamer config validate [-h] --config CONFIG

options:
  -h, --help       show this help message and exit
  --config CONFIG  Path to the camera list JSON file
```

Real parsing and validation: required fields, `device` must start with
`/dev/`, `width`/`height`/`fps` must be positive integers, `format` must
be one of `MJPG`/`YUYV`/`H264`, and camera names/devices must be unique.

```
$ hydra-umc-vision-streamer config validate --config cameras.json
2 camera(s) in cameras.json
  cam0: /dev/video0 1920x1080@30 MJPG
  cam1: /dev/video1 1280x720@60 YUYV
config OK
$ echo $?
0
```

A real malformed entry (missing `device`), exit code `1`:

```
$ hydra-umc-vision-streamer config validate --config cameras_bad.json
error: camera 0: missing field(s) ['device']
$ echo $?
1
```

A missing config file (real OS error, not a crash):

```
$ hydra-umc-vision-streamer config validate --config does_not_exist.json
error: could not read config does_not_exist.json: [Errno 2] No such file or directory: 'does_not_exist.json'
$ echo $?
1
```

A real RTSP IP camera entry (`source_type: "ip"`) alongside a USB one in
the same config file — `device` is only meaningful for `"usb"` cameras
(the default `source_type` when the field is omitted, matching every
config file written before this field existed), so it prints empty for
an IP camera; the real connection identity for a duplicate check is
`host`/`rtsp_port`/`rtsp_path` instead:

```json
// cameras_mixed.json
[
  {"name": "cam0", "device": "/dev/video0", "width": 1920, "height": 1080, "fps": 30, "format": "MJPG"},
  {"name": "cam1", "source_type": "ip", "host": "192.168.0.211", "rtsp_port": 554,
   "rtsp_path": "/11", "username": "admin", "password": "secret",
   "width": 1920, "height": 1080, "fps": 15, "format": "H264"}
]
```

```
$ hydra-umc-vision-streamer config validate --config cameras_mixed.json
2 camera(s) in cameras_mixed.json
  cam0: /dev/video0 1920x1080@30 MJPG
  cam1:  1920x1080@15 H264
config OK
$ echo $?
0
```

`CameraConfig.rtsp_url()` builds the real, correctly percent-encoded
connection URL for `cam1` above
(`rtsp://admin:secret@192.168.0.211:554/11`) — the same URL `stream serve
--device` below expects for an IP camera, and the same one
`mjpeg_server.py` opens via OpenCV's `cv2.CAP_FFMPEG` backend.

### `config gst --config PATH --camera NAME [--rtsp-base URL]`

```
$ hydra-umc-vision-streamer config gst -h
usage: hydra-umc-vision-streamer config gst [-h] --config CONFIG
                                            --camera CAMERA
                                            [--rtsp-base RTSP_BASE]

options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to the camera list JSON file
  --camera CAMERA       Camera name to build the pipeline for
  --rtsp-base RTSP_BASE
                        MediaMTX RTSP base URL (default:
                        rtsp://localhost:8554)
```

Prints the real GStreamer pipeline description for one named camera —
`v4l2src` into the codec-appropriate decode chain, `tee`d into both a
Hailo-8 appsink and an RTSP relay:

```
$ hydra-umc-vision-streamer config gst --config cameras.json --camera cam0
v4l2src device=/dev/video0 ! image/jpeg,width=1920,height=1080,framerate=30/1 ! jpegdec ! videoconvert ! tee name=t t. ! queue ! appsink name=cam0_hailo_sink t. ! queue ! rtspclientsink location=rtsp://localhost:8554/cam0
$ echo $?
0
```

A camera name not present in the config (exit code `1`):

```
$ hydra-umc-vision-streamer config gst --config cameras.json --camera nope
no camera named 'nope' in cameras.json
$ echo $?
1
```

### `config mediamtx --config PATH [--out FILE]`

```
$ hydra-umc-vision-streamer config mediamtx -h
usage: hydra-umc-vision-streamer config mediamtx [-h] --config CONFIG
                                                 [--out OUT]

options:
  -h, --help       show this help message and exit
  --config CONFIG  Path to the camera list JSON file
  --out OUT        Write to this file instead of stdout
```

Generates the `paths:` section of a MediaMTX `paths.yml`, one entry per
camera. Without `--out`, prints to stdout:

```
$ hydra-umc-vision-streamer config mediamtx --config cameras.json
paths:
  cam0:
    source: publisher
  cam1:
    source: publisher
```

With `--out`, writes the file for real instead:

```
$ hydra-umc-vision-streamer config mediamtx --config cameras.json --out mediamtx_paths.yml
wrote mediamtx_paths.yml
$ cat mediamtx_paths.yml
paths:
  cam0:
    source: publisher
  cam1:
    source: publisher
```

### `stream simulate [--buffer-size N] [--frames N] [--consumer-rate N] [--max-reconnect-attempts N] [--base-delay S] [--max-delay S]`

```
$ hydra-umc-vision-streamer stream simulate -h
usage: hydra-umc-vision-streamer stream simulate [-h]
                                                 [--buffer-size BUFFER_SIZE]
                                                 [--frames FRAMES]
                                                 [--consumer-rate CONSUMER_RATE]
                                                 [--max-reconnect-attempts MAX_RECONNECT_ATTEMPTS]
                                                 [--base-delay BASE_DELAY]
                                                 [--max-delay MAX_DELAY]

options:
  -h, --help            show this help message and exit
  --buffer-size BUFFER_SIZE
                        Max buffered frames (default: 8)
  --frames FRAMES       Total frames to push (default: 1000)
  --consumer-rate CONSUMER_RATE
                        Pop one frame every N pushes - lower is a faster
                        consumer (default: 50)
  --max-reconnect-attempts MAX_RECONNECT_ATTEMPTS
  --base-delay BASE_DELAY
                        Seconds (default: 0.5)
  --max-delay MAX_DELAY
                        Seconds (default: 8.0)
```

A real, deterministic simulation of the backpressure + reconnection
policy a live relay actually needs — no camera or GStreamer runtime
involved. It pushes `--frames` synthetic frames through a real bounded
`FrameBuffer`, popping only every `--consumer-rate` pushes (a slow
consumer), simulates a real disconnect halfway through, and drives the
real `ReconnectPolicy` until it either recovers or gives up.

**Default run** (`--consumer-rate 50`, a consumer that's fast enough to
keep up most of the time still drops the bulk of frames once
`--frames 1000` outruns the buffer):

```
$ hydra-umc-vision-streamer stream simulate
Pushed 1000 frame(s) through a buffer capped at 8
Max buffer size observed: 8 (must never exceed 8)
Frames dropped by backpressure: 972

Simulated disconnect at frame 500
Reconnect backoff schedule (s): [0.5, 1.0, 2.0, 4.0]
Final connection state: given_up
```

**Low-drop case** — a consumer fast enough to pop every single push
(`--consumer-rate 1`) never lets the buffer fill, so backpressure never
triggers:

```
$ hydra-umc-vision-streamer stream simulate --buffer-size 8 --frames 500 --consumer-rate 1
Pushed 500 frame(s) through a buffer capped at 8
Max buffer size observed: 1 (must never exceed 8)
Frames dropped by backpressure: 0

Simulated disconnect at frame 250
Reconnect backoff schedule (s): [0.5, 1.0, 2.0, 4.0]
Final connection state: given_up
```

**High-drop case** — a tiny buffer and a consumer that essentially never
pops (`--consumer-rate 1000` against only 500 frames) drops nearly
everything past the buffer's own capacity, and the buffer never exceeds
its declared bound:

```
$ hydra-umc-vision-streamer stream simulate --buffer-size 4 --frames 500 --consumer-rate 1000
Pushed 500 frame(s) through a buffer capped at 4
Max buffer size observed: 4 (must never exceed 4)
Frames dropped by backpressure: 495

Simulated disconnect at frame 250
Reconnect backoff schedule (s): [0.5, 1.0, 2.0, 4.0]
Final connection state: given_up
```

**Reconnect exhaustion** — a small `--max-reconnect-attempts 3` budget
against a real exponential backoff (`--base-delay 1.0`, doubling each
attempt): attempts 1 and 2 each produce a real scheduled delay, and the
3rd genuinely exhausts the budget and gives up rather than retrying
forever:

```
$ hydra-umc-vision-streamer stream simulate --frames 100 --max-reconnect-attempts 3 --base-delay 1.0 --max-delay 100.0
Pushed 100 frame(s) through a buffer capped at 8
Max buffer size observed: 8 (must never exceed 8)
Frames dropped by backpressure: 90

Simulated disconnect at frame 50
Reconnect backoff schedule (s): [1.0, 2.0]
Final connection state: given_up
```

`stream simulate` also self-checks its own real invariant: if the
observed buffer size ever exceeded the declared `--buffer-size`, it
would print a `FAIL:` line to stderr and exit `1` — a real bug in the
bounded buffer itself, not a simulation parameter problem. Every case
above stays within bound, so every one exits `0`.

### `stream serve --device DEVICE --port PORT [--addr ADDR] [--width W] [--height H] [--fps FPS]`

```
$ hydra-umc-vision-streamer stream serve -h
usage: hydra-umc-vision-streamer stream serve [-h] --device DEVICE
                                              [--addr ADDR] --port PORT
                                              [--width WIDTH]
                                              [--height HEIGHT] [--fps FPS]

options:
  -h, --help       show this help message and exit
  --device DEVICE  USB: a bare V4L2 index (e.g. 0 for /dev/video0) or a full
                   device path. IP camera: a full
                   rtsp://user:pass@host:port/path URL (see
                   CameraConfig.rtsp_url() in config.py to build one from a
                   persisted camera-list JSON entry instead of typing
                   credentials on the command line).
  --addr ADDR      Address to bind the MJPEG HTTP server to (default:
                   127.0.0.1)
  --port PORT      Port to serve the MJPEG stream on
  --width WIDTH
  --height HEIGHT
  --fps FPS
```

This is the one subcommand that actually opens a real camera — everything
above it (`config`/`stream simulate`) is real, hardware-independent
generation or simulation. `mjpeg_server.py`'s `MjpegCaptureSource` opens
`--device` through OpenCV: a `device` string starting with `rtsp://`
picks OpenCV's bundled `cv2.CAP_FFMPEG` backend (a real RTSP IP camera,
no extra dependency); anything else is treated as a local USB/V4L2
device (a bare index or a device path) opened via the platform's default
backend. Either way it serves a real MJPEG stream over HTTP at
`http://ADDR:PORT/`, frame by frame, until the client disconnects or the
process is stopped.

USB camera:

```bash
$ hydra-umc-vision-streamer stream serve --device 0 --port 8100
```

RTSP IP camera — simulator-tested only (verification against real
IP cameras is pending on the bench; a second pair of cameras may need
its own RTSP path, `profile0` rather than `/11`):

```bash
$ CAMERA_URL="rtsp://admin:secret@192.168.0.211:554/11" hydra-umc-vision-streamer stream serve --device-env CAMERA_URL --port 8100 --width 1920 --height 1080 --fps 15
```

A client disconnecting mid-stream (closing the browser tab, a dropped
network link) is handled as a normal, expected event — `BrokenPipeError`,
`ConnectionResetError`, and (Windows-specific) `ConnectionAbortedError`
all end that one request thread quietly rather than printing an
unhandled traceback.

Not yet verified against a real, physically-connected USB camera — only
against a real RTSP IP camera and against `cv2.VideoCapture` mocked at
the module boundary in `tests/test_mjpeg_server.py`.

### Capture tuning (`--capture-tuning FILE`)

Optional on `stream serve` and `stream serve-all`. A JSON object, all keys optional: `rtspOpenTimeoutMs` and `rtspReadTimeoutMs` (100 to 120000, 5000 by default) bound the wait of an RTSP camera when it is opened and when a frame is read, so a camera that stops answering lets the reconnection policy act; `usbFourcc` (four characters, `MJPG` by default, empty to keep the format the driver chooses) and `usbQueueFrames` (1 to 16, 1 by default) shape a USB camera. Without the file the defaults apply. A property the installed OpenCV does not know is skipped.

### Ring recording and publishing to MediaMTX (`--recording FILE`, `--publish FILE`)

Both options belong to `stream serve` and `stream serve-all`, both are off unless the option is given **and** its file says `"enabled": true`, and without them
none of the routes below exists (`404`).

`--recording FILE` keeps the newest frames of each camera in a ring in memory and writes them to disk only when an event asks. The file is a JSON object:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Must be `true`. |
| `seconds` | `10` | Seconds of video kept in the ring (1 to 600). |
| `maxBytes` | `67108864` | Size limit of the ring and of the post-roll (1 MiB to 512 MiB); the newest frame is always kept. |
| `postSeconds` | `5` | Seconds of frames after the trigger that are added to the incident (0 to 120). |
| `outDir` | required | Folder of the incidents, relative to the file or absolute, never with `..`; one subfolder per camera. |
| `maxIncidents` | `5` | Folders kept per camera; older ones are removed (1 to 100). |
| `minGapSeconds` | `30` | A trigger sooner than this after an accepted one is refused with `429` (0 to 3600). |

| Route | Method | Notes |
|---|---|---|
| `/<camera>/record/trigger` | `POST` | Body `{"reason": "1 to 120 printable ASCII characters", "source": "optional name"}` (at most 1024 bytes). `202` with the incident name when accepted, `429` when refused (gap, empty ring, too many incidents waiting), `400` for a bad body. Needs the bearer token when one is set. |
| `/<camera>/record` | `GET` | The ring (frames, bytes, seconds), the incidents waiting, the number written and on disk, and the last error. |
| `/<camera>/record/incidents` | `GET` | The incidents on disk, newest first: name, reason, source, instant, frames and bytes. |

An incident is a folder named `<UTC time>-<number>` with `00001.jpg`, `00002.jpg`... in capture order and `incident.json` (camera, reason, source, instant of the trigger, frames before and after, and for every frame its file, id, session, capture instant, size and SHA-256). It is built under a temporary name and renamed when complete. With `stream serve` (one camera) the routes have no camera in the path (`/record/trigger`).

`--publish FILE` runs `gst-launch-1.0` for each camera and feeds it the frames of the capture:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Must be `true`. |
| `gstLaunch` | `["gst-launch-1.0"]` | The program, as a list (at most 3 leading arguments). |
| `rtspBase` | `rtsp://127.0.0.1:8554` | Where MediaMTX listens; the camera is published at `<rtspBase>/<camera>`. Loopback unless `allowRemote` is `true`. |
| `codec` | `h264` | `h264` encodes with `x264enc`; `mjpeg` sends the JPEG frames on with `rtpjpegpay`. |
| `bitrateKbps` | `2000` | Bit rate of `x264enc` (100 to 20000). |
| `mediamtxApi` | none | Address of the MediaMTX API; the status then says whether the path is ready. |
| `allowRemote` | `false` | Allow `rtspBase` and `mediamtxApi` away from this machine. |
| `restart` | 5 attempts, 1 s to 30 s | `maxAttempts`, `baseDelaySeconds`, `maxDelaySeconds` of the restart delays. |

`GET /<camera>/publish` answers `state` (`starting`, `publishing`, `restarting`, `given_up`, `unavailable` or `stopped`), `codec`, `url`, `restarts`, `framesSent`, `ready` and `lastError`.
Needs GStreamer with `rtspclientsink` (and `x264enc` for `h264`) and a running MediaMTX; it has been tried only against a stand-in program.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | ok — including a `stream simulate` run with real dropped frames or a real reconnect give-up, which are expected, honestly-reported outcomes, not failures |
| `1` | a real, reported failure: invalid/missing camera config, an unknown `--camera` name, or (in `stream simulate` only) the bounded buffer actually exceeding its own declared bound |

## Out of scope for this CLI

`stream serve` above already opens a real USB/V4L2 device or a real RTSP
IP camera and serves real MJPEG over HTTP. Still not implemented, and
described in the project README's own roadmap: running the full
GStreamer/PyGObject pipeline that `config gst`/`config mediamtx` only
generate the description for, the pre-processing of the frames (resize and
format conversion; the ISP of the Pi 5 serves CSI cameras, not USB cameras, so
the backend has not been chosen), and feeding a real Hailo-8 NPU through `hailo_runtime.py` — these need
the GStreamer/PyGObject runtime and a real Hailo-8 module this
environment does not have. `stream serve` itself is also not yet
verified against a physically-connected USB camera (see above).
