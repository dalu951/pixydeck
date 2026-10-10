# Troubleshooting

[← README](../../README.md) · **English** · [Deutsch](../de/fehlerbehebung.md)

Start with **⚙ Setup** in PixyDeck – it checks permissions, the kernel module and the virtual camera and fixes most problems with one click.

| Symptom | Fix |
| --- | --- |
| **My meeting app does not see the camera** while PixyDeck shows a preview | Select **PixyDeck Virtual Camera** in the app, or click **Release camera** in PixyDeck and pick the physical EMEET PIXY. Only one program can read a webcam stream at a time. |
| **"PixyDeck Virtual Camera" is missing** | ⚙ Setup → *Virtual camera* → **Fix**. If the dialog says the `v4l2loopback` module is missing, install `v4l2loopback-dkms` (plus kernel headers). After a kernel update, reboot first. |
| **Tracking, privacy or focus buttons do nothing** / "Permission denied" on `/dev/hidraw*` | ⚙ Setup → *Camera controls* → **Fix**, or unplug and replug the PIXY. |
| **Preview froze** | PixyDeck restarts a stalled stream automatically after three seconds; *Release camera* → *Resume preview* also works. |
| **Zoom slider is greyed out** | The camera is released to another app and the video mode ignores hardware zoom (above 1080p, or 1080p at 60 fps). Use the processed virtual camera for digital zoom. |
| **AI options are greyed out** | OpenCV/ONNX Runtime are missing. Packages install them; with `install.sh` run `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'` from the source folder. |
| **Low frame rate with AI background** | AI matting needs about 30 ms per frame on the CPU. Use 1080p instead of 4K, or a green screen. |
| **The camera tilts into its base** | Positions below −52° are blocked since 0.3.0; store the preset again. |
| **Warning about `libvdpau_nvidia.so`** | Qt probes optional hardware decoders; harmless if the preview works. |

## Collecting information for a bug report

```bash
pixydeck-cli status
systemctl status pixydeck-virtual-camera.service
journalctl -u pixydeck-virtual-camera.service -b
v4l2-ctl --list-devices
```

Start `pixydeck` from a terminal to see Qt/FFmpeg messages, then [open an issue](https://github.com/dalu951/pixydeck/issues) with your distribution, kernel version and the output. More operational details are in the [runbook](../RUNBOOK.md).
