#!/usr/bin/env python3
"""EMEET PixyDeck - PySide6 desktop application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import logging
import sys
import time

from PySide6.QtCore import QEvent, QObject, QProcess, QSettings, QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoFrame, QVideoFrameFormat
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import APP_ID, APP_NAME, __version__, backend
from .backend import PixyController
from .background_panel import BackgroundMixin
from .constants import (
    FOV_H,
    FOV_V,
    FACE_LOST_AFTER,
    FIND_ME_AFTER,
    FIND_ME_COOLDOWN,
    FIND_ME_MIN_GAP,
    FRAMING,
    HW_ZOOM_MAX,
    PAN_LIMIT,
    PRESET_SLOTS,
    PREVIEW,
    RELEASED,
    TILT_MAX,
    TILT_MIN,
    TRACKING_MAX_ZOOM,
    VIRTUAL_DIRECT,
    VIRTUAL_PROCESSED,
    ZOOM_MAX,
    ZOOM_MIN,
)
from .controls import ControlsMixin, apply_controls
from .diagnostics import install_qt_message_handler, log_file, setup_logging
from .presets import PresetsMixin
from .privacy import PACTL, CallDetector, PrivacyMixin, set_default_microphone, set_pixy_microphone_muted
from .setup import SetupDialog, needs_attention, run_checks
from .virtual_camera import VirtualCameraMixin
from .vision import Crop, FrameProcessor, Smoother, framing_target, vision_available
from .widgets import Card, InfoPanel, PreviewView, PtzPad, SettingRow, SliderRow, THEME, WheelGuard
from .worker import ControlWorker

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional extra
    np = None

log = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent
ICON = PACKAGE_DIR / "assets" / "pixydeck.svg"


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


def migrate_settings(settings: QSettings) -> None:
    """Carry settings over from emeet-pixy-control, the project PixyDeck grew from."""
    if settings.allKeys():
        return
    old = QSettings("emeet-pixy", "control")
    for key in old.allKeys():
        settings.setValue(key, old.value(key))
    settings.sync()


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


class PixyGUI(ControlsMixin, PresetsMixin, BackgroundMixin, PrivacyMixin, VirtualCameraMixin, QMainWindow):
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
        self.last_face_seen_at = 0.0  # any face, also without auto-framing
        self.seat_tilt: float | None = None
        self.find_me_at = 0.0
        self.last_tick = time.monotonic()
        self.output_fps = 0.0

        self.move_dir = [0, 0]
        self.move_target = [0.0, 0.0]
        self.move_started = 0.0

        self.tracking_mode = "idle"
        self.mode_before_privacy = "idle"
        self.privacy_by_timer = False
        self.privacy_by_call = False
        self.call_detector = CallDetector()
        self.microphone_before_call: str | None = None
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
        self.wheel_guard = WheelGuard(self)
        QApplication.instance().installEventFilter(self.wheel_guard)

        self.start_camera()
        self.refresh_virtual_device()
        self.update_mode_ui()
        # After the camera state is restored, so the pipeline starts with it.
        QTimer.singleShot(1500, self, self.autostart_virtual_camera)

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
        QTimer.singleShot(600, self, self.restore_camera_state)
        QTimer.singleShot(1500, self, self.check_setup)

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
        version = QLabel(f"v{__version__}", objectName="subtle")
        version.setToolTip(f"Log file: {log_file()}")
        header.addWidget(version)
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
        for build, name in (
            (self.build_camera_tab, "Camera"),
            (self.build_tracking_tab, "Tracking"),
            (self.build_image_tab, "Image"),
            (self.build_background_tab, "Effects"),
            (self.build_calls_tab, "Calls"),
            (self.build_output_tab, "Output"),
        ):
            self.tabs.addTab(self.scroll(build()), name)
        self.tabs.setCurrentIndex(max(0, min(self.tabs.count() - 1, self.int_setting("ui/tab", 0))))
        self.tabs.currentChanged.connect(lambda index: self.settings.setValue("ui/tab", index))
        for card in self.tabs.findChildren(Card):
            if card.key:
                saved = self.settings.value(f"ui/expanded/{card.key}")
                if saved is not None:
                    card.set_expanded(str(saved).lower() == "true", notify=False)
                card.toggled.connect(lambda expanded, k=card.key: self.settings.setValue(f"ui/expanded/{k}", expanded))
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
        self.speed_sliders: dict[str, SliderRow] = {}
        for axis, label, hint in (
            ("pan", "Pan speed", "Turning left and right"),
            ("tilt", "Tilt speed", "Up and down – raise it if tracking loses you when you stand up or sit down"),
        ):
            row = SliderRow(label, backend.MOTOR_SPEED_MIN, backend.MOTOR_SPEED_MAX,
                            backend.MOTOR_SPEED_DEFAULT, fmt=lambda v: f"{v}°/s")
            row.setToolTip(hint + ". Face tracking uses this speed too.")
            row.value_changed.connect(lambda v, a=axis: self.set_motor_speed(a, v))
            aim.body.addWidget(row)
            self.speed_sliders[axis] = row
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
        presets.body.addWidget(self.hint("Click an empty slot to store, a filled one to go there · right-click for more"))
        layout.addWidget(presets)

        startup = Card("Startup position", key="startup", collapsed=True)
        self.startup_position = QComboBox()
        self.startup_position.addItem("Last position", "last")
        for slot in range(1, PRESET_SLOTS + 1):
            self.startup_position.addItem(f"Preset {slot}", str(slot))
        self.startup_position.currentIndexChanged.connect(self.startup_position_changed)
        startup.body.addWidget(SettingRow("When PixyDeck starts", self.startup_position))
        power_on = QPushButton("Save as camera power-on position")
        power_on.setToolTip("The PIXY itself turns to the current position when it powers on – "
                            "also without PixyDeck and on other computers")
        power_on.clicked.connect(self.save_power_on_position)
        startup.body.addWidget(power_on)
        layout.addWidget(startup)
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
        target = str(self.settings.value("camera/target", "auto"))
        self.target.set_current(target if target in backend.TARGET_TRACK_MODES else "auto")
        pan_speed = self.int_setting("camera/motor_speed", backend.MOTOR_SPEED_DEFAULT)
        for axis, key, default in (("pan", "camera/motor_speed", backend.MOTOR_SPEED_DEFAULT),
                                   ("tilt", "camera/tilt_speed", pan_speed)):
            value = self.int_setting(key, default)
            self.speed_sliders[axis].set_value_silently(
                max(backend.MOTOR_SPEED_MIN, min(backend.MOTOR_SPEED_MAX, value)))
        self.flicker.set_current(str(self.settings.value("camera/flicker", "60")))
        self.framing.set_current(str(self.settings.value("ai/framing", "medium")))
        self.show_faces.set_silently(self.bool_setting("ai/show_faces") and vision_available())
        self.view.show_faces = self.show_faces.isChecked()
        self.privacy_enabled.set_silently(self.bool_setting("privacy/enabled"))
        self.privacy_minutes.setValue(self.int_setting("privacy/minutes", 10))
        self.privacy_wake.set_silently(self.bool_setting("privacy/wake", True))
        self.privacy_mic.set_silently(self.bool_setting("privacy/mute_mic") and bool(PACTL))
        # On by default: apps find "EMEET PIXY (PixyDeck)" without anyone pressing Start.
        self.virtual_autostart.set_silently(self.bool_setting("virtual/autostart", True))
        self.find_me.set_silently(self.bool_setting("tracking/find_me", True))
        seat = self.settings.value("tracking/seat_tilt")
        try:
            self.seat_tilt = float(seat) if seat is not None else None
        except (TypeError, ValueError):
            self.seat_tilt = None
        self.calls_enabled.set_silently(self.bool_setting("calls/enabled"))
        start = str(self.settings.value("calls/start", "track"))
        self.calls_start.set_current(start if start in ("track", "keep") else "track")
        self.calls_mic.set_silently(self.bool_setting("calls/microphone") and bool(PACTL))
        self.calls_privacy.set_silently(self.bool_setting("calls/privacy", True))
        self.show_call_state()
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
        # Settings shim: "always" was the green-screen mode before AI matting existed.
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
        target = self.target.current() or "auto"
        speeds = {axis: row.value() for axis, row in self.speed_sliders.items()}
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
            apply_controls(c, image)
            c.flicker(flicker)
            c.tracking(tracking)
            c.gesture(gesture)
            c.audio(audio)
            c.target_track(target)
            for axis, speed in speeds.items():
                c.motor_speed(axis, speed)
            return True

        self.position = (pan, tilt)
        self.pad.set_position(pan, tilt)
        if self.seat_tilt is None:
            self.seat_tilt = float(tilt)  # until Find me has learned where you sit
        self.worker.submit(restore, done=lambda _: self.notify("Saved camera settings restored"))
        self.apply_zoom()
        self.load_image_controls()

    def save_position(self) -> None:
        if self.seat_tilt is not None:
            self.settings.setValue("tracking/seat_tilt", round(self.seat_tilt, 1))
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
            if "EMEET" in name and "PIXY" in name and not backend.is_virtual_camera(device.description()):
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
            QTimer.singleShot(3000, self, self.retry_camera)
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
        streaming = self.streams_frames and self.camera is not None
        if not streaming or self.recovering or time.monotonic() - self.last_frame_at < 3.0:
            return
        self.recovering = True
        if self.processor.showing_placeholder:
            self.notify("Waiting for the camera – another app may be using the PIXY directly", 5000)
        else:
            self.notify("Camera stream stalled – restarting it", 5000)
        self.stop_camera()

        def restart() -> None:
            self.recovering = False
            if self.streams_frames and self.camera is None:
                self.start_camera()

        # Let Qt finish releasing the device before reopening it.
        QTimer.singleShot(600, self, restart)

    def retry_camera(self) -> None:
        if self.camera is None and self.streams_frames:
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
        streaming_here = self.streams_frames
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
        if not self.streams_frames:
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
        if faces:
            self.last_face_seen_at = time.monotonic()
        else:
            self.check_find_me()
        if not self.autoframe.isChecked():
            return
        if faces:
            self.last_faces_at = time.monotonic()
            fill = FRAMING.get(self.framing.current() or "medium", 0.45)
            if self.tracking_mode == "track":
                # The camera already turns towards you; moving the crop as
                # well makes two controllers chase each other (up/down lag
                # when you sit down). Keep the crop centred, only zoom.
                target = framing_target(faces, fill=fill, max_zoom=TRACKING_MAX_ZOOM)
                target = Crop(0.5, 0.5, target.zoom)
            else:
                target = framing_target(faces, fill=fill)
            self.smoother.set_target(target)
        elif time.monotonic() - self.last_faces_at > FACE_LOST_AFTER:
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

    @property
    def streams_frames(self) -> bool:
        """True while PixyDeck itself receives the camera stream."""
        return self.mode in (PREVIEW, VIRTUAL_PROCESSED)

    @property
    def virtual_running(self) -> bool:
        return self.mode in (VIRTUAL_DIRECT, VIRTUAL_PROCESSED)

    def digital_zoom_allowed(self) -> bool:
        return self.streams_frames

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
            QTimer.singleShot(400, self, self.poll_position)

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
        self.learn_seat(tilt)

    # ------------------------------------------------------------------
    # Find me: tilt back to the seat when tracking has lost you
    # ------------------------------------------------------------------

    def find_me_active(self) -> bool:
        return self.find_me.isChecked() and self.tracking_mode == "track"

    def learn_seat(self, tilt: int) -> None:
        """Your seat is the lowest tilt at which the camera keeps seeing you.

        Standing raises the tilt for a while; the estimate drifts up only
        slowly, so a few minutes on your feet do not move the seat.
        """
        if not self.find_me_active() or time.monotonic() - self.last_face_seen_at > 0.5:
            return
        if self.seat_tilt is None or tilt < self.seat_tilt:
            self.seat_tilt = float(tilt)
        else:
            self.seat_tilt += (tilt - self.seat_tilt) * 0.02

    def check_find_me(self) -> None:
        now = time.monotonic()
        if not self.find_me_active() or self.seat_tilt is None:
            return
        if now - self.last_face_seen_at < FIND_ME_AFTER or now - self.find_me_at < FIND_ME_COOLDOWN:
            return
        if self.position[1] - self.seat_tilt < FIND_ME_MIN_GAP:
            return  # already at the seat: you really left
        self.find_me_at = now
        self.worker.submit(self.controller.move_to, None, round(self.seat_tilt), key="find-me")
        self.notify("Lost you – tilting back to your seat", 4000)

    def center_camera(self) -> None:
        self.manual_center = (0.5, 0.5)
        self.aim_at(0, 0)
        if not self.autoframe.isChecked():
            self.set_zoom(ZOOM_MIN, flash=True)


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
        wants = self.autoframe.isChecked() or self.show_faces.isChecked() or self.find_me_active()
        self.processor.set_detection(self.digital_zoom_allowed() and wants)


    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def save_snapshot(self) -> None:
        if not self.streams_frames:
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
        if self.virtual_running:
            self.stop_virtual_camera(False)
        if self.mic_muted_by_us:
            set_pixy_microphone_muted(False)
        if self.microphone_before_call is not None:
            previous, self.microphone_before_call = self.microphone_before_call, None
            set_default_microphone(previous)  # closed mid-call
        self.stop_camera()
        self.processor.shutdown()
        self.status_worker.shutdown(timeout=1.0)
        self.worker.shutdown()
        self.controller.close()
        event.accept()


def main() -> None:
    setup_logging()
    app = QApplication(sys.argv)
    install_qt_message_handler()
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    app.setStyleSheet(THEME)
    window = PixyGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
