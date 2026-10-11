"""A simulated EMEET PIXY HID interface for tests.

``FakePixy`` opens a pseudo terminal in raw mode and answers on the master
side like the camera answers on ``/dev/hidraw*``: every write is one 32-byte
report, every query gets a reply that echoes the head, carries
``00 len 00 len`` and the payload from offset 8. The backend talks to the
slave path with its real ``send_hid_report``/``hid_query`` code, so framing,
draining and echo matching are exercised end to end.

Behaviour mirrors what a PIXY (328f:00c0) was observed to do:

* motor replies come from the motor MCU (group byte 0x63),
* any motor speed is stored as sent,
* target-track mode 3 (full body) is ignored,
* the power-on position stores the *current* pan/tilt, not the request,
* the device-mode readback reports 3 for idle and tracking.
"""

from __future__ import annotations

import os
import pty
import struct
import threading
import tty

REPORT = 32


def frame(head, body=()):
    body = bytes(body)
    if not body:
        return bytes(head)
    return bytes(head) + bytes([0, len(body), 0, len(body)]) + body


class FakePixy:
    def __init__(self) -> None:
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.path = os.ttyname(slave)
        self._slave = slave  # kept open so the pty does not hang up between opens
        self.received: list[bytes] = []
        self.silent = False                # stop answering queries
        self.garbage: bytes | None = None  # answer every query with this instead
        self.state = {
            "mode": 0, "audio": 1, "gesture": 1, "focus": 0, "privacy_s": 0,
            "features": {1: 0, 2: 0, 4: 0},
            "speed": {1: 60.0, 2: 60.0},
            "pos": {1: 0.0, 2: 0.0},
            "target": 0,
            "locks": {0x0A: 0, 0x0C: 0, 0x0E: 0},
            "power_on": (1, 0.0, 0.0),
        }
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    # -- test helpers ----------------------------------------------------
    def push(self, report: bytes) -> None:
        """Send an unsolicited report, like the PIXY does after a gesture."""
        os.write(self.master, report.ljust(REPORT, b"\0"))

    def wait_until(self, predicate, timeout: float = 2.0) -> bool:
        """Writes without a reply are handled asynchronously; wait for them."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if predicate(self.state):
                    return True
            time.sleep(0.005)
        return False

    def sent_heads(self) -> list[tuple[int, ...]]:
        with self._lock:
            return [tuple(report[:4]) for report in self.received]

    def close(self) -> None:
        self._running = False
        for fd in (self.master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass
        self._thread.join(timeout=1)

    # -- protocol --------------------------------------------------------
    def _serve(self) -> None:
        buffer = b""
        while self._running:
            try:
                chunk = os.read(self.master, 4096)
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk
            while len(buffer) >= REPORT:
                report, buffer = buffer[:REPORT], buffer[REPORT:]
                with self._lock:
                    self.received.append(report)
                    reply = self._handle(report)
                if reply is not None and not self.silent:
                    if self.garbage is not None:
                        reply = self.garbage
                    try:
                        os.write(self.master, reply.ljust(REPORT, b"\0"))
                    except OSError:
                        return

    def _handle(self, report: bytes) -> bytes | None:
        head = report[:4]
        length = report[5] if report[4] == 0 and report[6] == 0 and report[5] == report[7] else 0
        body = report[8:8 + length]
        s = self.state
        h = tuple(head)
        if h == (9, 1, 1, 0):
            s["mode"] = body[0]
        elif h == (9, 1, 1, 1):
            return frame(head, [2 if s["mode"] == 2 else 3])
        elif h == (9, 2, 1, 0):
            s["privacy_s"] = body[0]
        elif h == (9, 2, 1, 1):
            return frame(head, [s["privacy_s"], 0, 0, 0])
        elif h == (9, 5, 0, 3):
            s["audio"] = body[0]
        elif h == (9, 5, 0, 4):
            return frame(head, [s["audio"]])
        elif h == (9, 4, 2, 0):
            s["gesture"] = body[1]
        elif h == (9, 4, 2, 1):
            return frame(head, [body[0] if body else 2, s["gesture"]])
        elif h in ((9, 4, 0, 1), (9, 4, 0, 3)):
            s["focus"] = body[0]
        elif h == (9, 4, 0, 2):
            return frame(head, [s["focus"], 0, 0, 0x7F, 0x7F])
        elif h == (9, 4, 0, 8):
            s["features"][body[0]] = body[1]
        elif h == (9, 4, 0, 7):
            return frame(head, [body[0], s["features"].get(body[0], 0)])
        elif h == (9, 4, 1, 0):
            if body[0] in (0, 1, 2):
                s["target"] = body[0]
        elif h == (9, 4, 1, 1):
            return frame(head, bytes([s["target"]]) + bytes(20))
        elif h[1] == 4 and h[2] == 0 and h[3] in (0x09, 0x0B, 0x0D):
            s["locks"][h[3] + 1] = body[0]
        elif h[1] == 4 and h[2] == 0 and h[3] in s["locks"]:
            return frame(head, [s["locks"][h[3]]])
        elif h[1] & 0x1F == 3:
            return self._motor(head, body)
        return None

    def _motor(self, head: bytes, body: bytes) -> bytes | None:
        s = self.state
        command = head[3]
        mcu = bytes([9, 0x63, 1, command])
        if command == 0x02:  # set speed
            s["speed"][body[0]] = struct.unpack_from("<f", body, 1)[0]
        elif command == 0x03:  # get speed
            axis = body[0]
            return frame(mcu, bytes([axis]) + struct.pack("<ff", s["speed"].get(axis, 0.0), 0.0))
        elif command == 0x01:  # get position: (target, actual)
            axis = body[0]
            angle = s["pos"].get(axis, 0.0)
            return frame(mcu, bytes([axis]) + struct.pack("<ff", angle, angle))
        elif command == 0x13:  # set power-on position: stores where it is now
            s["power_on"] = (1, s["pos"][1], s["pos"][2]) if body[0] == 1 else (0, 0.0, 0.0)
        elif command == 0x14:
            mode, pan, tilt = s["power_on"]
            return frame(head, bytes([mode]) + struct.pack("<fff", pan, tilt, 0.0))
        return None
