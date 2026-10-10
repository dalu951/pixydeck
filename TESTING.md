# Test checklist

Run on a machine with an EMEET PIXY connected.

## Automated

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[ai]'
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## From source, without installing

```bash
.venv/bin/pixydeck
```

- [ ] Preview starts; HUD shows resolution and LIVE
- [ ] Pan/tilt: pad click/drag, arrow buttons (hold), arrow keys, drag and double-click on the preview
- [ ] Tilt stops at -52°
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
