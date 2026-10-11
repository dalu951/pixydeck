"""Behaviour tests for the window's mixins: background replacement, privacy,
presets, virtual camera and the picture/AI controls.

Reuses the fake-hardware harness from test_gui; FFmpeg, pactl and dialogs
are replaced by fakes, all images are synthetic.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gui import FakeProcess, GuiTestCase

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QMenu

from pixydeck import (backend, background_panel, constants, controls, gui, presets, privacy,
                      virtual_camera)

REAL_PIXY_VIDEO_NODES = privacy.pixy_video_nodes


def run_now(_msec, *args):
    args[-1]()  # singleShot(msec, fn) or singleShot(msec, context, fn)


def synthetic_image(path, color=QColor(10, 120, 200)):
    image = QImage(64, 36, QImage.Format_RGB32)
    image.fill(color)
    image.save(str(path))
    return str(path)


class PanelCase(GuiTestCase):
    def status(self):
        return self.window.statusBar().currentMessage()

    def rebuild_window(self):
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller


# ----------------------------------------------------------------------
# Background
# ----------------------------------------------------------------------

class BackgroundStatusTest(PanelCase):
    def green_key(self, key):
        return mock.patch.object(type(self.window.processor), "key",
                                 new_callable=mock.PropertyMock, return_value=key)

    def test_status_for_every_mode(self):
        w = self.window
        cases = [
            ("off", None, True, ""),
            ("chroma", None, True, "Waiting for a green screen in the picture…"),
            ("chroma", (0.3, 0.2), True, "🟢 Green screen detected – keying it"),
            ("auto", (0.3, 0.2), True, "🟢 Green screen detected – keying it"),
            ("auto", None, True, "🧠 AI cutout active – no green screen in view"),
            ("ai", None, True, "🧠 AI cutout active"),
            ("ai", (0.3, 0.2), True, "🧠 AI cutout active"),
            ("ai", None, False, "AI cutout needs onnxruntime: pip install 'pixydeck[ai]'"),
            ("auto", None, False, "AI cutout needs onnxruntime: pip install 'pixydeck[ai]'"),
        ]
        for mode, key, matting, expected in cases:
            with self.subTest(mode=mode, key=key, matting=matting), self.green_key(key), \
                    mock.patch.object(background_panel, "matting_available", return_value=matting):
                w.bg_mode.set_current(mode)
                w.update_background_status()
                self.assertEqual(w.bg_status.text(), expected)

    def test_status_when_stream_is_elsewhere(self):
        w = self.window
        w.bg_mode.set_current("ai")
        w.toggle_release()
        self.assertEqual(w.bg_status.text(), "Only in the preview and the processed virtual camera")

    def test_every_fill_is_saved_and_shows_its_options(self):
        w = self.window
        w.bg_mode.set_current("ai")
        w.bg_image_path = "/somewhere/beach.png"
        for fill in ("blur", "gradient", "color", "image"):
            with self.subTest(fill=fill):
                w.bg_fill.buttons[fill].click()
                self.assertEqual(w.settings.value("background/fill"), fill)
                self.assertEqual(not w.bg_blur.isHidden(), fill == "blur")
                self.assertEqual(w.bg_image_label.text(), "Image: beach.png" if fill == "image" else "")

    def test_image_fill_without_image_asks_for_one(self):
        w = self.window
        with mock.patch.object(background_panel.QFileDialog, "getOpenFileName", return_value=("", "")) as ask:
            w.bg_fill.selected.emit("image")
        ask.assert_called_once()
        self.assertEqual(ask.call_args.args[2], str(Path.home() / "Pictures"))
        self.assertEqual(w.bg_fill.current(), "gradient")  # cancelled: fall back
        self.assertEqual(w.settings.value("background/fill"), "gradient")

    def test_chosen_image_is_used_and_remembered(self):
        w = self.window
        with tempfile.TemporaryDirectory() as folder:
            path = synthetic_image(Path(folder) / "beach.png")
            with mock.patch.object(background_panel.QFileDialog, "getOpenFileName", return_value=(path, "")):
                w.bg_image_button.click()
            self.assertEqual(w.bg_fill.current(), "image")
            self.assertEqual(w.settings.value("background/image"), path)
            self.assertEqual(w.bg_image_label.text(), "Image: beach.png")
            # Cancelling a second pick keeps the image and opens in its folder.
            with mock.patch.object(background_panel.QFileDialog, "getOpenFileName", return_value=("", "")) as ask:
                w.choose_background_image()
            self.assertEqual(ask.call_args.args[2], folder)
            self.assertEqual(w.bg_image_path, path)
            self.assertEqual(w.bg_fill.current(), "image")

    def test_color_picker_stores_bgr(self):
        w = self.window
        with mock.patch.object(background_panel.QColorDialog, "getColor", return_value=QColor(255, 128, 0)) as ask:
            w.bg_color_button.click()
        self.assertEqual(ask.call_args.args[0], QColor(40, 40, 40))  # starts from the current colour
        self.assertEqual(w.bg_color, (0, 128, 255))
        self.assertEqual(w.bg_fill.current(), "color")
        self.assertEqual(w.settings.value("background/color"), "0,128,255")

    def test_cancelled_color_picker_changes_nothing(self):
        w = self.window
        w.bg_fill.set_current("blur")
        with mock.patch.object(background_panel.QColorDialog, "getColor", return_value=QColor()):
            w.choose_background_color()
        self.assertEqual(w.bg_color, (40, 40, 40))
        self.assertEqual(w.bg_fill.current(), "blur")

    def test_slider_changes_are_applied_after_a_pause(self):
        w = self.window
        w.bg_mode.set_current("chroma")
        w.bg_similarity.slider.setValue(33)
        self.assertTrue(w.background_timer.isActive())
        self.assertTrue(self.settle(lambda: str(w.settings.value("background/similarity")) == "33"))


class GreenScreenTest(PanelCase):
    def test_detected_and_lost_notifications(self):
        w = self.window
        w.bg_mode.set_current("chroma")
        w.view.set_processed(QImage(32, 18, QImage.Format_RGB32))
        w.on_green_screen((0.3, 0.2))
        self.assertEqual(self.status(), "Green screen detected")
        self.assertTrue(w.view.processed.isVisible())
        w.on_green_screen(None)
        self.assertEqual(self.status(), "Green screen no longer in view")
        self.assertFalse(w.view.processed.isVisible())  # nothing to key any more

    def test_lost_green_screen_keeps_ai_cutout(self):
        w = self.window
        w.bg_mode.set_current("auto")
        w.view.set_processed(QImage(32, 18, QImage.Format_RGB32))
        w.on_green_screen(None)
        self.assertTrue(w.view.processed.isVisible())

    def test_processed_preview_shown_only_while_needed(self):
        w = self.window
        image = QImage(32, 18, QImage.Format_RGB32)
        image.fill(QColor(1, 2, 3))
        active = mock.patch.object(type(w.processor), "background_active",
                                   new_callable=mock.PropertyMock, return_value=True)
        with active, mock.patch.object(w.processor, "take_preview", return_value=image):
            w.on_processed_preview()
            self.assertTrue(w.view.processed.isVisible())
            w.toggle_release()
            w.on_processed_preview()
            self.assertFalse(w.view.processed.isVisible())
        with mock.patch.object(w.processor, "take_preview", return_value=image):
            w.toggle_release()
            w.on_processed_preview()  # neither background nor stabilizer: raw video
            self.assertFalse(w.view.processed.isVisible())


class WithoutVisionTest(PanelCase):
    """Without the optional AI extra the software features explain themselves."""

    def setUp(self):
        super().setUp()
        for module in (gui, controls, background_panel, virtual_camera):
            patch = mock.patch.object(module, "vision_available", return_value=False)
            patch.start()
            self.addCleanup(patch.stop)
        QSettings("pixydeck", "pixydeck").clear()  # forget what the first window saved
        self.rebuild_window()

    def test_software_features_disabled_with_hint(self):
        w = self.window
        for widget in (w.bg_mode, w.bg_fill, w.bg_color_button, w.bg_image_button, w.autoframe,
                       w.show_faces, w.framing, w.stabilize):
            self.assertFalse(widget.isEnabled())
        self.assertIn("pixydeck[ai]", w.autoframe_row.hint.text())
        self.assertIn("OpenCV", w.stabilize_row.hint.text())

    def test_background_tab_explains_why_it_is_disabled(self):
        self.assertIn("pixydeck[ai]", self.window.bg_status.text())

    def test_background_not_applied_or_saved(self):
        w = self.window
        w.bg_mode.set_current("ai")
        w.apply_background()
        self.assertIsNone(w.settings.value("background/mode"))

    def test_direct_virtual_camera_is_the_default(self):
        w = self.window
        self.assertEqual(w.virtual_mode.current(), constants.VIRTUAL_DIRECT)
        self.assertTrue(w.virtual_start.isEnabled())
        w.virtual_mode.buttons[constants.VIRTUAL_PROCESSED].click()
        self.assertIn("needs the optional AI extra", w.virtual_mode_hint.text())
        self.assertFalse(w.virtual_start.isEnabled())


# ----------------------------------------------------------------------
# Privacy
# ----------------------------------------------------------------------

class PrivacyTimerTest(PanelCase):
    def setUp(self):
        super().setUp()
        w = self.window
        w.privacy_enabled.set_silently(True)
        w.privacy_minutes.setValue(1)
        w.toggle_release()  # preview hidden: idle time counts

    def test_countdown_shown(self):
        w = self.window
        w.on_camera_users([])
        self.assertEqual(w.privacy_status.text(), "Privacy in 0:58")
        for _ in range(5):
            w.on_camera_users([])
        self.assertEqual(w.privacy_status.text(), "Privacy in 0:48")

    def test_camera_use_resets_and_pauses_countdown(self):
        w = self.window
        for _ in range(10):
            w.on_camera_users([])
        w.on_camera_users([(77, "obs"), (78, "zoom"), (79, "obs")])
        self.assertEqual(w.idle_seconds, 0)
        self.assertEqual(w.privacy_status.text(), "Camera in use – timer paused")
        self.assertEqual(w.pill_users.text(), "In use: obs, zoom")
        self.assertFalse(w.pill_users.isHidden())
        w.on_camera_users([])
        self.assertTrue(w.pill_users.isHidden())

    def test_timer_status_and_waking(self):
        w = self.window
        w.set_tracking_mode("track")
        for _ in range(30):
            w.on_camera_users([])
        self.assertEqual(w.privacy_status.text(), "In privacy mode (idle timer)")
        self.assertEqual(self.status(), "Privacy mode after idle timeout")
        w.privacy_wake.set_silently(True)
        w.on_camera_users([(5, "teams")])
        self.assertEqual(w.tracking_mode, "track")
        self.assertIn("teams is using the camera", self.status())

    def test_manual_privacy_status_and_no_wake_when_disabled(self):
        w = self.window
        w.privacy_wake.set_silently(False)
        w.set_tracking_mode("privacy")
        w.on_camera_users([(5, "teams")])
        self.assertEqual(w.tracking_mode, "privacy")
        self.assertEqual(w.privacy_status.text(), "In privacy mode")

    def test_disabled_timer_shows_nothing(self):
        w = self.window
        w.privacy_enabled.set_silently(False)
        for _ in range(40):
            w.on_camera_users([])
        self.assertEqual(w.privacy_status.text(), "")
        self.assertNotEqual(w.tracking_mode, "privacy")

    def test_poll_asks_about_pixy_nodes_excluding_ourselves(self):
        w = self.window
        seen = []

        def users(devices, own):
            seen.append((devices, own))
            return [(4242, "zoom")]

        with mock.patch.object(privacy, "pixy_video_nodes", return_value=["/dev/video0", "/dev/video20"]), \
                mock.patch.object(privacy, "camera_users", users):
            w.check_privacy()
            self.assertTrue(self.settle(lambda: w.pill_users.text() == "In use: zoom"))
        self.assertEqual(seen[0][0], ["/dev/video0", "/dev/video20"])
        self.assertIn(privacy.os.getpid(), seen[0][1])

    def test_no_poll_without_pixy_nodes(self):
        with mock.patch.object(self.window.worker, "submit") as submit:
            self.window.check_privacy()
        submit.assert_not_called()


class MicrophoneTest(unittest.TestCase):
    SOURCES = (
        "48\talsa_output.pci-0000.analog-stereo.monitor\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
        "49\talsa_input.usb-EMEET_EMEET_PIXY-02.analog-stereo\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n"
        "50\talsa_output.usb-EMEET_EMEET_PIXY-02.analog-stereo.monitor\tPipeWire\ts16le 2ch\tIDLE\n"
        "51\talsa_input.pci-0000.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
        "garbage line\n"
    )

    def run_with(self, muted):
        def fake_run(args, **_kwargs):
            if args[1:] == ["list", "short", "sources"]:
                return subprocess.CompletedProcess(args, 0, stdout=self.SOURCES)
            return subprocess.CompletedProcess(args, 0)

        with mock.patch.object(privacy, "PACTL", "/usr/bin/pactl"), \
                mock.patch.object(privacy.subprocess, "run", side_effect=fake_run) as run:
            changed = privacy.set_pixy_microphone_muted(muted)
        return changed, [c.args[0] for c in run.call_args_list[1:]]

    def test_mutes_only_the_pixy_input(self):
        changed, commands = self.run_with(True)
        self.assertTrue(changed)
        self.assertEqual(commands, [[
            "/usr/bin/pactl", "set-source-mute", "alsa_input.usb-EMEET_EMEET_PIXY-02.analog-stereo", "1"]])

    def test_unmute(self):
        _changed, commands = self.run_with(False)
        self.assertEqual(commands[0][-1], "0")

    def test_without_pactl_nothing_runs(self):
        with mock.patch.object(privacy, "PACTL", None), mock.patch.object(privacy.subprocess, "run") as run:
            self.assertFalse(privacy.set_pixy_microphone_muted(True))
        run.assert_not_called()

    def test_no_pixy_source(self):
        with mock.patch.object(privacy, "PACTL", "/usr/bin/pactl"), \
                mock.patch.object(privacy.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 0, stdout="1\tother\tx\n")) as run:
            self.assertFalse(privacy.set_pixy_microphone_muted(True))
        self.assertEqual(run.call_count, 1)

    def test_pixy_video_nodes_include_virtual_camera(self):
        nodes = [("/dev/video0", "EMEET PIXY: EMEET PIXY"), ("/dev/video2", "Integrated Camera"),
                 ("/dev/video20", "EMEET PIXY Virtual")]
        with mock.patch.object(privacy, "video_nodes", return_value=nodes):
            self.assertEqual(REAL_PIXY_VIDEO_NODES(), ["/dev/video0", "/dev/video20"])


# ----------------------------------------------------------------------
# Presets
# ----------------------------------------------------------------------

class RecordingMenu(QMenu):
    shown = []

    def exec(self, *_args):
        RecordingMenu.shown.append(self)


class PresetMenuTest(PanelCase):
    def open_menu(self, slot):
        RecordingMenu.shown.clear()
        with mock.patch.object(presets, "QMenu", RecordingMenu):
            self.window.preset_menu(slot)
        menu = RecordingMenu.shown[-1]
        return {action.text(): action for action in menu.actions()}

    def test_empty_slot_menu_only_offers_store(self):
        actions = self.open_menu(2)
        self.assertTrue(actions["Store current position here"].isEnabled())
        for name in ("Go to preset", "Use as startup position", "Clear"):
            self.assertFalse(actions[name].isEnabled(), name)
        self.window.position = (12, -3)
        actions["Store current position here"].trigger()
        self.assertEqual(self.window.preset(2), (12, -3, constants.ZOOM_MIN))
        self.assertEqual(self.status(), "Preset 2 stored (pan +12°, tilt -3°)")

    def test_filled_slot_menu_recall_startup_and_clear(self):
        w = self.window
        w.settings.setValue("presets/3", "40,10,150")
        w.refresh_preset_buttons()
        self.assertIn("pan +40°, tilt +10°, zoom 1.5×", w.preset_buttons[2].toolTip())
        actions = self.open_menu(3)
        actions["Go to preset"].trigger()
        self.assertEqual(w.position, (40, 10))
        self.assertEqual(w.zoom_value, 150)
        actions["Use as startup position"].trigger()
        self.assertEqual(w.settings.value("presets/startup"), "3")
        self.assertIn("startup position", w.preset_buttons[2].toolTip())
        actions["Clear"].trigger()
        self.assertIsNone(w.preset(3))
        self.assertEqual(w.startup_position.currentData(), "last")  # cleared startup slot falls back
        self.assertEqual(w.preset_buttons[2].text(), "3")
        self.assertIn("empty", w.preset_buttons[2].toolTip())

    def test_clearing_other_slot_keeps_startup(self):
        w = self.window
        w.settings.setValue("presets/1", "1,1,100")
        w.settings.setValue("presets/2", "2,2,100")
        w.startup_position.setCurrentIndex(w.startup_position.findData("1"))
        self.open_menu(2)["Clear"].trigger()
        self.assertEqual(w.startup_position.currentData(), "1")

    def test_recalling_empty_slot_reports_it(self):
        self.window.recall_preset(4)
        self.assertEqual(self.status(), "Preset 4 is empty")
        self.assertFalse(self.called("move_to"))

    def test_right_click_opens_menu(self):
        w = self.window
        with mock.patch.object(w, "preset_menu") as menu:
            w.preset_buttons[1].customContextMenuRequested.emit(w.preset_buttons[1].rect().center())
        menu.assert_called_once_with(2)


# ----------------------------------------------------------------------
# Virtual camera
# ----------------------------------------------------------------------

class RunningProcess(FakeProcess):
    """An FFmpeg that is running and ignores terminate()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.actions = []
        self.output = b""

    def state(self):
        return self.ProcessState.Running

    def processId(self):  # noqa: N802 - Qt API
        return 4711

    def terminate(self):
        self.actions.append("terminate")

    def kill(self):
        self.actions.append("kill")

    def waitForFinished(self, msec):  # noqa: N802 - Qt API
        self.actions.append(("wait", msec))
        return False

    def readAll(self):  # noqa: N802 - Qt API
        return self.output


class VirtualCameraBehaviourTest(PanelCase):
    def start_processed(self, **kwargs):
        w = self.window
        w.virtual_mode.set_current(constants.VIRTUAL_PROCESSED)
        with mock.patch.object(w.processor, "start_output", **kwargs) as start:
            w.start_virtual_camera()
        return start

    def start_direct(self, process_class=RunningProcess):
        w = self.window
        w.virtual_mode.set_current(constants.VIRTUAL_DIRECT)
        process_class.instances.clear()
        with mock.patch.object(virtual_camera, "QProcess", process_class), \
                mock.patch.object(virtual_camera.QTimer, "singleShot", side_effect=run_now):
            w.start_virtual_camera()
        return process_class.instances[-1]

    def test_mode_choice_saved_and_shows_matching_options(self):
        w = self.window
        w.virtual_mode.buttons[constants.VIRTUAL_DIRECT].click()
        self.assertEqual(w.settings.value("virtual/mode"), constants.VIRTUAL_DIRECT)
        self.assertTrue(w.output_size_row.isHidden())
        self.assertFalse(w.fps_row.isHidden())
        self.assertIn("Lowest CPU", w.virtual_mode_hint.text())
        w.virtual_mode.buttons[constants.VIRTUAL_PROCESSED].click()
        self.assertFalse(w.output_size_row.isHidden())
        self.assertTrue(w.fps_row.isHidden())
        self.assertIn("digital zoom", w.virtual_mode_hint.text())

    def test_output_size_is_remembered(self):
        w = self.window
        w.output_size.setCurrentIndex(w.output_size.findData("960x540"))
        self.assertEqual(w.settings.value("virtual/output_size"), "960x540")

    def test_output_never_larger_than_the_source(self):
        w = self.window
        w.resolution.setCurrentIndex(w.resolution.findData("1280x720"))
        w.output_size.setCurrentIndex(w.output_size.findData("1920x1080"))
        start = self.start_processed()
        self.assertEqual(start.call_args.args, ("/usr/bin/ffmpeg", "/dev/video20", 1280, 720, 30))
        self.assertEqual(w.virtual_status.text(), "Pipeline: processed – 1280 × 720")

    def test_odd_source_size_rounded_to_even(self):
        w = self.window
        w.resolution.addItem("odd", "1279x719")
        w.resolution.setCurrentIndex(w.resolution.findData("1279x719"))
        start = self.start_processed()
        self.assertEqual(start.call_args.args[2:4], (1278, 718))

    def test_second_start_is_ignored(self):
        start = self.start_processed()
        start2 = self.start_processed()
        start.assert_called_once()
        start2.assert_not_called()

    def test_ffmpeg_launch_failure_leaves_camera_off(self):
        w = self.window
        self.start_processed(side_effect=OSError("No such file"))
        self.assertEqual(self.status(), "Virtual camera error: No such file")
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertEqual(w.pill_virtual.text(), "Virtual cam off")

    def test_processed_from_released_reopens_the_camera(self):
        w = self.window
        w.toggle_release()
        self.start_processed()
        self.assertIsNotNone(w.camera)
        self.assertEqual(w.mode, constants.VIRTUAL_PROCESSED)

    def test_missing_device_or_ffmpeg(self):
        w = self.window
        for device, ffmpeg in ((None, "/usr/bin/ffmpeg"), ("/dev/video20", None)):
            with self.subTest(device=device, ffmpeg=ffmpeg), \
                    mock.patch.object(virtual_camera, "find_virtual_camera_device", return_value=device), \
                    mock.patch.object(virtual_camera, "FFMPEG", ffmpeg):
                w.refresh_virtual_device()
                self.assertFalse(w.virtual_start.isEnabled())
                w.start_virtual_camera()
                self.assertEqual(self.status(), "Virtual camera device or FFmpeg missing")
                self.assertEqual(w.mode, constants.PREVIEW)
                if device is None:
                    self.assertEqual(w.virtual_device_status.text(), "Device: missing – open ⚙ Setup to create it")
        w.refresh_virtual_device()
        self.assertEqual(w.virtual_device_status.text(), "Device: ready – /dev/video20")
        self.assertTrue(w.virtual_start.isEnabled())

    def test_direct_without_physical_device(self):
        w = self.window
        w.virtual_mode.set_current(constants.VIRTUAL_DIRECT)
        with mock.patch.object(self.controller, "video_device", return_value=None):
            w.start_virtual_camera()
        self.assertEqual(self.status(), "EMEET PIXY capture device not found")
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertIsNotNone(w.camera)

    def test_direct_stop_kills_stuck_ffmpeg_and_resumes_preview(self):
        w = self.window
        process = self.start_direct()
        self.assertIsNone(w.camera)
        self.assertIs(w.preview_stack.currentWidget(), w.info_panel)
        self.assertIn(4711, w.own_pids())  # our FFmpeg never counts as "camera in use"
        with mock.patch.object(virtual_camera.QTimer, "singleShot", side_effect=run_now):
            w.virtual_stop.click()
        self.assertEqual(process.actions, ["terminate", ("wait", 2000), "kill", ("wait", 1000)])
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertIsNotNone(w.camera)
        self.assertEqual(w.virtual_status.text(), "Pipeline: stopped")
        self.assertTrue(w.virtual_mode.isEnabled())

    def test_ffmpeg_exit_reported_and_ui_reset(self):
        w = self.window
        process = self.start_direct()
        process.output = b"[video4linux2] Device busy"
        with mock.patch.object(virtual_camera.QTimer, "singleShot", side_effect=run_now):
            w.virtual_process_finished(1, None)
        self.assertEqual(self.status(), "Virtual camera stopped (1) [video4linux2] Device busy")
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertEqual(w.pill_virtual.text(), "Virtual cam off")
        self.assertTrue(w.virtual_start.isEnabled())

    def test_exit_during_deliberate_stop_is_silent(self):
        w = self.window
        self.start_direct()
        w.virtual_stopping = True
        w.virtual_process_finished(0, None)
        self.assertEqual(w.mode, constants.VIRTUAL_DIRECT)
        w.virtual_stopping = False

    def test_ffmpeg_failed_to_start(self):
        w = self.window
        self.start_direct()
        w.virtual_process_error(virtual_camera.QProcess.ProcessError.Crashed)  # handled by finished()
        self.assertEqual(w.mode, constants.VIRTUAL_DIRECT)
        with mock.patch.object(virtual_camera.QTimer, "singleShot", side_effect=run_now):
            w.virtual_process_error(virtual_camera.QProcess.ProcessError.FailedToStart)
        self.assertEqual(self.status(), "FFmpeg failed to start")
        self.assertEqual(w.mode, constants.PREVIEW)

    def test_processed_output_error_resets_ui(self):
        w = self.window
        self.start_processed()
        w.on_output_fps(29.7)
        self.assertEqual(w.output_fps, 29.7)
        w.on_processed_output_error("x" * 300 + "Broken pipe")
        self.assertTrue(self.status().startswith("Virtual camera stopped: "))
        self.assertTrue(self.status().endswith("Broken pipe"))
        self.assertLess(len(self.status()), 200)
        self.assertEqual(w.mode, constants.PREVIEW)
        self.assertEqual(w.pill_virtual.text(), "Virtual cam off")
        self.assertEqual(w.output_fps, 0.0)
        self.assertTrue(w.virtual_start.isEnabled())

    def test_late_output_error_only_notifies(self):
        w = self.window
        with mock.patch.object(w, "stop_virtual_camera") as stop:
            w.on_processed_output_error("ffmpeg exited")
        stop.assert_not_called()
        self.assertEqual(self.status(), "Virtual camera stopped: ffmpeg exited")


# ----------------------------------------------------------------------
# Picture and on-board AI controls
# ----------------------------------------------------------------------

class ControlsBehaviourTest(PanelCase):
    def test_apply_controls_skips_unsupported(self):
        calls = []

        class Picky:
            def set(self, name, value):
                if name == "hue":
                    raise backend.PixyError("not supported")
                if name == "gamma":
                    raise KeyError(name)
                calls.append(name)

        controls.apply_controls(Picky(), {"hue": 1, "brightness": 2, "gamma": 3, "auto_exposure": 3})
        self.assertEqual(calls, ["auto_exposure", "brightness"])

    def test_gesture_audio_flicker_feature_sent_and_saved(self):
        w = self.window
        w.gesture.setChecked(True)
        w.audio.selected.emit("live")
        w.flicker.selected.emit("50")
        w.feature_toggles["vflip"].setChecked(True)
        expected = [("gesture", True), ("audio", "live"), ("flicker", "50"), ("feature", "vflip", True)]
        self.assertTrue(self.settle(lambda: all(c in self.controller.calls for c in expected)))
        self.assertIn(w.settings.value("camera/gesture"), (True, "true"))
        self.assertEqual(w.settings.value("camera/audio"), "live")
        self.assertEqual(w.settings.value("camera/flicker"), "50")
        self.assertIsNone(w.settings.value("camera/feature/vflip"))

    def test_focus_modes(self):
        w = self.window
        w.focus_mode.selected.emit("face")
        self.assertTrue(self.settle(lambda: ("focus_mode", "face") in self.controller.calls))
        self.assertTrue(self.settle(lambda: self.status() == "Focus: face"))
        w.focus_point = (0.2, 0.8)
        w.focus_mode.selected.emit("area")
        self.assertTrue(self.settle(lambda: ("focus_mode", "area", 0.2, 0.8) in self.controller.calls))
        self.assertIn("Click in the preview", self.status())

    def test_stabilization_off_drops_processed_picture(self):
        w = self.window
        w.view.set_processed(QImage(16, 9, QImage.Format_RGB32))
        w.stabilize.setChecked(True)
        self.assertEqual(self.status(), "Stabilization on")
        w.stabilize.setChecked(False)
        self.assertFalse(w.view.processed.isVisible())
        self.assertEqual(self.status(), "Stabilization off")
        self.assertIn(w.settings.value("effects/stabilize"), (False, "false"))

    def test_camera_reports_tracking_changed_on_device(self):
        w = self.window
        w.tracking_changed_at = 0
        w.on_camera_state({"tracking": "track"})
        self.assertEqual(w.tracking_mode, "track")
        self.assertEqual(w.pill_tracking.text(), "Face tracking")
        w.on_camera_state({"tracking": "idle"})
        self.assertEqual(w.tracking_mode, "idle")
        w.on_camera_state({"tracking": "privacy"})
        w.on_camera_state({"tracking": "privacy"})  # repeated report keeps the remembered mode
        self.assertEqual(w.mode_before_privacy, "idle")

    def test_state_poll_runs_off_the_command_worker(self):
        w = self.window
        with mock.patch.object(self.controller, "state", return_value={"audio": "org"}, create=True):
            w.poll_camera_state()
            self.assertTrue(self.settle(lambda: w.audio.current() == "org"))
        self.assertEqual(w.settings.value("camera/audio"), "org")

    def test_manual_mode_starts_from_automatic_value(self):
        w = self.window
        _label, auto, (on_value, off_value), manual, _slider, _unit = constants.IMAGE_AUTO[0]
        toggle = w.auto_toggles[auto]
        with mock.patch.object(self.controller, "get", return_value=73):
            toggle.setChecked(True)
            self.assertFalse(w.image_sliders[manual].isEnabled())
            self.assertTrue(self.settle(lambda: ("set", auto, on_value) in self.controller.calls))
            toggle.setChecked(False)
            self.assertTrue(self.settle(lambda: w.image_sliders[manual].value() == 73))
        self.assertTrue(w.image_sliders[manual].isEnabled())
        sets = [c for c in self.called("set") if c[1] == auto]
        self.assertEqual([c[2] for c in sets], [on_value, off_value])

    def test_backlight_toggle(self):
        w = self.window
        w.backlight.setChecked(True)
        self.assertTrue(self.settle(lambda: ("set", "backlight_compensation", 2) in self.controller.calls))

    def test_image_controls_reflect_what_the_camera_supports(self):
        w = self.window
        _label, auto, (on_value, _off), manual, _slider, _unit = constants.IMAGE_AUTO[2]  # autofocus

        def query(name):
            if name in ("hue", constants.IMAGE_AUTO[0][1], "backlight_compensation"):
                return None
            return {"min": 0, "max": 200, "step": 1, "default": 50, "inactive": False}

        def get(name):
            if name == "gamma":
                raise backend.PixyError("read failed")
            return on_value if name == auto else 120

        with mock.patch.object(self.controller, "query", side_effect=query), \
                mock.patch.object(self.controller, "get", side_effect=get):
            w.load_image_controls()
            self.assertTrue(self.settle(lambda: "contrast" in w.image_defaults))
        self.assertFalse(w.image_sliders["hue"].isEnabled())
        self.assertFalse(w.image_sliders["gamma"].isEnabled())
        self.assertTrue(w.image_sliders["contrast"].isEnabled())
        self.assertEqual(w.image_sliders["contrast"].value(), 120)
        self.assertIn("Range 0–200, default 50", w.image_sliders["contrast"].slider.toolTip())
        self.assertFalse(w.auto_toggles[constants.IMAGE_AUTO[0][1]].isEnabled())
        self.assertTrue(w.auto_toggles[auto].isChecked())
        self.assertFalse(w.image_sliders[manual].isEnabled())  # autofocus on: no manual focus
        self.assertFalse(w.backlight.isEnabled())
        self.assertNotIn("hue", w.image_defaults)

    def test_backlight_state_read_back(self):
        w = self.window
        with mock.patch.object(self.controller, "get", return_value=2):
            w.load_image_controls()
            self.assertTrue(self.settle(lambda: w.backlight.isChecked()))
        self.assertTrue(w.backlight.isEnabled())

    def test_reset_without_known_defaults_does_nothing(self):
        w = self.window
        w.settings.setValue("image/brightness", 10)
        w.image_defaults = {}
        w.reset_image()
        self.settle(timeout=0.1)
        self.assertFalse(self.called("set"))
        self.assertEqual(int(w.settings.value("image/brightness")), 10)

    def test_reset_forgets_saved_picture(self):
        w = self.window
        w.settings.setValue("image/brightness", 10)
        w.image_defaults = {"brightness": 128}
        w.reset_image()
        self.assertIsNone(QSettings("pixydeck", "pixydeck").value("image/brightness"))
        self.assertTrue(self.settle(lambda: self.status() == "Picture reset to camera defaults"))


if __name__ == "__main__":
    unittest.main()
