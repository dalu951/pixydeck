import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np

from PySide6.QtCore import QCoreApplication

from pixydeck.vision import Crop, FrameProcessor, Smoother, Stabilizer, framing_target, shift_image


class CropTest(unittest.TestCase):
    def test_clamped_keeps_crop_inside_frame(self):
        crop = Crop(0.0, 1.0, 2.0).clamped()
        x, y, w, h = crop.rect()
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y + h, 1.0)
        self.assertAlmostEqual(w, 0.5)

    def test_zoom_never_below_one(self):
        self.assertEqual(Crop(0.5, 0.5, 0.3).clamped().zoom, 1.0)


class FramingTest(unittest.TestCase):
    def test_no_faces_returns_full_frame(self):
        self.assertEqual(framing_target([]), Crop())

    def test_small_face_zooms_in_and_centres(self):
        target = framing_target([(0.6, 0.3, 0.05, 0.08)], fill=0.45)
        self.assertGreater(target.zoom, 1.5)
        self.assertAlmostEqual(target.cx, 0.625, delta=0.05)

    def test_large_face_stays_wide(self):
        self.assertEqual(framing_target([(0.3, 0.2, 0.3, 0.45)]).zoom, 1.0)

    def test_group_is_kept_in_frame(self):
        faces = [(0.1, 0.4, 0.05, 0.08), (0.85, 0.4, 0.05, 0.08)]
        x, _y, w, _h = framing_target(faces).rect()
        self.assertLessEqual(x, 0.1)
        self.assertGreaterEqual(x + w, 0.9)


class SmootherTest(unittest.TestCase):
    def test_dead_zone_ignores_small_shifts(self):
        smoother = Smoother(dead_zone=0.05)
        smoother.set_target(Crop(0.52, 0.5, 1.0))
        self.assertEqual(smoother.step(0.1), Crop())

    def test_converges_towards_target(self):
        smoother = Smoother()
        smoother.set_target(Crop(0.7, 0.4, 2.0))
        for _ in range(200):
            crop = smoother.step(1 / 60)
        self.assertAlmostEqual(crop.cx, 0.7, places=2)
        self.assertAlmostEqual(crop.zoom, 2.0, places=2)


def textured(width=640, height=360, seed=1):
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 255, (height // 8, width // 8, 3), np.uint8)
    return cv2.resize(noise, (width, height), interpolation=cv2.INTER_CUBIC)


def translated(image, dx, dy):
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(image, matrix, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REFLECT)


class StabilizerTest(unittest.TestCase):
    def test_shake_is_measured_and_cancelled(self):
        base = textured()
        stabilizer = Stabilizer(margin=0.05, smoothing=0.1)
        residual = []
        for frame in range(40):
            dx = 6 if frame % 2 else -6          # 12 px peak-to-peak vibration
            image = translated(base, dx, 0)
            offset = stabilizer.update(image)
            steady = shift_image(image, offset)
            if frame > 10:
                residual.append(steady)
        # After correction consecutive frames barely differ.
        (shift, _), _ = cv2.phaseCorrelate(
            cv2.cvtColor(residual[-1], cv2.COLOR_BGR2GRAY).astype(np.float32),
            cv2.cvtColor(residual[-2], cv2.COLOR_BGR2GRAY).astype(np.float32))
        self.assertLess(abs(shift), 3.0)

    def test_large_jump_resets_instead_of_correcting(self):
        base = textured()
        stabilizer = Stabilizer()
        stabilizer.update(base)
        self.assertEqual(stabilizer.update(translated(base, 120, 0)), (0.0, 0.0))

    def test_offset_never_exceeds_margin(self):
        base = textured()
        stabilizer = Stabilizer(margin=0.02, smoothing=0.01)
        offset = (0.0, 0.0)
        for step in range(1, 15):
            offset = stabilizer.update(translated(base, step * 8, 0))
        self.assertLessEqual(abs(offset[0]), 0.02 + 1e-6)


class OutputWatchTest(unittest.TestCase):
    """The processed virtual camera must notice when FFmpeg dies."""

    def setUp(self):
        self.processor = FrameProcessor()
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.errors = []
        self.processor.output_error.connect(self.errors.append)
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.processor.shutdown()
        self.tmp.cleanup()

    def wait_for_error(self, seconds: float) -> bool:
        """The error arrives as a queued signal, so pump the event loop."""
        deadline = time.monotonic() + seconds
        while not self.errors and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        return bool(self.errors)

    def fake_ffmpeg(self, body: str) -> str:
        path = Path(self.tmp.name) / "ffmpeg"
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
        return str(path)

    def test_exit_is_reported_with_stderr(self):
        ffmpeg = self.fake_ffmpeg("echo 'Invalid argument' >&2; exit 1")
        self.processor.start_output(ffmpeg, "/dev/null", 1280, 720, 30)
        self.assertTrue(self.wait_for_error(5))
        self.assertIn("Invalid argument", self.errors[0])
        self.assertIsNone(self.processor.output_pid)

    def test_silent_exit_still_reported(self):
        self.processor.start_output(self.fake_ffmpeg("exit 3"), "/dev/null", 1280, 720, 30)
        self.assertTrue(self.wait_for_error(5))
        self.assertIn("3", self.errors[0])

    def test_deliberate_stop_is_not_an_error(self):
        self.processor.start_output(self.fake_ffmpeg("cat > /dev/null"), "/dev/null", 1280, 720, 30)
        self.processor.stop_output()
        self.assertFalse(self.wait_for_error(0.5))
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
