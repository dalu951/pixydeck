"""Background execution of PIXY control commands.

Every UVC/HID call runs on one worker thread so the GUI never blocks
(HID mode changes include deliberate 200 ms pauses). Commands submitted
with a ``key`` are coalesced: while a slider is dragged only the newest
pending value is sent, so the camera follows the pointer instead of
working through a backlog.
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from .backend import PixyError


class ControlWorker(QObject):
    failed = Signal(str)
    _deliver = Signal(object, object)

    def __init__(self) -> None:
        super().__init__()
        self._cond = threading.Condition()
        self._latest: OrderedDict[str, tuple] = OrderedDict()
        self._queue: deque[tuple] = deque()
        self._running = True
        self._deliver.connect(self._on_deliver)
        self._thread = threading.Thread(target=self._run, name="pixy-control", daemon=True)
        self._thread.start()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        key: str | None = None,
        done: Callable[[Any], None] | None = None,
    ) -> None:
        """Run ``fn(*args)`` on the worker; call ``done(result)`` in the GUI thread."""
        item = (fn, args, done)
        with self._cond:
            if key is None:
                self._queue.append(item)
            else:
                self._latest.pop(key, None)
                self._latest[key] = item
            self._cond.notify()

    def shutdown(self, timeout: float = 3.0) -> None:
        with self._cond:
            self._running = False
            self._cond.notify()
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._running and not self._queue and not self._latest:
                    self._cond.wait()
                if self._queue:
                    fn, args, done = self._queue.popleft()
                elif self._latest:
                    _, (fn, args, done) = self._latest.popitem(last=False)
                else:
                    return
            try:
                result = fn(*args)
            except (PixyError, OSError, ValueError) as exc:
                self.failed.emit(str(exc))
                continue
            if done is not None:
                self._deliver.emit(done, result)

    @Slot(object, object)
    def _on_deliver(self, done, result) -> None:
        done(result)
