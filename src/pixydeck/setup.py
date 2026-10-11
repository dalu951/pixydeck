"""System checks and the first-run setup dialog.

PixyDeck needs a few things outside the app: HID permissions (udev), the
v4l2loopback virtual camera (kernel module + systemd unit) and write
access to that device. The dialog lists what is missing and fixes it via
``pkexec pixydeck-setup <action>``; the helper accepts only fixed actions,
so the polkit prompt authorizes exactly what is shown here.
"""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from . import APP_NAME, VIRTUAL_CAMERA_NAME, backend

UNIT = "pixydeck-virtual-camera.service"
# Packages install to /usr/lib, install.sh to /usr/local/lib.
HELPER_PATHS = (Path("/usr/lib/pixydeck/pixydeck-setup"), Path("/usr/local/lib/pixydeck/pixydeck-setup"))
UDEV_RULES = (Path("/usr/lib/udev/rules.d/70-pixydeck.rules"), Path("/etc/udev/rules.d/70-pixydeck.rules"))


@dataclass
class Check:
    key: str
    title: str
    ok: bool
    detail: str
    fix: str | None = None        # helper action that repairs it
    manual: str | None = None     # what to do when no automatic fix exists
    required: bool = True         # missing optional parts never pop up the dialog


def helper_path() -> Path | None:
    for path in HELPER_PATHS:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


# Exit code for "could not run at all"; pkexec itself uses 126/127 for a
# dismissed or failed authorization.
RUN_FAILED = -1
# Long enough to type a password at the polkit prompt.
FIX_TIMEOUT = 600


def _run(*args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, RUN_FAILED, "", f"{args[0]} timed out after {timeout:.0f} s")
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, RUN_FAILED, "", str(exc))


def camera_connected() -> bool:
    for device in Path("/sys/bus/usb/devices").glob("*"):
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if vendor == backend.VENDOR_ID.lower() and product == backend.PRODUCT_ID.lower():
            return True
    return False


def virtual_camera_device() -> str | None:
    return backend.find_virtual_camera()


def loopback_module_available() -> bool:
    return Path("/sys/module/v4l2loopback").exists() or _run("modinfo", "v4l2loopback").returncode == 0


def user_listed_in_video_group() -> bool:
    """True once the user was added to 'video' (even before re-login)."""
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
        return user in grp.getgrnam("video").gr_mem
    except KeyError:
        return False


def run_checks() -> list[Check]:
    checks: list[Check] = []

    connected = camera_connected()
    checks.append(Check(
        "camera", "EMEET PIXY connected", connected,
        "USB 328f:00c0 found" if connected else "Plug in the camera (USB 328f:00c0).",
        required=False))

    hid = backend.find_hidraw_device() if connected else None
    hid_ok = hid is not None and os.access(hid, os.R_OK | os.W_OK)
    rule = next((path for path in UDEV_RULES if path.exists()), None)
    if not connected:
        detail = "Checked once the camera is connected."
    elif hid_ok:
        detail = f"{hid} is accessible"
    elif rule is None:
        detail = "The PixyDeck udev rule is not installed."
    else:
        detail = f"{hid or 'The HID device'} is not accessible yet – the rule has to be applied."
    checks.append(Check(
        "hid", "Camera controls (tracking, privacy, focus …)", hid_ok or not connected, detail,
        fix="udev" if connected and rule is not None and not hid_ok else None,
        manual=None if rule is not None else "Reinstall PixyDeck (package or ./install.sh) to add the udev rule."))

    module = loopback_module_available()
    checks.append(Check(
        "module", "v4l2loopback kernel module", module,
        "available" if module else f"not installed for kernel {os.uname().release}",
        manual=None if module else
        "Install v4l2loopback (Ubuntu: v4l2loopback-dkms, Arch: v4l2loopback-dkms or your kernel's module); "
        "reboot first if the kernel was just updated."))

    device = virtual_camera_device()
    enabled = _run("systemctl", "is-enabled", UNIT).stdout.strip() == "enabled"
    if device:
        detail = f"{VIRTUAL_CAMERA_NAME} at {device}" + ("" if enabled else " (not started at boot)")
    else:
        detail = f"{VIRTUAL_CAMERA_NAME} does not exist yet."
    checks.append(Check(
        "virtual", "Virtual camera for Meet, Zoom, Teams, OBS", device is not None and enabled, detail,
        fix="virtual-camera" if module and (device is None or not enabled) else None))

    writable = device is not None and os.access(device, os.W_OK)
    listed = user_listed_in_video_group()
    group_ok = writable or device is None
    if writable:
        detail = "PixyDeck can send video to it."
    elif device is None:
        detail = "Checked once the virtual camera exists."
    elif listed:
        detail = "You were added to the 'video' group – log out and back in."
    else:
        detail = "Your user needs to be in the 'video' group."
    checks.append(Check(
        "group", "Permission to feed the virtual camera", group_ok, detail,
        fix="video-group" if not group_ok and not listed else None))

    ffmpeg = shutil.which("ffmpeg") is not None
    checks.append(Check(
        "ffmpeg", "FFmpeg", ffmpeg, "installed" if ffmpeg else "missing",
        manual=None if ffmpeg else "Install ffmpeg with your package manager."))

    from .vision import matting_available, vision_available
    ai = vision_available() and matting_available()
    checks.append(Check(
        "ai", "AI features (auto-framing, background)", ai,
        "OpenCV and ONNX Runtime available" if ai else "OpenCV or ONNX Runtime missing.",
        manual=None if ai else "Install the AI dependencies (package dependency, or pip install 'pixydeck[ai]').",
        required=False))
    return checks


def run_fix(action: str) -> tuple[bool, str]:
    helper = helper_path()
    if helper is None:
        return False, "The setup helper is not installed. Reinstall PixyDeck (package or ./install.sh)."
    if shutil.which("pkexec") is None:
        return False, f"pkexec is missing. Run manually: sudo {helper} {action}"
    result = _run("pkexec", str(helper), action, timeout=FIX_TIMEOUT)
    if result.returncode == 0:
        return True, "Done."
    if result.returncode in (126, 127):
        return False, "Authorization was cancelled."
    return False, (result.stderr or result.stdout).strip() or f"Failed with exit code {result.returncode}."


def needs_attention(checks: list[Check]) -> bool:
    return any(not check.ok and check.required for check in checks)


class SetupDialog(QDialog):
    """Lists the system checks; each problem gets a one-click fix where possible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – setup")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(QLabel(f"Set up {APP_NAME}", objectName="title"))
        intro = QLabel(
            "PixyDeck checks what your system needs for camera controls and the virtual camera. "
            "Fixes ask for your password in the system dialog and only run the step shown.")
        intro.setWordWrap(True)
        intro.setObjectName("subtle")
        layout.addWidget(intro)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        layout.addLayout(self.rows)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        recheck = QPushButton("Check again")
        recheck.clicked.connect(self.refresh)
        close = QPushButton("Close", objectName="primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(recheck)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for check in run_checks():
            self.rows.addWidget(self._row(check))

    def _row(self, check: Check) -> QWidget:
        frame = QFrame(objectName="card")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        icon = QLabel("✅" if check.ok else ("❌" if check.required else "⚠️"))
        icon.setFixedWidth(28)
        row.addWidget(icon, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(QLabel(f"<b>{check.title}</b>"))
        lines = [check.detail] + ([check.manual] if not check.ok and check.manual else [])
        detail = QLabel("<br>".join(lines))
        detail.setWordWrap(True)
        detail.setObjectName("subtle")
        text.addWidget(detail)
        row.addLayout(text, 1)
        if not check.ok and check.fix:
            button = QPushButton("Fix", objectName="primary")
            button.clicked.connect(lambda _=False, action=check.fix: self._fix(action))
            row.addWidget(button, 0, Qt.AlignVCenter)
        return frame

    def _fix(self, action: str) -> None:
        self.status.setText("Waiting for authorization…")
        self.repaint()
        ok, message = run_fix(action)
        if ok and action == "video-group":
            message = "Added to the 'video' group – log out and back in for it to take effect."
        self.status.setText(("✅ " if ok else "❌ ") + message)
        self.refresh()
