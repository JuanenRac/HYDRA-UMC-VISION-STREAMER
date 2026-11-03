# Bench tests

Every test below is **not executed**. The capture, the reconnection policy, the recorder and the publisher are tested with stand-in cameras, a stand-in GStreamer program and a fake MediaMTX API; none has run against the real device it is meant for. Write a result only after a person ran the step.

## What the software already covers (no camera needed)

- `PYTHONPATH=src python -m pytest tests -q` runs the capture with a stand-in `cv2` that records the properties the capture sets, the reconnection with a camera that dies, the ring recorder with synthetic frames and the publisher with a stand-in program.

## Setup

- A Raspberry Pi 5 or CM5 with the project installed, a USB camera that offers MJPG and YUYV, an RTSP IP camera on the local network and, for the last steps, `gst-launch-1.0` with the RTSP sink plugin and a MediaMTX server.
- A way to cut the network to the IP camera (a switch port or a cable) without touching other equipment.

## Steps

| # | Step | Expected result | Result |
|---|------|-----------------|--------|
| 1 | Start `stream serve` on the USB camera with the default tuning and read the stream for ten minutes at the highest resolution the camera offers. | The frames are MJPG, the frame rate is the one the bus carries, and the age of the newest frame stays below two frame periods. | not executed |
| 2 | Repeat with a tuning file that sets `usbFourcc` to an empty string, then to `YUYV`. | The stream still works; write the frame rate and the age of the newest frame for each format. | not executed |
| 3 | Start `stream serve` on the RTSP camera, then cut the network to the camera for 30 seconds. | The read ends within the read timeout, the state goes to reconnecting, and the stream resumes after the cable is back. | not executed |
| 4 | Start `stream serve` while the RTSP camera is off. | The open ends within the open timeout and the reconnection delays follow the policy; the process exits with an error after the last attempt. | not executed |
| 5 | Unplug the USB camera while streaming and plug it back. | The capture reconnects; frames from before and after carry different session identifiers. | not executed |
| 6 | Trigger the ring recorder (`POST /<camera>/record/trigger`) on a real camera. | The folder holds the frames of the ring and of the post-roll, each with the SHA-256 listed in `incident.json`. | not executed |
| 7 | Turn on the publisher against a real MediaMTX and play the stream in a second client. | The path is ready, the picture shows, and killing `gst-launch-1.0` makes it start again after the delay. | not executed |
| 8 | Load a detection model on a real Hailo device and read the frames of the capture through it. | The architecture of the device and the model agree and detections arrive; a model for another architecture is refused. | not executed |

## What this bench cannot show

The load of many cameras on the Wi-Fi uplink of a real installation and the behaviour of a camera model whose firmware ignores the timeouts; measure them on the final installation.
