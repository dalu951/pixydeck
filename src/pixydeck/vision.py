"""Software framing for the PIXY: digital zoom, auto-framing and the
processed virtual-camera output.

The PIXY delivers MJPEG. Qt hands us each compressed frame; the GUI thread
only copies the JPEG bytes (well under a millisecond) and this module does
all decoding, face detection, cropping and output work on a background
thread, so the live preview never stutters.

OpenCV/NumPy are optional (``pip install pixydeck[ai]``). Without
them the rest of the application works and these features report as
unavailable.
"""

from __future__ import annotations

import logging
import math
import queue
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - depends on optional extra
    cv2 = None
    np = None

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)

if cv2 is not None:
    from .background import Background, Matting, detect_green_screen, matting_available
else:  # pragma: no cover - optional extra
    Background = Matting = None
    detect_green_screen = None

    def matting_available() -> bool:
        return False

MODEL = Path(__file__).resolve().parent / "assets" / "face_detection_yunet_2023mar.onnx"
DETECT_WIDTH = 480
DETECT_INTERVAL = 0.15
GREEN_CHECK_INTERVAL = 0.5
# Keying works on a frame of at most this width (half-decoded 4K).
KEY_WIDTH = 1920
# A full 4K JPEG decode takes ~30 ms; decoding frames in parallel keeps the
# processed virtual camera at the camera's frame rate.
RENDER_THREADS = 3


def jpeg_complete(jpeg) -> bool:
    """True when the buffer still holds a whole JPEG (ends with EOI).

    Qt occasionally hands over a buffer the driver is already refilling;
    decoding it would show a grey band at the bottom of the frame.
    """
    tail = jpeg[-65536:].tobytes()
    return tail.rfind(b"\xff\xd9") != -1


def vision_available() -> bool:
    return cv2 is not None and hasattr(cv2, "FaceDetectorYN") and MODEL.exists()


@dataclass(frozen=True)
class Crop:
    """Normalized crop: centre (cx, cy) in 0..1 and zoom factor >= 1."""

    cx: float = 0.5
    cy: float = 0.5
    zoom: float = 1.0

    def clamped(self, max_zoom: float = 4.0) -> "Crop":
        zoom = max(1.0, min(self.zoom, max_zoom))
        half = 0.5 / zoom
        return Crop(
            min(max(self.cx, half), 1.0 - half),
            min(max(self.cy, half), 1.0 - half),
            zoom,
        )

    def rect(self) -> tuple[float, float, float, float]:
        """Return normalized (x, y, w, h)."""
        c = self.clamped()
        size = 1.0 / c.zoom
        return c.cx - size / 2, c.cy - size / 2, size, size


def framing_target(faces: list[tuple[float, float, float, float]],
                   fill: float = 0.42, max_zoom: float = 2.5) -> Crop:
    """Compute where the crop should go for the given normalized face boxes.

    The union of all faces is centred horizontally and placed slightly
    above the middle (classic headroom). ``fill`` is the share of the frame
    height the head-and-shoulders group should occupy.
    """
    if not faces:
        return Crop()
    x0 = min(f[0] for f in faces)
    y0 = min(f[1] for f in faces)
    x1 = max(f[0] + f[2] for f in faces)
    y1 = max(f[1] + f[3] for f in faces)
    width, height = x1 - x0, y1 - y0
    # A face is roughly 1/2.2 of a head-and-shoulders shot; keep groups in
    # frame horizontally as well.
    zoom = min(fill / max(height * 2.2, 1e-3), 0.8 / max(width * 1.6, 1e-3))
    zoom = max(1.0, min(zoom, max_zoom))
    cy = (y0 + y1) / 2 + 0.12 / zoom
    return Crop((x0 + x1) / 2, cy, zoom).clamped(max_zoom)


class Smoother:
    """Exponential approach towards a target crop.

    A dead zone keeps the frame perfectly still while someone only shifts
    slightly in their chair, which matters more for comfort than speed.
    """

    def __init__(self, speed: float = 2.5, dead_zone: float = 0.04) -> None:
        self.current = Crop()
        self.target = Crop()
        self.speed = speed
        self.dead_zone = dead_zone
        self._moving = False

    @staticmethod
    def _distance(a: Crop, b: Crop) -> float:
        return max(abs(a.cx - b.cx), abs(a.cy - b.cy), abs(a.zoom - b.zoom) / 4)

    def set_target(self, target: Crop) -> None:
        if self._moving or self._distance(target, self.current) > self.dead_zone:
            self.target = target
            self._moving = True

    def step(self, dt: float) -> Crop:
        alpha = 1.0 - math.exp(-self.speed * dt)
        c, t = self.current, self.target
        self.current = Crop(
            c.cx + (t.cx - c.cx) * alpha,
            c.cy + (t.cy - c.cy) * alpha,
            c.zoom + (t.zoom - c.zoom) * alpha,
        )
        if self._distance(t, self.current) < 0.002:
            self._moving = False
        return self.current


class Stabilizer:
    """Cancels small, fast camera shake (e.g. a wobbling monitor).

    The global shift between consecutive frames is measured with phase
    correlation. Integrated, it gives the camera path; a low-pass copy of
    that path is the intended motion (pans, slow drift). The difference is
    the shake, which the renderer shifts back out. Large jumps and PTZ moves
    reset the filter instead of being "stabilized".
    """

    SIZE = (320, 180)
    # Measurement noise floor (pixels at SIZE) and minimum match confidence.
    NOISE_PX = 0.35
    MIN_RESPONSE = 0.12

    def __init__(self, margin: float = 0.04, smoothing: float = 0.12) -> None:
        self.margin = margin
        self.smoothing = smoothing
        self._window = cv2.createHanningWindow(self.SIZE, cv2.CV_32F) if cv2 is not None else None
        self.paused_until = 0.0
        self.reset()

    def reset(self) -> None:
        self._previous = None
        self._path = [0.0, 0.0]
        self._smooth = [0.0, 0.0]

    def update(self, image) -> tuple[float, float]:
        """Feed the next frame (BGR, any size); return the normalized shake offset."""
        gray = cv2.cvtColor(cv2.resize(image, self.SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        gray = gray.astype(np.float32)
        previous, self._previous = self._previous, gray
        if previous is None:
            return 0.0, 0.0
        (dx, dy), response = cv2.phaseCorrelate(previous, gray, self._window)
        if response < self.MIN_RESPONSE:
            # Weak, ambiguous match (e.g. repetitive textures): don't trust it.
            dx = dy = 0.0
        # Sub-pixel noise would otherwise be "corrected" into visible jitter.
        dx = 0.0 if abs(dx) < self.NOISE_PX else dx
        dy = 0.0 if abs(dy) < self.NOISE_PX else dy
        dx, dy = dx / self.SIZE[0], dy / self.SIZE[1]
        self._path[0] += dx
        self._path[1] += dy
        if time.monotonic() < self.paused_until or max(abs(dx), abs(dy)) > 0.08:
            # Deliberate movement or a cut: follow it instead of fighting it.
            self._smooth = list(self._path)
            return 0.0, 0.0
        for axis in (0, 1):
            self._smooth[axis] += (self._path[axis] - self._smooth[axis]) * self.smoothing
        return tuple(max(-self.margin, min(self.margin, p - s)) for p, s in zip(self._path, self._smooth))


def shift_image(image, offset: tuple[float, float]):
    """Move image content by -offset (normalized), replicating the border."""
    ox, oy = offset
    if ox == 0 and oy == 0:
        return image
    height, width = image.shape[:2]
    matrix = np.float32([[1, 0, -ox * width], [0, 1, -oy * height]])
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


class FrameProcessor(QObject):
    """Background thread: face detection + processed virtual camera."""

    faces_detected = Signal(list)  # list of normalized (x, y, w, h)
    green_screen = Signal(object)  # detected key chroma (Cr, Cb) or None
    preview_ready = Signal()       # call take_preview() for the newest frame
    output_error = Signal(str)
    output_stats = Signal(float)   # output fps

    def __init__(self) -> None:
        super().__init__()
        self._cond = threading.Condition()
        self._jpeg = None
        self._running = True
        self._detect = False
        self._crop = Crop()
        self._output: subprocess.Popen | None = None
        self._output_lock = threading.Lock()
        self._output_size = (1280, 720)
        self._detector = None
        self._last_detect = 0.0
        self._source_width = 0
        self._background = Background() if Background is not None else None
        self._last_green = 0.0
        self._key: tuple[float, float] | None = None
        self._green_visible = False
        self._preview: QImage | None = None
        self._preview_pending = False
        self._preview_lock = threading.Lock()
        self._matting = None
        self._stabilizer = Stabilizer() if cv2 is not None else None
        self._stabilize = False
        if cv2 is not None:
            # Parallelism comes from the render pool; nested OpenCV thread
            # pools per worker would oversubscribe the CPU.
            cv2.setNumThreads(RENDER_THREADS - 1)
        self._pool = ThreadPoolExecutor(RENDER_THREADS, thread_name_prefix="pixy-render")
        self._in_flight = threading.Semaphore(RENDER_THREADS)
        self._rendered: queue.Queue[Future | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="pixy-vision", daemon=True)
        self._thread.start()
        self._writer = threading.Thread(target=self._write_loop, name="pixy-output", daemon=True)
        self._writer.start()

    # -- called from the GUI thread ------------------------------------
    @property
    def wants_frames(self) -> bool:
        background = self._background
        return self._detect or self._output is not None or self._stabilize or (
            background is not None and background.mode != "off")

    def set_stabilization(self, enabled: bool) -> None:
        self._stabilize = enabled and self._stabilizer is not None
        if self._stabilizer is not None:
            self._stabilizer.reset()

    @property
    def stabilizing(self) -> bool:
        return self._stabilize

    @property
    def stabilization_margin(self) -> float:
        return self._stabilizer.margin if self._stabilizer is not None else 0.0

    def pause_stabilization(self, seconds: float = 0.6) -> None:
        """Called while the camera is panned on purpose."""
        if self._stabilizer is not None:
            self._stabilizer.paused_until = time.monotonic() + seconds

    @property
    def key(self) -> tuple[float, float] | None:
        """Chroma of the detected green screen, or None."""
        return self._key

    @property
    def background_active(self) -> bool:
        return self._background is not None and self._background.active

    def set_background(self, background) -> None:
        """Install new background settings; the detected key is kept."""
        if self._background is None:
            return
        background.key = self._key
        self._background = background

    def take_preview(self) -> QImage | None:
        with self._preview_lock:
            image, self._preview = self._preview, None
            self._preview_pending = False
        return image

    def submit(self, jpeg, source_width: int = 0) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._source_width = source_width
            self._cond.notify()

    def busy(self) -> bool:
        return self._jpeg is not None

    def set_detection(self, enabled: bool) -> None:
        self._detect = enabled and vision_available()

    def set_crop(self, crop: Crop) -> None:
        self._crop = crop

    def start_output(self, ffmpeg: str, device: str, width: int, height: int, fps: int) -> None:
        self.stop_output()
        self._output_size = (width, height)
        process = subprocess.Popen(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "yuv420p",
                "-video_size", f"{width}x{height}", "-framerate", str(fps),
                "-i", "-",
                "-f", "v4l2", device,
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._output = process
        log.info("Virtual camera output: %s %dx%d@%d (ffmpeg pid %d)", device, width, height, fps, process.pid)
        threading.Thread(target=self._watch_output, args=(process,), name="ffmpeg-watch", daemon=True).start()

    def _watch_output(self, process: subprocess.Popen) -> None:
        """Drain FFmpeg's stderr (a full pipe would stall it) and report its exit."""
        tail: list[str] = []
        for raw in process.stderr:
            line = raw.decode(errors="replace").rstrip()
            if line:
                log.warning("ffmpeg: %s", line)
                tail = (tail + [line])[-5:]
        code = process.wait()
        for stream in (process.stdin, process.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass  # the writer thread may be closing it too
        self._output_failed(process, " ".join(tail) or f"FFmpeg exited ({code})")

    def stop_output(self) -> None:
        with self._output_lock:
            process, self._output = self._output, None
        if process is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    @property
    def output_pid(self) -> int | None:
        process = self._output
        return process.pid if process is not None else None

    def shutdown(self) -> None:
        self.stop_output()
        with self._cond:
            self._running = False
            self._cond.notify()
        self._thread.join(timeout=2)
        self._rendered.put(None)
        self._writer.join(timeout=2)
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- worker thread -------------------------------------------------
    def _run(self) -> None:
        while True:
            with self._cond:
                while self._running and self._jpeg is None:
                    self._cond.wait()
                if not self._running:
                    return
                jpeg, self._jpeg = self._jpeg, None
                source_width = self._source_width
            if cv2 is None or not jpeg_complete(jpeg):
                continue

            now = time.monotonic()
            small = None
            if self._detect and now - self._last_detect >= DETECT_INTERVAL:
                self._last_detect = now
                small = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_4)
                self._run_detection(small)
            background = self._background
            if background is not None and background.mode != "off" and now - self._last_green >= GREEN_CHECK_INTERVAL:
                self._last_green = now
                if small is None:
                    small = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_4)
                self._check_green_screen(small, background)

            shake = (0.0, 0.0)
            if self._stabilize:
                # Sequential by nature: every frame is compared with the last one.
                if small is None:
                    small = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_4)
                if small is not None:
                    shake = self._stabilizer.update(small)

            process = self._output
            keyed = background is not None and background.active
            want_preview = keyed or self._stabilize
            if (process is not None or want_preview) and self._in_flight.acquire(blocking=False):
                matte = None
                if keyed and background.uses_matting:
                    # Recurrent model: must see frames in order, on this thread.
                    matte = self._run_matting(jpeg)
                # Frames are rendered in parallel but written strictly in order.
                future = self._pool.submit(self._render, jpeg, self._crop, self._output_size, source_width,
                                           background if keyed else None, process is not None, matte,
                                           shake, want_preview)
                self._rendered.put((process, future))
            # else: all render slots busy -> drop this frame instead of queueing lag.

    def _run_matting(self, jpeg):
        if self._matting is None:
            try:
                self._matting = Matting()
            except Exception as exc:  # noqa: BLE001 - surface any model/runtime problem
                self.output_error.emit(f"AI background unavailable: {exc}")
                self._background.mode = "off"
                return None
        image = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_2)
        return None if image is None else self._matting.alpha(image)

    def _check_green_screen(self, small, background) -> None:
        if small is None:
            return
        key = detect_green_screen(cv2.resize(small, (480, 270), interpolation=cv2.INTER_AREA))
        if key is not None and self._key is not None:
            # Follow slow lighting changes without jitter.
            key = (self._key[0] * 0.8 + key[0] * 0.2, self._key[1] * 0.8 + key[1] * 0.2)
        # Report the screen entering or leaving the picture once. Chroma mode
        # keeps the last key while it is out of view, so visibility is
        # tracked on its own rather than derived from the key.
        visible = key is not None
        if key is not None or background.mode == "auto":
            self._key = key
            background.key = key
        if visible != self._green_visible:
            self._green_visible = visible
            self.green_screen.emit(key)

    def _write_loop(self) -> None:
        frames, window_start = 0, time.monotonic()
        while True:
            item = self._rendered.get()
            if item is None:
                return
            process, future = item
            try:
                data, preview = future.result()
            except Exception:  # noqa: BLE001 - a bad frame must not kill the pipeline
                data, preview = None, None
            finally:
                self._in_flight.release()
            if preview is not None:
                with self._preview_lock:
                    self._preview = preview
                    notify = not self._preview_pending
                    self._preview_pending = True
                if notify:
                    self.preview_ready.emit()
            if data is None or process is None or process is not self._output:
                continue
            try:
                process.stdin.write(data)
            except (BrokenPipeError, OSError, ValueError):
                # FFmpeg is gone; _watch_output reports it with its stderr.
                continue
            frames += 1
            now = time.monotonic()
            if now - window_start >= 1.0:
                self.output_stats.emit(frames / (now - window_start))
                frames, window_start = 0, now

    def _run_detection(self, image) -> None:
        if image is None:
            return
        height, width = image.shape[:2]
        if width > DETECT_WIDTH:
            scale = DETECT_WIDTH / width
            image = cv2.resize(image, (DETECT_WIDTH, round(height * scale)), interpolation=cv2.INTER_AREA)
            height, width = image.shape[:2]
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(str(MODEL), "", (width, height), 0.75)
        self._detector.setInputSize((width, height))
        _, found = self._detector.detect(image)
        faces = []
        if found is not None:
            for row in found:
                x, y, w, h = (float(v) for v in row[:4])
                faces.append((x / width, y / height, w / width, h / height))
        self.faces_detected.emit(faces)

    @staticmethod
    def _render(jpeg, crop: Crop, size: tuple[int, int], source_width: int,
                background, want_output: bool, matte=None, shake=(0.0, 0.0),
                want_preview: bool = False) -> tuple[bytes | None, QImage | None]:
        """Decode one frame; return (YUV420 output bytes, processed preview image)."""
        crop = crop.clamped()
        out_w, out_h = size
        preview = None
        if want_preview:
            # Process the whole frame once; preview and output both use it.
            reduced = source_width > KEY_WIDTH
            image = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_2 if reduced else cv2.IMREAD_COLOR)
            if image is None:
                return None, None
            if background is not None:
                if background.uses_matting and matte is None:
                    return None, None
                image = background.apply(image, matte)
            image = shift_image(image, shake)
            h, w = image.shape[:2]
            # Convert here, not in the GUI thread: RGB32 is Qt's native pixmap format.
            bgra = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
            preview = QImage(bgra.data, w, h, bgra.strides[0], QImage.Format_RGB32).copy()
        else:
            # Half-resolution decoding is ~3x faster; use it whenever the crop
            # still has enough pixels for the output size.
            reduced = source_width and (source_width / 2) / crop.zoom >= out_w * 0.9
            image = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_2 if reduced else cv2.IMREAD_COLOR)
            if image is None:
                return None, None
        if not want_output:
            return None, preview
        height, width = image.shape[:2]
        x, y, w, h = crop.rect()
        px, py = int(x * width), int(y * height)
        pw, ph = max(2, int(w * width)), max(2, int(h * height))
        region = image[py:py + ph, px:px + pw]
        interpolation = cv2.INTER_AREA if pw > out_w else cv2.INTER_LINEAR
        frame = cv2.resize(region, (out_w, out_h), interpolation=interpolation)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420).tobytes(), preview

    def _output_failed(self, process: subprocess.Popen, message: str) -> None:
        with self._output_lock:
            if process is not self._output:
                return  # stopped on purpose or already replaced
            self._output = None
        log.error("Virtual camera output stopped: %s", message)
        self.output_error.emit(message)
