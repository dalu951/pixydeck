import os
import subprocess
import sys
import tempfile
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


class FakeSysfs:
    """Redirects the absolute /sys paths setup.py reads into a temp dir."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def add_usb(self, name, vendor=None, product=None):
        device = self.root / "sys/bus/usb/devices" / name
        device.mkdir(parents=True)
        if vendor is not None:
            (device / "idVendor").write_text(vendor + "\n")
        if product is not None:
            (device / "idProduct").write_text(product + "\n")

    def path(self, value, *rest):
        if str(value).startswith("/sys"):
            return self.root / str(value).lstrip("/")
        return Path(value, *rest)

    def __enter__(self):
        (self.root / "sys/bus/usb/devices").mkdir(parents=True)
        self.patch = mock.patch.object(setup, "Path", side_effect=self.path)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()


class SystemProbeTest(unittest.TestCase):
    def test_camera_connected_matches_vendor_and_product(self):
        with FakeSysfs() as sysfs:
            sysfs.add_usb("1-1", "046d", "0825")
            sysfs.add_usb("1-2", "328f")  # no idProduct: unreadable, skipped
            self.assertFalse(setup.camera_connected())
            sysfs.add_usb("2-3", "328F", "00C0")
            self.assertTrue(setup.camera_connected())

    def test_loopback_module_loaded_skips_modinfo(self):
        with FakeSysfs() as sysfs, mock.patch.object(setup, "_run") as run:
            (sysfs.root / "sys/module/v4l2loopback").mkdir(parents=True)
            self.assertTrue(setup.loopback_module_available())
        run.assert_not_called()

    def test_loopback_module_falls_back_to_modinfo(self):
        with FakeSysfs(), mock.patch.object(setup, "_run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            self.assertTrue(setup.loopback_module_available())
            run.assert_called_once_with("modinfo", "v4l2loopback")
            run.return_value = subprocess.CompletedProcess([], 1, "", "not found")
            self.assertFalse(setup.loopback_module_available())

    def test_video_group_membership(self):
        user = setup.pwd.getpwuid(os.getuid()).pw_name
        with mock.patch.object(setup.grp, "getgrnam", return_value=mock.Mock(gr_mem=["other", user])):
            self.assertTrue(setup.user_listed_in_video_group())
        with mock.patch.object(setup.grp, "getgrnam", return_value=mock.Mock(gr_mem=["other"])):
            self.assertFalse(setup.user_listed_in_video_group())
        with mock.patch.object(setup.grp, "getgrnam", side_effect=KeyError("video")):
            self.assertFalse(setup.user_listed_in_video_group())

    def test_virtual_camera_device_looks_up_by_name(self):
        with mock.patch.object(setup.backend, "find_video_by_name", return_value="/dev/video42") as find:
            self.assertEqual(setup.virtual_camera_device(), "/dev/video42")
        self.assertEqual(find.call_args.args[0], setup.VIRTUAL_CAMERA_NAME)

    def test_helper_path_needs_executable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, executable = Path(tmp, "a"), Path(tmp, "b")
            plain.write_text("#!/bin/sh\n")
            executable.write_text("#!/bin/sh\n")
            executable.chmod(0o755)
            with mock.patch.object(setup, "HELPER_PATHS", (Path(tmp, "missing"), plain)):
                self.assertIsNone(setup.helper_path())
            with mock.patch.object(setup, "HELPER_PATHS", (plain, executable)):
                self.assertEqual(setup.helper_path(), executable)

    def test_run_captures_output_with_timeout(self):
        done = subprocess.CompletedProcess(["x"], 0, "out", "")
        with mock.patch.object(setup.subprocess, "run", return_value=done) as run:
            self.assertIs(setup._run("systemctl", "is-enabled", "x"), done)
        args, kwargs = run.call_args
        self.assertEqual(args, (("systemctl", "is-enabled", "x"),))
        self.assertEqual(kwargs["timeout"], 10)
        self.assertFalse(kwargs["check"])

    def test_run_errors_are_not_mistaken_for_a_cancelled_prompt(self):
        with mock.patch.object(setup.subprocess, "run", side_effect=FileNotFoundError("no systemctl")):
            result = setup._run("systemctl")
        self.assertEqual(result.returncode, setup.RUN_FAILED)
        self.assertEqual(result.stdout, "")
        self.assertIn("no systemctl", result.stderr)
        with mock.patch.object(setup.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 10)):
            result = setup._run("systemctl")
        self.assertEqual(result.returncode, setup.RUN_FAILED)
        self.assertIn("timed out", result.stderr)


class RunChecksTest(unittest.TestCase):
    """run_checks for individual broken pieces, everything else healthy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rule = Path(self.tmp.name, "70-pixydeck.rules")
        self.rule.write_text("# rule\n")

    def checks(self, connected=True, hid="/dev/hidraw0", rule=True, module=True, device="/dev/video20",
               enabled="enabled", denied=(), listed=False, ffmpeg=True, ai=True):
        rules = (Path(self.tmp.name, "missing.rules"),) + ((self.rule,) if rule else ())
        with mock.patch.multiple(
                setup,
                camera_connected=mock.Mock(return_value=connected),
                virtual_camera_device=mock.Mock(return_value=device),
                loopback_module_available=mock.Mock(return_value=module),
                user_listed_in_video_group=mock.Mock(return_value=listed),
                UDEV_RULES=rules), \
                mock.patch.object(setup.backend, "find_hidraw_device", return_value=hid) as find_hid, \
                mock.patch.object(setup.os, "access", side_effect=lambda path, mode: path not in denied), \
                mock.patch.object(setup.shutil, "which", side_effect=lambda name: "/usr/bin/ffmpeg" if ffmpeg else None), \
                mock.patch("pixydeck.vision.vision_available", return_value=ai), \
                mock.patch("pixydeck.vision.matting_available", return_value=True), \
                mock.patch.object(setup, "_run", return_value=subprocess.CompletedProcess([], 0, enabled + "\n", "")) as run:
            result = {check.key: check for check in setup.run_checks()}
        self.find_hid, self.run = find_hid, run
        return result

    def test_order_and_healthy_system(self):
        checks = self.checks()
        self.assertEqual(list(checks), ["camera", "hid", "module", "virtual", "group", "ffmpeg", "ai"])
        self.assertTrue(all(check.ok for check in checks.values()))
        self.assertFalse(setup.needs_attention(list(checks.values())))
        self.assertEqual(checks["hid"].detail, "/dev/hidraw0 is accessible")
        self.assertIn("/dev/video20", checks["virtual"].detail)
        self.run.assert_called_once_with("systemctl", "is-enabled", setup.UNIT)

    def test_disconnected_camera_skips_hid_lookup(self):
        checks = self.checks(connected=False)
        self.find_hid.assert_not_called()
        self.assertTrue(checks["hid"].ok)
        self.assertIsNone(checks["hid"].fix)
        self.assertIn("once the camera is connected", checks["hid"].detail)
        self.assertFalse(checks["camera"].ok)
        self.assertFalse(setup.needs_attention(list(checks.values())))

    def test_inaccessible_hid_with_rule_offers_udev_fix(self):
        checks = self.checks(denied=("/dev/hidraw0",))
        self.assertFalse(checks["hid"].ok)
        self.assertEqual(checks["hid"].fix, "udev")
        self.assertIsNone(checks["hid"].manual)
        self.assertIn("/dev/hidraw0 is not accessible", checks["hid"].detail)

    def test_missing_hidraw_node(self):
        checks = self.checks(hid=None)
        self.assertFalse(checks["hid"].ok)
        self.assertEqual(checks["hid"].fix, "udev")
        self.assertIn("The HID device is not accessible", checks["hid"].detail)

    def test_missing_udev_rule_needs_reinstall(self):
        checks = self.checks(denied=("/dev/hidraw0",), rule=False)
        self.assertFalse(checks["hid"].ok)
        self.assertIsNone(checks["hid"].fix)
        self.assertIn("udev rule is not installed", checks["hid"].detail)
        self.assertIn("Reinstall", checks["hid"].manual)

    def test_missing_module_is_manual(self):
        checks = self.checks(module=False, device=None)
        self.assertFalse(checks["module"].ok)
        self.assertIn(os.uname().release, checks["module"].detail)
        self.assertIsNone(checks["module"].fix)
        self.assertIsNone(checks["virtual"].fix)
        self.assertIn("does not exist yet", checks["virtual"].detail)

    def test_service_not_enabled_offers_virtual_camera_fix(self):
        checks = self.checks(enabled="disabled")
        self.assertFalse(checks["virtual"].ok)
        self.assertEqual(checks["virtual"].fix, "virtual-camera")
        self.assertIn("not started at boot", checks["virtual"].detail)
        self.assertTrue(setup.needs_attention(list(checks.values())))

    def test_group_check_waits_for_device(self):
        checks = self.checks(device=None)
        self.assertTrue(checks["group"].ok)
        self.assertIn("once the virtual camera exists", checks["group"].detail)

    def test_unwritable_device_offers_video_group_fix(self):
        checks = self.checks(denied=("/dev/video20",))
        self.assertFalse(checks["group"].ok)
        self.assertEqual(checks["group"].fix, "video-group")
        self.assertIn("needs to be in the 'video' group", checks["group"].detail)

    def test_already_listed_user_must_relogin(self):
        checks = self.checks(denied=("/dev/video20",), listed=True)
        self.assertFalse(checks["group"].ok)
        self.assertIsNone(checks["group"].fix)
        self.assertIn("log out and back in", checks["group"].detail)

    def test_missing_ffmpeg_and_ai(self):
        checks = self.checks(ffmpeg=False, ai=False)
        self.assertFalse(checks["ffmpeg"].ok)
        self.assertIn("ffmpeg", checks["ffmpeg"].manual)
        self.assertFalse(checks["ai"].ok)
        self.assertFalse(checks["ai"].required)
        self.assertIn("pixydeck[ai]", checks["ai"].manual)
        # ffmpeg is required, the AI extras are not.
        self.assertTrue(setup.needs_attention([checks["ffmpeg"]]))
        self.assertFalse(setup.needs_attention([checks["ai"]]))


class RunFixTest(unittest.TestCase):
    HELPER = Path("/usr/lib/pixydeck/pixydeck-setup")

    def fix(self, action="udev", returncode=0, stdout="", stderr="", pkexec="/usr/bin/pkexec"):
        result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        with mock.patch.object(setup, "helper_path", return_value=self.HELPER), \
                mock.patch.object(setup.shutil, "which", return_value=pkexec), \
                mock.patch.object(setup, "_run", return_value=result) as run:
            outcome = setup.run_fix(action)
        self.run = run
        return outcome

    def test_success_runs_fixed_action_through_pkexec(self):
        self.assertEqual(self.fix("virtual-camera"), (True, "Done."))
        self.run.assert_called_once_with("pkexec", str(self.HELPER), "virtual-camera", timeout=setup.FIX_TIMEOUT)

    def test_slow_password_entry_is_not_cut_off(self):
        self.assertGreaterEqual(setup.FIX_TIMEOUT, 120)

    def test_pkexec_timeout_is_reported_as_such(self):
        ok, message = self.fix(returncode=setup.RUN_FAILED, stderr="pkexec timed out after 600 s")
        self.assertFalse(ok)
        self.assertIn("timed out", message)

    def test_without_pkexec_shows_manual_command(self):
        ok, message = self.fix("video-group", pkexec=None)
        self.assertFalse(ok)
        self.assertIn(f"sudo {self.HELPER} video-group", message)
        self.run.assert_not_called()

    def test_cancelled_authorization(self):
        for code in (126, 127):
            self.assertEqual(self.fix(returncode=code), (False, "Authorization was cancelled."))

    def test_failure_reports_helper_output(self):
        self.assertEqual(self.fix(returncode=1, stderr="modprobe failed\n"), (False, "modprobe failed"))
        self.assertEqual(self.fix(returncode=1, stdout=" partial \n"), (False, "partial"))
        self.assertEqual(self.fix(returncode=3), (False, "Failed with exit code 3."))


class SetupDialogTest(unittest.TestCase):
    CHECKS = [
        setup.Check("camera", "EMEET PIXY connected", False, "Plug in", required=False),
        setup.Check("hid", "Camera controls", True, "/dev/hidraw0 is accessible"),
        setup.Check("module", "v4l2loopback", False, "not installed", manual="Install v4l2loopback-dkms"),
        setup.Check("virtual", "Virtual camera", False, "missing", fix="virtual-camera"),
        setup.Check("group", "Permission", False, "needs group", fix="video-group"),
    ]

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self):
        patcher = mock.patch.object(setup, "run_checks", return_value=list(self.CHECKS))
        self.run_checks = patcher.start()
        self.addCleanup(patcher.stop)
        dialog = setup.SetupDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def rows(self, dialog):
        return [dialog.rows.itemAt(i).widget() for i in range(dialog.rows.count())]

    def labels(self, row):
        from PySide6.QtWidgets import QLabel
        return [label.text() for label in row.findChildren(QLabel)]

    def fix_buttons(self, dialog):
        from PySide6.QtWidgets import QPushButton
        return {row: row.findChild(QPushButton) for row in self.rows(dialog)}

    def test_renders_one_row_per_check(self):
        dialog = self.make_dialog()
        self.assertIn("setup", dialog.windowTitle())
        rows = self.rows(dialog)
        self.assertEqual(len(rows), len(self.CHECKS))
        self.assertEqual([self.labels(row)[0] for row in rows], ["⚠️", "✅", "❌", "❌", "❌"])
        self.assertIn("<b>Camera controls</b>", self.labels(rows[1]))
        # Manual instructions are appended for failing checks without a fix.
        self.assertIn("not installed<br>Install v4l2loopback-dkms", self.labels(rows[2]))

    def test_fix_buttons_only_for_fixable_problems(self):
        dialog = self.make_dialog()
        buttons = list(self.fix_buttons(dialog).values())
        self.assertEqual([button is not None for button in buttons], [False, False, False, True, True])
        self.assertEqual(buttons[3].text(), "Fix")

    def test_fix_button_runs_its_action_and_rechecks(self):
        dialog = self.make_dialog()
        button = list(self.fix_buttons(dialog).values())[3]
        with mock.patch.object(setup, "run_fix", return_value=(True, "Done.")) as run_fix:
            button.click()
        run_fix.assert_called_once_with("virtual-camera")
        self.assertEqual(dialog.status.text(), "✅ Done.")
        self.assertEqual(self.run_checks.call_count, 2)
        self.assertEqual(dialog.rows.count(), len(self.CHECKS))

    def test_video_group_fix_explains_relogin(self):
        dialog = self.make_dialog()
        button = list(self.fix_buttons(dialog).values())[4]
        with mock.patch.object(setup, "run_fix", return_value=(True, "Done.")) as run_fix:
            button.click()
        run_fix.assert_called_once_with("video-group")
        self.assertIn("log out and back in", dialog.status.text())

    def test_failed_fix_shows_error(self):
        dialog = self.make_dialog()
        button = list(self.fix_buttons(dialog).values())[3]
        with mock.patch.object(setup, "run_fix", return_value=(False, "Authorization was cancelled.")):
            button.click()
        self.assertEqual(dialog.status.text(), "❌ Authorization was cancelled.")

    def test_check_again_and_close(self):
        from PySide6.QtWidgets import QPushButton
        dialog = self.make_dialog()
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        buttons["Check again"].click()
        self.assertEqual(self.run_checks.call_count, 2)
        buttons["Close"].click()
        self.assertEqual(dialog.result(), setup.QDialog.Accepted)


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



class DeviceScriptTest(unittest.TestCase):
    """deploy/virtual-camera-device against a fake sysfs and v4l2loopback-ctl."""

    SCRIPT = ROOT / "deploy" / "virtual-camera-device"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.sysfs, self.dev, self.log = root / "sys", root / "dev", root / "ctl.log"
        (self.sysfs / "class" / "video4linux").mkdir(parents=True)
        self.dev.mkdir()
        self.busy = root / "busy"
        self.ctl = root / "v4l2loopback-ctl"
        self.ctl.write_text(
            "#!/bin/sh\n"
            f"echo \"$*\" >> '{self.log}'\n"
            f"if [ \"$1\" = delete ] && [ -e '{self.busy}' ]; then exit 1; fi\n")
        self.ctl.chmod(0o755)

    def device(self, index, name):
        node = self.sysfs / "class" / "video4linux" / f"video{index}"
        node.mkdir()
        (node / "name").write_text(name + "\n")
        (self.dev / f"video{index}").touch()

    def run_script(self, action):
        env = {"PATH": "/usr/bin:/bin", "PIXYDECK_SYSFS": str(self.sysfs),
               "PIXYDECK_DEV": str(self.dev), "PIXYDECK_LOOPBACK_CTL": str(self.ctl)}
        return subprocess.run(["bash", str(self.SCRIPT), action], env=env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_creates_the_device_under_the_camera_name_first_in_line(self):
        result = self.run_script("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [f"add -n EMEET PIXY (PixyDeck) -x 1 {self.dev}/video0"])

    def test_takes_the_next_free_number_when_the_camera_came_first(self):
        self.device(0, "EMEET PIXY: EMEET PIXY")
        self.device(1, "EMEET PIXY: EMEET PIXY")
        self.assertEqual(self.run_script("start").returncode, 0)
        self.assertEqual(self.calls(), [f"add -n EMEET PIXY (PixyDeck) -x 1 {self.dev}/video2"])

    def test_unit_runs_before_the_cameras_are_announced(self):
        unit = (ROOT / "deploy" / "pixydeck-virtual-camera.service.in").read_text()
        self.assertIn("DefaultDependencies=no", unit)
        self.assertIn("Before=systemd-udev-trigger.service", unit)
        self.assertIn("WantedBy=sysinit.target", unit)
        for installer in (ROOT / "packaging" / "deb" / "postinst", ROOT / "install.sh", HELPER):
            # enable would keep the old multi-user.target link; reenable moves it.
            self.assertIn("reenable", installer.read_text(), installer)

    def test_existing_device_is_reused(self):
        self.device(20, "EMEET PIXY (PixyDeck)")
        self.assertEqual(self.run_script("start").stdout.strip(), f"{self.dev}/video20")
        self.assertEqual(self.calls(), [])

    def test_old_name_is_replaced(self):
        self.device(20, "PixyDeck Virtual Camera")
        (self.dev / "video20").unlink()  # the delete frees the node
        self.assertEqual(self.run_script("start").returncode, 0)
        self.assertEqual(self.calls(), [f"delete {self.dev}/video20",
                                        f"add -n EMEET PIXY (PixyDeck) -x 1 {self.dev}/video0"])

    def test_old_device_in_use_is_kept(self):
        self.device(20, "PixyDeck Virtual Camera")
        self.busy.touch()
        result = self.run_script("start")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), f"{self.dev}/video20")
        self.assertEqual(self.calls(), [f"delete {self.dev}/video20"])

    def test_stop_removes_both_names_and_tolerates_busy(self):
        self.device(20, "EMEET PIXY (PixyDeck)")
        self.device(21, "PixyDeck Virtual Camera")
        self.busy.touch()
        result = self.run_script("stop")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [f"delete {self.dev}/video20", f"delete {self.dev}/video21"])
        self.assertIn("in use, kept", result.stderr)

    def test_status(self):
        self.assertEqual(self.run_script("status").returncode, 1)
        self.device(22, "PixyDeck Virtual Camera")
        self.assertEqual(self.run_script("status").returncode, 0)

    def test_usage(self):
        self.assertEqual(self.run_script("dance").returncode, 2)

    def test_module_is_loaded_without_a_default_device(self):
        # A bare "modprobe v4l2loopback" adds an empty "Dummy video device" that apps list.
        for path in (ROOT / "deploy" / "pixydeck-virtual-camera.service.in", HELPER):
            lines = [line for line in path.read_text().splitlines()
                     if "modprobe v4l2loopback" in line and not line.lstrip().startswith("#")]
            self.assertTrue(lines, path)
            self.assertTrue(all("devices=0" in line for line in lines), path)


if __name__ == "__main__":
    unittest.main()
