#!/usr/bin/env python3
"""Low-level EMEET PIXY controls for Linux.

This is an independently written implementation of publicly documented and
community-reverse-engineered UVC/HID protocol facts for the EMEET PIXY
(USB 328f:00c0). See CREDITS.md for provenance.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import select
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable

VENDOR_ID = "328F"
PRODUCT_ID = "00C0"
HID_ID = f"0003:0000{VENDOR_ID}:000000{PRODUCT_ID}"

PAN_MIN = -540000
PAN_MAX = 540000
# V4L2 advertises -90..+90 deg tilt, but below -52 deg the PIXY only points
# into its own base and parks in the privacy/rest position.
TILT_MIN = -52 * 3600
TILT_MAX = 324000
ZOOM_MIN = 100
ZOOM_MAX = 150
DEGREE_UNIT = 3600
STEP_DEG = 2
STEP = STEP_DEG * DEGREE_UNIT

V4L2_CTL = shutil.which("v4l2-ctl") or "/usr/bin/v4l2-ctl"

# struct v4l2_control { __u32 id; __s32 value; } -> _IOWR('V', 27/28, 8 bytes)
VIDIOC_G_CTRL = 0xC008561B
VIDIOC_S_CTRL = 0xC008561C

CONTROL_IDS = {
    "brightness": 0x00980900,
    "contrast": 0x00980901,
    "saturation": 0x00980902,
    "hue": 0x00980903,
    "white_balance_automatic": 0x0098090C,
    "gamma": 0x00980910,
    "gain": 0x00980913,
    "power_line_frequency": 0x00980918,
    "white_balance_temperature": 0x0098091A,
    "sharpness": 0x0098091B,
    "backlight_compensation": 0x0098091C,
    "auto_exposure": 0x009A0901,
    "exposure_time_absolute": 0x009A0902,
    "pan_absolute": 0x009A0908,
    "tilt_absolute": 0x009A0909,
    "focus_absolute": 0x009A090A,
    "focus_automatic_continuous": 0x009A090C,
    "zoom_absolute": 0x009A090D,
}

# struct v4l2_queryctrl: id, type, name[32], min, max, step, default, flags,
# reserved[2] -> 68 bytes, _IOWR('V', 36, ...)
VIDIOC_QUERYCTRL = 0xC0445624
QUERYCTRL_FORMAT = "II32siiiiI2I"
V4L2_CTRL_FLAG_DISABLED = 0x0001
V4L2_CTRL_FLAG_INACTIVE = 0x0010

# auto_exposure menu values
EXPOSURE_MANUAL = 1
EXPOSURE_APERTURE_PRIORITY = 3


class PixyError(RuntimeError):
    """Raised when the PIXY cannot be controlled."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


VIDEO_SYSFS = Path("/sys/class/video4linux")
HIDRAW_SYSFS = Path("/sys/class/hidraw")


def video_sort_key(path: Path) -> int:
    suffix = path.name.removeprefix("video")
    return int(suffix) if suffix.isdigit() else 9999


def video_nodes(root: Path = VIDEO_SYSFS) -> list[tuple[str, str]]:
    """All V4L2 nodes as (``/dev/videoN``, device name), in numeric order."""
    nodes = []
    for dev_dir in sorted(root.glob("video*"), key=video_sort_key):
        try:
            nodes.append((f"/dev/{dev_dir.name}", (dev_dir / "name").read_text().strip()))
        except OSError:
            continue  # node vanished while scanning (unplug)
    return nodes


def find_video_by_name(name: str, root: Path = VIDEO_SYSFS) -> str | None:
    """Locate a node by its exact name instead of a fixed /dev/video number."""
    return next((device for device, node_name in video_nodes(root) if node_name == name), None)


def is_virtual_camera(name: str) -> bool:
    """True for PixyDeck's own v4l2loopback device, under any of its names."""
    from . import LEGACY_VIRTUAL_CAMERA_NAMES, VIRTUAL_CAMERA_NAME
    upper = name.upper()
    return (name in (VIRTUAL_CAMERA_NAME, *LEGACY_VIRTUAL_CAMERA_NAMES)
            or "PIXYDECK" in upper or "VIRTUAL" in upper)


def find_virtual_camera(root: Path = VIDEO_SYSFS) -> str | None:
    """PixyDeck's virtual camera node, preferring the current name."""
    from . import LEGACY_VIRTUAL_CAMERA_NAMES, VIRTUAL_CAMERA_NAME
    for name in (VIRTUAL_CAMERA_NAME, *LEGACY_VIRTUAL_CAMERA_NAMES):
        device = find_video_by_name(name, root)
        if device is not None:
            return device
    return None


def find_video_device(root: Path = VIDEO_SYSFS) -> str | None:
    """Return the physical PIXY video node that exposes PTZ controls."""
    for device, name in video_nodes(root):
        if is_virtual_camera(name):
            continue
        name = name.upper()
        if "EMEET" not in name or "PIXY" not in name:
            continue
        # Only the capture node answers PTZ control ioctls; the metadata
        # node returns ENOTTY.
        try:
            _ioctl_get(device, CONTROL_IDS["pan_absolute"])
        except OSError:
            continue
        return device
    return None


def find_hidraw_device(root: Path = HIDRAW_SYSFS) -> str | None:
    """Return the PIXY HID node by exact USB HID identity."""
    if not root.exists():
        return None
    for dev_dir in sorted(root.glob("hidraw*")):
        uevent = dev_dir / "device/uevent"
        try:
            text = uevent.read_text().upper()
        except OSError:
            continue
        if HID_ID in text or (
            "HID_NAME=EMEET EMEET PIXY" in text
            and VENDOR_ID in text
            and PRODUCT_ID in text
        ):
            return f"/dev/{dev_dir.name}"
    return None


def _ioctl_get(device: str, control_id: int, fd: int | None = None) -> int:
    own = fd is None
    if own:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    try:
        buf = bytearray(struct.pack("Ii", control_id, 0))
        fcntl.ioctl(fd, VIDIOC_G_CTRL, buf)
        return struct.unpack("Ii", buf)[1]
    finally:
        if own:
            os.close(fd)


def _ioctl_set(device: str, control_id: int, value: int, fd: int | None = None) -> None:
    own = fd is None
    if own:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, VIDIOC_S_CTRL, bytearray(struct.pack("Ii", control_id, value)))
    finally:
        if own:
            os.close(fd)


def query_control(device: str, control: str, fd: int | None = None) -> dict | None:
    """Return min/max/step/default/inactive for a control, or None."""
    own = fd is None
    try:
        if own:
            fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
        buf = bytearray(struct.pack(QUERYCTRL_FORMAT, CONTROL_IDS[control], 0, b"", 0, 0, 0, 0, 0, 0, 0))
        fcntl.ioctl(fd, VIDIOC_QUERYCTRL, buf)
    except (OSError, KeyError):
        return None
    finally:
        if own and fd is not None:
            os.close(fd)
    _, _, _, minimum, maximum, step, default, flags, _, _ = struct.unpack(QUERYCTRL_FORMAT, buf)
    if flags & V4L2_CTRL_FLAG_DISABLED:
        return None
    return {
        "min": minimum,
        "max": maximum,
        "step": step,
        "default": default,
        "inactive": bool(flags & V4L2_CTRL_FLAG_INACTIVE),
    }


def camera_users(devices: Iterable[str], exclude_pids: Iterable[int] = ()) -> list[tuple[int, str]]:
    """Return (pid, command) of processes that currently hold a device open.

    Used to notice that Zoom/Teams/Meet started using the camera. Only
    processes owned by the current user are visible, which is exactly the
    set we care about.
    """
    wanted = {os.path.realpath(device) for device in devices if os.path.exists(device)}
    if not wanted:
        return []
    excluded = set(exclude_pids)
    uid = os.getuid()
    users = []
    with os.scandir("/proc") as entries:
        for proc in entries:
            if not proc.name.isdigit() or int(proc.name) in excluded:
                continue
            try:
                # Other users' fd tables are unreadable anyway; skip them early.
                if proc.stat().st_uid != uid:
                    continue
                with os.scandir(f"/proc/{proc.name}/fd") as fds:
                    # readlink is far cheaper than stat() on every descriptor.
                    if any(os.readlink(fd.path) in wanted for fd in fds):
                        command = Path(f"/proc/{proc.name}/comm").read_text().strip()
                        users.append((int(proc.name), command))
            except OSError:
                continue  # process exited or fd closed while scanning
    return users


def get_control(device: str, control: str) -> int:
    control_id = CONTROL_IDS.get(control)
    if control_id is not None:
        try:
            return _ioctl_get(device, control_id)
        except OSError:
            pass  # fall back to v4l2-ctl for a better error message
    result = subprocess.run(
        [V4L2_CTL, "-d", device, f"--get-ctrl={control}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PixyError(result.stderr.strip() or f"Unable to read {control}")
    if ":" not in result.stdout:
        raise PixyError(f"Unexpected v4l2-ctl output for {control}")
    return int(result.stdout.split(":", 1)[1].strip())


def set_control(device: str, control: str, value: int) -> None:
    control_id = CONTROL_IDS.get(control)
    if control_id is not None:
        try:
            _ioctl_set(device, control_id, value)
            return
        except OSError:
            pass
    result = subprocess.run(
        [V4L2_CTL, "-d", device, f"--set-ctrl={control}={value}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PixyError(result.stderr.strip() or f"Unable to set {control}")


# Report heads PixyDeck must never send, whatever a caller asks for: power
# (reboot, auto shutdown), factory reset, device identity, firmware/RTC and
# SD card. Device groups are matched on ``head[1] & 0x1F`` like the camera's
# own router does (the motor MCU answers as 0x63).
FORBIDDEN_GROUPS = {0x00, 0x09, 0x0A}
FORBIDDEN_HEADS = {
    (0x09, 0x01, 0x00, 0x05),  # factory reset
    (0x09, 0x01, 0x00, 0x08),  # factory reset as named by the unshifted table
    (0x09, 0x01, 0x00, 0x0D),  # set device version
    (0x09, 0x01, 0x00, 0x0F),  # set device alias
}


def is_forbidden_head(data: bytes) -> bool:
    if len(data) < 4:
        return False
    if data[0] == 0x07:  # legacy V1 commands are not used by PixyDeck
        return True
    head = (data[0], data[1] & 0x1F, data[2], data[3])
    return head[1] in FORBIDDEN_GROUPS or head in FORBIDDEN_HEADS


def build_hid_report(payload: Iterable[int]) -> bytes:
    data = bytes(payload)
    if len(data) > 32:
        raise PixyError("HID report is longer than 32 bytes")
    if is_forbidden_head(data):
        raise PixyError(f"Refusing HID command {data[:4].hex(' ')}")
    return data + bytes(32 - len(data))


def hid_frame(head: Iterable[int], body: Iterable[int] = ()) -> list[int]:
    """A V2 report: 4-byte head, then ``00 len 00 len`` and the payload.

    A bare head (no body) is a query; replies use the same framing.
    """
    head, body = list(head), list(body)
    if len(head) != 4:
        raise PixyError("HID head must be 4 bytes")
    if not body:
        return head
    if len(body) > 24:
        raise PixyError("HID payload is longer than 24 bytes")
    return [*head, 0x00, len(body), 0x00, len(body), *body]


def reply_payload(reply: bytes | None, minimum: int = 1) -> bytes | None:
    """Payload of a V2 reply (from offset 8), or None if it is too short.

    The length bytes 5 and 7 are trusted only up to the bytes actually read.
    """
    if reply is None or len(reply) < 8 + minimum:
        return None
    length = min(reply[5], len(reply) - 8)
    if length < minimum:
        return None
    return bytes(reply[8:8 + length])


def send_hid_report(device: str, payload: Iterable[int]) -> None:
    report = build_hid_report(payload)
    try:
        with open(device, "wb", buffering=0) as hid:
            hid.write(report)
    except PermissionError as exc:
        raise PixyError(
            f"Permission denied writing to {device}. Install the supplied udev rule."
        ) from exc
    except OSError as exc:
        raise PixyError(f"Unable to write to {device}: {exc}") from exc


# V2 report heads, verified against a PIXY (328f:00c0) by sending each query
# and checking the echoed head and payload. The command names come from the
# official app's command table; note that in the community-extracted table
# (github.com/LarsArtmann/emeet-pixyd, docs/hid-protocol-official-map.md)
# every name sits one row below the head that carries it on the wire.
HEAD_SET_DEVICE_MODE = (0x09, 0x01, 0x01, 0x00)     # [mode]
HEAD_GET_DEVICE_MODE = (0x09, 0x01, 0x01, 0x01)
HEAD_SET_PRIVACY_TRIGGER = (0x09, 0x02, 0x01, 0x00)  # [seconds:u32 LE]
HEAD_GET_PRIVACY_TRIGGER = (0x09, 0x02, 0x01, 0x01)
HEAD_GET_MOTOR_POS = (0x09, 0x03, 0x01, 0x01)        # [axis] -> [axis][target:f32][actual:f32]
HEAD_SET_MOTOR_SPEED = (0x09, 0x03, 0x01, 0x02)      # [axis][deg/s:f32]
HEAD_GET_MOTOR_SPEED = (0x09, 0x03, 0x01, 0x03)      # [axis] -> [axis][deg/s:f32][limit:f32]
HEAD_SET_POWER_ON_POS = (0x09, 0x03, 0x01, 0x13)     # [mode][f32 x3]; mode 1 stores the current position
HEAD_GET_POWER_ON_POS = (0x09, 0x03, 0x01, 0x14)     # -> [mode][pan:f32][tilt:f32][zoom:f32]
HEAD_SET_FOCUS_MODE = (0x09, 0x04, 0x00, 0x01)       # [mode][x][y][w][h]
HEAD_GET_FOCUS_MODE = (0x09, 0x04, 0x00, 0x02)
HEAD_SET_METER_MODE = (0x09, 0x04, 0x00, 0x03)       # same body as focus
HEAD_GET_FEATURE = (0x09, 0x04, 0x00, 0x07)          # [feature] -> [feature][on]
HEAD_SET_FEATURE = (0x09, 0x04, 0x00, 0x08)          # [feature][on]
HEAD_SET_TARGET_TRACK = (0x09, 0x04, 0x01, 0x00)     # [mode][f32 x5]
HEAD_GET_TARGET_TRACK = (0x09, 0x04, 0x01, 0x01)
HEAD_SET_GESTURE = (0x09, 0x04, 0x02, 0x00)          # [type][on]
HEAD_GET_GESTURE = (0x09, 0x04, 0x02, 0x01)          # [type] -> [type][on]
HEAD_SET_AUDIO = (0x09, 0x05, 0x00, 0x03)            # [mode]
HEAD_GET_AUDIO = (0x09, 0x05, 0x00, 0x04)
# Lock heads: (set, get), payload [on].
LOCK_HEADS = {
    "white-balance": ((0x09, 0x04, 0x00, 0x09), (0x09, 0x04, 0x00, 0x0A)),
    "exposure": ((0x09, 0x04, 0x00, 0x0B), (0x09, 0x04, 0x00, 0x0C)),
    "focus": ((0x09, 0x04, 0x00, 0x0D), (0x09, 0x04, 0x00, 0x0E)),
}
GESTURE_TYPE = 0x02
MOTOR_AXES = {"pan": 0x01, "tilt": 0x02}
# The firmware stores any speed; below ~1 deg/s a move takes minutes, and
# above ~240 deg/s the motor does not get noticeably faster.
MOTOR_SPEED_MIN = 1
MOTOR_SPEED_MAX = 240
MOTOR_SPEED_DEFAULT = 60
# Smart-composition target; 3 (full body) is rejected by the PIXY firmware.
TARGET_TRACK_MODES = {"auto": 0x00, "face": 0x01, "upper-body": 0x02}


def set_tracking(device: str, mode: int) -> None:
    if mode not in (0x00, 0x01, 0x02):
        raise PixyError("Invalid tracking mode")
    send_hid_report(device, hid_frame(HEAD_SET_DEVICE_MODE, [mode]))
    time.sleep(0.2)
    send_hid_report(device, HEAD_GET_DEVICE_MODE)


def set_gesture(device: str, enabled: bool) -> None:
    value = 0x01 if enabled else 0x00
    send_hid_report(device, hid_frame(HEAD_SET_GESTURE, [GESTURE_TYPE, value]))
    time.sleep(0.2)
    send_hid_report(device, hid_frame(HEAD_GET_GESTURE, [GESTURE_TYPE]))


def set_audio_mode(device: str, mode: int) -> None:
    if mode not in (0x01, 0x02, 0x03):
        raise PixyError("Invalid audio mode")
    send_hid_report(device, hid_frame(HEAD_SET_AUDIO, [mode]))
    time.sleep(0.2)
    send_hid_report(device, HEAD_GET_AUDIO)


def set_auto_privacy(device: str, seconds: int) -> None:
    seconds = clamp(seconds, 0, 255)
    send_hid_report(device, hid_frame(HEAD_SET_PRIVACY_TRIGGER, [seconds, 0, 0, 0]))
    time.sleep(0.2)
    send_hid_report(device, HEAD_GET_PRIVACY_TRIGGER)

TRACKING_MODES = {"idle": 0x00, "track": 0x01, "privacy": 0x02}
AUDIO_MODES = {"nc": 0x01, "live": 0x02, "org": 0x03}
FLICKER_MODES = {"off": 0, "50": 1, "60": 2}
# Focus/metering: where the PIXY's AI lens points the autofocus.
FOCUS_MODES = {"center": 0x00, "face": 0x01, "area": 0x02}
FEATURES = {"hflip": 0x01, "vflip": 0x02, "autorotate": 0x04}


HID_TIMEOUT = 0.5  # seconds to wait for a reply


def hid_query(device: str, payload: Iterable[int], timeout: float | None = None) -> bytes | None:
    """Send a report and return the camera's reply with the same head.

    The PIXY also pushes unsolicited state reports, so stale input is
    drained first and replies are matched on group/command. Responses may
    set high bits in the group byte.
    """
    data = list(payload)
    try:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    except OSError as exc:
        raise PixyError(f"Unable to open {device}: {exc}") from exc
    try:
        # Bounded: a node that reports readable but returns nothing (EOF
        # after an unplug) must not spin here forever.
        for _ in range(64):
            if not select.select([fd], [], [], 0)[0]:
                break
            try:
                if not os.read(fd, 64):
                    break
            except BlockingIOError:
                break
        os.write(fd, build_hid_report(data))
        deadline = time.monotonic() + (HID_TIMEOUT if timeout is None else timeout)
        while (remaining := deadline - time.monotonic()) > 0:
            if not select.select([fd], [], [], remaining)[0]:
                break
            try:
                reply = os.read(fd, 64)
            except BlockingIOError:
                continue
            if len(reply) >= 9 and reply[1] & 0x1F == data[1] & 0x1F and reply[2:4] == bytes(data[2:4]):
                return reply
    except OSError as exc:
        raise PixyError(f"HID query failed: {exc}") from exc
    finally:
        os.close(fd)
    return None


def set_focus_mode(device: str, mode: int, x: int = 0, y: int = 0) -> None:
    """Focus/metering mode; x/y (0..127, top-left origin) for the selected area."""
    body = [mode, clamp(x, 0, 0x7F), clamp(y, 0, 0x7F), 0x7F, 0x7F]
    send_hid_report(device, hid_frame(HEAD_SET_FOCUS_MODE, body))
    send_hid_report(device, hid_frame(HEAD_SET_METER_MODE, body))
    send_hid_report(device, HEAD_GET_FOCUS_MODE)


def set_feature(device: str, feature: int, enabled: bool) -> None:
    send_hid_report(device, hid_frame(HEAD_SET_FEATURE, [feature, int(enabled)]))
    time.sleep(0.2)
    send_hid_report(device, hid_frame(HEAD_GET_FEATURE, [feature]))


def _float(value: float) -> list[int]:
    return list(struct.pack("<f", value))


def motor_axis(axis: str) -> int:
    if axis not in MOTOR_AXES:
        raise PixyError("Motor axis must be " + " or ".join(MOTOR_AXES))
    return MOTOR_AXES[axis]


def get_motor_speed(device: str, axis: str) -> float | None:
    """Pan or tilt speed in degrees per second."""
    code = motor_axis(axis)
    payload = reply_payload(hid_query(device, hid_frame(HEAD_GET_MOTOR_SPEED, [code])), 5)
    if payload is None or payload[0] != code:
        return None
    return struct.unpack_from("<f", payload, 1)[0]


def set_motor_speed(device: str, axis: str, degrees_per_second: float) -> float:
    speed = float(min(max(degrees_per_second, MOTOR_SPEED_MIN), MOTOR_SPEED_MAX))
    send_hid_report(device, hid_frame(HEAD_SET_MOTOR_SPEED, [motor_axis(axis), *_float(speed)]))
    return speed


def get_motor_position(device: str, axis: str) -> tuple[float, float] | None:
    """(target, actual) angle in degrees as the motor controller sees it."""
    code = motor_axis(axis)
    payload = reply_payload(hid_query(device, hid_frame(HEAD_GET_MOTOR_POS, [code])), 9)
    if payload is None or payload[0] != code:
        return None
    return struct.unpack_from("<ff", payload, 1)


def set_target_track(device: str, mode: int) -> None:
    if mode not in TARGET_TRACK_MODES.values():
        raise PixyError("Invalid tracking target")
    send_hid_report(device, hid_frame(HEAD_SET_TARGET_TRACK, [mode, *bytes(20)]))


def get_target_track(device: str) -> str | None:
    payload = reply_payload(hid_query(device, HEAD_GET_TARGET_TRACK))
    names = {code: name for name, code in TARGET_TRACK_MODES.items()}
    return names.get(payload[0]) if payload is not None else None


def save_power_on_position(device: str) -> None:
    """Make the camera's current pan/tilt its own power-on position.

    The camera stores where it is now; the coordinates in the request are
    ignored, so the caller moves the camera first.
    """
    send_hid_report(device, hid_frame(HEAD_SET_POWER_ON_POS, [0x01, *bytes(12)]))


def get_power_on_position(device: str) -> tuple[float, float] | None:
    """Stored power-on (pan, tilt) in degrees, or None if not stored."""
    payload = reply_payload(hid_query(device, HEAD_GET_POWER_ON_POS), 13)
    if payload is None or payload[0] != 0x01:
        return None
    return struct.unpack_from("<ff", payload, 1)


def set_lock(device: str, name: str, locked: bool) -> None:
    if name not in LOCK_HEADS:
        raise PixyError("Lock must be " + ", ".join(LOCK_HEADS))
    send_hid_report(device, hid_frame(LOCK_HEADS[name][0], [int(locked)]))


def get_lock(device: str, name: str) -> bool | None:
    payload = reply_payload(hid_query(device, LOCK_HEADS[name][1]))
    return payload[0] == 1 if payload is not None else None


def read_state(device: str) -> dict:
    """Current on-board state as reported by the camera itself.

    Keys are omitted when the camera does not answer or reports a value we
    cannot decode: tracking readback is often 0x03 for both idle and
    tracking, only privacy (0x02) is reliable.
    """
    state: dict = {}
    payload = reply_payload(hid_query(device, HEAD_GET_DEVICE_MODE))
    if payload is not None and payload[0] in (0, 1, 2):
        state["tracking"] = {0: "idle", 1: "track", 2: "privacy"}[payload[0]]
    payload = reply_payload(hid_query(device, HEAD_GET_AUDIO))
    if payload is not None and payload[0] in (1, 2, 3):
        state["audio"] = {1: "nc", 2: "live", 3: "org"}[payload[0]]
    payload = reply_payload(hid_query(device, hid_frame(HEAD_GET_GESTURE, [GESTURE_TYPE])), 2)
    if payload is not None:
        state["gesture"] = payload[1] == 1
    payload = reply_payload(hid_query(device, HEAD_GET_FOCUS_MODE))
    if payload is not None and payload[0] in (0, 1, 2):
        state["focus"] = {0: "center", 1: "face", 2: "area"}[payload[0]]
    for name, feature in FEATURES.items():
        payload = reply_payload(hid_query(device, hid_frame(HEAD_GET_FEATURE, [feature])), 2)
        if payload is not None and payload[0] == feature:
            state[name] = payload[1] == 1
    target = get_target_track(device)
    if target is not None:
        state["target"] = target
    for axis in MOTOR_AXES:
        speed = get_motor_speed(device, axis)
        if speed is not None:
            state[f"{axis}-speed"] = round(speed)
    for name in LOCK_HEADS:
        locked = get_lock(device, name)
        if locked is not None:
            state[f"{name}-lock"] = locked
    return state


def status_text(video_device: str) -> str:
    pan = get_control(video_device, "pan_absolute")
    tilt = get_control(video_device, "tilt_absolute")
    zoom = get_control(video_device, "zoom_absolute")
    return (
        f"Device: {video_device}\n"
        f"pan:  {round(pan / DEGREE_UNIT)} deg\n"
        f"tilt: {round(tilt / DEGREE_UNIT)} deg\n"
        f"zoom: {zoom}"
    )


class PixyController:
    """Long-lived, thread-safe PIXY handle for the GUI.

    Device paths and the video file descriptor are cached so a control
    change is a single ioctl instead of a device scan plus v4l2-ctl calls.
    On failure the cache is dropped and the device rediscovered once, which
    covers unplug/replug.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._video: str | None = None
        self._video_fd: int | None = None
        self._hid: str | None = None

    def close(self) -> None:
        with self._lock:
            self._drop_video()

    def _drop_video(self) -> None:
        if self._video_fd is not None:
            try:
                os.close(self._video_fd)
            except OSError:
                pass
        self._video_fd = None
        self._video = None

    def _ensure_video(self) -> tuple[str, int]:
        if self._video_fd is None:
            device = find_video_device()
            if device is None:
                raise PixyError("EMEET PIXY video device not found")
            try:
                self._video_fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
            except OSError as exc:
                raise PixyError(f"Unable to open {device}: {exc}") from exc
            self._video = device
        return self._video, self._video_fd

    def video_device(self) -> str | None:
        with self._lock:
            try:
                return self._ensure_video()[0]
            except PixyError:
                return None

    def hid_device(self) -> str:
        with self._lock:
            if self._hid is None or not os.path.exists(self._hid):
                self._hid = find_hidraw_device()
            if self._hid is None:
                raise PixyError("EMEET PIXY HID device not found")
            return self._hid

    def get(self, control: str) -> int:
        return self._video_call(control, None)

    def set(self, control: str, value: int) -> None:
        self._video_call(control, value)

    def _video_call(self, control: str, value: int | None) -> int:
        control_id = CONTROL_IDS[control]
        with self._lock:
            for attempt in (0, 1):
                device, fd = self._ensure_video()
                try:
                    if value is None:
                        return _ioctl_get(device, control_id, fd)
                    _ioctl_set(device, control_id, value, fd)
                    return value
                except OSError as exc:
                    self._drop_video()
                    if attempt:
                        raise PixyError(f"{control}: {exc.strerror or exc}") from exc
        raise AssertionError("unreachable")

    def query(self, control: str) -> dict | None:
        with self._lock:
            try:
                device, fd = self._ensure_video()
            except PixyError:
                return None
            return query_control(device, control, fd)

    def position(self) -> tuple[int, int, int]:
        """Return (pan degrees, tilt degrees, zoom)."""
        return (
            round(self.get("pan_absolute") / DEGREE_UNIT),
            round(self.get("tilt_absolute") / DEGREE_UNIT),
            self.get("zoom_absolute"),
        )

    def move_to(self, pan_deg: int | None = None, tilt_deg: int | None = None) -> None:
        if pan_deg is not None:
            self.set("pan_absolute", clamp(pan_deg * DEGREE_UNIT, PAN_MIN, PAN_MAX))
        if tilt_deg is not None:
            self.set("tilt_absolute", clamp(tilt_deg * DEGREE_UNIT, TILT_MIN, TILT_MAX))

    def set_zoom(self, zoom: int) -> None:
        self.set("zoom_absolute", clamp(zoom, ZOOM_MIN, ZOOM_MAX))

    def tracking(self, mode: str) -> None:
        set_tracking(self.hid_device(), TRACKING_MODES[mode])

    def gesture(self, enabled: bool) -> None:
        set_gesture(self.hid_device(), enabled)

    def audio(self, mode: str) -> None:
        set_audio_mode(self.hid_device(), AUDIO_MODES[mode])

    def flicker(self, mode: str) -> None:
        self.set("power_line_frequency", FLICKER_MODES[mode])

    def focus_mode(self, mode: str, x: float = 0.5, y: float = 0.5) -> None:
        """``x``/``y`` are normalized frame coordinates for the ``area`` mode."""
        point = (round(x * 0x7F), round(y * 0x7F)) if mode == "area" else (0, 0)
        set_focus_mode(self.hid_device(), FOCUS_MODES[mode], *point)

    def feature(self, name: str, enabled: bool) -> None:
        set_feature(self.hid_device(), FEATURES[name], enabled)

    def motor_speed(self, axis: str, degrees_per_second: float) -> float:
        return set_motor_speed(self.hid_device(), axis, degrees_per_second)

    def target_track(self, mode: str) -> None:
        set_target_track(self.hid_device(), TARGET_TRACK_MODES[mode])

    def lock(self, name: str, locked: bool) -> None:
        set_lock(self.hid_device(), name, locked)

    def save_power_on_position(self) -> None:
        save_power_on_position(self.hid_device())

    def power_on_position(self) -> tuple[float, float] | None:
        return get_power_on_position(self.hid_device())

    def state(self) -> dict:
        return read_state(self.hid_device())



def execute(command: str, value: str | None = None) -> str:
    video_commands = {
        "left", "right", "up", "down", "zoom-in", "zoom-out",
        "center", "pan", "tilt", "zoom", "status", "flicker",
    }
    hid_commands = {
        "idle", "track", "privacy", "gesture-on", "gesture-off",
        "audio", "auto-privacy", "state", "pan-speed", "tilt-speed", "target",
        "wb-lock", "exposure-lock", "focus-lock", "power-on-position",
    }

    video = find_video_device() if command in video_commands else None
    hid = find_hidraw_device() if command in hid_commands else None

    if command in video_commands and not video:
        raise PixyError("EMEET PIXY video device not found")
    if command in hid_commands and not hid:
        raise PixyError("EMEET PIXY HID device not found")

    tracking_messages = {"idle": "Tracking OFF (idle)", "track": "Tracking ON", "privacy": "Privacy mode ON"}
    if command in tracking_messages:
        set_tracking(hid, TRACKING_MODES[command])
        return tracking_messages[command]
    if command == "gesture-on":
        set_gesture(hid, True)
        return "Gesture control ON"
    if command == "gesture-off":
        set_gesture(hid, False)
        return "Gesture control OFF"
    if command == "audio":
        if value not in AUDIO_MODES:
            raise PixyError("Usage: audio " + "|".join(AUDIO_MODES))
        set_audio_mode(hid, AUDIO_MODES[value])
        return f"Audio: {value.upper()} mode"
    if command == "auto-privacy":
        seconds = int(value) if value is not None else 10
        set_auto_privacy(hid, seconds)
        return "Auto-privacy OFF" if seconds == 0 else f"Auto-privacy ON ({seconds}s)"
    if command == "state":
        state = read_state(hid)
        return "\n".join(f"{key}: {value}" for key, value in state.items()) or "No reply from the camera"
    if command in ("pan-speed", "tilt-speed"):
        axis = command.split("-")[0]
        if value is None:
            speed = get_motor_speed(hid, axis)
            return f"{axis} speed: {round(speed)}°/s" if speed is not None else "No reply from the camera"
        speed = set_motor_speed(hid, axis, float(value))
        return f"{axis} speed: {round(speed)}°/s"
    if command == "target":
        if value not in TARGET_TRACK_MODES:
            raise PixyError("Usage: target " + "|".join(TARGET_TRACK_MODES))
        set_target_track(hid, TARGET_TRACK_MODES[value])
        return f"Tracking target: {value}"
    if command in ("wb-lock", "exposure-lock", "focus-lock"):
        if value not in ("on", "off"):
            raise PixyError(f"Usage: {command} on|off")
        name = {"wb-lock": "white-balance", "exposure-lock": "exposure", "focus-lock": "focus"}[command]
        set_lock(hid, name, value == "on")
        return f"{name} lock: {value}"
    if command == "power-on-position":
        if value == "save":
            save_power_on_position(hid)
        elif value not in (None, "show"):
            raise PixyError("Usage: power-on-position [show|save]")
        position = get_power_on_position(hid)
        if position is None:
            return "Power-on position: not stored"
        return f"Power-on position: pan {round(position[0])}°, tilt {round(position[1])}°"
    if command == "flicker":
        if value not in FLICKER_MODES:
            raise PixyError("Usage: flicker " + "|".join(FLICKER_MODES))
        set_control(video, "power_line_frequency", FLICKER_MODES[value])
        return f"Anti-flicker: {value}"
    if command == "left":
        cur = get_control(video, "pan_absolute")
        set_control(video, "pan_absolute", clamp(cur - STEP, PAN_MIN, PAN_MAX))
        return ""
    if command == "right":
        cur = get_control(video, "pan_absolute")
        set_control(video, "pan_absolute", clamp(cur + STEP, PAN_MIN, PAN_MAX))
        return ""
    if command == "up":
        cur = get_control(video, "tilt_absolute")
        set_control(video, "tilt_absolute", clamp(cur + STEP, TILT_MIN, TILT_MAX))
        return ""
    if command == "down":
        cur = get_control(video, "tilt_absolute")
        set_control(video, "tilt_absolute", clamp(cur - STEP, TILT_MIN, TILT_MAX))
        return ""
    if command == "zoom-in":
        cur = get_control(video, "zoom_absolute")
        set_control(video, "zoom_absolute", clamp(cur + 10, ZOOM_MIN, ZOOM_MAX))
        return ""
    if command == "zoom-out":
        cur = get_control(video, "zoom_absolute")
        set_control(video, "zoom_absolute", clamp(cur - 10, ZOOM_MIN, ZOOM_MAX))
        return ""
    if command == "center":
        set_control(video, "pan_absolute", 0)
        set_control(video, "tilt_absolute", 0)
        set_control(video, "zoom_absolute", ZOOM_MIN)
        return "Centered"
    if command == "pan":
        degrees = int(value or 0)
        set_control(video, "pan_absolute", clamp(degrees * DEGREE_UNIT, PAN_MIN, PAN_MAX))
        return ""
    if command == "tilt":
        degrees = int(value or 0)
        set_control(video, "tilt_absolute", clamp(degrees * DEGREE_UNIT, TILT_MIN, TILT_MAX))
        return ""
    if command == "zoom":
        zoom = int(value or ZOOM_MIN)
        set_control(video, "zoom_absolute", clamp(zoom, ZOOM_MIN, ZOOM_MAX))
        return ""
    if command == "status":
        return status_text(video)

    raise PixyError(f"Unknown command: {command}")


# Single source for the CLI: argparse choices, --help and the README table.
CLI_COMMANDS = {
    "status": ("", "Show device, pan, tilt and zoom"),
    "center": ("", "Pan/tilt to 0° and zoom out"),
    "left": ("", f"Pan {STEP_DEG}° left"),
    "right": ("", f"Pan {STEP_DEG}° right"),
    "up": ("", f"Tilt {STEP_DEG}° up"),
    "down": ("", f"Tilt {STEP_DEG}° down"),
    "pan": ("DEGREES", "Pan to an absolute angle (-150…150)"),
    "tilt": ("DEGREES", f"Tilt to an absolute angle ({TILT_MIN // DEGREE_UNIT}…{TILT_MAX // DEGREE_UNIT})"),
    "zoom": ("100-150", "Set hardware zoom"),
    "zoom-in": ("", "Hardware zoom +10"),
    "zoom-out": ("", "Hardware zoom -10"),
    "track": ("", "Enable face tracking"),
    "idle": ("", "Disable tracking"),
    "privacy": ("", "Enter privacy mode"),
    "gesture-on": ("", "Enable gesture control"),
    "gesture-off": ("", "Disable gesture control"),
    "audio": ("nc|live|org", "Microphone mode: noise cancel, live, original"),
    "auto-privacy": ("SECONDS", "Camera-side auto-privacy delay (0 = off; experimental)"),
    "flicker": ("off|50|60", "Anti-flicker frequency"),
    "target": ("|".join(TARGET_TRACK_MODES), "What tracking keeps in frame"),
    "pan-speed": ("[DEG/S]", f"Show or set the pan motor speed ({MOTOR_SPEED_MIN}…{MOTOR_SPEED_MAX})"),
    "tilt-speed": ("[DEG/S]", f"Show or set the tilt motor speed ({MOTOR_SPEED_MIN}…{MOTOR_SPEED_MAX})"),
    "wb-lock": ("on|off", "Lock the white balance"),
    "exposure-lock": ("on|off", "Lock the exposure"),
    "focus-lock": ("on|off", "Lock the focus"),
    "power-on-position": ("[show|save]", "Show, or store the current pan/tilt as the camera's power-on position"),
    "state": ("", "Show the camera's on-board settings"),
}


def build_parser() -> argparse.ArgumentParser:
    epilog = "\n".join(
        f"  {name} {value}".ljust(30) + description
        for name, (value, description) in CLI_COMMANDS.items()
    )
    parser = argparse.ArgumentParser(
        prog="pixydeck-cli",
        description="EMEET PixyDeck command-line control for the EMEET PIXY",
        epilog="commands:\n" + epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=list(CLI_COMMANDS), metavar="command")
    parser.add_argument("value", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = execute(args.command, args.value)
    except (PixyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
