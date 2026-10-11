"""Behaviour tests for the PixyGUI main window: zoom, pan/tilt, auto-framing,
camera start/recovery, snapshots, setup checks and shutdown.

Reuses the fake-hardware harness from test_gui; nothing touches a real
camera, FFmpeg or the network. All pictures are synthetic.
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from test_gui import DemoCamera, GuiTestCase

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QLineEdit
from PySide6.QtMultimedia import QVideoFrameFormat

from pixydeck import backend, constants, gui
from pixydeck.setup import Check
from pixydeck.vision import Crop

# The harness replaces these per test; keep the real implementations.
REAL_START_CAMERA = gui.PixyGUI.start_camera
REAL_STOP_CAMERA = gui.PixyGUI.stop_camera


def run_now(_msec, *args):
    """Stand-in for QTimer.singleShot(msec, [context,] fn): run the callback now."""
    args[-1]()


class FakeFormat:
    def __init__(self, width, height, max_fps, min_fps=None):
        self.size = QSize(width, height)
        self.max_fps = max_fps
        self.min_fps = max_fps if min_fps is None else min_fps

    def resolution(self):
        return self.size

    def maxFrameRate(self):  # noqa: N802 - Qt API
        return self.max_fps

    def minFrameRate(self):  # noqa: N802 - Qt API
        return self.min_fps


class FakeDevice:
    def __init__(self, name, formats=()):
        self.name = name
        self.formats = list(formats)

    def description(self):
        return self.name

    def videoFormats(self):  # noqa: N802 - Qt API
        return self.formats


class FakeQCamera(QObject):
    """QCamera stand-in that records what the window asks of it."""

    errorOccurred = Signal(object, str)  # noqa: N815 - Qt API
    activeChanged = Signal(bool)  # noqa: N815 - Qt API

    def __init__(self, device=None, parent=None):
        super().__init__(parent)
        self.device = device
        self.calls = []
        self.active = False

    def setCameraFormat(self, fmt):  # noqa: N802 - Qt API
        self.calls.append(("format", fmt))

    def start(self):
        self.calls.append(("start",))
        self.active = True

    def stop(self):
        self.calls.append(("stop",))
        self.active = False

    def isActive(self):  # noqa: N802 - Qt API
        return self.active


class FakeFrame:
    """Just enough of QVideoFrame for on_video_frame."""

    def __init__(self, data=b"\xff\xd8jpeg\xff\xd9", fmt=QVideoFrameFormat.PixelFormat.Format_Jpeg, mappable=True):
        self.data = data
        self.fmt = fmt
        self.mappable = mappable
        self.unmapped = False

    def pixelFormat(self):  # noqa: N802 - Qt API
        return self.fmt

    def map(self, _mode):
        return self.mappable

    def bits(self, _plane):
        return self.data

    def mappedBytes(self, _plane):  # noqa: N802 - Qt API
        return len(self.data)

    def unmap(self):
        self.unmapped = True

    def width(self):
        return 640


def solid_image(width=200, height=100, color=QColor(30, 160, 90)):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(color)
    return image


class WindowCase(GuiTestCase):
    def status(self):
        return self.window.statusBar().currentMessage()

    def select_resolution(self, key):
        w = self.window
        w.resolution.setCurrentIndex(w.resolution.findData(key))

    def rebuild_window(self):
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller

    def zoom_commands(self):
        return [call[1] for call in self.called("set_zoom")]


class ZoomTest(WindowCase):
    def test_wheel_keys_and_slider_change_zoom(self):
        w = self.window
        w.view.wheel_zoom.emit(3)
        self.assertEqual(w.zoom_value, 130)
        self.assertEqual(w.view.hud_center.text(), "1.3×")
        w.zoom_in()
        self.assertEqual(w.zoom_value, 140)
        w.zoom_out()
        w.zoom_out()
        self.assertEqual(w.zoom_value, 120)
        w.zoom_slider.setValue(250)
        self.assertEqual(w.zoom_value, 250)
        self.assertEqual(w.zoom_label.text(), "2.5×")
        self.assertEqual(int(w.settings.value("camera/zoom")), 250)

    def test_zoom_is_clamped_to_range(self):
        w = self.window
        w.set_zoom(10)
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)
        w.set_zoom(10_000)
        self.assertEqual(w.zoom_value, constants.ZOOM_MAX)

    def test_hardware_zoom_first_then_digital_crop(self):
        w = self.window
        self.select_resolution("1280x720")
        w.set_zoom(300)
        self.assertTrue(self.settle(lambda: 150 in self.zoom_commands()))
        self.assertEqual(self.zoom_commands()[-1], constants.HW_ZOOM_MAX)
        w.crop_tick()
        self.assertAlmostEqual(w.view.crop.zoom, 2.0)  # 3.0x total = 1.5x optical * 2.0x digital

    def test_4k_zooms_digitally_only(self):
        w = self.window
        self.select_resolution("3840x2160")
        w.set_zoom(300)
        w.crop_tick()
        self.assertAlmostEqual(w.view.crop.zoom, 3.0)
        self.assertTrue(self.settle(lambda: self.zoom_commands()))
        self.assertEqual(self.zoom_commands()[-1], constants.ZOOM_MIN)

    def test_digital_crop_can_be_panned_but_not_beyond_the_frame(self):
        w = self.window
        self.select_resolution("3840x2160")
        w.set_zoom(200)
        w.crop_tick()
        w.on_preview_drag(0.1, -0.05)
        w.crop_tick()
        self.assertAlmostEqual(w.view.crop.cx, 0.6)
        self.assertAlmostEqual(w.view.crop.cy, 0.45)
        w.on_preview_drag(5.0, 5.0)  # far outside: clamped to the frame edge
        w.crop_tick()
        self.assertAlmostEqual(w.view.crop.cx, 0.75)
        self.assertAlmostEqual(w.view.crop.cy, 0.75)
        self.assertFalse(self.called("move_to"))  # panning the crop never moves the motors

    def test_double_click_recentres_digital_crop(self):
        w = self.window
        self.select_resolution("3840x2160")
        w.set_zoom(200)
        w.crop_tick()
        w.on_preview_double_click(0.3, 0.7)
        w.crop_tick()
        self.assertEqual((w.view.crop.cx, w.view.crop.cy), (0.3, 0.7))

    def test_zoom_tooltip_explains_the_limit(self):
        w = self.window
        self.assertIn("digital zoom beyond", w.zoom_slider.toolTip())
        w.toggle_release()
        self.assertEqual(w.zoom_slider.toolTip(), "EMEET PIXY hardware zoom")
        w.toggle_release()
        self.select_resolution("3840x2160")
        w.mode = constants.VIRTUAL_DIRECT  # FFmpeg passthrough at 4K: nothing can zoom
        w.sync_zoom_widgets()
        self.assertIn("unavailable", w.zoom_slider.toolTip())
        self.assertFalse(w.zoom_slider.isEnabled())

    def test_hud_shows_resolution_zoom_and_virtual_fps(self):
        w = self.window
        self.select_resolution("1920x1080")
        w.set_zoom(200)
        self.assertIn("● LIVE", w.view.hud_left.text())
        self.assertIn("1920×1080", w.view.hud_left.text())
        self.assertEqual(w.view.hud_right.text(), "2.0×")
        w.mode = constants.VIRTUAL_PROCESSED
        w.on_output_fps(24.6)
        self.assertIn("virtual cam 25 fps", w.view.hud_left.text())

    def test_hud_not_updated_without_own_stream(self):
        w = self.window
        w.update_hud()
        before = w.view.hud_left.text()
        w.toggle_release()
        w.zoom_value = 140
        w.update_hud()
        self.assertEqual(w.view.hud_left.text(), before)


class PanTiltTest(WindowCase):
    def test_held_arrow_moves_until_released(self):
        w = self.window
        w.start_move(1, 0)
        self.assertTrue(w.move_timer.isActive())
        self.assertEqual(w.position, (1, 0))  # first step goes out immediately
        self.assertTrue(self.settle(lambda: w.position[0] >= 4, timeout=2.0))
        w.stop_move(1, 0)
        self.assertFalse(w.move_timer.isActive())
        self.assertIsNone(w.pad.target)
        stopped_at = w.position
        self.settle(timeout=0.1)
        self.assertEqual(w.position, stopped_at)
        # The camera is last told to go exactly where the key was released.
        self.assertTrue(self.settle(lambda: self.called("move_to") and self.called("move_to")[-1][1:] == stopped_at))

    def test_releasing_other_direction_keeps_moving(self):
        w = self.window
        w.start_move(1, 0)
        w.start_move(0, 1)  # diagonal
        self.assertEqual(w.move_dir, [1, 1])
        w.stop_move(-1, 0)  # not the held direction
        self.assertEqual(w.move_dir, [1, 1])
        w.stop_move(1, 0)
        self.assertTrue(w.move_timer.isActive())
        self.assertEqual(w.move_dir, [0, 1])
        w.stop_move(0, 1)
        self.assertFalse(w.move_timer.isActive())

    def test_move_speeds_up_while_held_and_stops_at_the_limit(self):
        w = self.window
        w.position = (constants.PAN_LIMIT - 2, 0)
        w.start_move(1, 0)
        w.move_started = time.monotonic() - 5  # held for long: full speed
        for _ in range(5):
            w.move_tick()
        self.assertEqual(w.position[0], constants.PAN_LIMIT)
        w.stop_move(1, 0)

    def test_position_poll_updates_pad_unless_moving(self):
        w = self.window
        w.position = (40, 20)
        w.poll_position()
        self.assertTrue(self.settle(lambda: w.position == (0, 0)))
        self.assertEqual(w.pad.position, (0, 0))
        w.start_move(0, 1)
        moving_at = w.position
        w.on_position((90, 9, 100))  # stale readback while moving is ignored
        self.assertEqual(w.position, moving_at)
        w.stop_move(0, 1)

    def test_drag_without_digital_zoom_turns_the_camera(self):
        w = self.window
        w.position = (10, 5)
        w.on_preview_drag(0.1, 0.1)
        self.assertEqual(w.position, (10 + round(0.1 * constants.FOV_H), 5 - round(0.1 * constants.FOV_V)))
        w.on_preview_drag(0.1, 0.0)  # accumulates from the target, not the lagging readback
        self.assertEqual(w.position[0], 10 + round(0.2 * constants.FOV_H))
        self.assertTrue(self.settle(lambda: self.called("move_to") and self.called("move_to")[-1][1:] == w.position))

    def test_double_click_aims_at_point(self):
        w = self.window
        w.on_preview_double_click(1.0, 0.0)  # top-right corner of the frame
        self.assertEqual(w.position, (round(0.5 * constants.FOV_H), round(0.5 * constants.FOV_V)))

    def test_center_resets_aim_and_zoom(self):
        w = self.window
        w.aim_at(50, 20)
        w.set_zoom(250)
        w.manual_center = (0.2, 0.8)
        w.center_camera()
        self.assertEqual(w.position, (0, 0))
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)
        self.assertEqual(w.manual_center, (0.5, 0.5))

    def test_pan_is_clamped(self):
        self.window.aim_at(9999, 9999)
        self.assertEqual(self.window.position, (constants.PAN_LIMIT, constants.TILT_MAX))


class KeyFilterTest(WindowCase):
    def send(self, event_type, key, autorepeat=False):
        event = QKeyEvent(event_type, key, Qt.NoModifier, "", autorepeat)
        return self.window.key_filter.eventFilter(None, event)

    def test_arrow_keys_move_while_window_active(self):
        w = self.window
        with mock.patch.object(w, "isActiveWindow", return_value=True), \
                mock.patch.object(w, "start_move") as start, mock.patch.object(w, "stop_move") as stop:
            self.assertTrue(self.send(QEvent.KeyPress, Qt.Key_Left))
            self.assertTrue(self.send(QEvent.KeyPress, Qt.Key_Left, autorepeat=True))
            self.assertTrue(self.send(QEvent.KeyRelease, Qt.Key_Left))
            self.assertTrue(self.send(QEvent.KeyPress, Qt.Key_Up))
        start.assert_has_calls([mock.call(-1, 0), mock.call(0, 1)])
        self.assertEqual(start.call_count, 2)  # auto-repeat is swallowed
        stop.assert_called_once_with(-1, 0)

    def test_keys_ignored_when_inactive_or_typing(self):
        w = self.window
        with mock.patch.object(w, "start_move") as start:
            with mock.patch.object(w, "isActiveWindow", return_value=False):
                self.assertFalse(self.send(QEvent.KeyPress, Qt.Key_Right))
            with mock.patch.object(w, "isActiveWindow", return_value=True):
                self.assertFalse(self.send(QEvent.KeyPress, Qt.Key_A))
                editor = QLineEdit(w)
                with mock.patch.object(gui.QApplication, "focusWidget", return_value=editor):
                    self.assertFalse(self.send(QEvent.KeyPress, Qt.Key_Right))
            self.assertFalse(self.window.key_filter.eventFilter(None, QEvent(QEvent.FocusIn)))
        start.assert_not_called()


class ShortcutActionsTest(WindowCase):
    def test_toggle_tracking_and_privacy(self):
        w = self.window
        w.toggle_tracking()
        self.assertEqual(w.tracking_mode, "track")
        w.toggle_tracking()
        self.assertEqual(w.tracking_mode, "idle")
        w.toggle_privacy()
        self.assertEqual(w.tracking_mode, "privacy")
        w.toggle_privacy()
        self.assertEqual(w.tracking_mode, "idle")

    def test_toggle_autoframe_only_when_available(self):
        w = self.window
        w.autoframe.setEnabled(True)
        w.toggle_autoframe()
        self.assertTrue(w.autoframe.isChecked())
        w.toggle_autoframe()
        self.assertFalse(w.autoframe.isChecked())
        w.autoframe.setEnabled(False)
        w.toggle_autoframe()
        self.assertFalse(w.autoframe.isChecked())


class AutoFramingTest(WindowCase):
    def setUp(self):
        super().setUp()
        self.window.crop_timer.stop()  # drive crop_tick by hand
        self.select_resolution("3840x2160")

    def test_turning_on_persists_and_locks_manual_zoom(self):
        w = self.window
        w.autoframe.setChecked(True)
        self.assertTrue(w.settings.value("ai/autoframe") in (True, "true"))
        self.assertEqual(self.status(), "Auto-framing on")
        self.assertFalse(w.zoom_slider.isEnabled())
        self.assertIn("auto-framing", w.zoom_slider.toolTip())
        w.set_zoom(300)
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)
        self.assertIn("press F", self.status())
        w.update_hud()
        self.assertEqual(w.view.hud_right.text(), "AUTO-FRAME")

    def test_follows_faces_and_zooms_out_when_they_leave(self):
        w = self.window
        w.autoframe.setChecked(True)
        w.framing.set_current("tight")
        w.on_faces([(0.6, 0.3, 0.08, 0.12)])  # small face right of centre
        for _ in range(40):
            w.last_tick = time.monotonic() - 0.1
            w.crop_tick()
        self.assertGreater(w.zoom_value, 150)
        self.assertGreater(w.view.crop.cx, 0.55)
        self.assertEqual(w.zoom_slider.value(), w.zoom_value)
        w.on_faces([])  # brief dropout: keep the framing
        self.assertNotEqual(w.smoother.target, Crop())
        w.last_faces_at = time.monotonic() - 3
        w.on_faces([])
        for _ in range(60):
            w.last_tick = time.monotonic() - 0.1
            w.crop_tick()
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)

    def test_drag_and_double_click_ignored_while_framing(self):
        w = self.window
        w.autoframe.setChecked(True)
        w.on_preview_drag(0.2, 0.2)
        w.on_preview_double_click(0.9, 0.9)
        self.assertEqual(w.position, (0, 0))
        self.assertEqual(w.manual_center, (0.5, 0.5))

    def test_faces_ignored_while_off_but_shown_when_requested(self):
        w = self.window
        w.on_faces([(0.6, 0.3, 0.08, 0.12)])
        self.assertEqual(w.smoother.target, Crop())
        w.show_faces.setChecked(True)
        self.assertTrue(w.view.show_faces)
        self.assertTrue(w.processor.wants_frames)  # detection runs for the overlay
        w.show_faces.setChecked(False)
        self.assertFalse(w.view.show_faces)
        self.assertFalse(w.settings.value("ai/show_faces") in (True, "true"))

    def test_turning_off_resets_zoom_and_center(self):
        w = self.window
        w.autoframe.setChecked(True)
        w.zoom_value = 220
        w.manual_center = (0.3, 0.3)
        w.autoframe.setChecked(False)
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)
        self.assertEqual(w.manual_center, (0.5, 0.5))
        self.assertEqual(self.status(), "Auto-framing off")

    def test_preset_recall_keeps_framing_zoom(self):
        w = self.window
        w.settings.setValue("presets/1", "10,5,300")
        w.autoframe.setChecked(True)
        w.recall_preset(1)
        self.assertEqual(w.position, (10, 5))
        self.assertEqual(w.zoom_value, constants.ZOOM_MIN)


class VideoFrameTest(WindowCase):
    def test_jpeg_frames_go_to_the_processor_when_wanted(self):
        w = self.window
        w.processor.set_detection(True)
        frame = FakeFrame()
        with mock.patch.object(w.processor, "submit") as submit, \
                mock.patch.object(w.processor, "busy", return_value=False):
            w.on_video_frame(frame)
            w.on_video_frame(FakeFrame(fmt=QVideoFrameFormat.PixelFormat.Format_YUYV))
            w.on_video_frame(FakeFrame(mappable=False))
        submit.assert_called_once()
        jpeg, width = submit.call_args.args
        self.assertEqual(bytes(jpeg), frame.data)
        self.assertEqual(width, 640)
        self.assertTrue(frame.unmapped)

    def test_frames_skipped_when_nothing_needs_them(self):
        w = self.window
        w.processor.set_detection(False)
        with mock.patch.object(w.processor, "submit") as submit:
            w.on_video_frame(FakeFrame())
        submit.assert_not_called()

    def test_frames_feed_the_watchdog(self):
        w = self.window
        w.last_frame_at = 0
        w.mark_frame(None)
        self.assertGreater(w.last_frame_at, time.monotonic() - 1)


class CameraLifecycleTest(WindowCase):
    FORMATS = [
        FakeFormat(1920, 1080, 30),          # YUYV
        FakeFormat(1920, 1080, 60, 5),       # MJPEG: higher rate wins
        FakeFormat(3840, 2160, 30),
        FakeFormat(1280, 720, 60, 10),
    ]

    def test_finds_the_physical_pixy_only(self):
        devices = [FakeDevice("Integrated Webcam"), FakeDevice("EMEET PIXY (PixyDeck)"),
                   FakeDevice("PixyDeck Virtual Camera"), FakeDevice("EMEET PIXY: EMEET PIXY")]
        with mock.patch.object(gui.QMediaDevices, "videoInputs", return_value=devices):
            self.assertIs(gui.PixyGUI.find_pixy_camera(), devices[3])
        with mock.patch.object(gui.QMediaDevices, "videoInputs", return_value=devices[:3]):
            self.assertIsNone(gui.PixyGUI.find_pixy_camera())

    def test_resolutions_listed_once_with_best_frame_rate(self):
        w = self.window
        w.settings.setValue("camera/resolution", "1920x1080")
        w.settings.setValue("virtual/fps", 5)
        w.populate_resolutions(FakeDevice("PIXY", self.FORMATS))
        keys = [w.resolution.itemData(i) for i in range(w.resolution.count())]
        self.assertEqual(keys, ["3840x2160", "1920x1080", "1280x720"])
        self.assertEqual(w.resolution.currentData(), "1920x1080")
        self.assertEqual(w.resolution.currentText(), "1920 × 1080 · 60 fps")
        self.assertIs(w.selected_format(), self.FORMATS[1])
        self.assertEqual([w.fps.itemData(i) for i in range(w.fps.count())], [5, 60])
        self.assertEqual(w.fps.currentData(), 5)
        w.fps.setCurrentIndex(1)
        self.assertEqual(int(w.settings.value("virtual/fps")), 60)

    def test_unknown_resolution_falls_back_to_720p(self):
        w = self.window
        w.resolution.addItem("weird", "garbage")
        w.resolution.setCurrentIndex(w.resolution.count() - 1)
        self.assertEqual(w.selected_resolution(), (1280, 720))
        w.populate_fps()  # no known format: 30 fps
        self.assertEqual(w.fps.currentData(), 30)

    def test_resolution_change_switches_the_running_camera(self):
        w = self.window
        w.populate_resolutions(FakeDevice("PIXY", self.FORMATS))
        camera = FakeQCamera()
        w.camera = camera
        self.select_resolution("1280x720")
        self.assertEqual(w.settings.value("camera/resolution"), "1280x720")
        self.assertEqual(camera.calls, [("stop",), ("format", self.FORMATS[3]), ("start",)])
        self.assertEqual(w.stream_fps(), 60)
        self.assertTrue(w.hw_zoom_allowed())

    def test_1080p60_disables_hardware_zoom(self):
        w = self.window
        w.populate_resolutions(FakeDevice("PIXY", self.FORMATS))
        w.camera = FakeQCamera()
        self.select_resolution("1920x1080")
        self.assertFalse(w.hw_zoom_allowed())

    def test_switch_without_known_format_restarts_camera(self):
        w = self.window
        w.camera_formats = {}
        with mock.patch.object(w, "stop_camera") as stop, mock.patch.object(w, "start_camera") as start:
            w.switch_camera_format()
        stop.assert_called_once()
        start.assert_called_once()

    def test_start_camera_opens_selected_format(self):
        w = self.window
        w.camera = None
        w.camera_formats = {}
        device = FakeDevice("EMEET PIXY", self.FORMATS)
        w.settings.setValue("camera/resolution", "3840x2160")
        with mock.patch.object(gui.PixyGUI, "find_pixy_camera", return_value=device), \
                mock.patch.object(gui, "QCamera", FakeQCamera), \
                mock.patch.object(gui, "QMediaCaptureSession") as session:
            REAL_START_CAMERA(w)
        self.assertEqual(w.device_label.text(), "EMEET PIXY")
        self.assertIsInstance(w.camera, FakeQCamera)
        self.assertEqual(w.camera.calls, [("format", self.FORMATS[2]), ("start",)])
        session.return_value.setCamera.assert_called_once_with(w.camera)
        self.assertIs(w.preview_stack.currentWidget(), w.view)
        w.camera.errorOccurred.emit(None, "device busy")
        self.assertEqual(self.status(), "Camera error: device busy")
        camera = w.camera
        REAL_STOP_CAMERA(w)
        self.assertIsNone(w.camera)
        self.assertIsNone(w.capture_session)
        self.assertEqual(camera.calls[-1], ("stop",))

    def test_missing_camera_shows_hint_and_retries(self):
        w = self.window
        with mock.patch.object(gui.PixyGUI, "find_pixy_camera", return_value=None), \
                mock.patch.object(gui.QTimer, "singleShot") as later:
            REAL_START_CAMERA(w)
        self.assertEqual(w.device_label.text(), "Camera not found")
        self.assertIs(w.preview_stack.currentWidget(), w.info_panel)
        self.assertEqual(later.call_args.args, (3000, w, w.retry_camera))

    def test_retry_starts_camera_only_in_preview(self):
        w = self.window
        w.camera = None
        w.retry_camera()
        self.assertIsNotNone(w.camera)
        w.toggle_release()
        w.retry_camera()
        self.assertIsNone(w.camera)

    def test_release_and_resume(self):
        w = self.window
        w.toggle_release()
        self.assertEqual(w.release_button.text(), "Resume preview")
        self.assertFalse(w.snapshot_button.isEnabled())
        self.assertFalse(w.resolution.isEnabled())
        self.assertIsNone(w.camera)
        w.toggle_release()
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertIsNotNone(w.camera)
        self.assertEqual(self.status(), "Preview resumed")
        self.assertEqual(w.release_button.text(), "Release camera")
        self.assertTrue(w.snapshot_button.isEnabled())

    def test_release_button_locked_during_virtual_camera(self):
        w = self.window
        w.mode = constants.VIRTUAL_DIRECT
        w.toggle_release()  # neither preview nor released: no change
        self.assertEqual(w.mode, constants.VIRTUAL_DIRECT)
        self.assertFalse(w.release_button.isEnabled())


class WatchdogTest(WindowCase):
    def test_stalled_stream_is_restarted(self):
        w = self.window
        w.last_frame_at = time.monotonic() - 10
        with mock.patch.object(gui.QTimer, "singleShot", side_effect=run_now):
            w.check_frames()
        self.assertIn("stalled", self.status())
        self.assertIsInstance(w.camera, DemoCamera)  # stopped and opened again
        self.assertFalse(w.recovering)

    def test_restart_waits_for_device_release(self):
        w = self.window
        w.last_frame_at = time.monotonic() - 10
        with mock.patch.object(gui.QTimer, "singleShot") as later:
            w.check_frames()
            w.check_frames()  # already recovering: no second restart
        self.assertIsNone(w.camera)
        self.assertTrue(w.recovering)
        self.assertEqual(later.call_count, 1)
        w.toggle_release()  # user released meanwhile: do not grab the camera back
        later.call_args.args[-1]()
        self.assertIsNone(w.camera)

    def test_healthy_or_released_stream_left_alone(self):
        w = self.window
        camera = w.camera
        w.check_frames()  # fresh frames
        self.assertIs(w.camera, camera)
        w.toggle_release()
        w.last_frame_at = time.monotonic() - 10
        w.check_frames()
        self.assertFalse(w.recovering)


class SnapshotTest(WindowCase):
    def setUp(self):
        super().setUp()
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patch = mock.patch.object(gui.Path, "home", return_value=Path(self.home.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.folder = Path(self.home.name) / "Pictures" / "EMEET PIXY"

    def test_saves_visible_crop_as_png(self):
        w = self.window
        w.view.set_processed(solid_image(400, 200))
        w.view.set_crop(Crop(0.5, 0.5, 2.0))
        w.save_snapshot()
        files = list(self.folder.glob("pixy-*.png"))
        self.assertEqual(len(files), 1)
        saved = QImage(str(files[0]))
        self.assertEqual((saved.width(), saved.height()), (200, 100))
        self.assertEqual(saved.pixelColor(10, 10), QColor(30, 160, 90))
        self.assertIn(str(files[0]), self.status())
        self.assertEqual(w.view.hud_center.text(), "📷 Saved")

    def test_no_frame_yet(self):
        self.window.save_snapshot()
        self.assertEqual(self.status(), "No frame available yet")
        self.assertFalse(self.folder.exists())

    def test_nothing_saved_while_released(self):
        w = self.window
        w.toggle_release()
        w.view.processed.setPixmap(gui.QIcon().pixmap(1, 1))
        w.save_snapshot()
        self.assertFalse(self.folder.exists())

    def test_write_failure_reported(self):
        w = self.window
        w.view.set_processed(solid_image())
        with mock.patch.object(QImage, "save", return_value=False):
            w.save_snapshot()
        self.assertEqual(self.status(), "Could not save snapshot")


class SetupCheckTest(WindowCase):
    PROBLEM = [Check("virtual", "Virtual camera", False, "missing")]
    OPTIONAL = [Check("ai", "AI extra", False, "missing", required=False)]

    def check(self, checks, show=True):
        with mock.patch.object(gui, "run_checks", return_value=checks), \
                mock.patch.object(gui, "SetupDialog") as dialog:
            self.window.check_setup(show_if_needed=show)
        return dialog

    def test_dialog_opens_once_per_new_problem(self):
        w = self.window
        dialog = self.check(self.PROBLEM)
        dialog.return_value.exec.assert_called_once()
        self.assertEqual(w.setup_button.text(), "⚠ Setup")
        self.assertEqual(w.setup_button.objectName(), "danger")
        self.assertEqual(self.check(self.PROBLEM).call_count, 0)  # dismissed already

    def test_optional_problems_do_not_pop_up(self):
        dialog = self.check(self.OPTIONAL)
        dialog.assert_not_called()
        self.assertEqual(self.window.setup_button.text(), "⚙ Setup")

    def test_open_setup_rechecks_afterwards(self):
        w = self.window
        with mock.patch.object(gui, "SetupDialog") as dialog, \
                mock.patch.object(gui, "run_checks", return_value=self.PROBLEM):
            w.setup_button.click()
        dialog.assert_called_once_with(w)
        self.assertEqual(w.setup_button.text(), "⚠ Setup")


class SettingsTest(WindowCase):
    def tearDown(self):
        QSettings("emeet-pixy", "control").clear()

    def test_migrates_settings_from_predecessor(self):
        old = QSettings("emeet-pixy", "control")
        old.setValue("camera/pan", 15)
        old.setValue("presets/1", "1,2,100")
        new = QSettings("pixydeck-test", "migrate")
        new.clear()
        self.addCleanup(new.clear)
        gui.migrate_settings(new)
        self.assertEqual(int(new.value("camera/pan")), 15)
        self.assertEqual(new.value("presets/1"), "1,2,100")

    def test_existing_settings_are_not_overwritten(self):
        QSettings("emeet-pixy", "control").setValue("camera/pan", 15)
        new = QSettings("pixydeck-test", "migrate")
        new.clear()
        self.addCleanup(new.clear)
        new.setValue("camera/pan", -3)
        gui.migrate_settings(new)
        self.assertEqual(int(new.value("camera/pan")), -3)

    def test_broken_or_textual_values_fall_back(self):
        s = QSettings("pixydeck", "pixydeck")
        s.setValue("privacy/minutes", "soon")
        s.setValue("privacy/enabled", "yes")
        s.setValue("background/color", "red")
        s.setValue("background/mode", "always")  # pre-AI name of the green screen
        s.setValue("effects/stabilize", True)
        s.setValue("ai/autoframe", True)
        self.rebuild_window()
        w = self.window
        self.assertEqual(w.privacy_minutes.value(), 10)
        self.assertTrue(w.privacy_enabled.isChecked())
        self.assertEqual(w.bg_color, (40, 40, 40))
        self.assertEqual(w.bg_mode.current(), "chroma")
        self.assertTrue(w.stabilize.isChecked())
        self.assertTrue(w.processor.stabilizing)
        self.assertTrue(w.autoframe.isChecked())

    def test_restore_uses_startup_preset_and_saved_picture(self):
        s = QSettings("pixydeck", "pixydeck")
        s.setValue("presets/2", "30,-5,150")
        s.setValue("presets/startup", "2")
        s.setValue("image/contrast", 90)
        s.setValue("image/brightness", "bright")
        self.rebuild_window()
        w = self.window
        w.restore_camera_state()
        self.assertTrue(self.settle(lambda: self.called("motor_speed")))
        self.assertIn(("move_to", 30, -5), self.controller.calls)
        self.assertIn(("set", "contrast", 90), self.controller.calls)
        self.assertNotIn("brightness", [c[1] for c in self.called("set")])
        self.assertEqual(w.zoom_value, 150)
        self.assertEqual(w.position, (30, -5))
        self.assertTrue(self.settle(lambda: self.status() == "Saved camera settings restored"))


class CloseTest(WindowCase):
    def test_close_saves_position_and_stops_everything(self):
        w = self.window
        w.zoom_value = 130
        w.mic_muted_by_us = True
        w.mode = constants.VIRTUAL_PROCESSED
        with mock.patch.object(self.controller, "position", return_value=(22, -4, 100)), \
                mock.patch.object(gui, "set_pixy_microphone_muted") as mute, \
                mock.patch.object(w, "stop_virtual_camera") as stop_virtual:
            w.close()
        mute.assert_called_once_with(False)
        stop_virtual.assert_called_once_with(False)
        s = QSettings("pixydeck", "pixydeck")
        self.assertEqual((int(s.value("camera/pan")), int(s.value("camera/tilt"))), (22, -4))
        self.assertEqual(int(s.value("camera/zoom")), 130)
        self.assertIsNotNone(s.value("window/geometry"))
        self.assertIn(("close",), self.controller.calls)

    def test_close_keeps_last_known_position_when_camera_gone(self):
        w = self.window
        w.position = (7, 3)
        with mock.patch.object(self.controller, "position", side_effect=backend.PixyError("unplugged")):
            w.close()
        s = QSettings("pixydeck", "pixydeck")
        self.assertEqual((int(s.value("camera/pan")), int(s.value("camera/tilt"))), (7, 3))


class MainTest(unittest.TestCase):
    def test_main_builds_and_shows_window(self):
        with mock.patch.object(gui, "QApplication") as app_cls, \
                mock.patch.object(gui, "PixyGUI") as window_cls, \
                mock.patch.object(gui, "setup_logging") as logging_setup, \
                mock.patch.object(gui, "install_qt_message_handler"), \
                mock.patch.object(gui, "sys") as fake_sys:
            app_cls.return_value.exec.return_value = 3
            gui.main()
        logging_setup.assert_called_once()
        app_cls.return_value.setStyle.assert_called_once_with("Fusion")
        app_cls.return_value.setDesktopFileName.assert_called_once_with(gui.APP_ID)
        window_cls.return_value.show.assert_called_once()
        fake_sys.exit.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
