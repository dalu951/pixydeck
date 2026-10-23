import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unittest import mock

from pixydeck import backend
from pixydeck.backend import build_hid_report, clamp, video_sort_key


class BackendHelpersTest(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-5, 0, 10), 0)
        self.assertEqual(clamp(50, 0, 10), 10)

    def test_hid_report_is_32_bytes(self):
        report = build_hid_report([0x09, 0x01, 0x01])
        self.assertEqual(len(report), 32)
        self.assertEqual(report[:3], b"\x09\x01\x01")
        self.assertEqual(report[3:], bytes(29))

    def test_video_sort_key_handles_odd_names(self):
        names = [Path("video10"), Path("videoX"), Path("video2")]
        self.assertEqual([p.name for p in sorted(names, key=video_sort_key)], ["video2", "video10", "videoX"])

    def test_focus_point_is_scaled_to_camera_range(self):
        controller = backend.PixyController()
        with mock.patch.object(controller, "hid_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "send_hid_report") as send:
            controller.focus_mode("area", 0.75, 0.3)
        first = send.call_args_list[0].args[1]
        self.assertEqual(first, [0x09, 0x04, 0x00, 0x01, 0x00, 0x05, 0x00, 0x05, 0x02, 0x5F, 0x26, 0x7F, 0x7F])

    def test_cli_tracking_uses_mode_table(self):
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "set_tracking") as set_tracking:
            for command, mode in backend.TRACKING_MODES.items():
                backend.execute(command)
                self.assertEqual(set_tracking.call_args.args, ("/dev/hidrawX", mode))

    def test_cli_rejects_unknown_audio_mode(self):
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "send_hid_report") as send:
            with self.assertRaises(backend.PixyError):
                backend.execute("audio", "loud")
            send.assert_not_called()

    def test_cli_pan_is_clamped(self):
        with mock.patch.object(backend, "find_video_device", return_value="/dev/videoX"), \
                mock.patch.object(backend, "set_control") as set_control:
            backend.execute("tilt", "-90")
        self.assertEqual(set_control.call_args.args, ("/dev/videoX", "tilt_absolute", backend.TILT_MIN))

    def test_cli_commands_match_parser(self):
        parser_choices = backend.build_parser()._actions[1].choices
        self.assertEqual(list(parser_choices), list(backend.CLI_COMMANDS))

    def test_find_video_by_name_uses_sysfs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, name in ((10, "PixyDeck Virtual Camera"), (2, "EMEET PIXY: EMEET PIXY"), (21, "PixyDeck Virtual Camera")):
                (root / f"video{index}").mkdir()
                (root / f"video{index}" / "name").write_text(name + "\n")
            self.assertEqual(backend.find_video_by_name("PixyDeck Virtual Camera", root), "/dev/video10")
            self.assertIsNone(backend.find_video_by_name("Other", root))
            self.assertEqual([d for d, _ in backend.video_nodes(root)], ["/dev/video2", "/dev/video10", "/dev/video21"])

    def test_hid_report_rejects_oversize(self):
        with self.assertRaises(Exception):
            build_hid_report(range(33))


class FakeV4L2:
    """Stands in for fcntl.ioctl on a PIXY capture node."""

    def __init__(self):
        self.values = {cid: 0 for cid in backend.CONTROL_IDS.values()}
        self.values[backend.CONTROL_IDS["zoom_absolute"]] = 100
        self.fail_next = 0
        self.inactive = set()

    def ioctl(self, fd, request, buf):
        if self.fail_next:
            self.fail_next -= 1
            raise OSError(19, "No such device")
        if request == backend.VIDIOC_G_CTRL:
            cid, _ = struct.unpack("Ii", buf)
            if cid not in self.values:
                raise OSError(22, "Invalid argument")
            buf[:] = struct.pack("Ii", cid, self.values[cid])
        elif request == backend.VIDIOC_S_CTRL:
            cid, value = struct.unpack("Ii", buf)
            self.values[cid] = value
        elif request == backend.VIDIOC_QUERYCTRL:
            fields = list(struct.unpack(backend.QUERYCTRL_FORMAT, buf))
            flags = backend.V4L2_CTRL_FLAG_INACTIVE if fields[0] in self.inactive else 0
            buf[:] = struct.pack(backend.QUERYCTRL_FORMAT, fields[0], 1, b"x", -10, 10, 1, 0, flags, 0, 0)
        return 0

    def get(self, name):
        return self.values[backend.CONTROL_IDS[name]]


class V4L2TestCase(unittest.TestCase):
    def setUp(self):
        self.v4l2 = FakeV4L2()
        handle, self.device = tempfile.mkstemp()
        os.close(handle)
        self.addCleanup(os.unlink, self.device)
        patch = mock.patch.object(backend.fcntl, "ioctl", self.v4l2.ioctl)
        patch.start()
        self.addCleanup(patch.stop)


class ControlTest(V4L2TestCase):
    def test_get_and_set_via_ioctl(self):
        backend.set_control(self.device, "pan_absolute", 36000)
        self.assertEqual(backend.get_control(self.device, "pan_absolute"), 36000)

    def test_unknown_control_falls_back_to_v4l2_ctl(self):
        done = subprocess.CompletedProcess([], 0, stdout="led1_mode: 3\n", stderr="")
        with mock.patch.object(backend.subprocess, "run", return_value=done) as run:
            self.assertEqual(backend.get_control(self.device, "led1_mode"), 3)
        self.assertIn("--get-ctrl=led1_mode", run.call_args.args[0])

    def test_v4l2_ctl_errors_become_pixy_errors(self):
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="unknown control")
        odd = subprocess.CompletedProcess([], 0, stdout="garbage", stderr="")
        with mock.patch.object(backend.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(backend.PixyError, "unknown control"):
                backend.get_control(self.device, "led1_mode")
            with self.assertRaisesRegex(backend.PixyError, "unknown control"):
                backend.set_control(self.device, "led1_mode", 1)
        with mock.patch.object(backend.subprocess, "run", return_value=odd):
            with self.assertRaisesRegex(backend.PixyError, "Unexpected"):
                backend.get_control(self.device, "led1_mode")

    def test_ioctl_failure_falls_back_to_v4l2_ctl_on_set(self):
        self.v4l2.fail_next = 1
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(backend.subprocess, "run", return_value=done) as run:
            backend.set_control(self.device, "zoom_absolute", 120)
        self.assertIn("--set-ctrl=zoom_absolute=120", run.call_args.args[0])

    def test_query_control(self):
        self.v4l2.inactive.add(backend.CONTROL_IDS["exposure_time_absolute"])
        info = backend.query_control(self.device, "brightness")
        self.assertEqual(info, {"min": -10, "max": 10, "step": 1, "default": 0, "inactive": False})
        self.assertTrue(backend.query_control(self.device, "exposure_time_absolute")["inactive"])
        self.assertIsNone(backend.query_control(self.device, "no_such_control"))
        self.assertIsNone(backend.query_control("/nonexistent/video", "brightness"))


class CliV4L2Test(V4L2TestCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(backend, "find_video_device", return_value=self.device)
        patch.start()
        self.addCleanup(patch.stop)

    def test_privacy_faces_the_front_first(self):
        backend.execute("pan", "35")
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "set_tracking") as set_tracking:
            self.assertEqual(backend.execute("privacy"), "Privacy mode ON")
        self.assertEqual(self.v4l2.get("pan_absolute"), 0)
        set_tracking.assert_called_once()

    def test_steps_and_limits(self):
        backend.execute("right")
        backend.execute("up")
        self.assertEqual(self.v4l2.get("pan_absolute"), backend.STEP)
        self.assertEqual(self.v4l2.get("tilt_absolute"), backend.STEP)
        backend.execute("left")
        backend.execute("left")
        backend.execute("down")
        self.assertEqual(self.v4l2.get("pan_absolute"), -backend.STEP)
        self.assertEqual(self.v4l2.get("tilt_absolute"), 0)
        backend.execute("tilt", "-90")
        self.assertEqual(self.v4l2.get("tilt_absolute"), backend.TILT_MIN)
        backend.execute("down")
        self.assertEqual(self.v4l2.get("tilt_absolute"), backend.TILT_MIN)

    def test_zoom(self):
        backend.execute("zoom-in")
        self.assertEqual(self.v4l2.get("zoom_absolute"), 110)
        backend.execute("zoom", "500")
        self.assertEqual(self.v4l2.get("zoom_absolute"), backend.ZOOM_MAX)
        backend.execute("zoom-out")
        self.assertEqual(self.v4l2.get("zoom_absolute"), backend.ZOOM_MAX - 10)

    def test_center_and_status(self):
        backend.execute("pan", "45")
        self.assertIn("pan:  45 deg", backend.execute("status"))
        self.assertEqual(backend.execute("center"), "Centered")
        self.assertIn("pan:  0 deg", backend.execute("status"))
        self.assertIn("zoom: 100", backend.execute("status"))

    def test_flicker(self):
        self.assertEqual(backend.execute("flicker", "50"), "Anti-flicker: 50")
        self.assertEqual(self.v4l2.get("power_line_frequency"), 1)
        with self.assertRaises(backend.PixyError):
            backend.execute("flicker", "75")

    def test_missing_device(self):
        with mock.patch.object(backend, "find_video_device", return_value=None):
            with self.assertRaisesRegex(backend.PixyError, "video device not found"):
                backend.execute("status")

    def test_unknown_command(self):
        with self.assertRaisesRegex(backend.PixyError, "Unknown command"):
            backend.execute("dance")


class ControllerTest(V4L2TestCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(backend, "find_video_device", return_value=self.device)
        self.find = patch.start()
        self.addCleanup(patch.stop)
        hid = mock.patch.object(backend, "find_hidraw_device", return_value=None)  # never the real camera
        hid.start()
        self.addCleanup(hid.stop)
        self.controller = backend.PixyController()
        self.addCleanup(self.controller.close)

    def test_position_and_moves_are_clamped(self):
        self.controller.move_to(200, -80)
        self.controller.set_zoom(10)
        self.assertEqual(self.controller.position(), (150, -52, backend.ZOOM_MIN))

    def test_device_is_opened_once(self):
        for _ in range(5):
            self.controller.get("pan_absolute")
        self.assertEqual(self.find.call_count, 1)
        self.assertEqual(self.controller.video_device(), self.device)

    def test_unplug_triggers_one_rediscovery(self):
        self.controller.get("pan_absolute")
        self.v4l2.fail_next = 1
        self.assertEqual(self.controller.get("pan_absolute"), 0)
        self.assertEqual(self.find.call_count, 2)

    def test_persistent_failure_raises(self):
        self.v4l2.fail_next = 2
        with self.assertRaisesRegex(backend.PixyError, "pan_absolute"):
            self.controller.get("pan_absolute")

    def test_missing_camera(self):
        self.find.return_value = None
        self.assertIsNone(self.controller.video_device())
        self.assertIsNone(self.controller.query("brightness"))
        with self.assertRaises(backend.PixyError):
            self.controller.get("pan_absolute")
        with mock.patch.object(backend, "find_hidraw_device", return_value=None):
            with self.assertRaisesRegex(backend.PixyError, "HID device not found"):
                self.controller.hid_device()

    def test_position_prefers_the_motor_reading(self):
        self.controller.move_to(10, 5)
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "get_motor_position",
                                  side_effect=lambda _dev, axis: {"pan": (10.0, 33.4), "tilt": (5.0, 18.6)}[axis]):
            self.assertEqual(self.controller.position(), (33, 19, backend.ZOOM_MIN))

    def test_position_falls_back_to_v4l2_when_the_motor_is_silent(self):
        self.controller.move_to(10, 5)
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "get_motor_position", return_value=None):
            self.assertEqual(self.controller.position(), (10, 5, backend.ZOOM_MIN))

    def test_privacy_faces_the_front_first(self):
        self.controller.move_to(40, 10)
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "set_tracking",
                                  side_effect=lambda _dev, _mode: order.append(self.v4l2.get("pan_absolute"))):
            order = []
            self.controller.tracking("privacy")
        self.assertEqual(order, [0])  # pan was 0 when privacy was sent
        self.assertEqual(self.v4l2.get("tilt_absolute"), 10 * backend.DEGREE_UNIT)

    def test_other_modes_keep_the_position(self):
        self.controller.move_to(40, 10)
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "set_tracking"):
            self.controller.tracking("track")
            self.controller.tracking("idle")
        self.assertEqual(self.v4l2.get("pan_absolute"), 40 * backend.DEGREE_UNIT)

    def test_privacy_still_sent_when_pan_fails(self):
        self.v4l2.fail_next = 2  # the pan ioctl and its retry fail
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "set_tracking") as set_tracking:
            self.controller.tracking("privacy")
        set_tracking.assert_called_once_with("/dev/hidrawX", backend.TRACKING_MODES["privacy"])

    def test_flicker_and_query(self):
        self.controller.flicker("60")
        self.assertEqual(self.v4l2.get("power_line_frequency"), 2)
        self.assertEqual(self.controller.query("brightness")["max"], 10)


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def hidraw(self, name, uevent):
        path = self.root / name / "device"
        path.mkdir(parents=True)
        (path / "uevent").write_text(uevent)

    def test_hidraw_by_usb_identity(self):
        self.hidraw("hidraw0", "HID_ID=0003:0000046D:0000C52B\nHID_NAME=Logitech Receiver\n")
        self.hidraw("hidraw1", f"HID_ID={backend.HID_ID}\nHID_NAME=EMEET EMEET PIXY\n")
        (self.root / "hidraw2").mkdir()  # no uevent: skipped
        self.assertEqual(backend.find_hidraw_device(self.root), "/dev/hidraw1")

    def test_hidraw_by_name_and_ids(self):
        self.hidraw("hidraw3", "HID_NAME=EMEET EMEET PIXY\nPRODUCT=328f/c0/1\nHID_PHYS=328F:00C0\n")
        self.assertEqual(backend.find_hidraw_device(self.root), "/dev/hidraw3")

    def test_no_hidraw(self):
        self.assertIsNone(backend.find_hidraw_device(self.root / "missing"))
        self.hidraw("hidraw0", "HID_NAME=Keyboard\n")
        self.assertIsNone(backend.find_hidraw_device(self.root))

    def test_video_capture_node_is_the_one_with_ptz(self):
        for index, name in ((0, "Integrated Camera"), (2, "EMEET PIXY: EMEET PIXY"), (3, "EMEET PIXY: EMEET PIXY"),
                            (20, "PixyDeck Virtual Camera EMEET PIXY")):
            node = self.root / f"video{index}"
            node.mkdir()
            (node / "name").write_text(name + "\n")
        answers = {"/dev/video2": OSError(25, "Inappropriate ioctl"), "/dev/video3": 0}

        def ioctl_get(device, control_id, fd=None):
            result = answers[device]
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(backend, "_ioctl_get", ioctl_get):
            self.assertEqual(backend.find_video_device(self.root), "/dev/video3")
            answers["/dev/video3"] = OSError(25, "Inappropriate ioctl")
            self.assertIsNone(backend.find_video_device(self.root))


class VirtualCameraNameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def node(self, index, name):
        (self.root / f"video{index}").mkdir()
        (self.root / f"video{index}" / "name").write_text(name + "\n")

    def test_named_after_the_camera(self):
        from pixydeck import VIRTUAL_CAMERA_NAME
        self.assertEqual(VIRTUAL_CAMERA_NAME, "EMEET PIXY (PixyDeck)")
        self.assertLessEqual(len(VIRTUAL_CAMERA_NAME), 31)  # v4l2 card name limit

    def test_every_name_is_recognised_as_ours(self):
        for name in ("EMEET PIXY (PixyDeck)", "PixyDeck Virtual Camera", "Dummy video device (virtual)"):
            self.assertTrue(backend.is_virtual_camera(name), name)
        for name in ("EMEET PIXY: EMEET PIXY", "Integrated Camera"):
            self.assertFalse(backend.is_virtual_camera(name), name)

    def test_current_name_wins_over_the_old_one(self):
        self.node(20, "PixyDeck Virtual Camera")
        self.assertEqual(backend.find_virtual_camera(self.root), "/dev/video20")
        self.node(21, "EMEET PIXY (PixyDeck)")
        self.assertEqual(backend.find_virtual_camera(self.root), "/dev/video21")

    def test_no_virtual_camera(self):
        self.node(0, "EMEET PIXY: EMEET PIXY")
        self.assertIsNone(backend.find_virtual_camera(self.root))

    def test_renamed_device_is_never_taken_for_the_real_camera(self):
        self.node(0, "EMEET PIXY (PixyDeck)")
        self.node(2, "EMEET PIXY: EMEET PIXY")
        with mock.patch.object(backend, "_ioctl_get", return_value=0):
            self.assertEqual(backend.find_video_device(self.root), "/dev/video2")


class CameraUsersTest(unittest.TestCase):
    def test_finds_this_process_holding_a_device(self):
        with tempfile.NamedTemporaryFile() as device:
            users = backend.camera_users([device.name])
            self.assertIn(os.getpid(), [pid for pid, _ in users])
            self.assertEqual(backend.camera_users([device.name], exclude_pids=[os.getpid()]), [])

    def test_missing_devices(self):
        self.assertEqual(backend.camera_users(["/dev/does-not-exist"]), [])


class HidErrorTest(unittest.TestCase):
    def test_permission_error_names_the_udev_rule(self):
        with mock.patch("builtins.open", side_effect=PermissionError(13, "denied")):
            with self.assertRaisesRegex(backend.PixyError, "udev rule"):
                backend.send_hid_report("/dev/hidraw9", [9, 4, 0, 2])

    def test_write_and_open_errors(self):
        with mock.patch("builtins.open", side_effect=OSError(5, "I/O error")):
            with self.assertRaisesRegex(backend.PixyError, "Unable to write"):
                backend.send_hid_report("/dev/hidraw9", [9, 4, 0, 2])
        with self.assertRaisesRegex(backend.PixyError, "Unable to open"):
            backend.hid_query("/nonexistent/hidraw", [9, 4, 0, 2])

    def test_query_io_error(self):
        with tempfile.NamedTemporaryFile() as device, \
                mock.patch.object(backend.os, "write", side_effect=OSError(32, "Broken pipe")):
            with self.assertRaisesRegex(backend.PixyError, "HID query failed"):
                backend.hid_query(device.name, [9, 4, 0, 2])

    def test_query_on_a_node_at_eof_returns_in_time(self):
        import time
        with tempfile.NamedTemporaryFile() as device:  # always readable, reads return b""
            start = time.monotonic()
            self.assertIsNone(backend.hid_query(device.name, [9, 4, 0, 2], timeout=0.2))
            self.assertLess(time.monotonic() - start, 2)

    def test_cli_hid_commands(self):
        with mock.patch.object(backend, "find_hidraw_device", return_value="/dev/hidrawX"), \
                mock.patch.object(backend, "send_hid_report") as send, mock.patch.object(backend.time, "sleep"):
            self.assertEqual(backend.execute("gesture-on"), "Gesture control ON")
            self.assertEqual(backend.execute("gesture-off"), "Gesture control OFF")
            self.assertEqual(backend.execute("audio", "live"), "Audio: LIVE mode")
            self.assertEqual(backend.execute("auto-privacy", "0"), "Auto-privacy OFF")
            self.assertEqual(backend.execute("auto-privacy"), "Auto-privacy ON (10s)")
            self.assertEqual(backend.execute("privacy"), "Privacy mode ON")
        self.assertEqual(len(send.call_args_list), 12)


if __name__ == "__main__":
    unittest.main()
