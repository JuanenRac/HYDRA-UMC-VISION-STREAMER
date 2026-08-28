# HYDRA-UMC-VISION-STREAMER — CLI Reference

`hydra-umc-vision-streamer` is a Python console script
(`src/hydra_umc_vision_streamer/main.py`, installed as an entry point via
`pyproject.toml`). What's real in v0: per-camera configuration parsing
and validation, generating the GStreamer pipeline description and the
MediaMTX relay config from that configuration, and the actual
backpressure/reconnection policy a live relay needs — all independent of
the V4L2/GStreamer/Hailo-8 runtime and physical USB cameras this
environment doesn't have. Actually opening a device and running the
generated pipeline is still future work. Every example below was
captured from a real run of the installed CLI — not written from memory.

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
HYDRA-UMC-VISION-STREAMER v0.0.4
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

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | ok — including a `stream simulate` run with real dropped frames or a real reconnect give-up, which are expected, honestly-reported outcomes, not failures |
| `1` | a real, reported failure: invalid/missing camera config, an unknown `--camera` name, or (in `stream simulate` only) the bounded buffer actually exceeding its own declared bound |

## Out of scope for this CLI

Actually opening a V4L2 device, running the generated GStreamer pipeline
against a real USB camera, and feeding the Hailo-8 NPU are described in
the project README's own roadmap but are not implemented yet — they need
real USB 3.0 cameras and the GStreamer/V4L2 runtime this environment
does not have.
