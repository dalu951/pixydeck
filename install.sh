#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    echo "Run ./install.sh as your normal desktop user, not as root." >&2
    exit 1
fi

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
APP_HOME="$DATA_HOME/pixydeck"
VENV="$APP_HOME/venv"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_FILE="$DESKTOP_DIR/pixydeck.desktop"
ICON_FILE="$ICON_DIR/pixydeck.svg"

need=()
for cmd in python3 ffmpeg v4l2-ctl v4l2loopback-ctl modprobe systemctl; do
    command -v "$cmd" >/dev/null 2>&1 || need+=("$cmd")
done

if ((${#need[@]})); then
    echo "Missing required commands: ${need[*]}" >&2
    echo >&2
    if command -v pacman >/dev/null 2>&1; then
        echo "Arch/CachyOS prerequisites:" >&2
        echo "  sudo pacman -S --needed python python-pip v4l-utils ffmpeg v4l2loopback-utils" >&2
        echo "On vanilla Arch, install the headers matching your kernel if DKMS needs them." >&2
    elif command -v apt >/dev/null 2>&1; then
        echo "Debian/Ubuntu prerequisites:" >&2
        # shellcheck disable=SC2016  # printed for the user to run
        echo '  sudo apt install python3 python3-venv v4l-utils ffmpeg v4l2loopback-utils v4l2loopback-dkms linux-headers-$(uname -r)' >&2
    fi
    exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Python venv support is required (often package python3-venv)." >&2
    exit 1
fi

migrate_from_emeet_pixy_control() {
    # PixyDeck grew out of emeet-pixy-control; replace that install cleanly.
    # Saved settings are copied by the application itself on first start.
    local old_home="$DATA_HOME/emeet-pixy-control"
    local old_unit=emeet-pixy-virtual-camera.service
    if [[ -e /etc/systemd/system/$old_unit ]]; then
        echo "Removing the previous emeet-pixy-control system integration..."
        sudo systemctl disable --now "$old_unit" >/dev/null 2>&1 || true
        sudo rm -f "/etc/systemd/system/$old_unit"
        sudo systemctl reset-failed "$old_unit" >/dev/null 2>&1 || true
        sudo rm -rf /usr/local/lib/emeet-pixy-control
    fi
    sudo rm -f /etc/udev/rules.d/70-emeet-pixy.rules
    rm -f "$DESKTOP_DIR/emeet-pixy-control.desktop" "$ICON_DIR/emeet-pixy-control.svg"
    [[ -d "$old_home" ]] && rm -rf "$old_home"
    return 0
}

mkdir -p "$APP_HOME" "$DESKTOP_DIR" "$ICON_DIR"
migrate_from_emeet_pixy_control

if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" -m pip install --upgrade "${ROOT}[ai]"; then
    echo "AI extra (OpenCV/ONNX Runtime) could not be installed; continuing without AI features." >&2
    "$VENV/bin/python" -m pip install --upgrade "$ROOT"
fi

install -m 0644 "$ROOT/assets/pixydeck.svg" "$ICON_FILE"

exec_path="$VENV/bin/pixydeck"
sed "s#@EXEC@#$exec_path#g" "$ROOT/deploy/pixydeck.desktop.in" > "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"

LIBDIR=/usr/local/lib/pixydeck
POLICY=/usr/share/polkit-1/actions/io.github.dalu951.pixydeck.policy
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
sed "s#@LIBDIR@#$LIBDIR#g" "$ROOT/deploy/pixydeck-virtual-camera.service.in" > "$TMP/pixydeck-virtual-camera.service"
sed "s#@HELPER@#$LIBDIR/pixydeck-setup#g" "$ROOT/deploy/io.github.dalu951.pixydeck.policy.in" > "$TMP/pixydeck.policy"

sudo install -m 0644 "$ROOT/deploy/70-pixydeck.rules" /etc/udev/rules.d/70-pixydeck.rules
sudo install -d -m 0755 "$LIBDIR"
sudo install -m 0755 "$ROOT/deploy/virtual-camera-device" "$LIBDIR/virtual-camera-device"
sudo install -m 0755 "$ROOT/deploy/pixydeck-setup" "$LIBDIR/pixydeck-setup"
sudo install -m 0644 "$TMP/pixydeck-virtual-camera.service" /etc/systemd/system/pixydeck-virtual-camera.service
sudo install -m 0644 "$TMP/pixydeck.policy" "$POLICY"

sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw || true
sudo systemctl daemon-reload
sudo systemctl enable pixydeck-virtual-camera.service

if [[ -d "/lib/modules/$(uname -r)" ]] && modinfo v4l2loopback >/dev/null 2>&1; then
    if ! sudo systemctl restart pixydeck-virtual-camera.service; then
        echo "Warning: virtual-camera service could not start. Check:" >&2
        echo "  systemctl status pixydeck-virtual-camera.service" >&2
    fi
else
    echo "Warning: v4l2loopback is not available for the currently running kernel." >&2
    echo "The service is enabled and should start after you install the module or reboot into the updated kernel." >&2
fi

if getent group video >/dev/null 2>&1 && ! id -nG "$USER" | tr ' ' '\n' | grep -qx video; then
    sudo usermod -aG video "$USER"
    echo "Added $USER to the video group. Log out and back in before using Virtual Camera mode." >&2
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

cat <<MSG

EMEET PixyDeck installed.

Launch it from your application menu: EMEET PixyDeck
CLI: $VENV/bin/pixydeck-cli
In Meet/Zoom/Teams/OBS select: PixyDeck Virtual Camera

If HID controls are denied, unplug/replug the PIXY once (or log out/in).
Virtual camera service status:
  systemctl status pixydeck-virtual-camera.service
MSG
