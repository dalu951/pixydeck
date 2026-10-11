# Changelog

## Unreleased

- Auto-framing keeps up when you sit down or stand up: it widens after 0.8 s without a face (was 2.5 s), the face detector tolerates motion blur better, and while the camera's own tracking follows you the digital zoom stays at most 1.6×
- **Separate pan and tilt speed** – a fast tilt keeps tracking with you when you stand up or sit down; PixyDeck sets the speeds again when the camera falls back to its own
- The virtual camera service loads v4l2loopback with `devices=0`, so no empty “Dummy video device” appears in apps' camera lists

## 0.5.1 - 2026-10-11

- Virtual camera: every frame is flushed to FFmpeg at once; with Python 3.14's larger write buffer, small frames (such as the waiting screen) were held back

## 0.5.0 - 2026-10-11

- **The virtual camera is now called “EMEET PIXY (PixyDeck)”**, so apps list it next to the real camera. A device with the old name “PixyDeck Virtual Camera” keeps working and is renamed the next time it is created (reboot, or Setup → Virtual camera → Fix while no app uses it)
- **Tidier window**: six task tabs (Camera, Tracking, Image, Effects, Calls, Output); rarely used settings in folded cards; long explanations moved to tooltips; the last tab and open cards are remembered
- **Call detection** (AI & Privacy tab → *Calls*): when another app opens the PIXY or the virtual camera, tracking turns on; after the call the lens turns away. Optional: use the PIXY microphone as the default input during calls and switch back afterwards. Brief device probes by browsers are ignored (debounced)
- **Virtual camera waiting screen**: while PixyDeck has no camera picture (another app holds the PIXY, or it is unplugged) the virtual camera shows a still, so Meet, WhatsApp or Teams can still select it; the real picture follows as soon as the camera is free
- **Start the virtual camera with PixyDeck** (Output tab)
- At a call start, a hint when the app reads the PIXY directly and so misses the effects
- The camera is retried while the processed virtual camera runs, not only in preview
- Timers no longer fire into a closed window
- Tests: the GUI test harness can no longer run real `pactl` commands

## 0.4.1 - 2026-10-11

- Scrolling a tab no longer changes the slider, spin box or drop-down that passes under the mouse; click a control first to adjust it with the wheel

## 0.4.0 - 2026-10-11

- **Motor speed** (1–240 °/s) for pan and tilt – slider on the Camera tab, `pixydeck-cli pan-speed`/`tilt-speed`; restored on start
- **Tracking target**: *Auto*, *Face* or *Upper body* (`pixydeck-cli target`)
- All of the above verified on a PIXY by the user, not only by readback
- **Exposure, white-balance and focus locks** on the Image tab (`pixydeck-cli exposure-lock|wb-lock|focus-lock`)
- **Camera power-on position**: store the current pan/tilt in the PIXY itself (`pixydeck-cli power-on-position save`)
- `pixydeck-cli state` shows every on-board setting the camera reports
- HID safety guard: power, factory-reset, firmware and SD-card commands are refused before they reach the camera
- HID: a query on a node that reads EOF no longer spins forever
- Setup: the polkit password prompt is no longer killed after 10 s (and then misreported as “cancelled”)
- Green screen: leaving the picture in *Green screen* mode is reported once instead of every half second
- Background tab: without the AI extra the “needs the AI extra” hint now stays visible instead of being blanked at startup
- Logging: setting up logging twice no longer writes every line twice
- Tests: golden bytes for every HID command, a simulated PIXY over a pseudo terminal, fuzz/property tests, fake V4L2 driver, opt-in hardware suite (`PIXYDECK_HARDWARE=1`), coverage gate in CI

## 0.3.2 - 2026-10-11

- Processed virtual camera: FFmpeg's error output is drained and logged, and an FFmpeg exit is detected right away – PixyDeck shows the error and resets to *Virtual cam off* instead of staying “on” with a stale frame rate
- 28 GUI behaviour tests for the window and every mixin (fake controller, no camera or hardware access)
- Split the 1,870-line `gui.py` into mixin modules (`controls`, `presets`, `background_panel`, `privacy`, `virtual_camera`, `constants`); UI verified pixel-identical

## 0.3.1 - 2026-10-10

- Log file `~/.local/state/pixydeck/pixydeck.log` (rotating) with uncaught exceptions from the GUI and worker threads and Qt warnings; `PIXYDECK_DEBUG=1` for debug output
- Version shown in the header (tooltip: log file path)
- Release assets: `pixydeck.SRCINFO` instead of GitHub's `default.SRCINFO`, plus `SHA256SUMS`
- Docs: Arch install via the release `PKGBUILD` until the AUR package is published; `.deb` targets the 24.04 base

## 0.3.0 - unreleased

First release as **EMEET PixyDeck** (`pixydeck`), an independent project that grew out of emeet-pixy-control.

- Renamed package, commands (`pixydeck`, `pixydeck-cli`), service, udev rule and desktop entry
- Virtual camera is now called *PixyDeck Virtual Camera*
- Installer replaces an existing emeet-pixy-control install; settings are migrated on first start
- Setup dialog: checks camera access, v4l2loopback, the virtual camera, permissions, FFmpeg and AI extras; one-click fixes through a polkit-authorized helper with fixed actions
- `.deb` (Ubuntu/Pop!_OS 24.04, bundled deps, ~136 MB) and AUR packages; tag-driven release workflow
- Security: AUR key scoped to the publish step, pinned host key and action SHAs, sandboxed systemd unit, udev access to the virtual camera instead of the `video` group
- Performance: AI background 12.5 → 27 fps at 1080p, GUI thread no longer blocked, cheaper camera-user scan
- Fix: preview froze after some resolution changes (frame watchdog restarts stalled streams)
- Docs: README in English, German, French and Spanish; user guide, installation, troubleshooting and FAQ in English and German; synthetic screenshots and GIFs (`tools/make_media.py`)
- docs/CONTRIBUTING.md and docs/RUNBOOK.md; CLI, shortcut, command and install tables generated from code (`tools/gen_docs.py`, checked in CI)

## 0.2.0 - unreleased (emeet-pixy-control fork)

- Redesigned dark UI with tabs (Camera, AI & Privacy, Image, Output), status pills and preview HUD
- Camera commands run on a background thread via direct V4L2 ioctls (no per-click subprocesses)
- Aiming pad, accelerating hold-to-move, arrow keys, drag/double-click on the preview
- Unified hardware + digital zoom up to 4x; hardware zoom now also used at 1080p30
- PTZ presets with startup position
- Software auto-framing (YuNet face detection) and face overlay
- Privacy timer with automatic wake when another app opens the camera; optional mic mute
- Picture controls: colour, sharpness, gamma, gain, white balance, exposure, focus, backlight
- Processed virtual camera (keeps preview, includes digital zoom/auto-framing); frame-rate choice for direct mode
- Snapshot button
- AI focus modes: center, face, click-to-focus point in the preview
- Live sync of on-board state (gesture, microphone mode, focus, privacy, orientation)
- Mirror / vertical flip / auto-rotate
- Background replacement: AI person matting (Robust Video Matting) or automatically detected green screen; blur/gradient/colour/image fill
- Software stabilization against monitor/desk shake
- Tilt limited to -52° (lower values only park the camera)
- Fix: virtual-camera service used /usr/bin/modprobe, which does not exist on Debian/Ubuntu
- Fix: negative pan/tilt angles were rounded down in status output

## 0.1.0 - 2026-08-24 (emeet-pixy-control by Rolf Obermaier)

Initial public preview.

- Native PySide6 preview/control GUI
- Dynamic PIXY video/HID discovery
- PTZ, center, zoom, tracking, privacy, gesture, audio and anti-flicker controls
- Resolution selection and saved settings
- Release Preview mode for direct use by Meet/OBS/Teams
- FFmpeg + v4l2loopback Virtual Camera mode
- Persistent virtual-camera systemd service
- Targeted udev permissions for EMEET PIXY HID access
- Responsive split layout with scrollable controls
- Desktop launcher and project icon
