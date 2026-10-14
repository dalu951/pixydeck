<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="EMEET PixyDeck icon">

# EMEET PixyDeck

**The Linux control suite for the EMEET PIXY webcam.**<br>
Pan, tilt and zoom, the camera's own AI tracking, auto-framing, AI background blur, green screen,<br>
stabilization, call detection and a virtual camera for Meet, Zoom, Teams, WhatsApp and OBS – in one native app.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
![Platform](https://img.shields.io/badge/platform-Linux-informational)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

**English** · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

<img src="docs/media/background.gif" width="860" alt="PixyDeck switching between no effect, AI background blur, gradient and colour backgrounds">

</div>

> **Unofficial community project** – not affiliated with or endorsed by EMEET. EMEET and PIXY are trademarks of their respective owner. All pictures on this page show a painted demo scene, rendered by the real app.

## In 30 seconds

1. **Install** the package for your system ([below](#install)) and restart the computer once.
2. **Open EMEET PixyDeck** from the application menu. If something is missing, the setup dialog fixes it with one password prompt.
3. **Make your call** in WhatsApp, Meet, Zoom or Teams – they pick up *EMEET PIXY (PixyDeck)* by themselves, with your zoom, background and stabilization.

That's it. Everything else is optional.

## What it does

<table>
<tr>
<td width="33%"><img src="docs/media/zoom.gif" alt="Zoom and aim"></td>
<td width="33%"><img src="docs/media/autoframe.gif" alt="Auto-framing follows a person"></td>
<td width="33%"><img src="docs/media/stabilize.gif" alt="A shaking camera without and with Steady picture"></td>
</tr>
<tr>
<td><b>Aim and zoom up to 4×</b><br>Click, drag or hold the arrows to aim; scroll to zoom – hardware zoom where the PIXY supports it, sharp digital zoom beyond.</td>
<td><b>Auto-framing</b><br>Local face detection keeps you centred and nicely framed, also in the virtual camera.</td>
<td><b>Steady picture</b><br>Removes the shake of a wobbling monitor or desk – and does not mistake you for shake when you move.</td>
</tr>
</table>

**Control the camera**

| | |
| --- | --- |
| 🎯 **Tracking** | The PIXY follows you on its own; choose *Auto*, *Face* or *Upper body*. **Find me** tilts the camera back to your seat when tracking loses you as you sit down |
| ⚡ **Speed** | Separate pan and tilt speed – slow for calm moves on a stream, fast to keep up with you |
| 📍 **Presets** | Four positions on keys 1–4, a start position, and a power-on position stored in the camera itself |
| 🔍 **Focus** | Centre, face, or **click anything in the picture** to focus the second lens on it |

**Look better**

| | |
| --- | --- |
| 🪄 **Background** | AI blur or replacement without a green screen; automatic green-screen keying; optional NVIDIA CUDA render path |
| 🫨 **Stabilization** | Optical-flow stabilizer with RANSAC – shake out, you and deliberate camera moves stay |
| 🎛️ **Picture** | Brightness, colour, sharpness, gamma, gain; white balance, exposure and focus automatic, manual or locked; anti-flicker |

**In calls**

| | |
| --- | --- |
| 🎥 **Virtual camera** | *EMEET PIXY (PixyDeck)* carries every effect into any app, for several apps at once. It is the first camera in every list, so apps choose it without asking, and it shows a waiting screen instead of disappearing while PixyDeck has no picture |
| 📞 **Call detection** | When an app opens the camera, tracking turns on; when the call ends, the lens turns away. Optionally switches the microphone and locks focus for a steady call image |
| 🎙️ **Microphone** | The PIXY's noise cancelling, live or original mode |

**Privacy and setup**

| | |
| --- | --- |
| 🔒 **Privacy** | Privacy mode turns the lens away; the idle timer does it automatically and wakes up when an app needs the camera; the microphone can be muted with it |
| 🛠️ **Guided setup** | Checks permissions, kernel module and virtual camera, and fixes them with one click |
| ⌨️ **Command line** | `pixydeck-cli` for scripts and hotkeys – pan, tilt, zoom, tracking, speed, locks, state |

## GUI tour

<img src="docs/media/tour.png" width="860" alt="PixyDeck main window with numbered markers">

| | |
| --- | --- |
| **①** Status | Tracking mode, virtual camera, and the app currently using the camera (*📞 Call* during a call) |
| **②** Setup | Turns into **⚠ Setup** when something needs fixing |
| **③** Preview | Drag to aim, double-click to centre a spot, scroll to zoom; with *Click point* focus, click to focus |
| **④** Toolbar | Resolution, zoom, snapshot, and *Release camera* to hand the real camera to another app |
| **⑤** Tabs | Grouped by task – see below |
| **⑥** Cards | Settings; rarely used ones are folded (▸) – click the title to open them |

| Tab | For |
| --- | --- |
| **Camera** | Aim, pan/tilt speed, presets, start and power-on position |
| **Tracking** | The camera's tracking and what it keeps in frame, *Find me*, gestures, focus, auto-framing |
| **Image** | Picture sliders, stabilization; folded: automatic modes and locks, orientation and anti-flicker |
| **Effects** | Background replacement; folded: green-screen fine-tuning |
| **Calls** | Call detection, privacy timer, microphone |
| **Output** | Virtual camera, *Start with PixyDeck* |

Every setting explained, tab by tab: **[GUI tour](docs/en/gui-tour.md)**.

<details>
<summary><b>All screenshots</b></summary>

| Camera | Tracking | Image |
| --- | --- | --- |
| <img src="docs/media/camera.png" alt="Camera tab"> | <img src="docs/media/ai.png" alt="Tracking tab"> | <img src="docs/media/image.png" alt="Image tab"> |
| **Effects** | **Calls** | **Output** |
| <img src="docs/media/background.png" alt="Effects tab"> | <img src="docs/media/calls.png" alt="Calls tab"> | <img src="docs/media/output.png" alt="Output tab"> |
| **Setup** | | |
| <img src="docs/media/setup.png" alt="Setup dialog"> | | |

</details>

## Which camera do I pick?

| In the app choose | You get |
| --- | --- |
| **EMEET PIXY (PixyDeck)** – recommended | PixyDeck's picture with all effects; several apps can use it at the same time |
| **EMEET PIXY** | The raw camera – only while PixyDeck is closed or you clicked *Release camera*, because a webcam serves one program at a time |

Most apps take the first camera automatically, and that is *EMEET PIXY (PixyDeck)*. Tested with Google Meet in Firefox and WhatsApp ([Whatsie](https://flathub.org/apps/com.ktechpit.whatsie)); reports for other apps are welcome.

## Install

| System | Command |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | Download `pixydeck_<version>_amd64.deb` from the [releases](https://github.com/dalu951/pixydeck/releases), then `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | Download `PKGBUILD` and `pixydeck.install` from the [latest release](https://github.com/dalu951/pixydeck/releases/latest), then `makepkg -si` (AUR package coming soon) |
| **Any distribution** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Restart once afterwards, so the virtual camera is created ahead of the real one. Start **EMEET PixyDeck** from the application menu; if anything is missing – camera permissions, the `v4l2loopback` module or the virtual camera – the **⚙ Setup** dialog shows it and fixes it after one password prompt.

Details, requirements and uninstalling: **[Installation guide](docs/en/installation.md)**.

## Documentation

| | English | Deutsch |
| --- | --- | --- |
| Installation | [installation.md](docs/en/installation.md) | [installation.md](docs/de/installation.md) |
| GUI tour (every setting) | [gui-tour.md](docs/en/gui-tour.md) | [gui-tour.md](docs/de/gui-tour.md) |
| User guide (features, shortcuts, CLI) | [user-guide.md](docs/en/user-guide.md) | [benutzerhandbuch.md](docs/de/benutzerhandbuch.md) |
| Troubleshooting | [troubleshooting.md](docs/en/troubleshooting.md) | [fehlerbehebung.md](docs/de/fehlerbehebung.md) |
| FAQ | [faq.md](docs/en/faq.md) | [faq.md](docs/de/faq.md) |
| Operations runbook | [RUNBOOK.md](docs/RUNBOOK.md) | |
| Contributing | [CONTRIBUTING.md](docs/CONTRIBUTING.md) | |

## Privacy and security

- All AI (face detection, background matting, stabilization) runs **locally**; no frame leaves your computer, there is no network code.
- Privileged steps go through one small helper with fixed actions, authorized by your system's polkit dialog.
- Camera commands that could reboot, reset or reflash the PIXY are blocked before they reach it.
- The udev rules only match the PIXY (`328f:00c0`) and the PixyDeck virtual camera.

## Contributing

Bug reports, distribution feedback and pull requests are welcome – see [CONTRIBUTING.md](docs/CONTRIBUTING.md). Only camera commands verified on real hardware are exposed; the test suite (500+ tests, 98 % coverage) includes a simulated PIXY and an opt-in hardware check.

## Credits and license

PixyDeck began as a fork of [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) by Rolf Obermaier. It builds on community reverse engineering of the PIXY protocol (including [emeet-pixyd](https://github.com/LarsArtmann/emeet-pixyd)), YuNet (OpenCV Zoo) and Robust Video Matting – see [CREDITS.md](CREDITS.md).

Licensed under the **GNU GPL v3 only** – see [LICENSE](LICENSE).
