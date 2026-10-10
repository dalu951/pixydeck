import sys
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


if __name__ == "__main__":
    unittest.main()
