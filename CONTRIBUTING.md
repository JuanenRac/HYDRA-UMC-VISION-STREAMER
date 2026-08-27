# Contributing to HYDRA-UMC-VISION-STREAMER 🦾

We welcome contributions to the media ingestion layer of the Vision AI Node.

## Technology Stack
- **Language**: C++20, Python 3.12.
- **Frameworks**: GStreamer 1.22+, MediaMTX.
- **Hardware**: Raspberry Pi CM5 (BCM2712 ISP), USB 3.0 UVC Cameras.
- **Protocols**: RTSP, WebRTC, V4L2.

## Guidelines
1. **Pipeline Efficiency**: Use `glupload` and `v4l2h264enc` for hardware-accelerated paths.
2. **Buffer Management**: Ensure zero-copy transitions between plugins.
3. **Multi-Camera**: Validate changes against 8 simultaneous streams.
4. **Logging**: Use GStreamer's logging system (`GST_DEBUG`) for debugging.
