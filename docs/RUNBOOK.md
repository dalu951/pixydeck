# EMEET PixyDeck runbook

How to install, upgrade, check, troubleshoot and roll back PixyDeck on a desktop.

## What the installer puts on the system

<!-- AUTO-GENERATED:installed-files -->
Installed by `./install.sh`; the `.deb` and AUR packages use `/usr/lib/pixydeck` and `/usr/lib/{systemd,udev}` instead.

| Installed item | Location |
| --- | --- |
| `deploy/70-pixydeck.rules` | `/etc/udev/rules.d/70-pixydeck.rules` |
| `deploy/virtual-camera-device` | `/usr/local/lib/pixydeck/virtual-camera-device` |
| `deploy/pixydeck-setup` | `/usr/local/lib/pixydeck/pixydeck-setup` |
| `pixydeck-virtual-camera.service` (generated from a `deploy/*.in` template) | `/etc/systemd/system/pixydeck-virtual-camera.service` |
| `pixydeck.policy` (generated from a `deploy/*.in` template) | `/usr/share/polkit-1/actions/io.github.dalu951.pixydeck.policy` |
| systemd unit `pixydeck-virtual-camera.service` | enabled at boot |
| private virtualenv | `~/.local/share/pixydeck/venv` |
| desktop entry and icon | `~/.local/share/applications/pixydeck.desktop`, hicolor icon theme |
<!-- /AUTO-GENERATED:installed-files -->

Settings live in `~/.config/pixydeck/pixydeck.conf`; settings of an earlier emeet-pixy-control install are copied over on first start.

## Install and upgrade

| Installed via | Upgrade |
| --- | --- |
| `.deb` | `sudo apt install ./pixydeck_<new>_amd64.deb` |
| AUR / PKGBUILD | `makepkg -si` with the new release `PKGBUILD` (`yay -Syu` once it is in the AUR) |
| `install.sh` | `git pull && ./install.sh` |

The installer is idempotent: it rebuilds the private virtualenv package, reinstalls the system files, reloads udev and systemd and restarts the virtual-camera service. It replaces an existing emeet-pixy-control installation. Restart PixyDeck afterwards.

## Health checks

| Check | Command | Healthy result |
| --- | --- | --- |
| Camera detected | `lsusb \| grep 328f:00c0` | `EMEET PIXY` listed |
| Control path | `~/.local/share/pixydeck/venv/bin/pixydeck-cli status` | device, pan, tilt, zoom printed |
| HID access | `ls -l /dev/hidraw*` while PIXY is plugged in | the PIXY node is accessible to your user |
| Virtual camera service | `systemctl is-active pixydeck-virtual-camera.service` | `active` |
| Virtual camera device | `v4l2-ctl --list-devices` | `PixyDeck Virtual Camera` listed |
| AI features | Background tab status | no "needs the optional AI extra" hint |

## Common issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Device missing" for the virtual camera | `v4l2loopback` not available for the running kernel | install `v4l2loopback-dkms` + headers; after a kernel update, reboot; then `sudo systemctl restart pixydeck-virtual-camera.service` |
| Service fails with `203/EXEC` | outdated unit from emeet-pixy-control with `/usr/bin/modprobe` | run `./install.sh` again |
| HID controls "Permission denied" | udev rule not applied yet | replug the PIXY or log out/in; check `/etc/udev/rules.d/70-pixydeck.rules` |
| Meeting app sees no camera | PixyDeck preview owns the stream | select *PixyDeck Virtual Camera*, or *Release camera* in PixyDeck |
| AI options greyed out | OpenCV/ONNX Runtime missing | `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'` from the source folder |
| Low frame rate with AI background | AI matting is ~30 ms/frame on CPU | use 1080p instead of 4K, or the green-screen mode |
| Camera tilts into its base | old saved positions below -52° | positions are clamped automatically since 0.3.0; re-store the preset |

Logs: `~/.local/state/pixydeck/pixydeck.log` (rotating, 3 × 1 MB; `PIXYDECK_DEBUG=1` for debug level) contains app, Qt and FFmpeg messages and uncaught exceptions; service logs via `journalctl -u pixydeck-virtual-camera.service`.

## Rollback

To a previous PixyDeck version:

```bash
git checkout <tag-or-commit>
./install.sh
```

Remove PixyDeck completely (add `--purge` to delete settings):

```bash
./uninstall.sh
```

System packages (FFmpeg, v4l2loopback, …) are never removed by the scripts.
