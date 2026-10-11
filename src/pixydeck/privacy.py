"""Privacy timer, call detection and waking when other apps use the camera.

Mixed into ``PixyGUI``; methods use the window's widgets and state via ``self``.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .backend import camera_users, video_nodes
from .widgets import set_state


PACTL = shutil.which("pactl")


def pixy_video_nodes() -> list[str]:
    """All physical and virtual PIXY nodes, for noticing other apps using them."""
    return [device for device, name in video_nodes() if "PIXY" in name.upper()]


def set_pixy_microphone_muted(muted: bool) -> bool:
    """Mute/unmute the PIXY microphone through PipeWire/PulseAudio."""
    if not PACTL:
        return False
    result = subprocess.run([PACTL, "list", "short", "sources"], capture_output=True, text=True, check=False)
    changed = False
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        name = fields[1]
        if ("emeet" in name.lower() or "pixy" in name.lower()) and not name.endswith(".monitor"):
            subprocess.run([PACTL, "set-source-mute", name, "1" if muted else "0"], check=False)
            changed = True
    return changed


def pixy_microphone() -> str | None:
    """PipeWire/PulseAudio name of the PIXY microphone, if present."""
    if not PACTL:
        return None
    result = subprocess.run([PACTL, "list", "short", "sources"], capture_output=True, text=True, check=False)
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and "pixy" in fields[1].lower() and not fields[1].endswith(".monitor"):
            return fields[1]
    return None


def default_microphone() -> str | None:
    if not PACTL:
        return None
    result = subprocess.run([PACTL, "get-default-source"], capture_output=True, text=True, check=False)
    return result.stdout.strip() or None


def set_default_microphone(name: str) -> None:
    subprocess.run([PACTL, "set-default-source", name], check=False)


class CallDetector:
    """Turns "which apps hold the camera" polls into call start/end events.

    Browsers and some call apps open the camera for a moment to list devices,
    so a call starts only after ``start_polls`` consecutive polls with a user
    and ends after ``end_polls`` polls without one.
    """

    def __init__(self, start_polls: int = 2, end_polls: int = 3) -> None:
        self.start_polls = start_polls
        self.end_polls = end_polls
        self.active = False
        self.apps: list[str] = []
        self._streak = 0

    def update(self, apps: list[str]) -> str | None:
        in_use = bool(apps)
        if in_use:
            self.apps = sorted(set(apps))
        if in_use == self.active:
            self._streak = 0
            return None
        self._streak += 1
        if self._streak < (self.start_polls if in_use else self.end_polls):
            return None
        self._streak = 0
        self.active = in_use
        return "started" if in_use else "ended"

    def reset(self) -> None:
        self.active = False
        self.apps = []
        self._streak = 0


class PrivacyMixin:
    """Privacy timer, call detection and waking when other apps use the camera."""

    def own_pids(self) -> list[int]:
        pids = [os.getpid()]
        if self.virtual_process is not None and self.virtual_process.processId():
            pids.append(self.virtual_process.processId())
        if self.processor.output_pid:
            pids.append(self.processor.output_pid)
        return pids

    def check_privacy(self) -> None:
        devices = pixy_video_nodes()
        if devices:
            self.worker.submit(camera_users, devices, self.own_pids(), key="users", done=self.on_camera_users)

    def on_camera_users(self, users: list[tuple[int, str]]) -> None:
        if users:
            self.pill_users.setText("In use: " + ", ".join(sorted({name for _pid, name in users})))
            set_state(self.pill_users, "ok")
        self.pill_users.setVisible(bool(users))

        if users and self.tracking_mode == "privacy" and self.privacy_wake.isChecked():
            self.set_tracking_mode(self.mode_before_privacy if self.mode_before_privacy != "privacy" else "idle")
            self.notify(f"Left privacy mode – {users[0][1]} is using the camera", 6000)

        self.check_call(users)

        watching_here = self.streams_frames and self.isVisible() and not self.isMinimized()
        enabled = self.privacy_enabled.isChecked()
        if users or watching_here or self.tracking_mode == "privacy" or not enabled:
            self.idle_seconds = 0
        else:
            self.idle_seconds += self.privacy_timer.interval() // 1000
            if self.idle_seconds >= self.privacy_minutes.value() * 60:
                self.set_tracking_mode("privacy", by_timer=True)
                self.notify("Privacy mode after idle timeout", 6000)

        if self.tracking_mode == "privacy":
            status = "In privacy mode" + (
                " (idle timer)" if self.privacy_by_timer else " (call ended)" if self.privacy_by_call else "")
        elif not enabled:
            status = ""
        elif users:
            status = "Camera in use – timer paused"
        elif watching_here:
            status = "Preview visible – timer paused (release or minimise to start it)"
        else:
            remaining = max(0, self.privacy_minutes.value() * 60 - self.idle_seconds)
            status = f"Privacy in {remaining // 60}:{remaining % 60:02d}"
        self.privacy_status.setText(status)

    # -- calls ----------------------------------------------------------
    def check_call(self, users: list[tuple[int, str]]) -> None:
        if not self.calls_enabled.isChecked():
            return
        event = self.call_detector.update([name for _pid, name in users])
        if event == "started":
            self.on_call_started()
        elif event == "ended":
            self.on_call_ended()
        self.show_call_state()

    def on_call_started(self) -> None:
        apps = ", ".join(self.call_detector.apps)
        action = self.calls_start.current() or "track"
        if action == "track":
            self.set_tracking_mode("track")
        elif self.tracking_mode == "privacy":
            self.set_tracking_mode(self.mode_before_privacy if self.mode_before_privacy != "privacy" else "idle")
        if self.calls_mic.isChecked():
            self.worker.submit(self.switch_to_pixy_microphone, key="call-mic")
        self.notify(f"Call started – {apps}", 6000)

    def on_call_ended(self) -> None:
        if self.calls_privacy.isChecked():
            self.set_tracking_mode("privacy")
            self.privacy_by_call = True
        if self.microphone_before_call is not None:
            previous, self.microphone_before_call = self.microphone_before_call, None
            self.worker.submit(set_default_microphone, previous, key="call-mic")
        self.notify("Call ended" + (" – privacy mode" if self.calls_privacy.isChecked() else ""), 6000)

    def switch_to_pixy_microphone(self) -> None:
        """Runs on the worker: make the PIXY the default input, remembering the old one."""
        pixy = pixy_microphone()
        current = default_microphone()
        if pixy is None or current == pixy:
            return
        self.microphone_before_call = current
        set_default_microphone(pixy)

    def calls_toggled(self, enabled: bool) -> None:
        self.settings.setValue("calls/enabled", enabled)
        if not enabled:
            self.call_detector.reset()
        self.show_call_state()

    def show_call_state(self) -> None:
        if not self.calls_enabled.isChecked():
            text = ""
        elif self.call_detector.active:
            text = "📞 In a call – " + ", ".join(self.call_detector.apps)
        else:
            text = "No call – waiting for Zoom, Teams, Meet, OBS … to open the camera"
        self.calls_status.setText(text)
