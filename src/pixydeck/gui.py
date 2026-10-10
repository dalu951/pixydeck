#!/usr/bin/env python3
"""EMEET PixyDeck - PySide6 desktop application."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import (
    QCamera, QMediaCaptureSession, QMediaDevices, QVideoFrame, QVideoFrameFormat,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QColorDialog, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QPushButton, QScrollArea, QSlider,
    QSpinBox, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from . import APP_ID, APP_NAME, VIRTUAL_CAMERA_NAME, backend
from .backend import PixyController, camera_users, video_sort_key
from .setup import SetupDialog, needs_attention, run_checks
from .vision import (
    Background, Crop, FrameProcessor, Smoother, framing_target, matting_available, vision_available,
)
from .widgets import (
    THEME, Card, InfoPanel, PreviewView, PtzPad, Segmented, SettingRow,
    SliderRow, ToggleSwitch, section_title, set_state,
)
from .worker import ControlWorker

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional extra
    np = None

PACKAGE_DIR = Path(__file__).resolve().parent
ICON = PACKAGE_DIR / "assets" / "pixydeck.svg"
FFMPEG = shutil.which("ffmpeg")
PACTL = shutil.which("pactl")
VIRTUAL_NAME = VIRTUAL_CAMERA_NAME

ZOOM_MIN, HW_ZOOM_MAX, ZOOM_MAX = 100, 150, 400
PRESET_SLOTS = 4
PAN_LIMIT = backend.PAN_MAX // backend.DEGREE_UNIT
TILT_MIN = backend.TILT_MIN // backend.DEGREE_UNIT
TILT_MAX = backend.TILT_MAX // backend.DEGREE_UNIT
# Approximate field of view at 1x, used to turn preview clicks into angles.
FOV_H, FOV_V = 70, 40

IMAGE_SLIDERS = [
    ("brightness", "Brightness"),
    ("contrast", "Contrast"),
    ("saturation", "Saturation"),
    ("hue", "Hue"),
    ("sharpness", "Sharpness"),
    ("gamma", "Gamma"),
    ("gain", "Gain"),
]
# (toggle label, auto control, (auto value, manual value), manual control, slider label, unit)
IMAGE_AUTO = [
    ("Auto white balance", "white_balance_automatic", (1, 0), "white_balance_temperature", "Temperature", " K"),
    ("Auto exposure", "auto_exposure", (backend.EXPOSURE_APERTURE_PRIORITY, backend.EXPOSURE_MANUAL),
     "exposure_time_absolute", "Exposure time", ""),
    ("Autofocus", "focus_automatic_continuous", (1, 0), "focus_absolute", "Focus", ""),
]
AUTO_CONTROLS = [entry[1] for entry in IMAGE_AUTO]
FRAMING = {"tight": 0.62, "medium": 0.45, "wide": 0.3}

# Single source for keyboard shortcuts: installed by the window and listed
# in the README. Entries without a method are handled elsewhere (arrow keys
# by KeyFilter, presets by install_shortcuts) and only documented here.
SHORTCUTS = [
    (("Left", "Right", "Up", "Down"), "Pan / tilt while held", None),
    (("+", "="), "Zoom in", "zoom_in"),
    (("-",), "Zoom out", "zoom_out"),
    (("C",), "Center camera and reset zoom", "center_camera"),
    (("F",), "Toggle auto-framing", "toggle_autoframe"),
    (("T",), "Toggle face tracking", "toggle_tracking"),
    (("P",), "Toggle privacy mode", "toggle_privacy"),
    (("S",), "Save snapshot", "save_snapshot"),
    (("1", "2", "3", "4"), "Recall preset", None),
    (("Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4"), "Store preset", None),
    (("Ctrl+Q",), "Quit", "close"),
]

PREVIEW, RELEASED, VIRTUAL_DIRECT, VIRTUAL_PROCESSED = "preview", "released", "direct", "processed"


def find_virtual_camera_device() -> str | None:
    """Locate the loopback device by name instead of a fixed /dev/video number."""
    root = Path("/sys/class/video4linux")
    if not root.exists():
        return None
    for dev_dir in sorted(root.glob("video*"), key=video_sort_key):
        try:
            if (dev_dir / "name").read_text().strip() == VIRTUAL_NAME:
                return f"/dev/{dev_dir.name}"
        except OSError:
            continue
    return None


def pixy_video_nodes() -> list[str]:
    """All physical and virtual PIXY nodes, for noticing other apps using them."""
    nodes = []
    for dev_dir in Path("/sys/class/video4linux").glob("video*"):
        try:
            name = (dev_dir / "name").read_text().upper()
        except OSError:
            continue
        if "PIXY" in name:
            nodes.append(f"/dev/{dev_dir.name}")
    return nodes


def migrate_settings(settings: QSettings) -> None:
    """Carry settings over from emeet-pixy-control, the project PixyDeck grew from."""
    if settings.allKeys():
        return
    old = QSettings("emeet-pixy", "control")
    for key in old.allKeys():
        settings.setValue(key, old.value(key))
    settings.sync()


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


class KeyFilter(QObject):
    """Arrow keys move the camera unless a text/number widget has focus."""

    DIRECTIONS = {
        Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0),
        Qt.Key_Up: (0, 1), Qt.Key_Down: (0, -1),
    }

    def __init__(self, window: "PixyGUI") -> None:
        super().__init__(window)
        self.window = window

    def eventFilter(self, _obj, event) -> bool:  # noqa: N802 - Qt API
        if event.type() not in (QEvent.KeyPress, QEvent.KeyRelease):
            return False
        if event.key() not in self.DIRECTIONS or not self.window.isActiveWindow():
            return False
        if isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox, QComboBox, QSlider)):
            return False
        if event.isAutoRepeat():
            return True
        dx, dy = self.DIRECTIONS[event.key()]
        if event.type() == QEvent.KeyPress:
            self.window.start_move(dx, dy)
        else:
            self.window.stop_move(dx, dy)
        return True


class PixyGUI(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(APP_ID, APP_ID)
        migrate_settings(self.settings)
        self.controller = PixyController()
        self.worker = ControlWorker()
        self.worker.failed.connect(lambda msg: self.notify(f"⚠ {msg}", 6000))
        # Reading the on-board state takes ~0.7 s of HID round trips; keep it
        # off the command worker so pan/tilt never waits for it.
        self.status_worker = ControlWorker()
        self.processor = FrameProcessor()
        self.processor.faces_detected.connect(self.on_faces)
        self.processor.output_error.connect(self.on_processed_output_error)
        self.processor.output_stats.connect(self.on_output_fps)
        self.processor.green_screen.connect(self.on_green_screen)
        self.processor.preview_ready.connect(self.on_processed_preview)

        self.camera: QCamera | None = None
        self.capture_session: QMediaCaptureSession | None = None
        self.camera_formats: dict = {}
        self.image_defaults: dict[str, int] = {}
        self.mode = PREVIEW
        self.mode_before_virtual = PREVIEW
        self.virtual_process: QProcess | None = None
        self.virtual_stopping = False

        self.position = (0, 0)
        self.zoom_value = ZOOM_MIN
        self.hw_zoom_sent: int | None = None
        self.manual_center = (0.5, 0.5)
        self.smoother = Smoother()
        self.last_faces_at = 0.0
        self.last_tick = time.monotonic()
        self.output_fps = 0.0

        self.move_dir = [0, 0]
        self.move_target = [0.0, 0.0]
        self.move_started = 0.0

        self.tracking_mode = "idle"
        self.mode_before_privacy = "idle"
        self.privacy_by_timer = False
        self.mic_muted_by_us = False
        self.idle_seconds = 0
        self.focus_point = (0.5, 0.5)
        self.tracking_changed_at = 0.0

        self.setWindowTitle(APP_NAME)
        if ICON.exists():
            self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1320, 820)
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(self.width(), available.width() - 40), min(self.height(), available.height() - 40))

        self.move_timer = QTimer(self, interval=40)
        self.move_timer.timeout.connect(self.move_tick)

        self.build_ui()
        self.load_ui_state()
        self.install_shortcuts()
        self.key_filter = KeyFilter(self)
        QApplication.instance().installEventFilter(self.key_filter)

        self.start_camera()
        self.refresh_virtual_device()
        self.update_mode_ui()

        self.crop_timer = QTimer(self, interval=16)
        self.crop_timer.timeout.connect(self.crop_tick)
        self.crop_timer.start()
        self.poll_timer = QTimer(self, interval=700)
        self.poll_timer.timeout.connect(self.poll_position)
        self.poll_timer.start()
        self.privacy_timer = QTimer(self, interval=2000)
        self.privacy_timer.timeout.connect(self.check_privacy)
        self.privacy_timer.start()
        self.device_timer = QTimer(self, interval=3000)
        self.device_timer.timeout.connect(self.refresh_virtual_device)
        self.device_timer.start()
        self.last_frame_at = time.monotonic()
        self.recovering = False
        self.watchdog_timer = QTimer(self, interval=1000)
        self.watchdog_timer.timeout.connect(self.check_frames)
        self.watchdog_timer.start()
        self.state_timer = QTimer(self, interval=3000)
        self.state_timer.timeout.connect(self.poll_camera_state)
        self.state_timer.start()

        # Let USB/video startup settle before restoring the camera state.
        QTimer.singleShot(600, self.restore_camera_state)
        QTimer.singleShot(1500, self.check_setup)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 8)
        outer.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(QLabel(APP_NAME, objectName="title"))
        header.addSpacing(8)
        self.device_label = QLabel("Detecting camera…", objectName="subtle")
        header.addWidget(self.device_label)
        header.addStretch()
        self.pill_users = QLabel("", objectName="pill")
        self.pill_users.hide()
        self.pill_tracking = QLabel("Tracking off", objectName="pill")
        self.pill_virtual = QLabel("Virtual cam off", objectName="pill")
        for pill in (self.pill_users, self.pill_tracking, self.pill_virtual):
            header.addWidget(pill)
        self.setup_button = QPushButton("⚙ Setup")
        self.setup_button.setToolTip("Check camera permissions and the virtual camera")
        self.setup_button.clicked.connect(self.open_setup)
        header.addWidget(self.setup_button)
        left.addLayout(header)

        preview_card = QFrame(objectName="previewCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview_stack = QStackedWidget()
        self.view = PreviewView()
        self.view.wheel_zoom.connect(lambda steps: self.set_zoom(self.zoom_value + steps * 10, flash=True))
        self.view.drag_by.connect(self.on_preview_drag)
        self.view.double_clicked.connect(self.on_preview_double_click)
        self.view.clicked.connect(self.on_preview_click)
        self.view.video.videoSink().videoFrameChanged.connect(self.on_video_frame)
        self.view.video.videoSink().videoFrameChanged.connect(self.mark_frame)
        self.info_panel = InfoPanel()
        self.preview_stack.addWidget(self.view)
        self.preview_stack.addWidget(self.info_panel)
        preview_layout.addWidget(self.preview_stack)
        left.addWidget(preview_card, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.resolution = QComboBox()
        self.resolution.setToolTip("Capture resolution")
        self.resolution.currentIndexChanged.connect(self.resolution_changed)
        toolbar.addWidget(self.resolution)
        toolbar.addWidget(QLabel("🔍"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(ZOOM_MIN, ZOOM_MAX)
        self.zoom_slider.setMinimumWidth(160)
        self.zoom_slider.valueChanged.connect(lambda v: self.set_zoom(v, from_slider=True))
        toolbar.addWidget(self.zoom_slider, 1)
        self.zoom_label = QLabel("1.0×")
        self.zoom_label.setMinimumWidth(44)
        toolbar.addWidget(self.zoom_label)
        self.snapshot_button = QPushButton("📷 Snapshot")
        self.snapshot_button.setToolTip("Save the current view as PNG (S)")
        self.snapshot_button.clicked.connect(self.save_snapshot)
        toolbar.addWidget(self.snapshot_button)
        self.release_button = QPushButton("Release camera", objectName="primary")
        self.release_button.setToolTip("Free the camera for Meet/OBS/Teams; controls stay active")
        self.release_button.clicked.connect(self.toggle_release)
        toolbar.addWidget(self.release_button)
        left.addLayout(toolbar)
        outer.addLayout(left, 1)

        self.tabs = QTabWidget()
        self.tabs.setFixedWidth(420)
        self.tabs.addTab(self.scroll(self.build_camera_tab()), "Camera")
        self.tabs.addTab(self.scroll(self.build_ai_tab()), "AI && Privacy")
        self.tabs.addTab(self.scroll(self.build_image_tab()), "Image")
        self.tabs.addTab(self.scroll(self.build_background_tab()), "Background")
        self.tabs.addTab(self.scroll(self.build_output_tab()), "Output")
        outer.addWidget(self.tabs)

        self.statusBar().showMessage("Ready")

    @staticmethod
    def scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(widget)
        return area

    @staticmethod
    def tab_page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 6, 10)
        layout.setSpacing(12)
        return page, layout

    @staticmethod
    def hint(text: str) -> QLabel:
        label = QLabel(text, objectName="subtle")
        label.setWordWrap(True)
        return label

    def build_camera_tab(self) -> QWidget:
        page, layout = self.tab_page()

        aim = Card("Pan / Tilt")
        self.pad = PtzPad((-PAN_LIMIT, PAN_LIMIT), (TILT_MIN, TILT_MAX))
        self.pad.target_changed.connect(self.aim_at)
        aim.body.addWidget(self.pad)
        arrows = QGridLayout()
        arrows.setSpacing(6)
        for text, (dx, dy), row, col in (
            ("▲", (0, 1), 0, 1), ("◀", (-1, 0), 1, 0), ("▶", (1, 0), 1, 2), ("▼", (0, -1), 2, 1),
        ):
            button = QPushButton(text)
            button.setFocusPolicy(Qt.NoFocus)
            button.setMinimumSize(56, 34)
            button.pressed.connect(lambda d=(dx, dy): self.start_move(*d))
            button.released.connect(lambda d=(dx, dy): self.stop_move(*d))
            arrows.addWidget(button, row, col)
        center = QPushButton("● Center")
        center.setToolTip("Center pan/tilt and reset zoom (C)")
        center.setFocusPolicy(Qt.NoFocus)
        center.clicked.connect(self.center_camera)
        arrows.addWidget(center, 1, 1)
        aim.body.addLayout(arrows)
        aim.body.addWidget(self.hint(
            "Arrow keys move · scroll on the preview zooms · drag or double-click the preview to aim"))
        layout.addWidget(aim)

        presets = Card("Presets")
        row = QHBoxLayout()
        self.preset_buttons = []
        for slot in range(1, PRESET_SLOTS + 1):
            button = QPushButton(str(slot), objectName="preset")
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _=False, s=slot: self.preset_clicked(s))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda _pos, s=slot: self.preset_menu(s))
            row.addWidget(button)
            self.preset_buttons.append(button)
        presets.body.addLayout(row)
        presets.body.addWidget(self.hint(
            "Click an empty slot to store the current position, a filled one to go there. "
            "Right-click for more · keys 1–4 recall, Ctrl+1–4 store."))
        self.startup_position = QComboBox()
        self.startup_position.addItem("Last position", "last")
        for slot in range(1, PRESET_SLOTS + 1):
            self.startup_position.addItem(f"Preset {slot}", str(slot))
        self.startup_position.currentIndexChanged.connect(self.startup_position_changed)
        presets.body.addWidget(SettingRow("Position at startup", self.startup_position))
        layout.addWidget(presets)
        layout.addStretch()
        return page

    def build_ai_tab(self) -> QWidget:
        page, layout = self.tab_page()

        onboard = Card("PIXY on-board AI")
        self.tracking = Segmented([("Off", "idle"), ("Face tracking", "track"), ("Privacy", "privacy")])
        self.tracking.selected.connect(self.set_tracking_mode)
        onboard.body.addWidget(self.tracking)
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

    def build_background_tab(self) -> QWidget:
        page, layout = self.tab_page()

        screen = Card("Background replacement")
        self.bg_mode = Segmented([("Off", "off"), ("Auto", "auto"), ("Green screen", "chroma"), ("AI", "ai")])
        self.bg_mode.selected.connect(lambda _m: self.apply_background())
        screen.body.addWidget(self.bg_mode)
        self.bg_status = QLabel("", objectName="subtle")
        self.bg_status.setWordWrap(True)
        screen.body.addWidget(self.bg_status)
        screen.body.addWidget(self.hint(
            "Green screen keys the exact shade it detects at the picture's edges. AI cuts you "
            "out of any room (more CPU, up to 30 fps). Auto uses the green screen when one is "
            "in view and AI otherwise. Works in the preview and the processed virtual camera."))
        layout.addWidget(screen)

        fill = Card("Replace with")
        self.bg_fill = Segmented([("Blur", "blur"), ("Gradient", "gradient"), ("Color", "color"), ("Image", "image")])
        self.bg_fill.selected.connect(self.background_fill_selected)
        fill.body.addWidget(self.bg_fill)
        buttons = QHBoxLayout()
        self.bg_color_button = QPushButton("Choose color…")
        self.bg_color_button.clicked.connect(self.choose_background_color)
        self.bg_image_button = QPushButton("Choose image…")
        self.bg_image_button.clicked.connect(self.choose_background_image)
        buttons.addWidget(self.bg_color_button)
        buttons.addWidget(self.bg_image_button)
        fill.body.addLayout(buttons)
        self.bg_image_label = QLabel("", objectName="subtle")
        self.bg_image_label.setWordWrap(True)
        fill.body.addWidget(self.bg_image_label)
        self.bg_blur = SliderRow("Blur strength", 1, 20, 6)
        self.bg_blur.slider.valueChanged.connect(lambda _v: self.background_timer.start())
        fill.body.addWidget(self.bg_blur)
        layout.addWidget(fill)

        tuning = Card("Green screen fine-tuning")
        self.bg_similarity = SliderRow("Similarity", 5, 45, 20, fmt=lambda v: f"{v}%")
        self.bg_smoothness = SliderRow("Edge softness", 2, 40, 10, fmt=lambda v: f"{v}%")
        self.bg_spill = SliderRow("Green spill removal", 0, 100, 70, fmt=lambda v: f"{v}%")
        for row in (self.bg_similarity, self.bg_smoothness, self.bg_spill):
            row.slider.sliderReleased.connect(self.apply_background)
            row.slider.valueChanged.connect(lambda _v: self.background_timer.start())
            tuning.body.addWidget(row)
        tuning.body.addWidget(self.hint(
            "Raise similarity if green remains, lower it if parts of you disappear. "
            "Spill removal takes the green tint off hair and edges."))
        layout.addWidget(tuning)

        self.background_timer = QTimer(self, singleShot=True, interval=120)
        self.background_timer.timeout.connect(self.apply_background)
        self.bg_color = (40, 40, 40)
        self.bg_image_path = ""
        if not vision_available():
            for widget in (self.bg_mode, self.bg_fill, self.bg_color_button, self.bg_image_button,
                           self.bg_similarity, self.bg_smoothness, self.bg_spill, self.bg_blur):
                widget.setEnabled(False)
            self.bg_status.setText("Needs the optional AI extra: pip install 'pixydeck[ai]'")
        layout.addStretch()
        return page

    def build_output_tab(self) -> QWidget:
        page, layout = self.tab_page()

        virtual = Card("Virtual camera")
        self.virtual_mode = Segmented([("Processed", VIRTUAL_PROCESSED), ("Direct", VIRTUAL_DIRECT)])
        self.virtual_mode.selected.connect(self.virtual_mode_changed)
        virtual.body.addWidget(self.virtual_mode)
        self.virtual_mode_hint = self.hint("")
        virtual.body.addWidget(self.virtual_mode_hint)
        self.output_size = QComboBox()
        for w, h in ((1920, 1080), (1280, 720), (960, 540)):
            self.output_size.addItem(f"{w} × {h}", f"{w}x{h}")
        self.output_size.currentIndexChanged.connect(
            lambda: self.settings.setValue("virtual/output_size", self.output_size.currentData()))
        self.output_size_row = SettingRow("Output size", self.output_size)
        virtual.body.addWidget(self.output_size_row)
        self.fps = QComboBox()
        self.fps.currentIndexChanged.connect(self.fps_changed)
        self.fps_row = SettingRow("Frame rate", self.fps, "30 fps keeps hardware zoom working at 1080p")
        virtual.body.addWidget(self.fps_row)
        buttons = QHBoxLayout()
        self.virtual_start = QPushButton("Start", objectName="primary")
        self.virtual_start.clicked.connect(self.start_virtual_camera)
        self.virtual_stop = QPushButton("Stop", objectName="danger")
        self.virtual_stop.clicked.connect(lambda: self.stop_virtual_camera(True))
        self.virtual_stop.setEnabled(False)
        buttons.addWidget(self.virtual_start)
        buttons.addWidget(self.virtual_stop)
        virtual.body.addLayout(buttons)
        self.virtual_device_status = QLabel("Device: checking…", objectName="subtle")
        self.virtual_status = QLabel("Pipeline: stopped", objectName="subtle")
        virtual.body.addWidget(self.virtual_device_status)
        virtual.body.addWidget(self.virtual_status)
        layout.addWidget(virtual)

        direct = Card("Direct use by other apps")
        direct.body.addWidget(self.hint(
            "“Release camera” frees the physical PIXY so Meet, OBS or Teams can open it "
            "directly. Pan/tilt, tracking, privacy and picture controls keep working."))
        layout.addWidget(direct)
        layout.addStretch()
        return page

    def install_shortcuts(self) -> None:
        for keys, _description, method in SHORTCUTS:
            if method is None:
                continue
            for key in keys:
                QShortcut(QKeySequence(key), self).activated.connect(getattr(self, method))
        for slot in range(1, PRESET_SLOTS + 1):
            QShortcut(QKeySequence(str(slot)), self).activated.connect(lambda s=slot: self.recall_preset(s))
            QShortcut(QKeySequence(f"Ctrl+{slot}"), self).activated.connect(lambda s=slot: self.store_preset(s))

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom_value + 10, flash=True)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom_value - 10, flash=True)

    def toggle_autoframe(self) -> None:
        if self.autoframe.isEnabled():
            self.autoframe.toggle()

    def toggle_tracking(self) -> None:
        self.set_tracking_mode("idle" if self.tracking_mode == "track" else "track")

    def toggle_privacy(self) -> None:
        self.set_tracking_mode("idle" if self.tracking_mode == "privacy" else "privacy")

    def notify(self, text: str, timeout: int = 3500) -> None:
        self.statusBar().showMessage(text, timeout)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def bool_setting(self, key: str, default: bool = False) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "on")

    def int_setting(self, key: str, default: int) -> int:
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def load_ui_state(self) -> None:
        self.zoom_value = max(ZOOM_MIN, min(ZOOM_MAX, self.int_setting("camera/zoom", ZOOM_MIN)))
        tracking = str(self.settings.value("camera/tracking", "idle"))
        self.tracking_mode = tracking if tracking in backend.TRACKING_MODES else "idle"
        self.show_tracking_state()
        self.gesture.set_silently(self.bool_setting("camera/gesture"))
        self.audio.set_current(str(self.settings.value("camera/audio", "nc")))
        self.flicker.set_current(str(self.settings.value("camera/flicker", "60")))
        self.framing.set_current(str(self.settings.value("ai/framing", "medium")))
        self.show_faces.set_silently(self.bool_setting("ai/show_faces") and vision_available())
        self.view.show_faces = self.show_faces.isChecked()
        self.privacy_enabled.set_silently(self.bool_setting("privacy/enabled"))
        self.privacy_minutes.setValue(self.int_setting("privacy/minutes", 10))
        self.privacy_wake.set_silently(self.bool_setting("privacy/wake", True))
        self.privacy_mic.set_silently(self.bool_setting("privacy/mute_mic") and bool(PACTL))
        default_mode = VIRTUAL_PROCESSED if vision_available() else VIRTUAL_DIRECT
        self.virtual_mode.set_current(str(self.settings.value("virtual/mode", default_mode)))
        index = self.output_size.findData(str(self.settings.value("virtual/output_size", "1920x1080")))
        self.output_size.setCurrentIndex(max(0, index))
        self.startup_position.blockSignals(True)
        startup = self.startup_position.findData(str(self.settings.value("presets/startup", "last")))
        self.startup_position.setCurrentIndex(max(0, startup))
        self.startup_position.blockSignals(False)
        self.refresh_preset_buttons()
        self.update_virtual_mode_ui()
        mode = str(self.settings.value("background/mode", "off"))
        self.bg_mode.set_current({"always": "chroma"}.get(mode, mode))
        self.bg_fill.set_current(str(self.settings.value("background/fill", "blur")))
        self.bg_blur.set_value_silently(self.int_setting("background/blur", 6))
        try:
            self.bg_color = tuple(int(v) for v in str(self.settings.value("background/color", "40,40,40")).split(","))
        except ValueError:
            self.bg_color = (40, 40, 40)
        self.bg_image_path = str(self.settings.value("background/image", ""))
        self.bg_similarity.set_value_silently(self.int_setting("background/similarity", 20))
        self.bg_smoothness.set_value_silently(self.int_setting("background/smoothness", 10))
        self.bg_spill.set_value_silently(self.int_setting("background/spill", 70))
        self.apply_background()
        if self.bool_setting("effects/stabilize") and vision_available():
            self.stabilize.set_silently(True)
            self.processor.set_stabilization(True)
        if self.bool_setting("ai/autoframe") and vision_available():
            self.autoframe.set_silently(True)
        self.update_autoframe_availability()

    def restore_camera_state(self) -> None:
        startup = str(self.settings.value("presets/startup", "last"))
        preset = self.preset(int(startup)) if startup.isdigit() else None
        if preset is not None:
            pan, tilt, zoom = preset
            self.zoom_value = zoom
        else:
            pan = self.int_setting("camera/pan", 0)
            tilt = self.int_setting("camera/tilt", 0)
        pan = max(-PAN_LIMIT, min(PAN_LIMIT, pan))
        tilt = max(TILT_MIN, min(TILT_MAX, tilt))
        tracking = self.tracking_mode
        gesture = self.gesture.isChecked()
        audio = self.audio.current() or "nc"
        flicker = self.flicker.current() or "60"
        image = {}
        self.settings.beginGroup("image")
        for key in self.settings.childKeys():
            try:
                image[key] = int(self.settings.value(key))
            except (TypeError, ValueError):
                pass
        self.settings.endGroup()
        c = self.controller

        def restore() -> bool:
            c.move_to(pan, tilt)
            # Auto modes first, otherwise the camera rejects manual values.
            for name in sorted(image, key=lambda n: n not in AUTO_CONTROLS):
                try:
                    c.set(name, image[name])
                except (backend.PixyError, KeyError):
                    pass
            c.flicker(flicker)
            c.tracking(tracking)
            c.gesture(gesture)
            c.audio(audio)
            return True

        self.position = (pan, tilt)
        self.pad.set_position(pan, tilt)
        self.worker.submit(restore, done=lambda _: self.notify("Saved camera settings restored"))
        self.apply_zoom()
        self.load_image_controls()

    def save_position(self) -> None:
        pan, tilt = self.position
        self.settings.setValue("camera/pan", pan)
        self.settings.setValue("camera/tilt", tilt)
        self.settings.setValue("camera/zoom", self.zoom_value)

    # ------------------------------------------------------------------
    # Camera preview
    # ------------------------------------------------------------------

    @staticmethod
    def find_pixy_camera():
        for device in QMediaDevices.videoInputs():
            name = device.description().upper()
            if "EMEET" in name and "PIXY" in name and "VIRTUAL" not in name:
                return device
        return None

    def populate_resolutions(self, device) -> None:
        """One entry per resolution; prefer the format with the highest frame rate (MJPEG)."""
        formats = {}
        for fmt in device.videoFormats():
            size = fmt.resolution()
            key = f"{size.width()}x{size.height()}"
            existing = formats.get(key)
            if existing is None or fmt.maxFrameRate() > existing.maxFrameRate():
                formats[key] = fmt
        ordered = sorted(formats.items(), reverse=True,
                         key=lambda i: i[1].resolution().width() * i[1].resolution().height())
        self.camera_formats = dict(ordered)
        saved = str(self.settings.value("camera/resolution", "3840x2160"))
        self.resolution.blockSignals(True)
        self.resolution.clear()
        for index, (key, fmt) in enumerate(ordered):
            size = fmt.resolution()
            self.resolution.addItem(f"{size.width()} × {size.height()} · {round(fmt.maxFrameRate())} fps", key)
            if key == saved:
                self.resolution.setCurrentIndex(index)
        self.resolution.blockSignals(False)
        self.populate_fps()

    def selected_resolution(self) -> tuple[int, int]:
        try:
            w, h = (int(x) for x in str(self.resolution.currentData()).split("x", 1))
            return w, h
        except ValueError:
            return 1280, 720

    def selected_format(self):
        return self.camera_formats.get(str(self.resolution.currentData()))

    def populate_fps(self) -> None:
        fmt = self.selected_format()
        rates = {round(fmt.minFrameRate()), round(fmt.maxFrameRate())} if fmt is not None else {30}
        saved = self.int_setting("virtual/fps", 30)
        self.fps.blockSignals(True)
        self.fps.clear()
        for rate in sorted(rates):
            self.fps.addItem(f"{rate} fps", rate)
        index = self.fps.findData(saved)
        self.fps.setCurrentIndex(index if index >= 0 else 0)
        self.fps.blockSignals(False)

    def fps_changed(self) -> None:
        self.settings.setValue("virtual/fps", self.fps.currentData())

    def resolution_changed(self) -> None:
        if not self.camera_formats:
            return
        self.settings.setValue("camera/resolution", str(self.resolution.currentData()))
        self.populate_fps()
        if self.mode == PREVIEW:
            self.switch_camera_format()
        self.hw_zoom_sent = None
        self.apply_zoom()

    def switch_camera_format(self) -> None:
        """Change resolution on the running camera.

        Destroying the QCamera and opening a new one right away races with
        Qt's deferred teardown: the new instance sometimes gets the device
        while the old one still holds it and never receives a frame.
        Reusing the same QCamera avoids that.
        """
        fmt = self.selected_format()
        if self.camera is None or fmt is None:
            self.stop_camera()
            self.start_camera()
            return
        self.camera.stop()
        self.camera.setCameraFormat(fmt)
        self.camera.start()
        self.arm_frame_watchdog()

    def start_camera(self) -> None:
        device = self.find_pixy_camera()
        if device is None:
            self.device_label.setText("Camera not found")
            self.show_info("🔌", "EMEET PIXY not found", "Connect the camera; the preview starts automatically.")
            QTimer.singleShot(3000, self.retry_camera)
            return
        self.device_label.setText(device.description())
        if not self.camera_formats:
            self.populate_resolutions(device)
        self.capture_session = QMediaCaptureSession(self)
        self.camera = QCamera(device, self)
        fmt = self.selected_format()
        if fmt is not None:
            self.camera.setCameraFormat(fmt)
        self.capture_session.setCamera(self.camera)
        self.capture_session.setVideoOutput(self.view.video)
        self.camera.errorOccurred.connect(lambda _e, text: self.notify(f"Camera error: {text}", 8000))
        self.camera.activeChanged.connect(lambda _active: self.update_hud())
        self.preview_stack.setCurrentWidget(self.view)
        self.camera.start()
        self.arm_frame_watchdog()

    def check_setup(self, show_if_needed: bool = True) -> None:
        """Flag missing system pieces; open the dialog once per new problem set."""
        checks = run_checks()
        problems = sorted(c.key for c in checks if not c.ok and c.required)
        self.setup_button.setText("⚠ Setup" if problems else "⚙ Setup")
        self.setup_button.setObjectName("danger" if problems else "")
        self.setup_button.style().unpolish(self.setup_button)
        self.setup_button.style().polish(self.setup_button)
        signature = ",".join(problems)
        if show_if_needed and needs_attention(checks) and signature != self.settings.value("setup/dismissed", ""):
            self.settings.setValue("setup/dismissed", signature)
            self.open_setup()

    def open_setup(self) -> None:
        SetupDialog(self).exec()
        self.check_setup(show_if_needed=False)
        self.refresh_virtual_device()

    def mark_frame(self, _frame) -> None:
        self.last_frame_at = time.monotonic()

    def arm_frame_watchdog(self) -> None:
        """Give a (re)started camera a grace period before judging it stalled."""
        self.last_frame_at = time.monotonic()

    def check_frames(self) -> None:
        """Restart the camera if the stream silently stops delivering frames."""
        streaming = self.mode in (PREVIEW, VIRTUAL_PROCESSED) and self.camera is not None
        if not streaming or self.recovering or time.monotonic() - self.last_frame_at < 3.0:
            return
        self.recovering = True
        self.notify("Camera stream stalled – restarting it", 5000)
        self.stop_camera()

        def restart() -> None:
            self.recovering = False
            if self.mode in (PREVIEW, VIRTUAL_PROCESSED) and self.camera is None:
                self.start_camera()

        # Let Qt finish releasing the device before reopening it.
        QTimer.singleShot(600, restart)

    def retry_camera(self) -> None:
        if self.camera is None and self.mode == PREVIEW:
            self.start_camera()
            self.update_mode_ui()

    def stop_camera(self) -> None:
        if self.camera is not None:
            self.camera.stop()
            self.camera.deleteLater()
            self.camera = None
        if self.capture_session is not None:
            self.capture_session.deleteLater()
            self.capture_session = None

    def show_info(self, icon: str, heading: str, text: str) -> None:
        self.info_panel.show_message(icon, heading, text)
        self.preview_stack.setCurrentWidget(self.info_panel)

    def toggle_release(self) -> None:
        if self.mode == PREVIEW:
            self.stop_camera()
            self.mode = RELEASED
            self.show_info(
                "📡", "Camera released",
                "The EMEET PIXY is free for Google Meet, OBS, Teams and other apps.\n"
                "Pan/tilt, tracking, privacy and picture controls remain active.")
            self.notify("Camera available to other applications")
        elif self.mode == RELEASED:
            self.mode = PREVIEW
            self.start_camera()
            self.notify("Preview resumed")
        self.update_mode_ui()

    def update_mode_ui(self) -> None:
        streaming_here = self.mode in (PREVIEW, VIRTUAL_PROCESSED)
        self.release_button.setText("Resume preview" if self.mode == RELEASED else "Release camera")
        self.release_button.setEnabled(self.mode in (PREVIEW, RELEASED))
        self.resolution.setEnabled(self.mode == PREVIEW)
        self.snapshot_button.setEnabled(streaming_here)
        self.view.setEnabled(streaming_here)
        if not streaming_here:
            self.view.set_processed(None)
        if hasattr(self, "bg_status"):
            self.update_background_status()
        self.hw_zoom_sent = None
        self.update_autoframe_availability()
        self.apply_zoom()

    def update_hud(self) -> None:
        if self.mode not in (PREVIEW, VIRTUAL_PROCESSED):
            return
        live = self.camera is not None and self.camera.isActive()
        w, h = self.selected_resolution()
        left = f"{'● LIVE' if live else '○ starting'}  ·  {w}×{h}"
        if self.mode == VIRTUAL_PROCESSED:
            left += f"  ·  → virtual cam {self.output_fps:.0f} fps"
        right = []
        if self.autoframe.isChecked():
            right.append("AUTO-FRAME")
        if self.zoom_value > ZOOM_MIN:
            right.append(f"{self.zoom_value / 100:.1f}×")
        self.view.set_hud(left, "  ·  ".join(right))

    # ------------------------------------------------------------------
    # Frames for the software features
    # ------------------------------------------------------------------

    def on_video_frame(self, frame: QVideoFrame) -> None:
        if np is None or not self.processor.wants_frames or self.processor.busy():
            return
        if frame.pixelFormat() != QVideoFrameFormat.PixelFormat.Format_Jpeg:
            return
        if not frame.map(QVideoFrame.MapMode.ReadOnly):
            return
        try:
            # Copy while the buffer is guaranteed valid; decode off-thread.
            jpeg = np.frombuffer(frame.bits(0), np.uint8, frame.mappedBytes(0)).copy()
        finally:
            frame.unmap()
        self.processor.submit(jpeg, frame.width())

    def on_faces(self, faces: list) -> None:
        self.view.set_faces(faces)
        if not self.autoframe.isChecked():
            return
        if faces:
            self.last_faces_at = time.monotonic()
            fill = FRAMING.get(self.framing.current() or "medium", 0.45)
            self.smoother.set_target(framing_target(faces, fill=fill))
        elif time.monotonic() - self.last_faces_at > 2.5:
            self.smoother.set_target(Crop())

    def crop_tick(self) -> None:
        now = time.monotonic()
        dt, self.last_tick = now - self.last_tick, now
        if self.autoframe.isChecked() and self.digital_zoom_allowed():
            crop = self.smoother.step(dt)
            crop = Crop(crop.cx, crop.cy, max(crop.zoom, self.min_digital_zoom()))
            zoom = round(crop.zoom * 100)
            if zoom != self.zoom_value:
                self.zoom_value = zoom
                self.sync_zoom_widgets()
        else:
            digital = self.zoom_value / self.hw_zoom_for(self.zoom_value) if self.digital_zoom_allowed() else 1.0
            crop = Crop(*self.manual_center, max(digital, self.min_digital_zoom())).clamped()
            self.manual_center = (crop.cx, crop.cy)
        if crop != self.view.crop:
            self.view.set_crop(crop)
            self.processor.set_crop(self.view.crop)

    # ------------------------------------------------------------------
    # Zoom (hardware first, then digital)
    # ------------------------------------------------------------------

    def stream_fps(self) -> int:
        if self.mode == VIRTUAL_DIRECT:
            return int(self.fps.currentData() or 30)
        fmt = self.selected_format()
        return round(fmt.maxFrameRate()) if fmt is not None else 30

    def hw_zoom_allowed(self) -> bool:
        """The PIXY ignores zoom_absolute above 1080p and at 1080p60."""
        if self.mode == RELEASED:
            return True  # the other application picks the mode
        width, _ = self.selected_resolution()
        return width < 1920 or (width == 1920 and self.stream_fps() <= 30)

    def digital_zoom_allowed(self) -> bool:
        return self.mode in (PREVIEW, VIRTUAL_PROCESSED)

    def max_zoom(self) -> int:
        if self.digital_zoom_allowed():
            return ZOOM_MAX
        return HW_ZOOM_MAX if self.hw_zoom_allowed() else ZOOM_MIN

    def hw_zoom_for(self, zoom: int) -> int:
        return min(zoom, HW_ZOOM_MAX) if self.hw_zoom_allowed() else ZOOM_MIN

    def set_zoom(self, value: int, from_slider: bool = False, flash: bool = False) -> None:
        if self.autoframe.isChecked() and self.digital_zoom_allowed():
            if not from_slider:
                self.notify("Auto-framing controls the zoom (press F to turn it off)")
            return
        self.zoom_value = max(ZOOM_MIN, min(self.max_zoom(), int(value)))
        self.apply_zoom()
        if flash:
            self.view.flash(f"{self.zoom_value / 100:.1f}×")
        self.settings.setValue("camera/zoom", self.zoom_value)

    def apply_zoom(self) -> None:
        self.zoom_value = max(ZOOM_MIN, min(self.max_zoom(), self.zoom_value))
        hw = self.hw_zoom_for(self.zoom_value)
        if hw != self.hw_zoom_sent:
            self.hw_zoom_sent = hw
            self.worker.submit(self.controller.set_zoom, hw, key="zoom")
        self.sync_zoom_widgets()

    def sync_zoom_widgets(self) -> None:
        maximum = self.max_zoom()
        auto = self.autoframe.isChecked() and self.digital_zoom_allowed()
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setMaximum(maximum)
        self.zoom_slider.setValue(self.zoom_value)
        self.zoom_slider.blockSignals(False)
        self.zoom_slider.setEnabled(maximum > ZOOM_MIN and not auto)
        if auto:
            tip = "Zoom is controlled by auto-framing"
        elif maximum == ZOOM_MIN:
            tip = "Zoom unavailable here: the PIXY ignores hardware zoom above 1080p30"
        elif self.digital_zoom_allowed():
            tip = "Hardware zoom up to 1.5× where the video mode allows it, digital zoom beyond"
        else:
            tip = "EMEET PIXY hardware zoom"
        self.zoom_slider.setToolTip(tip)
        self.zoom_label.setText(f"{self.zoom_value / 100:.1f}×")
        self.update_hud()

    def on_preview_drag(self, dx: float, dy: float) -> None:
        if self.autoframe.isChecked():
            return
        if self.view.crop.zoom > 1.001:
            cx, cy = self.manual_center
            self.manual_center = (cx + dx, cy + dy)
        else:
            # Not digitally zoomed: dragging the picture turns the camera.
            self.move_target = [self.move_target[0] + dx * FOV_H, self.move_target[1] - dy * FOV_V] \
                if self.pad.target else [self.position[0] + dx * FOV_H, self.position[1] - dy * FOV_V]
            self.aim_at(round(self.move_target[0]), round(self.move_target[1]))

    def on_preview_double_click(self, nx: float, ny: float) -> None:
        if self.autoframe.isChecked():
            return
        if self.view.crop.zoom > 1.001:
            self.manual_center = (nx, ny)
        else:
            pan, tilt = self.position
            self.aim_at(round(pan + (nx - 0.5) * FOV_H), round(tilt - (ny - 0.5) * FOV_V))

    # ------------------------------------------------------------------
    # Pan / tilt
    # ------------------------------------------------------------------

    def aim_at(self, pan: int, tilt: int) -> None:
        self.processor.pause_stabilization(1.2)
        pan = max(-PAN_LIMIT, min(PAN_LIMIT, pan))
        tilt = max(TILT_MIN, min(TILT_MAX, tilt))
        self.position = (pan, tilt)
        self.pad.target = (pan, tilt)
        self.pad.update()
        self.worker.submit(self.controller.move_to, pan, tilt, key="pantilt")

    def start_move(self, dx: int, dy: int) -> None:
        if dx:
            self.move_dir[0] = dx
        if dy:
            self.move_dir[1] = dy
        if not self.move_timer.isActive():
            self.move_target = [float(self.position[0]), float(self.position[1])]
            self.move_started = time.monotonic()
            self.move_timer.start()
            self.move_tick()

    def stop_move(self, dx: int, dy: int) -> None:
        if dx and self.move_dir[0] == dx:
            self.move_dir[0] = 0
        if dy and self.move_dir[1] == dy:
            self.move_dir[1] = 0
        if self.move_dir == [0, 0]:
            self.move_timer.stop()
            self.pad.target = None
            QTimer.singleShot(400, self.poll_position)

    def move_tick(self) -> None:
        held = time.monotonic() - self.move_started
        speed = 18 + min(held, 1.5) / 1.5 * 52  # deg/s, accelerating while held
        step = max(1.0, speed * self.move_timer.interval() / 1000)
        self.move_target[0] = max(-PAN_LIMIT, min(PAN_LIMIT, self.move_target[0] + self.move_dir[0] * step))
        self.move_target[1] = max(TILT_MIN, min(TILT_MAX, self.move_target[1] + self.move_dir[1] * step))
        pan, tilt = round(self.move_target[0]), round(self.move_target[1])
        self.processor.pause_stabilization(0.8)
        self.position = (pan, tilt)
        self.pad.set_position(pan, tilt)
        self.worker.submit(self.controller.move_to, pan, tilt, key="pantilt")

    def poll_position(self) -> None:
        if self.move_timer.isActive() or self.pad.dragging:
            return
        self.worker.submit(self.controller.position, key="poll", done=self.on_position)

    def on_position(self, position) -> None:
        if self.move_timer.isActive() or self.pad.dragging:
            return
        pan, tilt, _zoom = position
        self.position = (pan, tilt)
        self.pad.set_position(pan, tilt)

    def center_camera(self) -> None:
        self.manual_center = (0.5, 0.5)
        self.aim_at(0, 0)
        if not self.autoframe.isChecked():
            self.set_zoom(ZOOM_MIN, flash=True)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def preset(self, slot: int) -> tuple[int, int, int] | None:
        value = self.settings.value(f"presets/{slot}")
        if not value:
            return None
        try:
            pan, tilt, zoom = (int(v) for v in str(value).split(","))
        except ValueError:
            return None
        return pan, tilt, zoom

    def startup_position_changed(self) -> None:
        self.settings.setValue("presets/startup", self.startup_position.currentData())
        self.refresh_preset_buttons()

    def refresh_preset_buttons(self) -> None:
        startup = str(self.startup_position.currentData())
        for slot, button in enumerate(self.preset_buttons, start=1):
            preset = self.preset(slot)
            is_startup = startup == str(slot)
            button.setProperty("filled", preset is not None)
            button.setProperty("startup", is_startup)
            button.setText(f"★ {slot}" if is_startup else str(slot))
            if preset is None:
                button.setToolTip(f"Preset {slot}: empty – click to store the current position")
            else:
                pan, tilt, zoom = preset
                extra = " · startup position" if is_startup else ""
                button.setToolTip(f"Preset {slot}: pan {pan:+d}°, tilt {tilt:+d}°, zoom {zoom / 100:.1f}×{extra}")
            button.style().unpolish(button)
            button.style().polish(button)

    def preset_clicked(self, slot: int) -> None:
        if self.preset(slot) is None:
            self.store_preset(slot)
        else:
            self.recall_preset(slot)

    def store_preset(self, slot: int) -> None:
        pan, tilt = self.position
        self.settings.setValue(f"presets/{slot}", f"{pan},{tilt},{self.zoom_value}")
        self.refresh_preset_buttons()
        self.notify(f"Preset {slot} stored (pan {pan:+d}°, tilt {tilt:+d}°)")

    def recall_preset(self, slot: int) -> None:
        preset = self.preset(slot)
        if preset is None:
            self.notify(f"Preset {slot} is empty")
            return
        pan, tilt, zoom = preset
        self.aim_at(pan, tilt)
        if not self.autoframe.isChecked():
            self.manual_center = (0.5, 0.5)
            self.set_zoom(zoom)
        self.notify(f"Preset {slot}")

    def preset_menu(self, slot: int) -> None:
        filled = self.preset(slot) is not None
        menu = QMenu(self)
        menu.addAction("Go to preset", lambda: self.recall_preset(slot)).setEnabled(filled)
        menu.addAction("Store current position here", lambda: self.store_preset(slot))
        menu.addAction(
            "Use as startup position",
            lambda: self.startup_position.setCurrentIndex(self.startup_position.findData(str(slot))),
        ).setEnabled(filled)

        def clear() -> None:
            self.settings.remove(f"presets/{slot}")
            if self.startup_position.currentData() == str(slot):
                self.startup_position.setCurrentIndex(0)
            self.refresh_preset_buttons()

        menu.addAction("Clear", clear).setEnabled(filled)
        menu.exec(self.cursor().pos())

    # ------------------------------------------------------------------
    # On-board AI / audio / picture
    # ------------------------------------------------------------------

    def show_tracking_state(self) -> None:
        mode = self.tracking_mode
        self.tracking.set_current(mode)
        self.pill_tracking.setText({"idle": "Tracking off", "track": "Face tracking", "privacy": "Privacy"}[mode])
        set_state(self.pill_tracking, {"idle": "", "track": "on", "privacy": "warn"}[mode])

    def set_tracking_mode(self, mode: str, by_timer: bool = False) -> None:
        if mode == "privacy" and self.tracking_mode != "privacy":
            self.mode_before_privacy = self.tracking_mode
        self.privacy_by_timer = by_timer and mode == "privacy"
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
                except backend.PixyError:
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
            for name in sorted(defaults, key=lambda n: n not in AUTO_CONTROLS):
                try:
                    self.controller.set(name, defaults[name])
                except backend.PixyError:
                    pass
            return True

        def done(_result) -> None:
            self.load_image_controls()
            self.notify("Picture reset to camera defaults")

        self.worker.submit(reset, done=done)

    # ------------------------------------------------------------------
    # Background replacement
    # ------------------------------------------------------------------

    def apply_background(self) -> None:
        if not vision_available():
            return
        mode = self.bg_mode.current() or "off"
        fill = self.bg_fill.current() or "gradient"
        background = Background(
            mode=mode, fill=fill, color=self.bg_color, image_path=self.bg_image_path,
            similarity=self.bg_similarity.value() / 100,
            smoothness=self.bg_smoothness.value() / 100,
            spill=self.bg_spill.value() / 100,
            blur=float(self.bg_blur.value()),
        )
        self.processor.set_background(background)
        for key, value in (("mode", mode), ("fill", fill), ("color", ",".join(map(str, self.bg_color))),
                           ("image", self.bg_image_path), ("similarity", self.bg_similarity.value()),
                           ("smoothness", self.bg_smoothness.value()), ("spill", self.bg_spill.value()),
                           ("blur", self.bg_blur.value())):
            self.settings.setValue(f"background/{key}", value)
        if mode == "off":
            self.view.set_processed(None)
        self.update_background_status()

    def background_fill_selected(self, fill: str) -> None:
        if fill == "image" and not self.bg_image_path:
            self.choose_background_image()
        self.apply_background()

    def choose_background_color(self) -> None:
        b, g, r = self.bg_color
        color = QColorDialog.getColor(QColor(r, g, b), self, "Background color")
        if color.isValid():
            self.bg_color = (color.blue(), color.green(), color.red())
            self.bg_fill.set_current("color")
            self.apply_background()

    def choose_background_image(self) -> None:
        start = str(Path(self.bg_image_path).parent if self.bg_image_path else Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(self, "Background image", start,
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.bg_image_path = path
            self.bg_fill.set_current("image")
            self.apply_background()
        elif not self.bg_image_path:
            self.bg_fill.set_current("gradient")

    def update_background_status(self) -> None:
        mode = self.bg_mode.current() or "off"
        name = Path(self.bg_image_path).name if self.bg_image_path else "no image chosen"
        self.bg_image_label.setText(f"Image: {name}" if self.bg_fill.current() == "image" else "")
        self.bg_blur.setVisible(self.bg_fill.current() == "blur")
        green = self.processor.key is not None
        if mode == "off":
            text = ""
        elif mode in ("auto", "chroma") and green:
            text = "🟢 Green screen detected – keying it"
        elif mode in ("auto", "ai") and not matting_available():
            text = "AI cutout needs onnxruntime: pip install 'pixydeck[ai]'"
        elif mode in ("auto", "ai"):
            text = "🧠 AI cutout active" + (" – no green screen in view" if mode == "auto" else "")
        else:
            text = "Waiting for a green screen in the picture…"
        if mode != "off" and not self.digital_zoom_allowed():
            text = "Only in the preview and the processed virtual camera"
        self.bg_status.setText(text)

    def on_green_screen(self, key) -> None:
        if key is None and self.bg_mode.current() == "chroma":
            self.view.set_processed(None)
        self.notify("Green screen detected" if key is not None else "Green screen no longer in view")
        self.update_background_status()

    def on_processed_preview(self) -> None:
        image = self.processor.take_preview()
        processed = self.processor.background_active or self.processor.stabilizing
        if processed and self.digital_zoom_allowed():
            self.view.set_processed(image)
        else:
            self.view.set_processed(None)

    # ------------------------------------------------------------------
    # Auto-framing
    # ------------------------------------------------------------------

    def set_autoframe(self, enabled: bool) -> None:
        self.settings.setValue("ai/autoframe", enabled)
        self.smoother.current = self.view.crop if enabled else Crop()
        self.smoother.target = self.smoother.current
        if not enabled:
            self.zoom_value = ZOOM_MIN
            self.manual_center = (0.5, 0.5)
        self.update_autoframe_availability()
        self.apply_zoom()
        self.notify("Auto-framing on" if enabled else "Auto-framing off")

    def set_show_faces(self, enabled: bool) -> None:
        self.settings.setValue("ai/show_faces", enabled)
        self.view.show_faces = enabled
        self.update_autoframe_availability()
        if not enabled:
            self.view.set_faces([])

    def update_autoframe_availability(self) -> None:
        wants = self.autoframe.isChecked() or self.show_faces.isChecked()
        self.processor.set_detection(self.digital_zoom_allowed() and wants)

    # ------------------------------------------------------------------
    # Privacy timer
    # ------------------------------------------------------------------

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

        watching_here = self.mode in (PREVIEW, VIRTUAL_PROCESSED) and self.isVisible() and not self.isMinimized()
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

    # ------------------------------------------------------------------
    # Virtual camera
    # ------------------------------------------------------------------

    def virtual_mode_changed(self, mode: str) -> None:
        self.settings.setValue("virtual/mode", mode)
        self.update_virtual_mode_ui()
        self.refresh_virtual_device()

    def update_virtual_mode_ui(self) -> None:
        processed = self.virtual_mode.current() == VIRTUAL_PROCESSED
        if processed and not vision_available():
            hint = "Processed mode needs the optional AI extra (OpenCV)."
        elif processed:
            hint = ("Keeps the preview running and sends exactly what you see – digital zoom "
                    "and auto-framing included.")
        else:
            hint = "Lowest CPU use: FFmpeg forwards the camera unchanged. Hardware zoom only."
        self.virtual_mode_hint.setText(hint)
        self.output_size_row.setVisible(processed)
        self.fps_row.setVisible(not processed)
        self.virtual_mode.setEnabled(self.mode not in (VIRTUAL_DIRECT, VIRTUAL_PROCESSED))

    def refresh_virtual_device(self) -> None:
        device = find_virtual_camera_device()
        running = self.mode in (VIRTUAL_DIRECT, VIRTUAL_PROCESSED)
        if device:
            self.virtual_device_status.setText(f"Device: ready – {device}")
        else:
            self.virtual_device_status.setText("Device: missing – open ⚙ Setup to create it")
        processed_ok = self.virtual_mode.current() != VIRTUAL_PROCESSED or vision_available()
        self.virtual_start.setEnabled(bool(device) and bool(FFMPEG) and not running and processed_ok)

    def start_virtual_camera(self) -> None:
        if self.mode in (VIRTUAL_DIRECT, VIRTUAL_PROCESSED):
            return
        virtual_device = find_virtual_camera_device()
        if virtual_device is None or not FFMPEG:
            self.notify("Virtual camera device or FFmpeg missing", 6000)
            return
        self.mode_before_virtual = self.mode
        if self.virtual_mode.current() == VIRTUAL_PROCESSED:
            self.start_processed_virtual(virtual_device)
        else:
            self.start_direct_virtual(virtual_device)

    def start_processed_virtual(self, virtual_device: str) -> None:
        out_w, out_h = (int(x) for x in str(self.output_size.currentData()).split("x"))
        src_w, src_h = self.selected_resolution()
        if out_w > src_w:
            out_w, out_h = src_w - src_w % 2, src_h - src_h % 2
        if self.mode == RELEASED:
            self.start_camera()
        try:
            self.processor.start_output(FFMPEG, virtual_device, out_w, out_h, self.stream_fps())
        except OSError as exc:
            self.notify(f"Virtual camera error: {exc}", 8000)
            return
        self.mode = VIRTUAL_PROCESSED
        self.virtual_status.setText(f"Pipeline: processed – {out_w} × {out_h}")
        self.on_virtual_started()

    def start_direct_virtual(self, virtual_device: str) -> None:
        physical = self.controller.video_device()
        if physical is None:
            self.notify("EMEET PIXY capture device not found", 6000)
            return
        resolution = str(self.resolution.currentData() or "1280x720")
        fps = int(self.fps.currentData() or 30)
        self.stop_camera()
        self.mode = VIRTUAL_DIRECT
        self.show_info(
            "🎥", "Virtual camera active",
            f"The PIXY feeds “{VIRTUAL_NAME}” directly ({resolution.replace('x', ' × ')} @ {fps} fps).\n"
            "Select it in Meet, OBS or Teams. Camera controls remain active.")
        process = QProcess(self)
        process.setProgram(FFMPEG)
        process.setArguments([
            "-hide_banner", "-loglevel", "warning",
            "-f", "v4l2", "-input_format", "mjpeg", "-video_size", resolution, "-framerate", str(fps),
            "-i", physical,
            "-vf", "format=yuv420p", "-f", "v4l2", virtual_device,
        ])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(self.virtual_process_finished)
        process.errorOccurred.connect(self.virtual_process_error)
        self.virtual_process = process
        # Give Qt a moment to fully release the physical device.
        QTimer.singleShot(350, process.start)
        self.virtual_status.setText(f"Pipeline: direct – {resolution.replace('x', ' × ')} @ {fps} fps")
        self.on_virtual_started()

    def on_virtual_started(self) -> None:
        self.pill_virtual.setText("Virtual cam on")
        set_state(self.pill_virtual, "on")
        self.virtual_start.setEnabled(False)
        self.virtual_stop.setEnabled(True)
        self.update_virtual_mode_ui()
        self.update_mode_ui()
        self.notify(f"{VIRTUAL_NAME} running")

    def stop_virtual_camera(self, restore: bool = True) -> None:
        self.virtual_stopping = True
        self.processor.stop_output()
        process, self.virtual_process = self.virtual_process, None
        if process is not None:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(2000):
                    process.kill()
                    process.waitForFinished(1000)
            process.deleteLater()
        self.virtual_stopping = False
        was_direct = self.mode == VIRTUAL_DIRECT
        self.mode = PREVIEW
        self.output_fps = 0.0
        self.virtual_status.setText("Pipeline: stopped")
        self.pill_virtual.setText("Virtual cam off")
        set_state(self.pill_virtual, "")
        self.virtual_stop.setEnabled(False)
        if restore:
            if self.mode_before_virtual == RELEASED:
                self.toggle_release()  # PREVIEW -> RELEASED, stops our stream
            elif was_direct:
                QTimer.singleShot(300, lambda: (self.start_camera(), self.update_mode_ui()))
        self.update_virtual_mode_ui()
        self.refresh_virtual_device()
        self.update_mode_ui()

    def virtual_process_finished(self, exit_code, _status) -> None:
        if self.virtual_stopping or self.mode != VIRTUAL_DIRECT or self.virtual_process is None:
            return
        output = bytes(self.virtual_process.readAll()).decode(errors="replace").strip()
        self.notify(f"Virtual camera stopped ({exit_code}) {output[-160:]}", 10000)
        self.stop_virtual_camera(True)

    def virtual_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.mode == VIRTUAL_DIRECT:
            self.notify("FFmpeg failed to start", 8000)
            self.stop_virtual_camera(True)

    def on_processed_output_error(self, message: str) -> None:
        self.notify(f"Virtual camera stopped: {message[-160:]}", 10000)
        if self.mode == VIRTUAL_PROCESSED:
            self.stop_virtual_camera(True)

    def on_output_fps(self, fps: float) -> None:
        self.output_fps = fps
        self.update_hud()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def save_snapshot(self) -> None:
        if self.mode not in (PREVIEW, VIRTUAL_PROCESSED):
            return
        if self.view.processed.isVisible():
            image = self.view.processed.pixmap().toImage()
        else:
            image = self.view.video.videoSink().videoFrame().toImage()
        if image.isNull():
            self.notify("No frame available yet")
            return
        x, y, w, h = self.view.crop.rect()
        image = image.copy(round(x * image.width()), round(y * image.height()),
                           round(w * image.width()), round(h * image.height()))
        folder = Path.home() / "Pictures" / "EMEET PIXY"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"pixy-{datetime.now():%Y%m%d-%H%M%S}.png"
        if image.save(str(path)):
            self.view.flash("📷 Saved")
            self.notify(f"Snapshot saved to {path}", 6000)
        else:
            self.notify("Could not save snapshot")

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        try:
            pan, tilt, _zoom = self.controller.position()
            self.position = (pan, tilt)
        except backend.PixyError:
            pass
        self.save_position()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.sync()
        if self.mode in (VIRTUAL_DIRECT, VIRTUAL_PROCESSED):
            self.stop_virtual_camera(False)
        if self.mic_muted_by_us:
            set_pixy_microphone_muted(False)
        self.stop_camera()
        self.processor.shutdown()
        self.status_worker.shutdown(timeout=1.0)
        self.worker.shutdown()
        self.controller.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    app.setStyleSheet(THEME)
    window = PixyGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
