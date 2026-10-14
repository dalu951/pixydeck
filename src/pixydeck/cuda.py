"""Optional NVIDIA CUDA renderer for PixyDeck's processed frames.

Camera JPEG decoding and the v4l2loopback write necessarily touch host
memory.  Between those boundaries this module keeps background effects,
stabilization, crop/resize and I420 conversion on the GPU.  CuPy is imported
optionally so the normal CPU installation remains unchanged.
"""

from __future__ import annotations

import os

try:
    import cupy as cp
    from cupyx.scipy import ndimage
except Exception:  # noqa: BLE001  # pragma: no cover - missing driver/cache/dependency
    cp = None
    ndimage = None

import numpy as np
from PySide6.QtGui import QImage

from .background import DEFAULT_KEY, MAX_CHROMA_DISTANCE


def cuda_available() -> bool:
    """Whether a usable CuPy CUDA device is present (never raises)."""
    if cp is None or os.environ.get("PIXYDECK_DISABLE_CUDA", "") not in ("", "0"):
        return False
    try:
        return cp.cuda.runtime.getDeviceCount() > 0
    except Exception:  # noqa: BLE001 - broken/missing driver means CPU fallback
        return False


def cuda_device_name() -> str | None:
    if not cuda_available():
        return None
    try:
        value = cp.cuda.runtime.getDeviceProperties(0)["name"]
        return value.decode(errors="replace") if isinstance(value, bytes) else str(value)
    except Exception:  # noqa: BLE001 - diagnostics must never break rendering
        return "NVIDIA CUDA"


def _resize(image, width: int, height: int):
    """Bilinear CUDA resize with an exact requested output shape."""
    old_h, old_w = image.shape[:2]
    if (old_w, old_h) == (width, height):
        return image
    result = ndimage.zoom(image, (height / old_h, width / old_w, 1), order=1, prefilter=False)
    # scipy.ndimage rounds output dimensions; normal ratios are exact, but
    # guard unusual camera sizes without dropping the frame.
    if result.shape[:2] != (height, width):
        ys = cp.minimum((cp.arange(height) * old_h / height).astype(cp.int32), old_h - 1)
        xs = cp.minimum((cp.arange(width) * old_w / width).astype(cp.int32), old_w - 1)
        result = image[ys[:, None], xs[None, :]]
    return result


def _alpha(image, key, similarity: float, smoothness: float):
    """Green-screen foreground alpha, entirely on CUDA."""
    work = image.astype(cp.float32)
    b, g, r = work[:, :, 0], work[:, :, 1], work[:, :, 2]
    y = 0.114 * b + 0.587 * g + 0.299 * r
    cr = (r - y) * 0.713 + 128.0
    cb = (b - y) * 0.564 + 128.0
    distance = cp.sqrt((cr - key[0]) ** 2 + (cb - key[1]) ** 2)
    softness = max(smoothness, 1e-3)
    alpha = cp.clip(distance / (MAX_CHROMA_DISTANCE * softness) - similarity / softness, 0.0, 1.0)
    # Remove screen speckles and pinholes, then soften the edge.
    alpha = ndimage.maximum_filter(ndimage.minimum_filter(alpha, size=3), size=3)
    alpha = ndimage.minimum_filter(ndimage.maximum_filter(alpha, size=3), size=3)
    return ndimage.gaussian_filter(alpha, sigma=0.5)


def _blurred(image, strength: float):
    height, width = image.shape[:2]
    small = _resize(image, max(16, width // 4), max(9, height // 4)).astype(cp.float32)
    blurred = ndimage.gaussian_filter(small, sigma=(max(0.5, strength), max(0.5, strength), 0))
    return cp.clip(_resize(blurred, width, height), 0, 255).astype(cp.uint8)


def _apply_background(image, background, matte, backdrop=None):
    height, width = image.shape[:2]
    if matte is not None:
        alpha = cp.asarray(matte, dtype=cp.float32)
        if alpha.ndim == 2:
            alpha = alpha[:, :, None]
        alpha = _resize(alpha, width, height)[:, :, 0]
        foreground = image
    else:
        alpha = _alpha(image, background.key or DEFAULT_KEY,
                       background.similarity, background.smoothness)
        foreground = image
        if background.spill > 0:
            foreground = image.copy()
            b = foreground[:, :, 0].astype(cp.float32)
            g = foreground[:, :, 1].astype(cp.float32)
            r = foreground[:, :, 2].astype(cp.float32)
            corrected = g - cp.maximum(g - cp.maximum(r, b), 0) * background.spill
            foreground[:, :, 1] = cp.clip(corrected, 0, 255).astype(cp.uint8)
    if background.fill == "blur" and matte is not None:
        backdrop = _blurred(image, background.blur)
    elif backdrop is None:
        backdrop = cp.asarray(background.backdrop(width, height))
    a = alpha[:, :, None]
    return cp.clip(foreground.astype(cp.float32) * a + backdrop.astype(cp.float32) * (1.0 - a),
                   0, 255).astype(cp.uint8)


def _shift(image, offset: tuple[float, float]):
    ox, oy = offset
    if ox == 0 and oy == 0:
        return image
    height, width = image.shape[:2]
    return ndimage.shift(image, (-oy * height, -ox * width, 0), order=1, mode="nearest",
                         prefilter=False)


def _i420(image) -> bytes:
    """Convert an even-sized CUDA BGR image to BT.601 limited-range I420."""
    work = image.astype(cp.int32)
    b, g, r = work[:, :, 0], work[:, :, 1], work[:, :, 2]
    y = cp.clip(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16, 0, 255).astype(cp.uint8)
    u = cp.clip(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128, 0, 255)
    v = cp.clip(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128, 0, 255)
    # 2x2 chroma average; virtual-camera output dimensions are always even.
    u = ((u[0::2, 0::2] + u[0::2, 1::2] + u[1::2, 0::2] + u[1::2, 1::2]) // 4).astype(cp.uint8)
    v = ((v[0::2, 0::2] + v[0::2, 1::2] + v[1::2, 0::2] + v[1::2, 1::2]) // 4).astype(cp.uint8)
    packed = cp.concatenate((y.ravel(), u.ravel(), v.ravel()))
    return cp.asnumpy(packed).tobytes()


class CudaRenderer:
    """Render a decoded BGR frame through the processed-camera pipeline."""

    def __init__(self) -> None:
        if not cuda_available():
            raise RuntimeError("no usable NVIDIA CUDA device")
        self.device_name = cuda_device_name() or "NVIDIA CUDA"
        # CuPy caches allocations for speed. Bound the cache so a long call
        # cannot crowd out other desktop GPU applications.
        try:
            fraction = float(os.environ.get("PIXYDECK_CUDA_MEMORY_FRACTION", "0.25"))
            cp.get_default_memory_pool().set_limit(fraction=max(0.05, min(fraction, 0.8)))
        except (TypeError, ValueError):
            cp.get_default_memory_pool().set_limit(fraction=0.25)
        self._backdrops = {}

    def render(self, image: np.ndarray, crop, size: tuple[int, int], background,
               want_output: bool, matte=None, shake=(0.0, 0.0),
               want_preview: bool = False) -> tuple[bytes | None, QImage | None]:
        image_gpu = cp.asarray(image)
        if background is not None:
            if background.uses_matting and matte is None:
                return None, None
            backdrop = None
            if not (background.fill == "blur" and matte is not None):
                key = (id(background), image.shape[1], image.shape[0])
                backdrop = self._backdrops.get(key)
                if backdrop is None:
                    if len(self._backdrops) >= 2:
                        self._backdrops.clear()
                    backdrop = cp.asarray(background.backdrop(image.shape[1], image.shape[0]))
                    self._backdrops[key] = backdrop
            image_gpu = _apply_background(image_gpu, background, matte, backdrop)
        image_gpu = _shift(image_gpu, shake)

        preview = None
        if want_preview:
            # Download three bytes/pixel; Qt supports BGR directly, avoiding
            # a fourth alpha channel and another GPU allocation.
            host = cp.asnumpy(image_gpu)
            height, width = host.shape[:2]
            preview = QImage(host.data, width, height, host.strides[0], QImage.Format_BGR888).copy()

        if not want_output:
            return None, preview
        out_w, out_h = size
        height, width = image_gpu.shape[:2]
        x, y, w, h = crop.clamped().rect()
        px, py = int(x * width), int(y * height)
        pw, ph = max(2, int(w * width)), max(2, int(h * height))
        frame = _resize(image_gpu[py:py + ph, px:px + pw], out_w, out_h)
        return _i420(frame), preview
