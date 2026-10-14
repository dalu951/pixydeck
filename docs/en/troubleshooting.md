# Troubleshooting

[← README](../../README.md) · **English** · [Deutsch](../de/fehlerbehebung.md)

Start with **⚙ Setup** in PixyDeck – it checks permissions, the kernel module and the virtual camera and fixes most problems with one click.

| Symptom | Fix |
| --- | --- |
| **My meeting app does not see the camera** while PixyDeck shows a preview | Select **EMEET PIXY (PixyDeck)** in the app, or click **Release camera** in PixyDeck and pick the physical EMEET PIXY. Only one program can read a webcam stream at a time. |
| **"EMEET PIXY (PixyDeck)" is missing** | ⚙ Setup → *Virtual camera* → **Fix**. If the dialog says the `v4l2loopback` module is missing, install `v4l2loopback-dkms` (plus kernel headers). After a kernel update, reboot first. |
| **Apps still list "PixyDeck Virtual Camera"** | That is the same virtual camera under its name before 0.5.0. It is renamed when it is next created – after a restart, or ⚙ Setup → *Virtual camera* → **Fix** while no app uses it. Select it again in your apps afterwards. |
| **Tracking, privacy or focus buttons do nothing** / "Permission denied" on `/dev/hidraw*` | ⚙ Setup → *Camera controls* → **Fix**, or unplug and replug the PIXY. |
| **Preview froze** | PixyDeck restarts a stalled stream automatically after three seconds; *Release camera* → *Resume preview* also works. |
| **Zoom slider is greyed out** | The camera is released to another app and the video mode ignores hardware zoom (above 1080p, or 1080p at 60 fps). Use the processed virtual camera for digital zoom. |
| **AI options are greyed out** | OpenCV/ONNX Runtime are missing. Packages install them; with `install.sh` run `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'` from the source folder. |
| **Low frame rate with AI background** | With `--gpu`, ONNX matting runs through CUDA when available. If inference still exceeds one frame, PixyDeck preserves output speed using the newest completed matte; the HUD shows *AI BACKGROUND EASED* and edges can trail fast motion slightly. Close other GPU-heavy programs, use 1080p, or use a green screen. |
| **`--gpu` still uses the CPU** | Run `nvidia-smi`, then `~/.local/share/pixydeck/venv/bin/pixydeck-gpu-benchmark`. The log names the CUDA device or the fallback reason. `PIXYDECK_DISABLE_CUDA=1` also forces CPU rendering. |
| **The camera tilts into its base** | Positions below −52° are blocked since 0.3.0; store the preset again. |
| **Warning about `libvdpau_nvidia.so`** | Qt probes optional hardware decoders; harmless if the preview works. |

## Collecting information for a bug report

```bash
pixydeck-cli status
systemctl status pixydeck-virtual-camera.service
journalctl -u pixydeck-virtual-camera.service -b
v4l2-ctl --list-devices
```

PixyDeck writes a log to `~/.local/state/pixydeck/pixydeck.log` (hover over the version number in the header to see the path); set `PIXYDECK_DEBUG=1` for more detail. Attach the log and the output above when you [open an issue](https://github.com/dalu951/pixydeck/issues), together with your distribution and kernel version. More operational details are in the [runbook](../RUNBOOK.md).
