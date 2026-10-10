"""Log file and crash capture.

A desktop app started from the menu has no visible stderr, so warnings,
Qt messages and uncaught exceptions (GUI and worker threads) go to a
rotating log file that bug reports can include.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME, __version__

log = logging.getLogger("pixydeck")


def log_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "pixydeck"


def log_file() -> Path:
    return log_dir() / "pixydeck.log"


def setup_logging(debug: bool | None = None) -> Path | None:
    """Log to ~/.local/state/pixydeck/pixydeck.log (1 MB x 3) and stderr.

    Set PIXYDECK_DEBUG=1 for debug output. Returns the log path, or None if
    the directory is not writable (logging then only goes to stderr).
    """
    if debug is None:
        debug = os.environ.get("PIXYDECK_DEBUG", "") not in ("", "0")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    path: Path | None = log_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    except OSError as exc:
        log.warning("cannot write log file %s: %s", path, exc)
        path = None
    install_crash_handlers()
    log.info("%s %s on Python %s, %s", APP_NAME, __version__, platform.python_version(), platform.platform())
    return path


def install_crash_handlers() -> None:
    """Record uncaught exceptions instead of losing them on a hidden stderr."""

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        log.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


def install_qt_message_handler() -> None:
    """Forward Qt's own warnings (camera, multimedia, platform) to the log."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qt_log = logging.getLogger("qt")

    def handler(mode, context, message):
        category = f"[{context.category}] " if context.category else ""
        qt_log.log(levels.get(mode, logging.WARNING), "%s%s", category, message)

    qInstallMessageHandler(handler)
