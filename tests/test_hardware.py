"""Checks against a real EMEET PIXY – skipped unless PIXYDECK_HARDWARE=1.

Every test puts back what it changes. Nothing here moves the camera or
touches the power-on position; the motor tests only read and write speeds.

    PIXYDECK_HARDWARE=1 PYTHONPATH=src python -m unittest tests.test_hardware -v
"""

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixydeck import backend  # noqa: E402

ENABLED = os.environ.get("PIXYDECK_HARDWARE") == "1"
HID = backend.find_hidraw_device() if ENABLED else None
VIDEO = backend.find_video_device() if ENABLED else None


@unittest.skipUnless(ENABLED and HID, "set PIXYDECK_HARDWARE=1 with a PIXY attached")
class HardwareTest(unittest.TestCase):
    def test_state_answers_every_query(self):
        state = backend.read_state(HID)
        for key in ("audio", "gesture", "focus", "hflip", "target", "pan-speed", "tilt-speed",
                    "white-balance-lock", "exposure-lock", "focus-lock"):
            self.assertIn(key, state)

    def test_motor_speed_roundtrip(self):
        for axis in backend.MOTOR_AXES:
            before = backend.get_motor_speed(HID, axis)
            self.assertIsNotNone(before)
            try:
                backend.set_motor_speed(HID, axis, 37)
                time.sleep(0.2)
                self.assertEqual(backend.get_motor_speed(HID, axis), 37.0)
            finally:
                backend.set_motor_speed(HID, axis, before)
                time.sleep(0.2)
            self.assertEqual(backend.get_motor_speed(HID, axis), before)

    def test_target_track_roundtrip(self):
        before = backend.get_target_track(HID)
        self.assertIn(before, backend.TARGET_TRACK_MODES)
        try:
            for name, code in backend.TARGET_TRACK_MODES.items():
                backend.set_target_track(HID, code)
                time.sleep(0.3)
                self.assertEqual(backend.get_target_track(HID), name)
        finally:
            backend.set_target_track(HID, backend.TARGET_TRACK_MODES[before])

    def test_locks_roundtrip(self):
        for name in backend.LOCK_HEADS:
            before = backend.get_lock(HID, name)
            self.assertIsNotNone(before)
            try:
                backend.set_lock(HID, name, not before)
                time.sleep(0.2)
                self.assertEqual(backend.get_lock(HID, name), not before)
            finally:
                backend.set_lock(HID, name, before)
                time.sleep(0.2)
            self.assertEqual(backend.get_lock(HID, name), before)

    @unittest.skipUnless(VIDEO, "video node not found")
    def test_motor_position_matches_v4l2(self):
        for axis, control in (("pan", "pan_absolute"), ("tilt", "tilt_absolute")):
            target, actual = backend.get_motor_position(HID, axis)
            v4l2 = backend.get_control(VIDEO, control) / backend.DEGREE_UNIT
            self.assertAlmostEqual(target, v4l2, delta=0.5)
            self.assertAlmostEqual(actual, v4l2, delta=1.0)

    def test_power_on_position_is_readable(self):
        position = backend.get_power_on_position(HID)
        if position is not None:
            pan, tilt = position
            self.assertLessEqual(abs(pan), 150)
            self.assertLessEqual(abs(tilt), 90)


if __name__ == "__main__":
    unittest.main()
