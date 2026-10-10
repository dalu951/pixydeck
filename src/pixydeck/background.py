"""Background replacement: green-screen keying and AI person matting.

All functions work on OpenCV BGR uint8 images and are pure, so they can be
used from the render thread pool and tested without a camera.

Keying happens in YCrCb: the distance of each pixel's chroma (Cr, Cb) to
the key colour decides how transparent it is. Brightness is ignored, which
makes the key robust against the uneven lighting real green screens have.

Without a green screen, Robust Video Matting (RVM, GPL-3.0) separates the
person from the room. It is recurrent - each frame refines the previous
mask - so it has to see frames in order on a single thread.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

try:
    import onnxruntime
except ImportError:  # pragma: no cover - optional extra
    onnxruntime = None

MATTING_MODEL = Path(__file__).resolve().parent / "assets" / "rvm_mobilenetv3_fp32.onnx"
# RVM input size; the mask is scaled up to the frame afterwards.
MATTING_SIZE = (960, 540)

# Chroma of a typical chroma-key green (BGR 64, 177, 0) in YCrCb.
DEFAULT_KEY = (64.0, 85.0)
# Distances are normalized by the largest possible chroma distance.
MAX_CHROMA_DISTANCE = 181.0


def detect_green_screen(image: np.ndarray, min_share: float = 0.4) -> tuple[float, float] | None:
    """Return the key chroma (Cr, Cb) if the frame border is mostly green.

    Only the top and side borders are sampled; the lower middle is where
    the person sits. Green walls, cloths and pop-up screens all qualify.
    """
    height, width = image.shape[:2]
    band_h, band_w = max(2, height // 8), max(2, width // 8)
    border = np.concatenate([
        image[:band_h].reshape(-1, 3),
        image[:, :band_w].reshape(-1, 3),
        image[:, -band_w:].reshape(-1, 3),
    ])
    hsv = cv2.cvtColor(border.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    green = (hsv[:, 0] >= 35) & (hsv[:, 0] <= 90) & (hsv[:, 1] >= 70) & (hsv[:, 2] >= 40)
    if green.mean() < min_share:
        return None
    ycrcb = cv2.cvtColor(border[green].reshape(-1, 1, 3), cv2.COLOR_BGR2YCrCb).reshape(-1, 3)
    return float(np.median(ycrcb[:, 1])), float(np.median(ycrcb[:, 2]))


def key_alpha(image: np.ndarray, key: tuple[float, float],
              similarity: float = 0.2, smoothness: float = 0.1) -> np.ndarray:
    """Foreground alpha in 0..1 (float32, same size as ``image``).

    The mask is computed at half resolution and scaled up, which is faster
    and gives naturally soft edges.
    """
    height, width = image.shape[:2]
    small = cv2.resize(image, (width // 2, height // 2), interpolation=cv2.INTER_AREA)
    _y, cr, cb = cv2.split(cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb))
    distance = cv2.magnitude(cr.astype(np.float32) - key[0], cb.astype(np.float32) - key[1])
    # alpha = clip((distance / MAX - similarity) / smoothness, 0, 1)
    smoothness = max(smoothness, 1e-3)
    alpha = distance * (1.0 / (MAX_CHROMA_DISTANCE * smoothness)) - similarity / smoothness
    alpha = np.clip(alpha, 0.0, 1.0, out=alpha)
    # Remove speckles in the screen and pinholes in the person.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel)
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    return cv2.resize(alpha, (width, height), interpolation=cv2.INTER_LINEAR)


def despill(image: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """Remove green light reflected onto hair, skin and edges."""
    if strength <= 0:
        return image
    b, g, r = cv2.split(image)
    spill = cv2.subtract(g, cv2.max(r, b))          # saturates at 0
    g = cv2.addWeighted(g, 1.0, spill, -strength, 0)
    return cv2.merge([b, g, r])


def composite(foreground: np.ndarray, alpha: np.ndarray, background: np.ndarray) -> np.ndarray:
    return cv2.blendLinear(foreground, background, alpha, 1.0 - alpha)


def gradient_background(width: int, height: int) -> np.ndarray:
    """Calm studio-style gradient used when no image is chosen."""
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    glow = np.exp(-(((x - 0.5) ** 2) / 0.18 + ((y - 0.35) ** 2) / 0.25))
    top = np.array([58, 40, 30], np.float32)      # BGR, deep blue-grey
    bottom = np.array([24, 18, 14], np.float32)
    light = np.array([150, 110, 80], np.float32)
    image = top * (1 - y)[..., None] + bottom * y[..., None]
    image = image + (light - image) * (glow[..., None] * 0.45)
    return np.clip(image, 0, 255).astype(np.uint8)


def cover(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Scale and centre-crop ``image`` to fill width x height."""
    h, w = image.shape[:2]
    scale = max(width / w, height / h)
    size = (max(width, round(w * scale)), max(height, round(h * scale)))
    resized = cv2.resize(image, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y:y + height, x:x + width]


def matting_available() -> bool:
    return onnxruntime is not None and MATTING_MODEL.exists()


class Matting:
    """Stateful RVM session: call ``alpha`` with consecutive frames."""

    def __init__(self, threads: int | None = None) -> None:
        options = onnxruntime.SessionOptions()
        # Measured on a 16-core machine with the render pool busy: 6 threads
        # with ORT's default spinning were fastest (36 ms vs 51 ms at 4).
        options.intra_op_num_threads = threads or max(2, min(6, (os.cpu_count() or 4) // 2))
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(MATTING_MODEL), options, providers=["CPUExecutionProvider"])
        self._ratio = np.array([0.4], np.float32)
        self.reset()

    def reset(self) -> None:
        self._state = [np.zeros((1, 1, 1, 1), np.float32)] * 4

    def alpha(self, image: np.ndarray) -> np.ndarray:
        """Foreground alpha (float32 0..1) at ``MATTING_SIZE``."""
        # One pass: resize, BGR->RGB, scale to 0..1, NCHW float32.
        src = cv2.dnn.blobFromImage(image, 1 / 255.0, MATTING_SIZE, swapRB=True)
        r1, r2, r3, r4 = self._state
        _fgr, pha, *self._state = self._session.run(None, {
            "src": src, "r1i": r1, "r2i": r2, "r3i": r3, "r4i": r4, "downsample_ratio": self._ratio,
        })
        return pha[0, 0]


def blurred(image: np.ndarray, strength: float) -> np.ndarray:
    """Cheap strong blur: shrink, blur, grow back."""
    height, width = image.shape[:2]
    small = cv2.resize(image, (max(16, width // 4), max(9, height // 4)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, strength))
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)


@dataclass
class Background:
    """Settings for one keying pass; replaced (not mutated) by the GUI."""

    mode: str = "off"            # off | auto | chroma ("Green screen" in the UI) | ai
    fill: str = "blur"           # blur | gradient | color | image
    color: tuple[int, int, int] = (40, 40, 40)   # BGR
    image_path: str = ""
    similarity: float = 0.2
    smoothness: float = 0.1
    spill: float = 0.7
    blur: float = 6.0
    key: tuple[float, float] | None = None       # detected key chroma
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def uses_matting(self) -> bool:
        """AI matting: always in ``ai`` mode, in ``auto`` while no green screen is seen."""
        return matting_available() and (
            self.mode == "ai" or (self.mode == "auto" and self.key is None))

    @property
    def active(self) -> bool:
        if self.mode == "off":
            return False
        return (self.key is not None and self.mode in ("auto", "chroma")) or self.uses_matting

    def backdrop(self, width: int, height: int) -> np.ndarray:
        with self._lock:
            cached = self._cache.get((width, height))
        if cached is not None:
            return cached
        image = None
        if self.fill == "image" and self.image_path and Path(self.image_path).is_file():
            loaded = cv2.imread(self.image_path, cv2.IMREAD_COLOR)
            if loaded is not None:
                image = cover(loaded, width, height)
        if image is None and self.fill == "color":
            image = np.empty((height, width, 3), np.uint8)
            image[:] = self.color
        if image is None:
            image = gradient_background(width, height)
        with self._lock:
            self._cache[(width, height)] = image
        return image

    def apply(self, image: np.ndarray, matte: np.ndarray | None = None) -> np.ndarray:
        """Replace the background; ``matte`` is the AI alpha when matting is used."""
        height, width = image.shape[:2]
        if matte is not None:
            alpha = cv2.resize(matte, (width, height), interpolation=cv2.INTER_LINEAR)
            foreground = image
        else:
            alpha = key_alpha(image, self.key or DEFAULT_KEY, self.similarity, self.smoothness)
            foreground = despill(image, self.spill)
        if self.fill == "blur" and matte is not None:
            backdrop = blurred(image, self.blur)
        else:
            # Blurring a green screen only gives a green blur; use the gradient.
            backdrop = self.backdrop(width, height)
        return composite(foreground, alpha, backdrop)
