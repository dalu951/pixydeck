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
        self.level = logging.getLogger().level

    def tearDown(self):
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if handler not in self.handlers:
                root.removeHandler(handler)
                handler.close()
        sys.excepthook, threading.excepthook = self.hooks
        root.setLevel(self.level)
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


    def setup(self, *args, **kwargs):
        with mock.patch("sys.stderr", new=io.StringIO()):
            return diagnostics.setup_logging(*args, **kwargs)

    def test_default_log_dir_without_xdg(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("XDG_STATE_HOME", None)
            self.assertEqual(diagnostics.log_dir(), Path.home() / ".local" / "state" / "pixydeck")

    def test_empty_xdg_falls_back_to_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": ""}):
            self.assertEqual(diagnostics.log_file(), Path.home() / ".local/state/pixydeck/pixydeck.log")

    def test_rotating_file_handler_settings(self):
        path = self.setup()
        handlers = [h for h in logging.getLogger().handlers
                    if isinstance(h, diagnostics.RotatingFileHandler) and h not in self.handlers]
        self.assertEqual(len(handlers), 1)
        self.assertEqual(Path(handlers[0].baseFilename), path)
        self.assertEqual(handlers[0].maxBytes, 1_000_000)
        self.assertEqual(handlers[0].backupCount, 3)

    def test_info_level_by_default(self):
        for value in ("", "0"):
            with self.subTest(PIXYDECK_DEBUG=value), mock.patch.dict(os.environ, {"PIXYDECK_DEBUG": value}):
                self.setup()
                self.assertEqual(logging.getLogger().level, logging.INFO)
                logging.getLogger("pixydeck.test").debug("hidden-debug-line")
                self.assertNotIn("hidden-debug-line", self.read_log())

    def test_pixydeck_debug_env_enables_debug(self):
        with mock.patch.dict(os.environ, {"PIXYDECK_DEBUG": "1"}):
            self.setup()
        self.assertEqual(logging.getLogger().level, logging.DEBUG)
        logging.getLogger("pixydeck.test").debug("visible-debug-line")
        self.assertIn("visible-debug-line", self.read_log())

    def test_explicit_debug_argument_wins(self):
        with mock.patch.dict(os.environ, {"PIXYDECK_DEBUG": "1"}):
            self.setup(debug=False)
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_unwritable_log_dir_falls_back_to_stderr(self):
        blocker = Path(self.tmp.name) / "file"
        blocker.write_text("not a directory")
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(blocker)}), \
                mock.patch("sys.stderr", new=stderr):
            path = diagnostics.setup_logging()
        self.assertIsNone(path)
        self.assertIn("cannot write log file", stderr.getvalue())
        self.assertIn("EMEET PixyDeck", stderr.getvalue())

    def test_keyboard_interrupt_goes_to_default_hook(self):
        diagnostics.install_crash_handlers()
        with mock.patch.object(sys, "__excepthook__") as default, \
                mock.patch.object(diagnostics.log, "critical") as critical:
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        default.assert_called_once()
        critical.assert_not_called()

    def test_thread_hook_without_thread_name(self):
        diagnostics.install_crash_handlers()
        args = mock.Mock(thread=None, exc_type=ValueError, exc_value=ValueError("x"), exc_traceback=None)
        with self.assertLogs("pixydeck", level="CRITICAL") as logs:
            threading.excepthook(args)
        self.assertIn("Uncaught exception in thread ?", logs.output[0])



class QtMessageHandlerTest(unittest.TestCase):
    def setUp(self):
        from PySide6 import QtCore
        self.qt = QtCore
        self.addCleanup(QtCore.qInstallMessageHandler, None)

    def test_qt_messages_are_forwarded_with_levels(self):
        diagnostics.install_qt_message_handler()
        with self.assertLogs("qt", level="DEBUG") as logs:
            self.qt.qDebug("qt-debug-msg")
            self.qt.qInfo("qt-info-msg")
            self.qt.qWarning("qt-warning-msg")
            self.qt.qCritical("qt-critical-msg")
        levels = {record.getMessage().split()[-1]: record.levelno for record in logs.records}
        self.assertEqual(levels, {
            "qt-debug-msg": logging.DEBUG,
            "qt-info-msg": logging.INFO,
            "qt-warning-msg": logging.WARNING,
            "qt-critical-msg": logging.ERROR,
        })

    def test_category_prefix(self):
        diagnostics.install_qt_message_handler()
        captured = []
        with mock.patch.object(logging.getLogger("qt"), "log",
                               side_effect=lambda level, fmt, *args: captured.append((level, fmt % args))):
            # Uninstalling hands back the installed closure to call directly.
            handler = self.qt.qInstallMessageHandler(None)
            context = mock.Mock(category="qt.multimedia")
            handler(self.qt.QtMsgType.QtWarningMsg, context, "camera busy")
            handler(self.qt.QtMsgType.QtFatalMsg, mock.Mock(category=None), "fatal")
            handler(object(), mock.Mock(category=""), "odd")
        self.assertEqual(captured, [
            (logging.WARNING, "[qt.multimedia] camera busy"),
            (logging.CRITICAL, "fatal"),
            (logging.WARNING, "odd"),
        ])


if __name__ == "__main__":
    unittest.main()
