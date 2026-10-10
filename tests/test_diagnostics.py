import io
import logging
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixydeck import diagnostics  # noqa: E402


class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name})
        self.env.start()
        self.handlers = list(logging.getLogger().handlers)
        self.hooks = (sys.excepthook, threading.excepthook)

    def tearDown(self):
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if handler not in self.handlers:
                root.removeHandler(handler)
                handler.close()
        sys.excepthook, threading.excepthook = self.hooks
        self.env.stop()
        self.tmp.cleanup()

    def read_log(self) -> str:
        for handler in logging.getLogger().handlers:
            handler.flush()
        return diagnostics.log_file().read_text()

    def test_log_file_in_xdg_state_dir(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            path = diagnostics.setup_logging()
        self.assertEqual(path, Path(self.tmp.name) / "pixydeck" / "pixydeck.log")
        self.assertIn("EMEET PixyDeck", self.read_log())

    def test_uncaught_exceptions_are_logged(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            diagnostics.setup_logging()
            try:
                raise RuntimeError("boom in gui")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
            worker = threading.Thread(target=lambda: 1 / 0, name="pixy-test")
            worker.start()
            worker.join()
        text = self.read_log()
        self.assertIn("boom in gui", text)
        self.assertIn("Uncaught exception in thread pixy-test", text)
        self.assertIn("ZeroDivisionError", text)


if __name__ == "__main__":
    unittest.main()
