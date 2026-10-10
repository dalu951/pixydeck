# Installation

[← README](../../README.md) · **English** · [Deutsch](../de/installation.md)

PixyDeck needs Linux with systemd, an EMEET PIXY (USB `328f:00c0`) and – for the virtual camera – the `v4l2loopback` kernel module.

## Ubuntu, Pop!_OS, Linux Mint (24.04 base)

1. Download `pixydeck_<version>_amd64.deb` (and optionally `SHA256SUMS` to verify it with `sha256sum -c --ignore-missing SHA256SUMS`) from the [releases page](https://github.com/dalu951/pixydeck/releases). The package is built for the **24.04** base (Python 3.12); on other versions use the install script below.
2. Install it with apt, which also pulls in FFmpeg, v4l-utils and `v4l2loopback-dkms`:

   ```bash
   sudo apt install ./pixydeck_*_amd64.deb
   ```

3. Start **EMEET PixyDeck** from the application menu.

The package bundles its Python libraries (Qt, OpenCV, ONNX Runtime) in `/opt/pixydeck`, so it does not interfere with system Python packages. It enables the `pixydeck-virtual-camera` service automatically.

## Arch Linux, CachyOS, EndeavourOS, Manjaro

Until the package is published in the AUR, build it from the release files:

```bash
mkdir pixydeck-pkg && cd pixydeck-pkg
curl -LO https://github.com/dalu951/pixydeck/releases/latest/download/PKGBUILD
curl -LO https://github.com/dalu951/pixydeck/releases/latest/download/pixydeck.install
makepkg -si
```

The package uses the official Arch packages (`pyside6`, `python-opencv`, `python-onnxruntime`, …). As usual on Arch, services are not enabled automatically: open **⚙ Setup** in PixyDeck once and click **Fix** next to *Virtual camera*, or run `sudo systemctl enable --now pixydeck-virtual-camera.service`.

If your kernel does not ship `v4l2loopback`, also install `v4l2loopback-dkms` and the headers for your kernel.

## Any other distribution (install script)

Install Python 3.10+, `python3-venv`, `v4l-utils`, FFmpeg and `v4l2loopback` (module + `v4l2loopback-ctl`) with your package manager, then:

```bash
git clone https://github.com/dalu951/pixydeck.git
cd pixydeck
./install.sh
```

The script installs PixyDeck into a private virtual environment in `~/.local/share/pixydeck`, adds the menu entry, and asks for `sudo` once to install the udev rules, the polkit action, the setup helper and the virtual-camera service. It replaces an earlier *emeet-pixy-control* installation and carries over its settings.

## First start

PixyDeck checks your system when it starts. If something is missing, the **⚙ Setup** dialog opens:

<img src="../media/setup.png" width="560" alt="Setup dialog">

| Check | What a fix does |
| --- | --- |
| Camera controls | applies the udev rule so your desktop session may talk to the PIXY |
| v4l2loopback kernel module | cannot be fixed automatically – install the package the dialog names |
| Virtual camera | loads the module and enables `pixydeck-virtual-camera.service` |
| Permission to feed the virtual camera | normally granted by udev; as a fallback adds you to the `video` group (log out and in afterwards) |

Every fix asks for your password in the system's polkit dialog and runs only the step shown – nothing else.

## Updating

- **.deb:** install the newer `.deb` the same way.
- **AUR:** your AUR helper updates it with the system.
- **Script:** `git pull && ./install.sh`.

## Uninstalling

| Installed via | Command |
| --- | --- |
| .deb | `sudo apt remove pixydeck` |
| AUR | `sudo pacman -R pixydeck` |
| install.sh | `./uninstall.sh` (add `--purge` to delete your settings too) |

Settings are stored in `~/.config/pixydeck/pixydeck.conf`. System packages such as FFmpeg or v4l2loopback are never removed.
