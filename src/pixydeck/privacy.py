"""Privacy timer: idle detection and waking when other apps use the camera.

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


class PrivacyMixin:
    """Privacy timer: idle detection and waking when other apps use the camera."""

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
            status = "In privacy mode" + (" (idle timer)" if self.privacy_by_timer else "")
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