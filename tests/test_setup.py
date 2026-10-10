import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pixydeck import setup  # noqa: E402

HELPER = ROOT / "deploy" / "pixydeck-setup"


def checks_by_key(**patches):
    defaults = dict(
        camera_connected=True,
        virtual_camera_device="/dev/video20",
        loopback_module_available=True,
        user_listed_in_video_group=False,
    )
    defaults.update(patches)
    with mock.patch.multiple(setup, **{k: mock.Mock(return_value=v) for k, v in defaults.items()}), \
            mock.patch.object(setup.backend, "find_hidraw_device", return_value="/dev/hidraw0"), \
            mock.patch.object(setup.os, "access", return_value=True), \
            mock.patch.object(setup, "_run", return_value=subprocess.CompletedProcess([], 0, "enabled\n", "")):
        return {check.key: check for check in setup.run_checks()}


class ChecksTest(unittest.TestCase):
    def test_healthy_system_needs_no_attention(self):
        checks = checks_by_key()
        self.assertTrue(all(check.ok for key, check in checks.items() if key not in ("ai", "ffmpeg")))

    def test_missing_virtual_camera_offers_fix(self):
        checks = checks_by_key(virtual_camera_device=None)
        self.assertFalse(checks["virtual"].ok)
        self.assertEqual(checks["virtual"].fix, "virtual-camera")
        self.assertTrue(setup.needs_attention(list(checks.values())))

    def test_missing_module_has_no_automatic_fix(self):
        checks = checks_by_key(virtual_camera_device=None, loopback_module_available=False)
        self.assertIsNone(checks["virtual"].fix)
        self.assertIn("v4l2loopback", checks["module"].manual)

    def test_disconnected_camera_is_not_an_error(self):
        checks = checks_by_key(camera_connected=False)
        self.assertFalse(checks["camera"].required)
        self.assertTrue(checks["hid"].ok)

    def test_run_fix_without_helper(self):
        with mock.patch.object(setup, "helper_path", return_value=None):
            ok, message = setup.run_fix("udev")
        self.assertFalse(ok)
        self.assertIn("Reinstall", message)


class HelperScriptTest(unittest.TestCase):
    def test_refuses_without_root(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        result = subprocess.run(["bash", str(HELPER), "udev"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root", result.stderr)

    def test_only_known_actions(self):
        text = HELPER.read_text()
        for action in ("virtual-camera)", "udev)", "video-group)"):
            self.assertIn(action, text)
        self.assertNotIn("eval", text)


if __name__ == "__main__":
    unittest.main()
