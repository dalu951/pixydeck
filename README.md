<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="EMEET PixyDeck icon">

# EMEET PixyDeck

**The Linux control suite for the EMEET PIXY webcam.**<br>
Pan, tilt and zoom, the camera's own AI, auto-framing, AI background blur, green screen,<br>
stabilization and a virtual camera for Meet, Zoom, Teams and OBS – in one native app.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
![Platform](https://img.shields.io/badge/platform-Linux-informational)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

**English** · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

<img src="docs/media/background.gif" width="860" alt="PixyDeck switching between no effect, AI background blur, gradient and colour backgrounds">

</div>

> **Unofficial community project** – not affiliated with or endorsed by EMEET. EMEET and PIXY are trademarks of their respective owner. All pictures on this page show a painted demo scene, rendered by the real app.

## Highlights

<table>
<tr>
<td width="50%"><img src="docs/media/zoom.gif" alt="Zoom and aim"></td>
<td width="50%"><img src="docs/media/autoframe.gif" alt="Auto-framing follows a person"></td>
</tr>
<tr>
<td><b>Smooth PTZ and zoom up to 4×</b><br>Aim by clicking or dragging, hold arrows to glide, scroll to zoom. Hardware zoom where the PIXY supports it, sharp digital zoom beyond – even at 4K.</td>
<td><b>Auto-framing</b><br>Local face detection keeps you centred and nicely framed, also in the virtual camera.</td>
</tr>
</table>

| | |
| --- | --- |
| 🎯 **PIXY on-board AI** | Face tracking, privacy mode, gestures, **click-to-focus** with the second lens, microphone noise cancelling – with live sync of changes made by gestures |
| 🪄 **Background** | AI blur or replacement without a green screen; automatic green-screen keying when one is in view |
| 🎥 **Virtual camera** | *PixyDeck Virtual Camera* carries zoom, framing and background effects into any video app |
| 🫨 **Stabilization** | Removes shake from a wobbling monitor or desk |
| 🔒 **Privacy timer** | Lens turns away after idle minutes and wakes up when Zoom, Teams, Meet or OBS opens the camera |
| 🎛️ **Picture control** | Colour, sharpness, gamma, gain, white balance, exposure, focus, anti-flicker, presets |
| 🛠️ **Guided setup** | Checks permissions, kernel module and virtual camera, and fixes them with one click |

<details>
<summary><b>Screenshots</b></summary>

| Camera | Tracking | Image |
| --- | --- | --- |
| <img src="docs/media/camera.png" alt="Camera tab"> | <img src="docs/media/ai.png" alt="Tracking tab"> | <img src="docs/media/image.png" alt="Image tab"> |
| **Effects** | **Output** | **Setup** |
| <img src="docs/media/background.png" alt="Effects tab"> | <img src="docs/media/output.png" alt="Output tab"> | <img src="docs/media/setup.png" alt="Setup dialog"> |

</details>

## Install

| System | Command |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | Download `pixydeck_<version>_amd64.deb` from the [releases](https://github.com/dalu951/pixydeck/releases), then `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | Download `PKGBUILD` and `pixydeck.install` from the [latest release](https://github.com/dalu951/pixydeck/releases/latest), then `makepkg -si` (AUR package coming soon) |
| **Any distribution** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Start **EMEET PixyDeck** from the application menu. If anything is missing – camera permissions, the `v4l2loopback` module or the virtual camera – the **⚙ Setup** dialog shows it and fixes it after one password prompt.

Details, requirements and uninstalling: **[Installation guide](docs/en/installation.md)**.

## Documentation

| | English | Deutsch |
| --- | --- | --- |
| Installation | [installation.md](docs/en/installation.md) | [installation.md](docs/de/installation.md) |
| User guide (features, shortcuts, CLI) | [user-guide.md](docs/en/user-guide.md) | [benutzerhandbuch.md](docs/de/benutzerhandbuch.md) |
| Troubleshooting | [troubleshooting.md](docs/en/troubleshooting.md) | [fehlerbehebung.md](docs/de/fehlerbehebung.md) |
| FAQ | [faq.md](docs/en/faq.md) | [faq.md](docs/de/faq.md) |
| Operations runbook | [RUNBOOK.md](docs/RUNBOOK.md) | |
| Contributing | [CONTRIBUTING.md](docs/CONTRIBUTING.md) | |

## Privacy and security

- All AI (face detection, background matting, stabilization) runs **locally**; no frame leaves your computer, there is no network code.
- Privileged steps go through one small helper with fixed actions, authorized by your system's polkit dialog.
- The udev rules only match the PIXY (`328f:00c0`) and the PixyDeck virtual camera.

## Contributing

Bug reports, distribution feedback and pull requests are welcome – see [CONTRIBUTING.md](docs/CONTRIBUTING.md). Only camera commands verified on real hardware are exposed.

## Credits and license

PixyDeck began as a fork of [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) by Rolf Obermaier. It builds on community reverse engineering of the PIXY protocol, YuNet (OpenCV Zoo) and Robust Video Matting – see [CREDITS.md](CREDITS.md).

Licensed under the **GNU GPL v3 only** – see [LICENSE](LICENSE).
