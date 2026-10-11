"""Call detection: the start/end state machine, microphone switching and the
window's reaction (tracking on, privacy afterwards) – no camera, no audio."""

import random
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gui import GuiTestCase  # noqa: E402

from PySide6.QtCore import QSettings  # noqa: E402

from pixydeck import gui, privacy  # noqa: E402
from pixydeck.privacy import CallDetector  # noqa: E402

ZOOM = [(4242, "zoom")]


class CallDetectorTest(unittest.TestCase):
    def test_brief_device_probe_is_not_a_call(self):
        calls = CallDetector()
        self.assertIsNone(calls.update(["firefox"]))
        self.assertIsNone(calls.update([]))
        self.assertIsNone(calls.update(["firefox"]))
        self.assertFalse(calls.active)

    def test_call_starts_after_two_polls_and_ends_after_three(self):
        calls = CallDetector()
        self.assertEqual([calls.update(["zoom"]) for _ in range(3)], [None, "started", None])
        self.assertTrue(calls.active)
        self.assertEqual([calls.update([]) for _ in range(4)], [None, None, "ended", None])
        self.assertFalse(calls.active)

    def test_short_gap_does_not_end_a_call(self):
        calls = CallDetector()
        calls.update(["teams"])
        calls.update(["teams"])
        for apps in ([], [], ["teams"], [], [], ["teams"]):
            self.assertIsNone(calls.update(apps))
        self.assertTrue(calls.active)

    def test_apps_are_named_once_and_sorted(self):
        calls = CallDetector(start_polls=1)
        calls.update(["zoom", "obs", "zoom"])
        self.assertEqual(calls.apps, ["obs", "zoom"])

    def test_reset(self):
        calls = CallDetector(start_polls=1)
        calls.update(["zoom"])
        calls.reset()
        self.assertFalse(calls.active)
        self.assertEqual(calls.apps, [])

    def test_random_polls_alternate_start_and_end(self):
        rng = random.Random(20261011)
        for _ in range(200):
            calls = CallDetector(rng.randint(1, 4), rng.randint(1, 4))
            events = [calls.update(["app"] if rng.random() < 0.5 else []) for _ in range(200)]
            events = [event for event in events if event]
            self.assertTrue(all(a != b for a, b in zip(events, events[1:])))
            if events:
                self.assertEqual(events[0], "started")
                self.assertEqual(calls.active, events[-1] == "started")


class MicrophoneHelperTest(unittest.TestCase):
    SOURCES = (
        "48\talsa_output.usb-EMEET_EMEET_PIXY-02.analog-stereo.monitor\tPipeWire\n"
        "49\talsa_input.usb-Desk_Mic-00.analog-stereo\tPipeWire\n"
        "50\talsa_input.usb-EMEET_EMEET_PIXY-02.mono-fallback\tPipeWire\n"
    )

    def pactl(self, args, **_kwargs):
        if args[1:] == ["list", "short", "sources"]:
            return subprocess.CompletedProcess(args, 0, stdout=self.SOURCES)
        if args[1:] == ["get-default-source"]:
            return subprocess.CompletedProcess(args, 0, stdout="alsa_input.usb-Desk_Mic-00.analog-stereo\n")
        return subprocess.CompletedProcess(args, 0, stdout="")

    def test_finds_the_pixy_input_not_its_monitor(self):
        with mock.patch.object(privacy, "PACTL", "/usr/bin/pactl"), \
                mock.patch.object(privacy.subprocess, "run", side_effect=self.pactl):
            self.assertEqual(privacy.pixy_microphone(), "alsa_input.usb-EMEET_EMEET_PIXY-02.mono-fallback")
            self.assertEqual(privacy.default_microphone(), "alsa_input.usb-Desk_Mic-00.analog-stereo")

    def test_set_default(self):
        with mock.patch.object(privacy, "PACTL", "/usr/bin/pactl"), \
                mock.patch.object(privacy.subprocess, "run") as run:
            privacy.set_default_microphone("mic")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pactl", "set-default-source", "mic"])

    def test_without_pactl(self):
        with mock.patch.object(privacy, "PACTL", None):
            self.assertIsNone(privacy.pixy_microphone())
            self.assertIsNone(privacy.default_microphone())

    def test_no_pixy_microphone(self):
        self.SOURCES = "49\talsa_input.usb-Desk_Mic-00.analog-stereo\tPipeWire\n"
        with mock.patch.object(privacy, "PACTL", "/usr/bin/pactl"), \
                mock.patch.object(privacy.subprocess, "run", side_effect=self.pactl):
            self.assertIsNone(privacy.pixy_microphone())


class CallsWindowTest(GuiTestCase):
    def setUp(self):
        super().setUp()
        self.window.calls_enabled.setChecked(True)
        self.calls_mic = []
        for patch in (
            mock.patch.object(privacy, "pixy_microphone", return_value="pixy-mic"),
            mock.patch.object(privacy, "default_microphone", return_value="desk-mic"),
            mock.patch.object(privacy, "set_default_microphone", side_effect=self.calls_mic.append),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def poll(self, users, times=1):
        for _ in range(times):
            self.window.on_camera_users(users)

    def start_call(self):
        self.poll(ZOOM, 2)

    def end_call(self):
        self.poll([], 3)

    def test_disabled_detection_does_nothing(self):
        w = self.window
        w.calls_enabled.setChecked(False)
        self.start_call()
        self.assertEqual(w.pill_users.text(), "In use: zoom")
        self.end_call()
        self.assertEqual(w.tracking_mode, "idle")
        self.assertEqual(w.calls_status.text(), "")

    def test_call_turns_tracking_on_and_privacy_on_afterwards(self):
        w = self.window
        self.start_call()
        self.assertEqual(w.tracking_mode, "track")
        self.assertIn("In a call – zoom", w.calls_status.text())
        self.assertEqual(w.pill_users.text(), "📞 Call: zoom")
        self.assertIn("Call started – zoom", w.statusBar().currentMessage())
        self.end_call()
        self.assertEqual(w.tracking_mode, "privacy")
        self.assertEqual(w.privacy_status.text(), "In privacy mode (call ended)")
        self.assertIn("No call", w.calls_status.text())
        self.assertTrue(self.settle(lambda: ("tracking", "privacy") in self.controller.calls))

    def test_next_call_wakes_from_privacy(self):
        w = self.window
        self.start_call()
        self.end_call()
        self.start_call()
        self.assertEqual(w.tracking_mode, "track")
        self.assertFalse(w.privacy_by_call)

    def test_keep_mode_only_leaves_privacy(self):
        w = self.window
        w.calls_start.set_current("keep")
        w.set_tracking_mode("idle")
        w.set_tracking_mode("privacy")
        w.privacy_wake.set_silently(False)
        self.start_call()
        self.assertEqual(w.tracking_mode, "idle")

    def test_privacy_after_call_can_be_turned_off(self):
        w = self.window
        w.calls_privacy.setChecked(False)
        self.start_call()
        self.end_call()
        self.assertEqual(w.tracking_mode, "track")
        self.assertEqual(w.statusBar().currentMessage(), "Call ended")

    def test_microphone_switches_for_the_call_and_back(self):
        w = self.window
        w.calls_mic.setEnabled(True)
        w.calls_mic.setChecked(True)
        self.start_call()
        self.assertTrue(self.settle(lambda: self.calls_mic == ["pixy-mic"]))
        self.end_call()
        self.assertTrue(self.settle(lambda: self.calls_mic == ["pixy-mic", "desk-mic"]))
        self.assertIsNone(w.microphone_before_call)

    def test_microphone_left_alone_when_already_the_pixy(self):
        w = self.window
        w.calls_mic.setEnabled(True)
        w.calls_mic.setChecked(True)
        with mock.patch.object(privacy, "default_microphone", return_value="pixy-mic"):
            self.start_call()
            self.settle(lambda: False, timeout=0.3)
        self.end_call()
        self.settle(lambda: False, timeout=0.3)
        self.assertEqual(self.calls_mic, [])

    def test_closing_mid_call_restores_the_microphone(self):
        w = self.window
        w.microphone_before_call = "desk-mic"
        with mock.patch.object(gui, "set_default_microphone") as restore:
            w.close()
        restore.assert_called_once_with("desk-mic")

    def test_turning_detection_off_forgets_the_call(self):
        w = self.window
        self.start_call()
        w.calls_enabled.setChecked(False)
        self.assertFalse(w.call_detector.active)
        self.assertFalse(QSettings("pixydeck", "pixydeck").value("calls/enabled", type=bool))

    def test_settings_are_restored(self):
        settings = QSettings("pixydeck", "pixydeck")
        settings.setValue("calls/enabled", True)
        settings.setValue("calls/start", "keep")
        settings.setValue("calls/privacy", False)
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        w = self.window
        self.assertTrue(w.calls_enabled.isChecked())
        self.assertEqual(w.calls_start.current(), "keep")
        self.assertFalse(w.calls_privacy.isChecked())
        self.assertIn("No call", w.calls_status.text())

    def test_unknown_start_action_falls_back_to_tracking(self):
        QSettings("pixydeck", "pixydeck").setValue("calls/start", "dance")
        self.close_window()
        self.window = gui.PixyGUI()
        self.controller = self.window.controller
        self.assertEqual(self.window.calls_start.current(), "track")


if __name__ == "__main__":
    unittest.main()
