# Credits and provenance

## Origin

EMEET PixyDeck began as a fork of **emeet-pixy-control** by Rolf Obermaier (https://github.com/rolfobermaier/emeet-pixy-control, GPL-3.0). The installer, the systemd/udev/v4l2loopback integration, the application icon and the first HID implementation come from that project.

## EMEET PIXY HID protocol

The PIXY exposes standard UVC controls for PTZ/zoom and a proprietary HID interface for tracking/privacy, gesture control, and audio modes.

The HID command families used by this project were documented through community reverse engineering, including:

- rm1138 — `cam_ptz.sh`: https://gist.github.com/rm1138/ef132c3a39f3c1effabf6354e2eca965
- branzo — fork/continued notes: https://gist.github.com/branzo/de238cfe001fa4a834ca21ac43dca580
- LarsArtmann — `emeet-pixyd`: https://github.com/LarsArtmann/emeet-pixyd (its command table extracted from the official app pointed PixyDeck to motor speed, tracking target, power-on position and the lock commands; PixyDeck verified each head on hardware, where every command name turned out to belong to the head one row above it in that table)
- Romonaga — `PixyPilot`: https://github.com/Romonaga/PixyPilot (focus/metering, feature toggles and query formats)

The backend in this repository is an independently written implementation based on those publicly documented protocol facts and local testing. It does not copy the shell implementation from the gists.

## Application icon

The application icon was derived from the **Camera** vector distributed by SVG Repo under CC0 and then modified for PTZ use.

Source: https://www.svgrepo.com/svg/450023/camera

SVG Repo lists that source vector under the CC0 License. Attribution is not required by CC0, but provenance is recorded here for clarity.

## Face detection model

`face_detection_yunet_2023mar.onnx` is YuNet from the OpenCV Model Zoo (https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), MIT License, Copyright (c) 2020 Shiqi Yu.

## Person matting model

`rvm_mobilenetv3_fp32.onnx` is Robust Video Matting by Shanchuan Lin et al. (https://github.com/PeterL1n/RobustVideoMatting), GPL-3.0.

## Trademarks

EMEET and PIXY are trademarks of their respective owner. This project is unofficial and is not affiliated with or endorsed by EMEET.
