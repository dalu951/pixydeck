"""Compare PixyDeck's CPU and CUDA render paths on the local NVIDIA GPU."""

from __future__ import annotations

import argparse
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np

from .background import Background
from .cuda import CudaRenderer, cp, cuda_available
from .vision import Crop, FrameProcessor


def sample(width: int, height: int):
    image = np.empty((height, width, 3), np.uint8)
    image[:] = (64, 177, 0)
    image[height // 5: height * 9 // 10, width * 3 // 8: width * 5 // 8] = (120, 150, 200)
    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError("could not create benchmark JPEG")
    return jpeg.reshape(-1)


def measure(label, render, frames: int, warmup: int) -> float:
    for _ in range(warmup):
        render()
    started = time.perf_counter()
    size = 0
    for _ in range(frames):
        data, preview = render()
        size = len(data or b"")
        if preview is None:
            raise RuntimeError(f"{label} did not produce a preview")
    elapsed = time.perf_counter() - started
    fps = frames / elapsed
    print(f"{label:>5}: {fps:6.1f} fps · {elapsed * 1000 / frames:5.1f} ms/frame · {size:,} bytes")
    return fps


def dimensions(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT") from exc
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("dimensions must be positive and even")
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--source", type=dimensions, default=(1920, 1080))
    parser.add_argument("--output", type=dimensions, default=(1280, 720))
    args = parser.parse_args()
    if not cuda_available():
        print("No usable CUDA device. Run ./install.sh --gpu and check nvidia-smi.")
        return 2
    jpeg = sample(*args.source)
    background = Background(mode="chroma", fill="color", color=(20, 30, 80), key=(64.0, 85.0))
    renderer = CudaRenderer()

    def render(cuda=None):
        return FrameProcessor._render(jpeg, Crop(), args.output, args.source[0], background, True,
                                      want_preview=True, cuda_renderer=cuda)

    print(f"GPU: {renderer.device_name}")
    print(f"Source: {args.source[0]}x{args.source[1]} · output: "
          f"{args.output[0]}x{args.output[1]} · chroma-key pipeline")
    cpu_fps = measure("CPU", render, args.frames, args.warmup)
    gpu_fps = measure("CUDA", lambda: render(renderer), args.frames, args.warmup)
    pool = cp.get_default_memory_pool()
    print(f"Speedup: {gpu_fps / cpu_fps:.2f}x · CuPy pool: "
          f"{pool.used_bytes() / 2**20:.0f} MiB used / {pool.total_bytes() / 2**20:.0f} MiB reserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
