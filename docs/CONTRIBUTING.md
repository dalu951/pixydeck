# Contributing to EMEET PixyDeck

Thanks for helping! PixyDeck is GPL-3.0-only; contributions are accepted under the same license.

## Development setup

Prerequisites: an EMEET PIXY, Python 3.10+, `v4l-utils`, FFmpeg and (for the virtual camera) `v4l2loopback` – see the README's install section.

```bash
git clone https://github.com/dalu951/pixydeck.git
cd pixydeck
python3 -m venv .venv
.venv/bin/pip install -e '.[ai]' pyflakes coverage
.venv/bin/pixydeck
```

An editable install picks up code changes on the next start. It does not touch an installed copy in `~/.local/share/pixydeck`.

### Dependencies

<!-- AUTO-GENERATED:dependencies -->
Python `>=3.10`.

| Package | Needed for |
| --- | --- |
| `PySide6-Essentials>=6.8,<7` | required |
| `PySide6-Addons>=6.8,<7` | required |
| `numpy>=1.24` | extra `[ai]` |
| `opencv-python-headless>=4.8` | extra `[ai]` |
| `onnxruntime>=1.17` | extra `[ai]` |
| `numpy>=1.24` | extra `[gpu]` |
| `opencv-python-headless>=4.8` | extra `[gpu]` |
| `onnxruntime-gpu[cuda,cudnn]>=1.21,<1.24` | extra `[gpu]` |
| `cupy-cuda12x[ctk]>=14.0,<15` | extra `[gpu]` |
<!-- /AUTO-GENERATED:dependencies -->

## Commands

<!-- AUTO-GENERATED:commands -->
| Command | Entry point / purpose |
| --- | --- |
| `pixydeck` | `pixydeck.gui:main` |
| `pixydeck-cli` | `pixydeck.backend:main` |
| `pixydeck-gpu-benchmark` | `pixydeck.gpu_benchmark:main` |
| `python tools/gen_docs.py` | Regenerate AUTO-GENERATED doc sections |
| `python tools/gen_docs.py --check` | Fail if docs are stale (CI) |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests` | Run the test suite |
| `python -m coverage run -m unittest discover -s tests && python -m coverage report` | Test suite with coverage (CI floor in `pyproject.toml`) |
| `PIXYDECK_HARDWARE=1 PYTHONPATH=src python -m unittest tests.test_hardware -v` | Round-trip checks on a connected PIXY |
| `python -m pyflakes src tests` | Lint |
<!-- /AUTO-GENERATED:commands -->

## Tests

- Tests live in `tests/` and use `unittest`; Qt runs with `QT_QPA_PLATFORM=offscreen`.
- Pure logic (framing, smoothing, stabilization, keying, HID report building) must be testable without a camera – keep it out of widget classes.
- Code that talks to hardware gets a test against the simulated camera (`tests/pixy_sim.py`) or the fake V4L2 driver in `tests/test_backend.py`; a new HID command also gets a golden-bytes test with the bytes captured on a PIXY and, if it can be undone, a round-trip in `tests/test_hardware.py`.
- New HID heads must not fall into a group blocked by `backend.is_forbidden_head`; probe unknown heads read-only first.
- Anything touching the camera also needs a manual check from [TESTING.md](TESTING.md).

## Code layout

| Module | Responsibility |
| --- | --- |
| `gui.py` | `PixyGUI` window: layout, preview, zoom, pan/tilt, auto-framing, snapshot, startup |
| `controls.py` | `ControlsMixin` – tracking, focus, calls/privacy cards, picture controls (Tracking, Calls & Image tabs) |
| `presets.py` | `PresetsMixin` – pan/tilt/zoom presets and startup position |
| `background_panel.py` | `BackgroundMixin` – green screen / AI background and its tab |
| `privacy.py` | `PrivacyMixin` – privacy timer, wake on camera use, mic mute |
| `virtual_camera.py` | `VirtualCameraMixin` – processed/direct virtual camera, Output tab |
| `constants.py` | shared limits, modes and control tables |
| `widgets.py` | theme and custom widgets |
| `vision.py`, `background.py` | frame processing, auto-framing, stabilization, keying, matting |
| `backend.py`, `worker.py` | UVC/HID control and the command thread |
| `setup.py`, `diagnostics.py` | setup dialog, log file and crash capture |

Mixins share the window's state through `self`; put new features in the mixin they belong to rather than growing `gui.py`.

## Code style

- Match the surrounding code: type hints, `from __future__ import annotations`, small functions, comments that explain *why*.
- Camera commands run on `ControlWorker`; never block the GUI thread with I/O.
- Per-frame work belongs in `FrameProcessor` (parallel render pool); anything recurrent or order-dependent (matting, stabilization) runs on its sequential frame thread.
- Only expose vendor HID commands verified on real hardware, and document what was tested.
- `python -m pyflakes src tests` must be clean.

## Packaging

| Target | How to build | Tested by |
| --- | --- | --- |
| `.deb` (Ubuntu/Pop!_OS 24.04) | `packaging/deb/docker-build.sh` – bundles Python deps in `/opt/pixydeck`, prunes unused Qt, verifies imports | install/remove in a clean `ubuntu:24.04` container |
| AUR | `packaging/aur/PKGBUILD` – official Arch packages | `makepkg -si` (runs the test suite) in an `archlinux` container |
| Release | push a tag `vX.Y.Z` matching `pyproject.toml`; `release.yml` attaches the `.deb`, `PKGBUILD` and `.SRCINFO` and publishes to the AUR if `AUR_SSH_PRIVATE_KEY` is set | |

Shell scripts must pass `shellcheck`.

## Documentation

- User docs live in `docs/en` and `docs/de`; `README.*.md` are short overviews in four languages. Keep English and German pages in sync.
- Screenshots and GIFs in `docs/media` are generated by `python tools/make_media.py` from the real UI with a painted demo scene – **never commit real camera pictures**.

Sections between `<!-- AUTO-GENERATED:… -->` markers are generated from the code – do not edit them by hand:

- CLI and shortcut tables in `docs/en/user-guide.md` and `docs/de/benutzerhandbuch.md` ← `CLI_COMMANDS` (`backend.py`) and `SHORTCUTS` (`gui.py`)
- Commands and dependencies ← `pyproject.toml`
- Installed files ← `install.sh`

Run `python tools/gen_docs.py` after changing any of these; CI fails on stale docs.

## Pull request checklist

- [ ] Tests added or updated, suite passes
- [ ] `pyflakes` clean
- [ ] `python tools/gen_docs.py --check` passes
- [ ] Manually tested on a PIXY (state which items of TESTING.md)
- [ ] `CHANGELOG.md` updated under the unreleased version
- [ ] New third-party code, models or protocol knowledge credited in `CREDITS.md` with a compatible license
