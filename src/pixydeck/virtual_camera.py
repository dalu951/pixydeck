"""Processed/direct virtual camera and the Output tab.

Mixed into ``PixyGUI``; methods use the window's widgets and state via ``self``.
"""

from __future__ import annotations

import shutil

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from . import VIRTUAL_CAMERA_NAME
from .backend import find_video_by_name
from .constants import PREVIEW, RELEASED, VIRTUAL_DIRECT, VIRTUAL_PROCESSED
from .vision import vision_available
from .widgets import Card, Segmented, SettingRow, ToggleSwitch, set_state


FFMPEG = shutil.which("ffmpeg")


def find_virtual_camera_device() -> str | None:
    return find_video_by_name(VIRTUAL_CAMERA_NAME)


class VirtualCameraMixin:
    """Processed/direct virtual camera and the Output tab."""

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
        self.virtual_autostart = ToggleSwitch()
        self.virtual_autostart.toggled.connect(lambda v: self.settings.setValue("virtual/autostart", v))
        virtual.body.addWidget(SettingRow(
            "Start with PixyDeck", self.virtual_autostart,
            "Keeps “PixyDeck Virtual Camera” available, so Meet, WhatsApp or Teams can stay set to it. "
            "While PixyDeck has no camera picture it shows a waiting screen."))
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
        self.virtual_mode.setEnabled(not self.virtual_running)

    def refresh_virtual_device(self) -> None:
        device = find_virtual_camera_device()
        running = self.virtual_running
        if device:
            self.virtual_device_status.setText(f"Device: ready – {device}")
        else:
            self.virtual_device_status.setText("Device: missing – open ⚙ Setup to create it")
        processed_ok = self.virtual_mode.current() != VIRTUAL_PROCESSED or vision_available()
        self.virtual_start.setEnabled(bool(device) and bool(FFMPEG) and not running and processed_ok)

    def autostart_virtual_camera(self) -> None:
        if self.virtual_autostart.isChecked() and not self.virtual_running:
            self.start_virtual_camera()

    def start_virtual_camera(self) -> None:
        if self.virtual_running:
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
            f"The PIXY feeds “{VIRTUAL_CAMERA_NAME}” directly ({resolution.replace('x', ' × ')} @ {fps} fps).\n"
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
        QTimer.singleShot(350, process, process.start)
        self.virtual_status.setText(f"Pipeline: direct – {resolution.replace('x', ' × ')} @ {fps} fps")
        self.on_virtual_started()

    def on_virtual_started(self) -> None:
        self.pill_virtual.setText("Virtual cam on")
        set_state(self.pill_virtual, "on")
        self.virtual_start.setEnabled(False)
        self.virtual_stop.setEnabled(True)
        self.update_virtual_mode_ui()
        self.update_mode_ui()
        self.notify(f"{VIRTUAL_CAMERA_NAME} running")

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
                QTimer.singleShot(300, self, lambda: (self.start_camera(), self.update_mode_ui()))
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