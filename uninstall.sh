#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    echo "Run ./uninstall.sh as your normal desktop user, not as root." >&2
    exit 1
fi

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
APP_HOME="$DATA_HOME/pixydeck"
DESKTOP_FILE="$DATA_HOME/applications/pixydeck.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/scalable/apps/pixydeck.svg"

sudo systemctl disable --now pixydeck-virtual-camera.service >/dev/null 2>&1 || true
sudo rm -f /etc/systemd/system/pixydeck-virtual-camera.service
sudo rm -f /etc/udev/rules.d/70-pixydeck.rules
sudo rm -f /usr/share/polkit-1/actions/io.github.dalu951.pixydeck.policy
sudo rm -rf /usr/local/lib/pixydeck
sudo systemctl daemon-reload
sudo udevadm control --reload-rules

rm -rf "$APP_HOME"
rm -f "$DESKTOP_FILE" "$ICON_FILE"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

if [[ ${1:-} == "--purge" ]]; then
    rm -rf "$HOME/.config/pixydeck"
    echo "Removed saved camera settings."
fi

echo "EMEET PixyDeck removed. System packages were left installed."
