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

    def test_hid_report_rejects_oversize(self):
        with self.assertRaises(Exception):
            build_hid_report(range(33))


if __name__ == "__main__":
    unittest.main()
