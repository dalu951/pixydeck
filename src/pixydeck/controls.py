"""On-board AI, focus, orientation and picture controls (AI & Image tabs).

Mixed into ``PixyGUI``; methods use the window's widgets and state via ``self``.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtWidgets import QLabel, QPushButton, QSpinBox, QWidget

from . import backend
from .backend import PixyController
from .constants import AUTO_CONTROLS, IMAGE_AUTO, IMAGE_SLIDERS
from .privacy import PACTL, set_pixy_microphone_muted
from .vision import vision_available
from .widgets import Card, Segmented, SettingRow, SliderRow, ToggleSwitch, section_title, set_state

log = logging.getLogger(__name__)

TARGET_LABELS = {"auto": "auto", "face": "face", "upper-body": "upper body"}


def apply_controls(controller: PixyController, values: dict[str, int]) -> None:
    """Set picture controls, automatic modes first (the camera rejects manual
    values while the matching auto mode is on). Unsupported ones are skipped."""
    for name in sorted(values, key=lambda n: n not in AUTO_CONTROLS):
        try:
            controller.set(name, values[name])
        except (backend.PixyError, KeyError) as exc:
            log.debug("skipping control %s: %s", name, exc)


class ControlsMixin:
    """On-board AI, focus, orientation and picture controls (AI & Image tabs)."""

    def build_ai_tab(self) -> QWidget:
        page, layout = self.tab_page()

        onboard = Card("PIXY on-board AI")
        self.tracking = Segmented([("Off", "idle"), ("Face tracking", "track"), ("Privacy", "privacy")])
        self.tracking.selected.connect(self.set_tracking_mode)
        onboard.body.addWidget(self.tracking)
        onboard.body.addWidget(section_title("Tracking keeps in frame"))
        self.target = Segmented([("Auto", "auto"), ("Face", "face"), ("Upper body", "upper-body")])
        self.target.selected.connect(self.set_target)
        onboard.body.addWidget(self.target)
        self.gesture = ToggleSwitch()
        self.gesture.toggled.connect(self.set_gesture)
        onboard.body.addWidget(SettingRow("Gesture control", self.gesture, "Hand gestures steer the camera"))
        onboard.body.addWidget(section_title("Microphone"))
        self.audio = Segmented([("Noise cancel", "nc"), ("Live", "live"), ("Original", "org")])
        self.audio.selected.connect(self.set_audio)
        onboard.body.addWidget(self.audio)
        layout.addWidget(onboard)

        focus = Card("AI focus")
        self.focus_mode = Segmented([("Center", "center"), ("Face", "face"), ("Click point", "area")])
        self.focus_mode.selected.connect(self.set_focus_mode)
        focus.body.addWidget(self.focus_mode)
        focus.body.addWidget(self.hint(
            "The PIXY's second lens steers autofocus and exposure. With “Click point”, "
            "click anything in the preview – e.g. an object you hold up – to focus on it."))
        layout.addWidget(focus)

        framing = Card("Auto-framing (software)")
        self.autoframe = ToggleSwitch()
        self.autoframe.toggled.connect(self.set_autoframe)
        self.autoframe_row = SettingRow(
            "Auto-framing", self.autoframe,
            "Digitally zooms and follows faces – also at 4K and in the processed virtual camera (F)")
        framing.body.addWidget(self.autoframe_row)
        self.framing = Segmented([("Wide", "wide"), ("Medium", "medium"), ("Tight", "tight")])
        self.framing.selected.connect(lambda v: self.settings.setValue("ai/framing", v))
        framing.body.addWidget(self.framing)
        self.show_faces = ToggleSwitch()
        self.show_faces.toggled.connect(self.set_show_faces)
        framing.body.addWidget(SettingRow("Show detected faces", self.show_faces))
        if not vision_available():
            for widget in (self.autoframe, self.framing, self.show_faces):
                widget.setEnabled(False)
            self.autoframe_row.hint.setText(
                "Needs the optional AI extra: pip install 'pixydeck[ai]'")
        layout.addWidget(framing)

        calls = Card("Calls")
        self.calls_enabled = ToggleSwitch()
        self.calls_enabled.toggled.connect(self.calls_toggled)
        calls.body.addWidget(SettingRow(
            "Detect calls", self.calls_enabled,
            "A call starts when another app opens the PIXY and ends a few seconds after it lets go"))
        calls.body.addWidget(section_title("When a call starts"))
        self.calls_start = Segmented([("Face tracking", "track"), ("Keep mode", "keep")])
        self.calls_start.selected.connect(lambda v: self.settings.setValue("calls/start", v))
        calls.body.addWidget(self.calls_start)
        self.calls_mic = ToggleSwitch()
        self.calls_mic.toggled.connect(lambda v: self.settings.setValue("calls/microphone", v))
        self.calls_mic.setEnabled(bool(PACTL))
        calls.body.addWidget(SettingRow(
            "Use the PIXY microphone", self.calls_mic,
            "Makes it the default input during the call and switches back afterwards"
            if PACTL else "pactl not found"))
        self.calls_privacy = ToggleSwitch()
        self.calls_privacy.toggled.connect(lambda v: self.settings.setValue("calls/privacy", v))
        calls.body.addWidget(SettingRow(
            "Privacy when the call ends", self.calls_privacy, "The lens turns away"))
        self.calls_status = QLabel("", objectName="subtle")
        calls.body.addWidget(self.calls_status)
        layout.addWidget(calls)

        privacy = Card("Privacy timer")
        self.privacy_enabled = ToggleSwitch()
        self.privacy_enabled.toggled.connect(lambda v: self.settings.setValue("privacy/enabled", v))
        privacy.body.addWidget(SettingRow(
            "Enter privacy when idle", self.privacy_enabled,
            "The lens turns away when no app has used the camera for a while"))
        self.privacy_minutes = QSpinBox()
        self.privacy_minutes.setRange(1, 240)
        self.privacy_minutes.setSuffix(" min")
        self.privacy_minutes.valueChanged.connect(lambda v: self.settings.setValue("privacy/minutes", v))
        privacy.body.addWidget(SettingRow("Idle time", self.privacy_minutes))
        self.privacy_wake = ToggleSwitch()
        self.privacy_wake.toggled.connect(lambda v: self.settings.setValue("privacy/wake", v))
        privacy.body.addWidget(SettingRow(
            "Wake when an app needs the camera", self.privacy_wake,
            "Leaves privacy mode as soon as Zoom, Teams, Meet, OBS … open the PIXY"))
        self.privacy_mic = ToggleSwitch()
        self.privacy_mic.toggled.connect(lambda v: self.settings.setValue("privacy/mute_mic", v))
        self.privacy_mic.setEnabled(bool(PACTL))
        privacy.body.addWidget(SettingRow(
            "Mute PIXY microphone in privacy", self.privacy_mic,
            "Via PipeWire/PulseAudio" if PACTL else "pactl not found"))
        self.privacy_status = QLabel("", objectName="subtle")
        privacy.body.addWidget(self.privacy_status)
        layout.addWidget(privacy)
        layout.addStretch()
        return page

    def build_image_tab(self) -> QWidget:
        page, layout = self.tab_page()

        picture = Card("Picture")
        self.image_sliders: dict[str, SliderRow] = {}
        for control, label in IMAGE_SLIDERS:
            row = SliderRow(label, 0, 255, 128)
            row.value_changed.connect(lambda v, c=control: self.set_image_control(c, v))
            picture.body.addWidget(row)
            self.image_sliders[control] = row
        layout.addWidget(picture)

        auto = Card("Automatic modes")
        self.auto_toggles: dict[str, ToggleSwitch] = {}
        for label, auto_control, values, manual, slider_label, unit in IMAGE_AUTO:
            toggle = ToggleSwitch()
            toggle.toggled.connect(
                lambda on, a=auto_control, v=values, m=manual: self.set_auto_mode(a, v, m, on))
            auto.body.addWidget(SettingRow(label, toggle))
            slider = SliderRow(slider_label, 0, 100, 0, fmt=lambda v, u=unit: f"{v}{u}")
            slider.value_changed.connect(lambda v, c=manual: self.set_image_control(c, v))
            auto.body.addWidget(slider)
            self.auto_toggles[auto_control] = toggle
            self.image_sliders[manual] = slider
        self.backlight = ToggleSwitch()
        self.backlight.toggled.connect(
            lambda on: self.set_image_control("backlight_compensation", 2 if on else 1))
        auto.body.addWidget(SettingRow("Backlight compensation", self.backlight))
        layout.addWidget(auto)

        stabilize = Card("Stabilization")
        self.stabilize = ToggleSwitch()
        self.stabilize.toggled.connect(self.set_stabilization)
        self.stabilize_row = SettingRow(
            "Steady picture", self.stabilize,
            "Cancels shake, e.g. from a wobbling monitor or desk. Uses an 8 % digital zoom "
            "as reserve; pans and PTZ moves pass through.")
        stabilize.body.addWidget(self.stabilize_row)
        if not vision_available():
            self.stabilize.setEnabled(False)
            self.stabilize_row.hint.setText("Needs the optional AI extra (OpenCV).")
        layout.addWidget(stabilize)

        orientation = Card("Orientation")
        self.feature_toggles: dict[str, ToggleSwitch] = {}
        for name, label, hint in (
            ("hflip", "Mirror horizontally", None),
            ("vflip", "Flip vertically", None),
            ("autorotate", "Auto-rotate when upside down", "For ceiling or under-monitor mounting"),
        ):
            toggle = ToggleSwitch()
            toggle.toggled.connect(lambda on, n=name: self.set_feature(n, on))
            orientation.body.addWidget(SettingRow(label, toggle, hint))
            self.feature_toggles[name] = toggle
        layout.addWidget(orientation)

        locks = Card("Locks")
        self.lock_toggles: dict[str, ToggleSwitch] = {}
        for name, label in (
            ("exposure", "Lock exposure"),
            ("white-balance", "Lock white balance"),
            ("focus", "Lock focus"),
        ):
            toggle = ToggleSwitch()
            toggle.toggled.connect(lambda on, n=name: self.set_lock(n, on))
            locks.body.addWidget(SettingRow(label, toggle))
            self.lock_toggles[name] = toggle
        locks.body.addWidget(self.hint(
            "Freezes the camera's automatic adjustment at the current value, e.g. so the "
            "picture does not pump when you lean in or hold something up."))
        layout.addWidget(locks)

        power = Card("Anti-flicker")
        self.flicker = Segmented([("Off", "off"), ("50 Hz", "50"), ("60 Hz", "60")])
        self.flicker.selected.connect(self.set_flicker)
        power.body.addWidget(self.flicker)
        layout.addWidget(power)

        reset = QPushButton("Reset picture to camera defaults")
        reset.clicked.connect(self.reset_image)
        layout.addWidget(reset)
        layout.addStretch()
        return page

    def show_tracking_state(self) -> None:
        mode = self.tracking_mode
        self.tracking.set_current(mode)
        self.pill_tracking.setText({"idle": "Tracking off", "track": "Face tracking", "privacy": "Privacy"}[mode])
        set_state(self.pill_tracking, {"idle": "", "track": "on", "privacy": "warn"}[mode])

    def set_tracking_mode(self, mode: str, by_timer: bool = False) -> None:
        if mode == "privacy" and self.tracking_mode != "privacy":
            self.mode_before_privacy = self.tracking_mode
        self.privacy_by_timer = by_timer and mode == "privacy"
        self.privacy_by_call = False
        self.tracking_changed_at = time.monotonic()
        self.tracking_mode = mode
        self.settings.setValue("camera/tracking", mode)
        self.show_tracking_state()
        text = self.pill_tracking.text()
        self.worker.submit(self.controller.tracking, mode, key="tracking", done=lambda _: self.notify(text))
        if mode == "privacy" and self.privacy_mic.isChecked() and not self.mic_muted_by_us:
            self.mic_muted_by_us = True
            self.worker.submit(set_pixy_microphone_muted, True)
        elif mode != "privacy" and self.mic_muted_by_us:
            self.mic_muted_by_us = False
            self.worker.submit(set_pixy_microphone_muted, False)
        self.idle_seconds = 0

    def set_gesture(self, enabled: bool) -> None:
        self.settings.setValue("camera/gesture", enabled)
        self.worker.submit(self.controller.gesture, enabled, key="gesture",
                           done=lambda _: self.notify(f"Gesture control {'on' if enabled else 'off'}"))

    def set_audio(self, mode: str) -> None:
        self.settings.setValue("camera/audio", mode)
        self.worker.submit(self.controller.audio, mode, key="audio",
                           done=lambda _: self.notify("Microphone mode updated"))

    def set_target(self, mode: str) -> None:
        self.settings.setValue("camera/target", mode)
        self.worker.submit(self.controller.target_track, mode, key="target",
                           done=lambda _: self.notify(f"Tracking target: {TARGET_LABELS[mode]}"))

    def set_motor_speed(self, speed: int) -> None:
        self.settings.setValue("camera/motor_speed", speed)
        for axis in backend.MOTOR_AXES:
            self.worker.submit(self.controller.motor_speed, axis, speed, key=f"speed/{axis}")

    def set_lock(self, name: str, locked: bool) -> None:
        self.worker.submit(self.controller.lock, name, locked, key=f"lock/{name}")

    def save_power_on_position(self) -> None:
        def save():
            self.controller.save_power_on_position()
            return self.controller.power_on_position()

        def done(position) -> None:
            if position is None:
                self.notify("The camera did not confirm the power-on position", 6000)
            else:
                self.notify(f"Camera powers on at pan {round(position[0])}°, tilt {round(position[1])}°")

        self.worker.submit(save, key="power-on", done=done)

    def set_flicker(self, mode: str) -> None:
        self.settings.setValue("camera/flicker", mode)
        self.worker.submit(self.controller.flicker, mode, key="flicker")

    def set_focus_mode(self, mode: str) -> None:
        if mode == "area":
            self.notify("Click in the preview to choose the focus point")
            x, y = self.focus_point
            self.worker.submit(self.controller.focus_mode, "area", x, y, key="focus")
        else:
            self.worker.submit(self.controller.focus_mode, mode, key="focus",
                               done=lambda _: self.notify(f"Focus: {mode}"))

    def on_preview_click(self, nx: float, ny: float) -> None:
        if self.focus_mode.current() != "area":
            return
        # nx/ny are already full-frame coordinates, also when digitally zoomed.
        self.focus_point = (nx, ny)
        self.view.show_focus_point(nx, ny)
        self.worker.submit(self.controller.focus_mode, "area", nx, ny, key="focus")

    def set_feature(self, name: str, enabled: bool) -> None:
        self.worker.submit(self.controller.feature, name, enabled, key=f"feature/{name}")

    def set_stabilization(self, enabled: bool) -> None:
        self.settings.setValue("effects/stabilize", enabled)
        self.processor.set_stabilization(enabled)
        if not enabled and not self.processor.background_active:
            self.view.set_processed(None)
        self.notify("Stabilization on" if enabled else "Stabilization off")

    def min_digital_zoom(self) -> float:
        """Reserve border for the stabilizer to shift into."""
        if self.processor.stabilizing:
            return 1.0 + 2 * self.processor.stabilization_margin
        return 1.0

    def poll_camera_state(self) -> None:
        self.status_worker.submit(self.controller.state, key="state", done=self.on_camera_state)

    def on_camera_state(self, state: dict) -> None:
        """Mirror changes made on the camera itself (gestures, other apps)."""
        if "audio" in state and state["audio"] != self.audio.current():
            self.audio.set_current(state["audio"])
            self.settings.setValue("camera/audio", state["audio"])
        if "gesture" in state and state["gesture"] != self.gesture.isChecked():
            self.gesture.set_silently(state["gesture"])
            self.settings.setValue("camera/gesture", state["gesture"])
        if "focus" in state and state["focus"] != self.focus_mode.current():
            self.focus_mode.set_current(state["focus"])
        for name, toggle in self.feature_toggles.items():
            if name in state and state[name] != toggle.isChecked():
                toggle.set_silently(state[name])
        for name, toggle in self.lock_toggles.items():
            locked = state.get(f"{name}-lock")
            if locked is not None and locked != toggle.isChecked():
                toggle.set_silently(locked)
        if "target" in state and state["target"] != self.target.current():
            self.target.set_current(state["target"])
            self.settings.setValue("camera/target", state["target"])
        tracking = state.get("tracking")
        if time.monotonic() - self.tracking_changed_at < 4:
            tracking = None  # the camera reports our own change with a delay
        if tracking == "privacy" and self.tracking_mode != "privacy":
            self.mode_before_privacy = self.tracking_mode
            self.tracking_mode = "privacy"
            self.show_tracking_state()
        elif tracking in ("idle", "track") and tracking != self.tracking_mode:
            self.tracking_mode = tracking
            self.show_tracking_state()

    def set_image_control(self, control: str, value: int) -> None:
        self.settings.setValue(f"image/{control}", value)
        self.worker.submit(self.controller.set, control, value, key=f"image/{control}")

    def set_auto_mode(self, auto_control: str, values: tuple[int, int], manual: str, on: bool) -> None:
        self.set_image_control(auto_control, values[0] if on else values[1])
        self.image_sliders[manual].setEnabled(not on)
        if not on:
            # Start the manual slider from what the camera had chosen automatically.
            self.worker.submit(self.controller.get, manual,
                               done=lambda v, m=manual: self.image_sliders[m].set_value_silently(v))

    def load_image_controls(self) -> None:
        names = list(self.image_sliders) + AUTO_CONTROLS + ["backlight_compensation"]

        def read() -> dict:
            result = {}
            for name in names:
                info = self.controller.query(name)
                if info is None:
                    continue
                try:
                    info["value"] = self.controller.get(name)
                except backend.PixyError as exc:
                    log.debug("cannot read %s: %s", name, exc)
                    continue
                result[name] = info
            return result

        self.worker.submit(read, done=self.on_image_controls)

    def on_image_controls(self, controls: dict) -> None:
        for name, row in self.image_sliders.items():
            info = controls.get(name)
            row.setEnabled(info is not None)
            if info is None:
                continue
            row.set_range(info["min"], info["max"])
            row.set_value_silently(info["value"])
            row.slider.setToolTip(f"Range {info['min']}–{info['max']}, default {info['default']}")
        for _label, auto_control, values, manual, _slider, _unit in IMAGE_AUTO:
            info = controls.get(auto_control)
            toggle = self.auto_toggles[auto_control]
            toggle.setEnabled(info is not None)
            if info is None:
                continue
            on = info["value"] == values[0]
            toggle.set_silently(on)
            self.image_sliders[manual].setEnabled(not on and manual in controls)
        backlight = controls.get("backlight_compensation")
        self.backlight.setEnabled(backlight is not None)
        if backlight is not None:
            self.backlight.set_silently(backlight["value"] >= 2)
        self.image_defaults = {name: info["default"] for name, info in controls.items()}

    def reset_image(self) -> None:
        defaults = dict(self.image_defaults)
        if not defaults:
            return
        self.settings.remove("image")

        def reset() -> bool:
            apply_controls(self.controller, defaults)
            return True

        def done(_result) -> None:
            self.load_image_controls()
            self.notify("Picture reset to camera defaults")

        self.worker.submit(reset, done=done)