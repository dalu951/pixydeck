# Test checklist

Run on a machine with an EMEET PIXY connected.

## Automated

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[ai]' 'coverage[toml]'
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m coverage run -m unittest discover -s tests -v
.venv/bin/python -m coverage report
```

CI runs the same on Python 3.10, 3.12 and 3.14 and fails below the coverage floor set in `pyproject.toml` (`[tool.coverage.report] fail_under`).

| Layer | Where | What it guarantees |
| --- | --- | --- |
| Golden bytes | `tests/test_protocol.py` `GoldenBytesTest` | Every HID command byte for byte as captured from a PIXY |
| Safety guard | `SafetyGuardTest` | Power, factory-reset, firmware and SD-card commands can never be sent – also not with masked group bytes (2,000 random heads) |
| Properties / fuzz | `FramingPropertyTest` | Frames round-trip through the reply parser; random replies never crash it; speeds are clamped and float-encoded (seeded, reproducible) |
| Simulated camera | `tests/pixy_sim.py` + `SimulatedCameraTest`, `CliTest` | The real send/query code over a pseudo terminal that answers like the PIXY: echo matching, stale-report draining, silent and garbage replies |
| V4L2 / discovery | `tests/test_backend.py` | ioctl path with a fake driver, v4l2-ctl fallback, unplug and rediscovery, sysfs matching of the capture and HID nodes |
| GUI behaviour | `tests/test_gui.py`, `test_gui_window.py`, `test_gui_panels.py`, `test_widgets.py` | Window, every mixin and every custom widget with a recording fake controller: zoom split, held-key moves, auto-framing, watchdog, snapshot, settings migration |
| Setup / logging | `tests/test_setup.py`, `tests/test_diagnostics.py` | Every system check and fix path (polkit mocked), log rotation and crash hooks |
| Pipeline | `tests/test_vision.py`, `tests/test_background.py`, `tests/test_pipeline.py` | Frame processing, matting/keying, stabilizer and the FFmpeg watchdog with synthetic images only |
| Hardware | `tests/test_hardware.py` | Opt-in checks against a real PIXY; every value is restored |

### On a PIXY

```bash
PIXYDECK_HARDWARE=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_hardware -v
```

Reads every on-board setting and round-trips motor speed, tracking target and locks, restoring each value. It never moves the camera or changes the power-on position.

## From source, without installing

```bash
.venv/bin/pixydeck
```

- [ ] Preview starts; HUD shows resolution and LIVE
- [ ] Pan/tilt: pad click/drag, arrow buttons (hold), arrow keys, drag and double-click on the preview
- [ ] Tilt stops at -52°
- [ ] Motor speed slider: 5 °/s pans visibly slowly, 240 °/s fast; setting survives a restart
- [ ] Tracking keeps in frame: *Face* vs *Upper body* changes how tight tracking frames you
- [ ] Locks: with *Lock exposure* on, holding a bright object up does not darken the picture
- [ ] *Save as camera power-on position*, unplug/replug: the camera returns there
- [ ] Zoom: slider, mouse wheel, `+`/`-`; hardware zoom at 1280×720, digital at 4K
- [ ] Presets: store, recall, startup position
- [ ] Tracking / privacy / gesture switch on the camera; gesture changes show up in the UI within ~3 s
- [ ] AI focus: center, face, click point (yellow marker)
- [ ] Mirror / flip / auto-rotate
- [ ] Picture sliders change the image; auto/manual toggles; reset
- [ ] Auto-framing with face overlay
- [ ] Background: AI blur, gradient, colour, image; green screen if available
- [ ] Stabilization: tap the monitor, picture stays steady
- [ ] Privacy timer counts down when the preview is released; wakes when another app opens the camera
- [ ] Snapshot saved to `~/Pictures/EMEET PIXY`

## Installed

```bash
./install.sh
```

- [ ] *EMEET PixyDeck* appears in the application menu and starts
- [ ] Settings from an earlier emeet-pixy-control install were carried over
- [ ] `systemctl status pixydeck-virtual-camera.service` is active and `v4l2-ctl --list-devices` lists *PixyDeck Virtual Camera*
- [ ] Processed virtual camera works in Meet/Zoom/Teams/OBS, effects included
- [ ] Direct virtual camera works; 1080p at 30 fps keeps hardware zoom
- [ ] *Release camera*: the physical PIXY works in another app while PTZ still responds
- [ ] `./uninstall.sh` removes menu entry, service and udev rule
