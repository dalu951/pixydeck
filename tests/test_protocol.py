"""HID protocol: byte-exact commands, the safety guard, parser robustness and
end-to-end behaviour against the simulated camera (tests/pixy_sim.py)."""

import random
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from pixydeck import backend  # noqa: E402
from pixydeck.backend import PixyError, build_hid_report, hid_frame, is_forbidden_head, reply_payload  # noqa: E402
from pixy_sim import FakePixy, frame  # noqa: E402

SEED = 20261011


def recorded(fn, *args):
    """Reports a command function sends, without a device."""
    with mock.patch.object(backend, "send_hid_report") as send, mock.patch.object(backend.time, "sleep"):
        fn("/dev/hidrawX", *args)
    return [bytes(call.args[1]) for call in send.call_args_list]


class GoldenBytesTest(unittest.TestCase):
    """Every command byte for byte as captured from a PIXY (328f:00c0)."""

    def test_device_mode(self):
        self.assertEqual(recorded(backend.set_tracking, 1), [
            bytes.fromhex("09 01 01 00 00 01 00 01 01"), bytes.fromhex("09 01 01 01")])

    def test_gesture(self):
        self.assertEqual(recorded(backend.set_gesture, False), [
            bytes.fromhex("09 04 02 00 00 02 00 02 02 00"), bytes.fromhex("09 04 02 01 00 01 00 01 02")])

    def test_audio(self):
        self.assertEqual(recorded(backend.set_audio_mode, 3), [
            bytes.fromhex("09 05 00 03 00 01 00 01 03"), bytes.fromhex("09 05 00 04")])

    def test_auto_privacy(self):
        self.assertEqual(recorded(backend.set_auto_privacy, 30), [
            bytes.fromhex("09 02 01 00 00 04 00 04 1e 00 00 00"), bytes.fromhex("09 02 01 01")])

    def test_focus_and_metering(self):
        self.assertEqual(recorded(backend.set_focus_mode, 2, 0x5F, 0x26), [
            bytes.fromhex("09 04 00 01 00 05 00 05 02 5f 26 7f 7f"),
            bytes.fromhex("09 04 00 03 00 05 00 05 02 5f 26 7f 7f"),
            bytes.fromhex("09 04 00 02")])

    def test_feature(self):
        self.assertEqual(recorded(backend.set_feature, 0x01, True), [
            bytes.fromhex("09 04 00 08 00 02 00 02 01 01"), bytes.fromhex("09 04 00 07 00 01 00 01 01")])

    def test_motor_speed(self):
        self.assertEqual(recorded(backend.set_motor_speed, "pan", 30), [
            bytes.fromhex("09 03 01 02 00 05 00 05 01 00 00 f0 41")])

    def test_target_track(self):
        self.assertEqual(recorded(backend.set_target_track, 2), [
            bytes.fromhex("09 04 01 00 00 15 00 15 02") + bytes(20)])

    def test_power_on_position(self):
        self.assertEqual(recorded(backend.save_power_on_position), [
            bytes.fromhex("09 03 01 13 00 0d 00 0d 01") + bytes(12)])

    def test_locks(self):
        self.assertEqual(recorded(backend.set_lock, "exposure", True), [bytes.fromhex("09 04 00 0b 00 01 00 01 01")])
        self.assertEqual(recorded(backend.set_lock, "white-balance", False), [bytes.fromhex("09 04 00 09 00 01 00 01 00")])
        self.assertEqual(recorded(backend.set_lock, "focus", True), [bytes.fromhex("09 04 00 0d 00 01 00 01 01")])

    def test_reply_decoding_from_captured_replies(self):
        speed = bytes.fromhex("09 63 01 03 00 09 00 09 01 00 00 70 42 00 00 00 00")
        self.assertEqual(struct.unpack_from("<f", reply_payload(speed, 5), 1)[0], 60.0)
        position = bytes.fromhex("09 63 01 01 00 09 00 09 01 05 00 98 41 fd 57 98 41")
        target, actual = struct.unpack_from("<ff", reply_payload(position, 9), 1)
        self.assertAlmostEqual(target, 19.0, places=3)
        self.assertAlmostEqual(actual, 19.04, places=2)


class SafetyGuardTest(unittest.TestCase):
    """PixyDeck must not be able to reboot, reset or reflash the camera."""

    def test_dangerous_groups_are_refused(self):
        for head in ("09 00 00 01", "09 00 00 03", "09 01 00 05", "09 01 00 08", "09 01 00 0d",
                     "09 01 00 0f", "09 09 00 01", "09 0a 00 01", "07 02 09 00", "09 60 00 01", "09 69 00 01"):
            with self.subTest(head=head), self.assertRaises(PixyError):
                build_hid_report(bytes.fromhex(head))

    def test_used_heads_are_allowed(self):
        for name in dir(backend):
            if name.startswith("HEAD_"):
                with self.subTest(name=name):
                    self.assertFalse(is_forbidden_head(bytes(getattr(backend, name))))
        for heads in backend.LOCK_HEADS.values():
            for head in heads:
                self.assertFalse(is_forbidden_head(bytes(head)))

    def test_random_heads_in_forbidden_groups_never_pass(self):
        rng = random.Random(SEED)
        for _ in range(2000):
            group = rng.choice(sorted(backend.FORBIDDEN_GROUPS)) | rng.choice((0x00, 0x20, 0x40, 0x60))
            data = bytes([0x09, group, rng.randrange(256), rng.randrange(256)])
            self.assertTrue(is_forbidden_head(data), data.hex(" "))

    def test_short_reports_are_not_misread(self):
        self.assertFalse(is_forbidden_head(b"\x09\x00"))


class FramingPropertyTest(unittest.TestCase):
    def test_frame_roundtrips_through_reply_parser(self):
        rng = random.Random(SEED)
        for _ in range(500):
            body = bytes(rng.randrange(256) for _ in range(rng.randint(1, 24)))
            report = bytes(hid_frame((9, 4, 0, 2), body))
            self.assertEqual(report[4:8], bytes([0, len(body), 0, len(body)]))
            self.assertEqual(reply_payload(build_hid_report(report), len(body)), body)

    def test_bare_head_is_a_query(self):
        self.assertEqual(hid_frame((9, 5, 0, 4)), [9, 5, 0, 4])

    def test_frame_limits(self):
        with self.assertRaises(PixyError):
            hid_frame((9, 4, 0))
        with self.assertRaises(PixyError):
            hid_frame((9, 4, 0, 2), bytes(25))
        self.assertEqual(len(build_hid_report(hid_frame((9, 4, 0, 2), bytes(24)))), 32)

    def test_reply_parser_never_crashes(self):
        rng = random.Random(SEED)
        for _ in range(3000):
            data = bytes(rng.randrange(256) for _ in range(rng.randint(0, 64)))
            minimum = rng.randint(1, 24)
            payload = reply_payload(data, minimum)
            if payload is not None:
                self.assertGreaterEqual(len(payload), minimum)
                self.assertLessEqual(len(payload), max(0, len(data) - 8))

    def test_reply_parser_trusts_only_bytes_read(self):
        self.assertEqual(reply_payload(bytes.fromhex("09 05 00 04 00 ff 00 ff 02")), b"\x02")
        self.assertIsNone(reply_payload(bytes.fromhex("09 05 00 04 00 00 00 00 02")))
        self.assertIsNone(reply_payload(None))

    def test_speed_is_clamped_and_float_encoded(self):
        rng = random.Random(SEED)
        for _ in range(200):
            value = rng.uniform(-1000, 1000)
            sent = recorded(backend.set_motor_speed, "tilt", value)[0]
            speed = struct.unpack_from("<f", sent, 9)[0]
            self.assertGreaterEqual(speed, backend.MOTOR_SPEED_MIN)
            self.assertLessEqual(speed, backend.MOTOR_SPEED_MAX)
            self.assertEqual(sent[8], backend.MOTOR_AXES["tilt"])

    def test_invalid_arguments(self):
        for call in (
            lambda: backend.set_tracking("/dev/x", 7),
            lambda: backend.set_audio_mode("/dev/x", 0),
            lambda: backend.set_target_track("/dev/x", 3),
            lambda: backend.set_lock("/dev/x", "iris", True),
            lambda: backend.motor_axis("zoom"),
        ):
            with self.assertRaises(PixyError):
                call()


class SimulatedCameraTest(unittest.TestCase):
    """The real send/query code against the simulated camera."""

    def setUp(self):
        self.pixy = FakePixy()
        self.dev = self.pixy.path
        self.addCleanup(self.pixy.close)
        for patch in (mock.patch.object(backend.time, "sleep"), mock.patch.object(backend, "HID_TIMEOUT", 0.1)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_motor_speed_roundtrip(self):
        self.assertEqual(backend.get_motor_speed(self.dev, "pan"), 60.0)
        backend.set_motor_speed(self.dev, "pan", 25)
        self.assertEqual(backend.get_motor_speed(self.dev, "pan"), 25.0)
        self.assertEqual(backend.get_motor_speed(self.dev, "tilt"), 60.0)

    def test_motor_position_comes_from_the_motor_mcu(self):
        self.pixy.state["pos"][1] = 19.0
        self.assertEqual(backend.get_motor_position(self.dev, "pan"), (19.0, 19.0))

    def test_target_track_rejects_what_the_camera_ignores(self):
        backend.set_target_track(self.dev, 2)
        self.assertEqual(backend.get_target_track(self.dev), "upper-body")
        with self.assertRaises(PixyError):
            backend.set_target_track(self.dev, 3)
        self.assertEqual(backend.get_target_track(self.dev), "upper-body")

    def test_power_on_position_stores_the_current_position(self):
        self.pixy.state["pos"].update({1: 12.0, 2: -8.0})
        backend.save_power_on_position(self.dev)
        self.assertEqual(backend.get_power_on_position(self.dev), (12.0, -8.0))

    def test_power_on_position_not_stored(self):
        self.pixy.state["power_on"] = (0, 0.0, 0.0)
        self.assertIsNone(backend.get_power_on_position(self.dev))

    def test_locks_roundtrip(self):
        for name in backend.LOCK_HEADS:
            backend.set_lock(self.dev, name, True)
            self.assertTrue(backend.get_lock(self.dev, name))
            backend.set_lock(self.dev, name, False)
            self.assertFalse(backend.get_lock(self.dev, name))

    def test_read_state_reports_everything(self):
        self.pixy.state.update(mode=2, audio=2, gesture=0, focus=1, target=1)
        self.pixy.state["features"][1] = 1
        state = backend.read_state(self.dev)
        self.assertEqual(state["tracking"], "privacy")
        self.assertEqual(state["audio"], "live")
        self.assertFalse(state["gesture"])
        self.assertEqual(state["focus"], "face")
        self.assertTrue(state["hflip"])
        self.assertFalse(state["vflip"])
        self.assertEqual(state["target"], "face")
        self.assertEqual(state["pan-speed"], 60)
        self.assertFalse(state["exposure-lock"])

    def test_ambiguous_tracking_readback_is_omitted(self):
        self.pixy.state["mode"] = 1  # the PIXY answers 3 for idle and tracking
        self.assertNotIn("tracking", backend.read_state(self.dev))

    def test_silent_camera_gives_empty_state(self):
        self.pixy.silent = True
        self.assertEqual(backend.read_state(self.dev), {})
        self.assertIsNone(backend.get_motor_speed(self.dev, "pan"))

    def test_garbage_replies_are_ignored(self):
        self.pixy.garbage = bytes(range(32))
        self.assertEqual(backend.read_state(self.dev), {})

    def test_stale_reports_are_drained_before_a_query(self):
        self.pixy.push(frame((9, 5, 0, 4), [3]))  # an old audio report
        backend.set_audio_mode(self.dev, 2)
        self.assertEqual(backend.read_state(self.dev)["audio"], "live")

    def test_other_heads_do_not_answer_a_query(self):
        self.pixy.push(frame((9, 4, 0, 2), [1, 0, 0, 0x7F, 0x7F]))  # unsolicited focus report
        self.assertEqual(backend.get_motor_speed(self.dev, "tilt"), 60.0)

    def test_every_command_reaches_the_camera_as_a_32_byte_report(self):
        backend.set_tracking(self.dev, 2)
        backend.set_gesture(self.dev, True)
        backend.set_focus_mode(self.dev, 1)
        backend.read_state(self.dev)
        self.assertTrue(self.pixy.received)
        self.assertTrue(all(len(report) == 32 for report in self.pixy.received))
        self.assertFalse(any(is_forbidden_head(bytes(head)) for head in self.pixy.sent_heads()))

    def test_controller_uses_the_cached_hid_node(self):
        controller = backend.PixyController()
        with mock.patch.object(backend, "find_hidraw_device", return_value=self.dev) as find:
            controller.motor_speed("pan", 90)
            controller.target_track("face")
            controller.lock("focus", True)
            controller.save_power_on_position()
            self.assertEqual(controller.power_on_position(), (0.0, 0.0))
            self.assertEqual(controller.state()["pan-speed"], 90)
        self.assertEqual(find.call_count, 1)
        self.assertTrue(self.pixy.wait_until(lambda s: s["target"] == 1 and s["locks"][0x0E] == 1))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.pixy = FakePixy()
        self.addCleanup(self.pixy.close)
        for patch in (mock.patch.object(backend, "find_hidraw_device", return_value=self.pixy.path),
                      mock.patch.object(backend.time, "sleep"), mock.patch.object(backend, "HID_TIMEOUT", 0.1)):
            patch.start()
            self.addCleanup(patch.stop)

    def run_cli(self, *argv):
        with mock.patch("sys.stdout") as out, mock.patch("sys.stderr") as err:
            code = backend.main(list(argv))
        text = "".join(call.args[0] for call in out.write.call_args_list)
        error = "".join(call.args[0] for call in err.write.call_args_list)
        return code, text + error

    def test_state(self):
        code, text = self.run_cli("state")
        self.assertEqual(code, 0)
        self.assertIn("pan-speed: 60", text)
        self.assertIn("target: auto", text)

    def test_speed_show_and_set(self):
        self.assertIn("pan speed: 60°/s", self.run_cli("pan-speed")[1])
        self.assertIn("tilt speed: 240°/s", self.run_cli("tilt-speed", "999")[1])
        self.assertTrue(self.pixy.wait_until(lambda s: s["speed"][2] == 240.0))

    def test_target(self):
        self.assertEqual(self.run_cli("target", "upper-body")[0], 0)
        self.assertTrue(self.pixy.wait_until(lambda s: s["target"] == 2))
        code, text = self.run_cli("target", "full-body")
        self.assertEqual(code, 1)
        self.assertIn("Usage: target", text)

    def test_locks(self):
        self.assertEqual(self.run_cli("focus-lock", "on")[0], 0)
        self.assertTrue(self.pixy.wait_until(lambda s: s["locks"][0x0E] == 1))
        self.assertEqual(self.run_cli("wb-lock", "maybe")[0], 1)

    def test_power_on_position(self):
        self.pixy.state["pos"].update({1: 30.0, 2: -10.0})
        self.assertIn("pan 0°, tilt 0°", self.run_cli("power-on-position")[1])
        self.assertIn("pan 30°, tilt -10°", self.run_cli("power-on-position", "save")[1])
        self.assertEqual(self.run_cli("power-on-position", "delete")[0], 1)
        self.pixy.state["power_on"] = (0, 0.0, 0.0)
        self.assertIn("not stored", self.run_cli("power-on-position", "show")[1])

    def test_silent_camera(self):
        self.pixy.silent = True
        self.assertIn("No reply", self.run_cli("state")[1])
        self.assertIn("No reply", self.run_cli("pan-speed")[1])

    def test_missing_camera(self):
        with mock.patch.object(backend, "find_hidraw_device", return_value=None):
            code, text = self.run_cli("state")
        self.assertEqual(code, 1)
        self.assertIn("HID device not found", text)


if __name__ == "__main__":
    unittest.main()
