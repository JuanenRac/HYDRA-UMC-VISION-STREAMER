# Simulation bench

The streamer can run without a camera. The simulated camera is a stand-in for `cv2.VideoCapture` that follows a script drawn from a fixed seed: frames of synthetic JPEG bytes with a real frame header, bursts of failed reads that are only jitter, a long silence that is a disconnect, a device that comes back at the first try or only after several, and one that never comes back. The capture loop under test is the real one, with its reconnect schedule made fast.

## Run it

```
python -m pytest -q tests/test_simulation_bench.py
```

## What the scenarios check

| Scenario | What it shows |
|----------|---------------|
| a healthy camera | numbered frames with the size the scene has and the metadata of the frame message |
| jitter under the threshold (forty bursts of one to three bad reads) | no reconnect and no new session |
| a long silence | the device is released and reopened, the session changes and the numbering never goes backwards |
| a device that needs several tries | it is reopened in the end |
| a device that never comes back | given up with a reason; the health says so and a viewer is not left waiting |
| a burst nobody reads | the buffer keeps only the newest frames |
| a viewer far slower than the camera | it gets the newest frame, skips frames and never blocks the camera |
| two thousand damaged JPEG headers | the reader of sizes never raises |
| a frame whose size cannot be read, a hostile session name | no metadata; the name is cleaned |
| the reconnect schedule | it doubles up to its cap and ends in a given-up state |
| the buffer | it drops the oldest when full and counts what it dropped |

The workflow named "Simulation bench" runs the bench on every change, so the simulated path has its own visible job.

## What it cannot show

A real camera, a real cable, a real network and the real timing of a capture device need the camera.
