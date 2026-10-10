# Contributing to EMEET PixyDeck

Thanks for helping! PixyDeck is GPL-3.0-only; contributions are accepted under the same license.

## Development setup

Prerequisites: an EMEET PIXY, Python 3.10+, `v4l-utils`, FFmpeg and (for the virtual camera) `v4l2loopback` – see the README's install section.

```bash
git clone https://github.com/dalu951/pixydeck.git
cd pixydeck
python3 -m venv .venv
.venv/bin/pip install -e '.[ai]' pyflakes
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
<!-- /AUTO-GENERATED:dependencies -->

## Commands

<!-- AUTO-GENERATED:commands -->
| Command | Entry point / purpose |
| --- | --- |
| `pixydeck` | `pixydeck.gui:main` |
| `pixydeck-cli` | `pixydeck.backend:main` |
| `python tools/gen_docs.py` | Regenerate AUTO-GENERATED doc sections |
| `python tools/gen_docs.py --check` | Fail if docs are stale (CI) |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests` | Run the test suite |
| `python -m pyflakes src tests` | Lint |
<!-- /AUTO-GENERATED:commands -->

## Tests

- Tests live in `tests/` and use `unittest`; Qt runs with `QT_QPA_PLATFORM=offscreen`.
- Pure logic (framing, smoothing, stabilization, keying, HID report building) must be testable without a camera – keep it out of widget classes.
- Code that talks to hardware gets a mock-based test where possible (see `test_focus_point_is_scaled_to_camera_range`).
- Anything touching the camera also needs a manual check from [TESTING.md](../TESTING.md).

## Code style

- Match the surrounding code: type hints, `from __future__ import annotations`, small functions, comments that explain *why*.
- Camera commands run on `ControlWorker`; never block the GUI thread with I/O.
- Per-frame work belongs in `FrameProcessor` (parallel render pool); anything recurrent or order-dependent (matting, stabilization) runs on its sequential frame thread.
- Only expose vendor HID commands verified on real hardware, and document what was tested.
- `python -m pyflakes src tests` must be clean.

## Documentation

Sections between `<!-- AUTO-GENERATED:… -->` markers are generated from the code – do not edit them by hand:

- CLI table ← `CLI_COMMANDS` in `src/pixydeck/backend.py`
- Shortcut table ← `SHORTCUTS` in `src/pixydeck/gui.py`
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
