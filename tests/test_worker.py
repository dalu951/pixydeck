import os
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from pixydeck.backend import PixyError, camera_users
from pixydeck.worker import ControlWorker

APP = QCoreApplication.instance() or QCoreApplication([])


def wait_for(predicate, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class ControlWorkerTest(unittest.TestCase):
    def setUp(self):
        self.worker = ControlWorker()

    def tearDown(self):
        self.worker.shutdown()

    def test_keyed_commands_are_coalesced(self):
        gate = threading.Event()
        calls = []
        self.worker.submit(gate.wait)  # keep the worker busy
        for value in range(10):
            self.worker.submit(calls.append, value, key="zoom")
        gate.set()
        self.assertTrue(wait_for(lambda: calls))
        time.sleep(0.05)
        self.assertEqual(calls, [9])

    def test_done_runs_with_result(self):
        results = []
        self.worker.submit(lambda: 42, done=results.append)
        self.assertTrue(wait_for(lambda: results))
        self.assertEqual(results, [42])

    def test_errors_are_reported(self):
        errors = []
        self.worker.failed.connect(errors.append)

        def fail():
            raise PixyError("boom")

        self.worker.submit(fail)
        self.assertTrue(wait_for(lambda: errors))
        self.assertEqual(errors, ["boom"])


class CameraUsersTest(unittest.TestCase):
    def test_finds_and_excludes_processes(self):
        with open("/dev/null", "rb"):
            users = camera_users(["/dev/null"])
            self.assertIn(os.getpid(), [pid for pid, _ in users])
            excluded = camera_users(["/dev/null"], exclude_pids=[os.getpid()])
            self.assertNotIn(os.getpid(), [pid for pid, _ in excluded])

    def test_missing_device(self):
        self.assertEqual(camera_users(["/dev/does-not-exist"]), [])


if __name__ == "__main__":
    unittest.main()
