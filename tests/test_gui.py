"""Behaviour tests for PixyGUI and its mixins – no camera, no hardware.

Every test window gets a recording fake controller, a demo camera object,
neutral system data and throw-away settings, so the tests run on CI and on
a developer machine with a real PIXY attached without touching it.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = _TMP.name + "/config"
os.environ["XDG_STATE_HOME"] = _TMP.name + "/state"

from PySide6.QtCore import QEvent, QObject, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pixydeck import constants, controls, gui, privacy, virtual_camera  # noqa: E402

APP = QApplication.instance() or QApplication([])


class FakeController:
    """Records every camera command instead of sending it."""

    def __init__(self):
        self.calls = []

    def position(self):
        return 0, 0, 100

    def query(self, name):
        return {"min": 0, "max": 255, "step": 1, "default": 128, "inactive": False}

    def get(self, name):
        return 128

    def set(self, name, value):
        self.calls.append(("set", name, value))

    def state(self):
        return {}

    def video_device(self):
        return "/dev/video-test"

    def power_on_position(self):
        return (12.4, -7.6)

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, *args))
        return record


class DemoCamera(QObject):
    def isActive(self):  # noqa: N802 - Qt API
        return True

    def stop(self):
        pass


def demo_start_camera(window):
    if window.resolution.count() == 0:
        for key in ("3840x2160", "1920x1080", "1280x720"):
            window.resolution.addItem(key, key)
    window.camera = DemoCamera(window)
    window.preview_stack.setCurrentWidget(window.view)


class GuiTestCase(unittest.TestCase):
    """Fresh window with fake hardware for every test."""

    def setUp(self):
        QSettings("pixydeck", "pixydeck").clear()
        for patch in (
            mock.patch.object(gui, "PixyController", FakeController),
            mock.patch.object(gui.PixyGUI, "start_camera", demo_start_camera),
            mock.patch.object(gui.PixyGUI, "stop_camera", lambda self: setattr(self, "camera", None)),
            mock.patch.object(gui, "run_checks", lambda: []),
            mock.patch.object(privacy, "camera_users", lambda *a, **k: []),
            mock.patch.object(privacy, "pixy_video_nodes", lambda: []),
            # Never touch the developer's real audio setup.
            mock.patch.object(privacy.subprocess, "run", side_effect=AssertionError("real pactl call in a GUI test")),
            mock.patch.object(gui, "set_default_microphone", lambda name: None),
            mock.patch.object(gui, "set_pixy_microphone_muted", lambda muted: False),
            mock.patch.object(virtual_camera, "find_virtual_camera_device", lambda: "/dev/video20"),
            mock.patch.object(virtual_camera, "FFMPEG", "/usr/bin/ffmpeg"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        # processEvents() outside a running event loop skips deferred deletes;
        # without this every closed window keeps its timers ticking.
        APP.sendPostedEvents(None, QEvent.DeferredDelete)

    def settle(self, predicate=lambda: True, timeout=2.0):
        """Let the worker thread and queued signals run."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            APP.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def called(self, name):
        return [call for call in self.controller.calls if call[0] == name]


class PresetsTest(GuiTestCase):
    def test_store_and_recall(self):
        w = self.window
        w.position = (20, -10)
        w.zoom_value = 180
        w.store_preset(2)
        self.assertEqual(w.preset(2), (20, -10, 180))
        w.position = (0, 0)
        w.recall_preset(2)
        self.assertTrue(self.settle(lambda: self.called("move_to")))
        self.assertEqual(self.called("move_to")[-1][1:], (20, -10))
        self.assertEqual(w.zoom_value, 180)

    def test_empty_slot_click_stores_filled_slot_recalls(self):
        w = self.window
        w.position = (5, 5)
        w.preset_clicked(1)
        self.assertEqual(w.preset(1)[:2], (5, 5))
        w.position = (0, 0)
        w.preset_clicked(1)
        self.assertEqual(w.position, (5, 5))

    def test_startup_preset_marked(self):
        w = self.window
        w.store_preset(3)
        w.startup_position.setCurrentIndex(w.startup_position.findData("3"))
        self.assertEqual(w.settings.value("presets/startup"), "3")
        self.assertTrue(w.preset_buttons[2].text().startswith("★"))

    def test_corrupt_preset_is_ignored(self):
        self.window.settings.setValue("presets/4", "not,a,preset")
        self.assertIsNone(self.window.preset(4))


class ControlsTest(GuiTestCase):
    def test_privacy_remembers_previous_mode(self):
        w = self.window
        w.set_tracking_mode("track")
        w.set_tracking_mode("privacy")
        self.assertEqual(w.mode_before_privacy, "track")
        self.assertEqual(w.pill_tracking.text(), "Privacy")
        self.assertTrue(self.settle(lambda: ("tracking", "privacy") in self.controller.calls))

    def test_privacy_mutes_microphone_when_enabled(self):
        w = self.window
        w.privacy_mic.setEnabled(True)
        w.privacy_mic.set_silently(True)
        with mock.patch.object(controls, "set_pixy_microphone_muted") as mute:
            w.set_tracking_mode("privacy")
            self.assertTrue(self.settle(lambda: mute.called))
            mute.assert_called_with(True)
            w.set_tracking_mode("idle")
            self.assertTrue(self.settle(lambda: mute.call_count == 2))
            mute.assert_called_with(False)

    def test_click_point_focus_uses_frame_coordinates(self):
        w = self.window
        w.focus_mode.set_current("area")
        w.on_preview_click(0.75, 0.3)
        self.assertTrue(self.settle(lambda: self.called("focus_mode")))
        self.assertEqual(self.called("focus_mode")[-1][1:], ("area", 0.75, 0.3))

    def test_click_without_point_mode_does_nothing(self):
        self.window.focus_mode.set_current("face")
        self.window.on_preview_click(0.5, 0.5)
        self.settle(timeout=0.2)
        self.assertFalse(self.called("focus_mode"))

    def test_camera_state_sync(self):
        w = self.window
        w.tracking_changed_at = 0
        w.on_camera_state({"gesture": True, "audio": "live", "focus": "face", "hflip": True, "tracking": "privacy"})
        self.assertTrue(w.gesture.isChecked())
        self.assertEqual(w.audio.current(), "live")
        self.assertEqual(w.focus_mode.current(), "face")
        self.assertTrue(w.feature_toggles["hflip"].isChecked())
        self.assertEqual(w.tracking_mode, "privacy")

    def test_own_tracking_change_is_not_overwritten_by_stale_readback(self):
        w = self.window
        w.set_tracking_mode("track")
        w.on_camera_state({"tracking": "idle"})  # camera still reports the old mode
        self.assertEqual(w.tracking_mode, "track")

    def test_image_control_persisted_and_sent(self):
        self.window.set_image_control("brightness", 200)
        self.assertEqual(int(self.window.settings.value("image/brightness")), 200)
        self.assertTrue(self.settle(lambda: ("set", "brightness", 200) in self.controller.calls))

    def test_reset_applies_auto_modes_first(self):
        w = self.window
        w.image_defaults = {"focus_absolute": 192, "focus_automatic_continuous": 1, "brightness": 128}
        w.reset_image()
        self.assertTrue(self.settle(lambda: len(self.called("set")) >= 3))
        order = [call[1] for call in self.called("set")]
        self.assertLess(order.index("focus_automatic_continuous"), order.index("focus_absolute"))

    def test_stabilization_reserves_digital_zoom(self):
        w = self.window
        self.assertEqual(w.min_digital_zoom(), 1.0)
        w.set_stabilization(True)
        if w.processor.stabilizing:  # needs the optional OpenCV extra
            self.assertGreater(w.min_digital_zoom(), 1.0)


class BackgroundTest(GuiTestCase):
    def test_settings_are_saved_and_applied(self):
        w = self.window
        w.bg_mode.set_current("ai")
        w.bg_fill.set_current("color")
        w.bg_spill.set_value_silently(40)
        w.apply_background()
        self.assertEqual(w.settings.value("background/mode"), "ai")
        self.assertEqual(w.settings.value("background/fill"), "color")
        self.assertEqual(int(w.settings.value("background/spill")), 40)
        if w.processor._background is not None:  # optional OpenCV extra
            self.assertEqual(w.processor._background.mode, "ai")
            self.assertAlmostEqual(w.processor._background.spill, 0.4)

    def test_turning_off_hides_processed_layer(self):
        w = self.window
        w.view.processed.show()
        w.bg_mode.set_current("off")
        w.apply_background()
        self.assertFalse(w.view.processed.isVisible())
        self.assertEqual(w.bg_status.text(), "")

    def test_blur_strength_only_for_blur_fill(self):
        w = self.window
        w.bg_mode.set_current("ai")
        for fill, visible in (("blur", True), ("color", False)):
            w.bg_fill.set_current(fill)
            w.update_background_status()
            self.assertEqual(not w.bg_blur.isHidden(), visible, fill)


class PrivacyTest(GuiTestCase):
    def test_wakes_when_another_app_opens_the_camera(self):
        w = self.window
        w.privacy_wake.set_silently(True)
        w.set_tracking_mode("track")
        w.set_tracking_mode("privacy")
        w.on_camera_users([(4242, "zoom")])
        self.assertEqual(w.tracking_mode, "track")
        self.assertIn("zoom", w.pill_users.text())

    def test_idle_timer_enters_privacy(self):
        w = self.window
        w.privacy_enabled.set_silently(True)
        w.privacy_minutes.setValue(1)
        w.mode = constants.RELEASED  # preview hidden -> idle time counts
        for _ in range(30):  # 30 polls x 2 s = 60 s
            w.on_camera_users([])
        self.assertEqual(w.tracking_mode, "privacy")
        self.assertTrue(w.privacy_by_timer)

    def test_visible_preview_pauses_timer(self):
        w = self.window
        w.privacy_enabled.set_silently(True)
        w.privacy_minutes.setValue(1)
        w.show()
        for _ in range(40):
            w.on_camera_users([])
        self.assertNotEqual(w.tracking_mode, "privacy")
        self.assertIn("paused", w.privacy_status.text())

    def test_own_processes_are_excluded(self):
        w = self.window
        with mock.patch.object(type(w.processor), "output_pid", new_callable=mock.PropertyMock, return_value=999):
            pids = w.own_pids()
        self.assertIn(os.getpid(), pids)
        self.assertIn(999, pids)


class FakeProcess(QObject):
    """Stands in for QProcess so no FFmpeg is started."""

    instances = []
    ProcessChannelMode = virtual_camera.QProcess.ProcessChannelMode
    ProcessState = virtual_camera.QProcess.ProcessState
    ProcessError = virtual_camera.QProcess.ProcessError

    def __init__(self, parent=None):
        super().__init__(parent)
        self.arguments = []
        self.finished = mock.MagicMock()
        self.errorOccurred = mock.MagicMock()
        FakeProcess.instances.append(self)

    def setProgram(self, program):  # noqa: N802 - Qt API
        self.program = program

    def setArguments(self, arguments):  # noqa: N802 - Qt API
        self.arguments = arguments

    def setProcessChannelMode(self, _mode):  # noqa: N802 - Qt API
        pass

    def start(self):
        pass

    def state(self):
        return self.ProcessState.NotRunning

    def processId(self):  # noqa: N802 - Qt API
        return 0


class VirtualCameraTest(GuiTestCase):
    def test_processed_mode_keeps_preview(self):
        w = self.window
        w.virtual_mode.set_current("processed")
        with mock.patch.object(w.processor, "start_output") as start:
            w.start_virtual_camera()
        start.assert_called_once()
        self.assertEqual(w.mode, constants.VIRTUAL_PROCESSED)
        self.assertTrue(w.virtual_running and w.streams_frames)
        self.assertEqual(w.pill_virtual.text(), "Virtual cam on")
        w.stop_virtual_camera(True)
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertEqual(w.pill_virtual.text(), "Virtual cam off")

    def test_direct_mode_runs_ffmpeg_passthrough(self):
        w = self.window
        w.virtual_mode.set_current("direct")
        w.resolution.setCurrentIndex(w.resolution.findData("1920x1080"))
        FakeProcess.instances.clear()
        with mock.patch.object(virtual_camera, "QProcess", FakeProcess):
            w.start_virtual_camera()
        self.assertEqual(w.mode, constants.VIRTUAL_DIRECT)
        self.assertFalse(w.streams_frames)
        args = FakeProcess.instances[-1].arguments
        self.assertEqual(args[args.index("-i") + 1], "/dev/video-test")
        self.assertEqual(args[args.index("-video_size") + 1], "1920x1080")
        self.assertEqual(args[-1], "/dev/video20")

    def test_returns_to_released_mode_after_stop(self):
        w = self.window
        w.toggle_release()
        self.assertEqual(w.mode, constants.RELEASED)
        with mock.patch.object(w.processor, "start_output"):
            w.virtual_mode.set_current("processed")
            w.start_virtual_camera()
            w.stop_virtual_camera(True)
        self.assertEqual(w.mode, constants.RELEASED)

    def test_mode_switch_locked_while_running(self):
        w = self.window
        with mock.patch.object(w.processor, "start_output"):
            w.virtual_mode.set_current("processed")
            w.start_virtual_camera()
        self.assertFalse(w.virtual_mode.isEnabled())
        w.stop_virtual_camera(False)
        self.assertTrue(w.virtual_mode.isEnabled())


class WindowTest(GuiTestCase):
    def test_tilt_is_clamped(self):
        self.window.aim_at(0, -90)
        self.assertEqual(self.window.position, (0, constants.TILT_MIN))

    def test_hardware_zoom_only_where_the_pixy_applies_it(self):
        w = self.window
        w.resolution.setCurrentIndex(w.resolution.findData("1280x720"))
        self.assertTrue(w.hw_zoom_allowed())
        w.resolution.setCurrentIndex(w.resolution.findData("3840x2160"))
        self.assertFalse(w.hw_zoom_allowed())
        w.set_zoom(250)
        self.assertEqual(w.zoom_value, 250)
        self.assertEqual(w.hw_zoom_for(w.zoom_value), constants.ZOOM_MIN)  # all digital at 4K

    def test_zoom_limited_without_digital_zoom(self):
        w = self.window
        w.toggle_release()
        w.set_zoom(400)
        self.assertEqual(w.zoom_value, constants.HW_ZOOM_MAX)

    def test_tabs_are_grouped_by_task(self):
        tabs = self.window.tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["Camera", "Tracking", "Image", "Effects", "Calls", "Output"])

    def test_tab_and_folded_cards_are_remembered(self):
        from pixydeck.widgets import Card
        w = self.window
        w.tabs.setCurrentIndex(4)
        cards = {card.key: card for card in w.tabs.findChildren(Card) if card.key}
        self.assertFalse(cards["auto"].expanded)       # rarely used: folded by default
        self.assertTrue(cards["framing"].expanded)
        cards["auto"].header.click()
        cards["framing"].header.click()
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        cards = {card.key: card for card in self.window.tabs.findChildren(Card) if card.key}
        self.assertEqual(self.window.tabs.currentIndex(), 4)
        self.assertTrue(cards["auto"].expanded)
        self.assertFalse(cards["framing"].expanded)

    def test_shortcuts_are_installed(self):
        from PySide6.QtGui import QShortcut
        keys = {s.key().toString() for s in self.window.findChildren(QShortcut)}
        for expected in ("C", "F", "T", "P", "S", "+", "-", "1", "Ctrl+4", "Ctrl+Q"):
            self.assertIn(expected, keys)


class CameraCommandsTest(GuiTestCase):
    """Tracking target, motor speed, locks and the power-on position."""

    def test_target_is_sent_and_persisted(self):
        w = self.window
        w.target.selected.emit("upper-body")
        self.assertTrue(self.settle(lambda: self.called("target_track")))
        self.assertEqual(self.called("target_track")[-1], ("target_track", "upper-body"))
        self.assertEqual(w.settings.value("camera/target"), "upper-body")

    def test_motor_speed_goes_to_both_axes(self):
        w = self.window
        w.motor_speed.slider.setValue(120)
        self.assertTrue(self.settle(lambda: len(self.called("motor_speed")) >= 2))
        self.assertEqual({c[1] for c in self.called("motor_speed")}, {"pan", "tilt"})
        self.assertTrue(all(c[2] == 120 for c in self.called("motor_speed")))
        self.assertEqual(int(w.settings.value("camera/motor_speed")), 120)

    def test_motor_speed_range_matches_backend(self):
        slider = self.window.motor_speed.slider
        self.assertEqual((slider.minimum(), slider.maximum()),
                         (gui.backend.MOTOR_SPEED_MIN, gui.backend.MOTOR_SPEED_MAX))

    def test_locks_are_sent_not_persisted(self):
        w = self.window
        w.lock_toggles["focus"].setChecked(True)
        self.assertTrue(self.settle(lambda: self.called("lock")))
        self.assertEqual(self.called("lock")[-1], ("lock", "focus", True))
        self.assertIsNone(w.settings.value("camera/lock/focus"))

    def test_power_on_position_reports_where_the_camera_stored(self):
        w = self.window
        with mock.patch.object(w, "notify") as notify:
            w.save_power_on_position()
            self.assertTrue(self.settle(lambda: notify.called))
        self.assertTrue(self.called("save_power_on_position"))
        self.assertIn("pan 12°, tilt -8°", notify.call_args.args[0])

    def test_power_on_position_unconfirmed(self):
        w = self.window
        with mock.patch.object(self.controller, "power_on_position", return_value=None, create=True), \
                mock.patch.object(w, "notify") as notify:
            w.save_power_on_position()
            self.assertTrue(self.settle(lambda: notify.called))
        self.assertIn("did not confirm", notify.call_args.args[0])

    def test_camera_state_mirrors_target_and_locks(self):
        w = self.window
        w.on_camera_state({"target": "face", "exposure-lock": True, "focus-lock": False})
        self.assertEqual(w.target.current(), "face")
        self.assertTrue(w.lock_toggles["exposure"].isChecked())
        self.assertFalse(w.lock_toggles["focus"].isChecked())
        self.assertFalse(self.called("lock"))  # mirroring must not echo commands back

    def test_restore_applies_target_and_speed(self):
        QSettings("pixydeck", "pixydeck").setValue("camera/target", "face")
        QSettings("pixydeck", "pixydeck").setValue("camera/motor_speed", 30)
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        self.assertEqual(self.window.motor_speed.value(), 30)
        self.window.restore_camera_state()
        self.assertTrue(self.settle(lambda: len(self.called("motor_speed")) >= 2))
        self.assertIn(("target_track", "face"), self.controller.calls)
        self.assertIn(("motor_speed", "pan", 30), self.controller.calls)

    def test_unknown_saved_target_falls_back_to_auto(self):
        QSettings("pixydeck", "pixydeck").setValue("camera/target", "full-body")
        QSettings("pixydeck", "pixydeck").setValue("camera/motor_speed", 9999)
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        self.assertEqual(self.window.target.current(), "auto")
        self.assertEqual(self.window.motor_speed.value(), gui.backend.MOTOR_SPEED_MAX)


if __name__ == "__main__":
    unittest.main()
