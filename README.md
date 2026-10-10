# EMEET PixyDeck

**The Linux control suite for the EMEET PIXY webcam** (USB `328f:00c0`): pan/tilt/zoom, the camera's own AI features, software auto-framing, AI background blur and replacement, green screen, stabilization and a virtual camera for Meet, Zoom, Teams and OBS – in one native app.

> **Unofficial community project.** Not affiliated with or endorsed by EMEET. EMEET and PIXY are trademarks of their respective owner.

## Status

**Beta, hardware-specific.** Developed and tested with an EMEET PIXY on Pop!_OS (Ubuntu-based) and, in its origins, on CachyOS (Arch-based). Reports from other distributions are welcome.

## Features

### Camera control
- **Responsive PTZ:** every command is a direct V4L2 ioctl on a background thread – the UI never blocks
- Aim with a click-and-drag **pan/tilt pad**, accelerating **hold-to-move** buttons, **arrow keys**, or by **dragging / double-clicking the preview**
- **Unified zoom up to 4×:** PIXY hardware zoom (1.0–1.5×) where the video mode supports it, digital zoom beyond – also at 4K; mouse wheel and `+`/`-` on the preview
- **Presets:** four pan/tilt/zoom slots and a selectable startup position
- Tilt is limited to the usable range (-52° … +90°); lower angles only park the camera

### PIXY on-board AI
- Face tracking, privacy mode and gesture control
- **AI focus:** center, face, or **click any point in the preview** – e.g. an object you hold up – and the PIXY's second lens focuses there
- Microphone DSP mode: noise cancel / live / original
- Mirror, vertical flip and auto-rotate for upside-down mounting
- **Live state sync:** changes made by gestures or other apps show up in the UI

### Software AI and effects
- **Auto-framing:** YuNet face detection digitally frames and follows you
- **Background blur/replacement without green screen:** Robust Video Matting cuts you out of any room
- **Green screen:** detected automatically, keyed with soft edges and spill removal
- Fill with blur, gradient, colour or your own image; *Auto* prefers a green screen when one is in view
- **Stabilization** against shake from a wobbling monitor or desk

### Privacy
- **Privacy timer:** enters privacy mode after X idle minutes, wakes up automatically when Zoom/Teams/Meet/OBS open the camera, optionally mutes the PIXY microphone
- All AI runs locally; no frames leave the computer

### Picture
- Brightness, contrast, saturation, hue, sharpness, gamma, gain
- Auto/manual white balance, exposure and focus; backlight compensation; anti-flicker
- Ranges are read from the camera; reset to defaults with one click

### Output
- **Processed virtual camera:** preview keeps running; zoom, auto-framing, background and stabilization are sent to **PixyDeck Virtual Camera**
- **Direct virtual camera:** FFmpeg passthrough for the lowest CPU use, with frame-rate choice
- **Release camera:** frees the physical PIXY for other apps while all controls keep working
- Snapshot to `~/Pictures/EMEET PIXY`

### Keyboard shortcuts

<!-- AUTO-GENERATED:shortcuts -->
| Key | Action |
| --- | --- |
| Arrow keys | Pan / tilt while held |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| Mouse wheel on the preview | Zoom |
| `C` | Center camera and reset zoom |
| `F` | Toggle auto-framing |
| `T` | Toggle face tracking |
| `P` | Toggle privacy mode |
| `S` | Save snapshot |
| `1`–`4` | Recall preset |
| `Ctrl+1`–`Ctrl+4` | Store preset |
| `Ctrl+Q` | Quit |
<!-- /AUTO-GENERATED:shortcuts -->

## Install

### Prerequisites

Pop!_OS / Ubuntu / Debian:

```bash
sudo apt install python3 python3-venv v4l-utils ffmpeg v4l2loopback-utils v4l2loopback-dkms linux-headers-$(uname -r)
```

CachyOS / Arch:

```bash
sudo pacman -S --needed python python-pip v4l-utils ffmpeg v4l2loopback-utils
```

On vanilla Arch, `v4l2loopback-utils` normally uses the `v4l2loopback-dkms` module provider; install the headers for your kernel if DKMS needs them.

### PixyDeck

```bash
git clone https://github.com/dalu951/pixydeck.git
cd pixydeck
./install.sh
```

The installer creates a private virtual environment in `~/.local/share/pixydeck` (PySide6, OpenCV and ONNX Runtime), adds **EMEET PixyDeck** to the application menu, installs a udev rule that grants HID access to the PIXY only, and enables the `pixydeck-virtual-camera` service. An existing *emeet-pixy-control* installation is replaced and its settings are carried over.

If HID controls are denied right after installing, unplug and replug the PIXY once (or log out and in).

Uninstall with `./uninstall.sh` (add `--purge` to also delete saved settings). System packages are left installed.

## Zoom behaviour

The PIXY applies hardware zoom (`zoom_absolute` 100–150) below 1080p and at **1080p30**, but ignores it at **1080p60** and above 1080p, even though V4L2 accepts the value. Qt always opens 1080p at 60 fps. PixyDeck therefore combines both: hardware zoom first where it works, digital zoom on top (up to 4×) whenever the picture runs through the app. In *Direct* virtual-camera mode, choose 30 fps at 1080p to keep hardware zoom.

## Virtual camera vs. releasing the camera

Linux apps usually cannot share one physical webcam stream.

- **Processed virtual camera** – select *PixyDeck Virtual Camera* in your meeting app. Everything you see in PixyDeck, including effects, is what others see.
- **Direct virtual camera** – FFmpeg forwards the PIXY unchanged; lowest CPU, hardware zoom only.
- **Release camera** – the physical PIXY becomes available to other apps directly; PixyDeck keeps controlling PTZ, AI and picture settings.

The virtual device is created at boot by `pixydeck-virtual-camera.service` (prefers `/dev/video20`, falls back to `/dev/video21`–`29`) and is found by name.

## Camera features not offered on purpose

PixyDeck only exposes vendor commands verified on real hardware:

- HID-based PTZ movement and on-camera presets move the motor, but the camera then reports no position over UVC or HID, so the app would lose track of where it points. Pan/tilt stays on standard UVC controls.
- Half-/full-body tracking framing, HDR, object tracking, motor speed, focus/exposure/white-balance locks and the power-on position are either ignored or unanswered by current PIXY firmware.

## CLI

<!-- AUTO-GENERATED:cli -->
Installed at `~/.local/share/pixydeck/venv/bin/pixydeck-cli`.

| Command | Description |
| --- | --- |
| `pixydeck-cli status` | Show device, pan, tilt and zoom |
| `pixydeck-cli center` | Pan/tilt to 0° and zoom out |
| `pixydeck-cli left` | Pan 2° left |
| `pixydeck-cli right` | Pan 2° right |
| `pixydeck-cli up` | Tilt 2° up |
| `pixydeck-cli down` | Tilt 2° down |
| `pixydeck-cli pan DEGREES` | Pan to an absolute angle (-150…150) |
| `pixydeck-cli tilt DEGREES` | Tilt to an absolute angle (-52…90) |
| `pixydeck-cli zoom 100-150` | Set hardware zoom |
| `pixydeck-cli zoom-in` | Hardware zoom +10 |
| `pixydeck-cli zoom-out` | Hardware zoom -10 |
| `pixydeck-cli track` | Enable face tracking |
| `pixydeck-cli idle` | Disable tracking |
| `pixydeck-cli privacy` | Enter privacy mode |
| `pixydeck-cli gesture-on` | Enable gesture control |
| `pixydeck-cli gesture-off` | Disable gesture control |
| `pixydeck-cli audio nc|live|org` | Microphone mode: noise cancel, live, original |
| `pixydeck-cli auto-privacy SECONDS` | Camera-side auto-privacy delay (0 = off; experimental) |
| `pixydeck-cli flicker off|50|60` | Anti-flicker frequency |
<!-- /AUTO-GENERATED:cli -->

## Troubleshooting

**Meeting app can't see the camera while PixyDeck shows a preview** – select *PixyDeck Virtual Camera*, or click *Release camera* and pick the physical EMEET PIXY.

**`Permission denied` on `/dev/hidraw*`** – check that `/etc/udev/rules.d/70-pixydeck.rules` exists, then replug the camera.

**Virtual camera "Device missing"** – check `systemctl status pixydeck-virtual-camera.service` and `v4l2-ctl --list-devices`.

**`modprobe: Module v4l2loopback not found`** – install the module for your running kernel (plus headers for DKMS). After a kernel update, reboot into the new kernel first.

**AI features greyed out** – the optional dependencies are missing: `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'`.

**Qt/FFmpeg mentions `libvdpau_nvidia.so`** – Qt probes optional hardware decoders; harmless if the preview works.

## Security and permissions

The udev rule only matches USB `328f:00c0`; it does **not** open every `/dev/hidraw*` device. The loopback device is managed by a root systemd unit; the app only writes video frames to it. AI models run locally with no network access.

## Project layout

```text
src/pixydeck/
  gui.py         main window
  widgets.py     theme and custom widgets (preview, aiming pad, switches)
  worker.py      background thread for camera commands
  vision.py      auto-framing, digital zoom, stabilization, processed virtual camera
  background.py  green-screen keying and AI person matting
  backend.py     UVC (ioctl) and HID control + CLI
  assets/        icon and AI models
deploy/          udev rule, systemd unit, loopback helper, desktop entry
install.sh / uninstall.sh
```

## Development

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). Operating the installed suite (service, upgrades, rollback, diagnostics) is covered in [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Origins and credits

PixyDeck began as a fork of [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) by Rolf Obermaier, whose installer, systemd/udev integration and first HID implementation it still builds on. Protocol knowledge, AI models and other third-party work are credited in [CREDITS.md](CREDITS.md).

## License

**GNU GPL v3 only** – see [LICENSE](LICENSE).
