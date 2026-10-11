"""End-to-end tests of FrameProcessor: JPEG bytes in, preview / virtual camera out.

Only synthetic images are used. Signals are emitted from worker threads and
reach plain callables through the Qt event loop, so the helpers pump it.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np

from PySide6.QtCore import QCoreApplication

from pixydeck import vision
from pixydeck.background import Background, matting_available
from pixydeck.vision import Crop, FrameProcessor, vision_available

GREEN = (64, 177, 0)
SKIN = (120, 150, 200)


def encode(image):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return data.reshape(-1)


def split_frame(width=320, height=180):
    """Left half red, right half blue (BGR)."""
    image = np.empty((height, width, 3), np.uint8)
    image[:, : width // 2] = (0, 0, 255)
    image[:, width // 2:] = (255, 0, 0)
    return image


def green_screen_with_person(width=640, height=360):
    image = np.empty((height, width, 3), np.uint8)
    image[:] = GREEN
    image[height // 3:, width * 3 // 8: width * 5 // 8] = SKIN
    return image


def textured(width=640, height=360, seed=1):
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 255, (height // 8, width // 8, 3), np.uint8)
    return cv2.resize(noise, (width, height), interpolation=cv2.INTER_CUBIC)


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Cleanups run last-in first-out: stop FFmpeg before deleting its script.
        self.processor = FrameProcessor()
        self.addCleanup(self.processor.shutdown)
        self.previews = 0

        def on_preview():
            self.previews += 1
        self.processor.preview_ready.connect(on_preview)

    def wait_until(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        self.app.processEvents()
        return predicate()

    def next_preview(self, jpeg, source_width=0, timeout=3.0):
        """Submit one frame and return the preview it produces (or None)."""
        start = self.previews
        self.processor.submit(jpeg, source_width)
        if not self.wait_until(lambda: self.previews > start, timeout):
            return None
        return self.processor.take_preview()

    def fake_ffmpeg(self, body):
        path = Path(self.tmp.name) / "ffmpeg"
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
        return str(path)


class PreviewPipelineTest(PipelineTestCase):
    def test_idle_processor_renders_nothing(self):
        self.processor.submit(encode(split_frame()))
        self.assertFalse(self.wait_until(lambda: self.previews > 0, 0.3))
        self.assertIsNone(self.processor.take_preview())
        self.assertFalse(self.processor.busy())

    def test_stabilized_preview_has_source_size(self):
        self.processor.set_stabilization(True)
        preview = self.next_preview(encode(textured()))
        self.assertIsNotNone(preview)
        self.assertEqual((preview.width(), preview.height()), (640, 360))
        self.assertIsNone(self.processor.take_preview())   # consumed

    def test_preview_signal_is_coalesced_until_taken(self):
        self.processor.set_stabilization(True)
        for seed in range(3):
            self.processor.submit(encode(textured(seed=seed)))
            time.sleep(0.05)
        self.wait_until(lambda: False, 0.3)
        self.assertEqual(self.previews, 1)                  # one signal, newest frame kept
        self.assertIsNotNone(self.processor.take_preview())
        self.assertIsNotNone(self.next_preview(encode(textured(seed=9))))

    def test_incomplete_and_corrupt_frames_do_not_stop_the_pipeline(self):
        self.processor.set_stabilization(True)
        good = encode(textured())
        self.processor.submit(good[: len(good) // 2])      # still being refilled by the driver
        self.processor.submit(np.frombuffer(b"\x00" * 128 + b"\xff\xd9", np.uint8))
        self.assertIsNotNone(self.next_preview(good))

    def test_green_screen_is_detected_and_replaced(self):
        events = []
        self.processor.green_screen.connect(events.append)
        self.processor.set_background(Background(mode="chroma", fill="color", color=(0, 0, 255)))
        self.assertFalse(self.processor.background_active)
        preview = self.next_preview(encode(green_screen_with_person()))
        self.assertTrue(self.wait_until(lambda: events, 1.0))
        self.assertIsNotNone(events[0])
        self.assertIsNotNone(self.processor.key)
        self.assertTrue(self.processor.background_active)
        self.assertIsNotNone(preview)
        corner = preview.pixelColor(10, 10)
        self.assertGreater(corner.red(), 200)
        self.assertLess(corner.green(), 40)
        person = preview.pixelColor(320, 300)          # untouched apart from JPEG noise
        for got, want in zip((person.red(), person.green(), person.blue()), SKIN[::-1]):
            self.assertAlmostEqual(got, want, delta=4)

    def test_frame_failing_to_render_is_skipped(self):
        class FlakyBackground(Background):
            calls = 0

            def apply(self, image, matte=None):
                FlakyBackground.calls += 1
                if FlakyBackground.calls == 1:
                    raise RuntimeError("bad frame")
                return super().apply(image, matte)

        self.processor._key = (64.0, 85.0)
        self.processor.set_background(FlakyBackground(mode="chroma", fill="color"))
        jpeg = encode(green_screen_with_person())
        self.processor.submit(jpeg)
        self.assertTrue(self.wait_until(lambda: FlakyBackground.calls >= 1))
        self.assertIsNotNone(self.next_preview(jpeg))

    @unittest.skipUnless(matting_available(), "RVM model / onnxruntime not installed")
    def test_ai_background_runs_matting(self):
        self.processor.set_background(Background(mode="ai", fill="color", color=(0, 0, 255)))
        preview = self.next_preview(encode(np.full((180, 320, 3), 128, np.uint8)), timeout=5.0)
        self.assertIsNotNone(preview)
        self.assertIsNotNone(self.processor._matting)
        # A flat grey wall has no person: the backdrop colour shows through.
        self.assertGreater(preview.pixelColor(160, 90).red(), 200)
        self.assertLess(preview.pixelColor(160, 90).green(), 60)

    def test_matting_failure_turns_background_off(self):
        errors = []
        self.processor.output_error.connect(errors.append)
        background = Background(mode="ai")
        with mock.patch.object(vision, "matting_available", return_value=True), \
                mock.patch("pixydeck.background.matting_available", return_value=True), \
                mock.patch.object(vision, "Matting", side_effect=RuntimeError("no model")):
            self.processor.set_background(background)
            self.processor.submit(encode(split_frame()))
            self.assertTrue(self.wait_until(lambda: errors))
        self.assertIn("AI background unavailable: no model", errors[0])
        self.assertEqual(background.mode, "off")
        self.assertFalse(self.processor.wants_frames)


class DetectionPipelineTest(PipelineTestCase):
    def setUp(self):
        super().setUp()
        if not vision_available():
            self.skipTest("YuNet model not available")
        self.faces = []
        self.processor.faces_detected.connect(self.faces.append)

    def test_blank_frame_has_no_faces(self):
        self.processor.set_detection(True)
        self.processor.submit(encode(np.full((360, 640, 3), 90, np.uint8)))
        self.assertTrue(self.wait_until(lambda: self.faces))
        self.assertEqual(self.faces[0], [])

    def test_faces_are_normalized_to_frame(self):
        class FakeDetector:
            def __init__(self):
                self.sizes = []

            def setInputSize(self, size):
                self.sizes.append(size)

            def detect(self, image):
                h, w = image.shape[:2]
                row = np.array([[w * 0.25, h * 0.5, w * 0.1, h * 0.2] + [0.0] * 11], np.float32)
                return 1, row

        detector = FakeDetector()
        self.processor._detector = detector
        self.processor.set_detection(True)
        # 2560 wide -> decoded at 1/4 = 640 -> scaled down to DETECT_WIDTH.
        self.processor.submit(encode(np.full((1440, 2560, 3), 90, np.uint8)))
        self.assertTrue(self.wait_until(lambda: self.faces))
        self.assertEqual(detector.sizes[0], (vision.DETECT_WIDTH, 270))
        (x, y, w, h), = self.faces[0]
        self.assertAlmostEqual(x, 0.25, places=3)
        self.assertAlmostEqual(y, 0.5, places=3)
        self.assertAlmostEqual(w, 0.1, places=3)
        self.assertAlmostEqual(h, 0.2, places=3)

    def test_detection_disabled_emits_nothing(self):
        self.processor.set_detection(False)
        self.processor.submit(encode(np.full((360, 640, 3), 90, np.uint8)))
        self.assertFalse(self.wait_until(lambda: self.faces, 0.3))


class OutputPipelineTest(PipelineTestCase):
    WIDTH, HEIGHT = 64, 36
    FRAME = WIDTH * HEIGHT * 3 // 2

    def start(self, fps=30):
        self.sink = Path(self.tmp.name) / "out.yuv"
        ffmpeg = self.fake_ffmpeg(f"cat > '{self.sink}'")
        self.processor.start_output(ffmpeg, "/dev/null", self.WIDTH, self.HEIGHT, fps)
        self.assertIsNotNone(self.processor.output_pid)
        self.assertTrue(self.processor.wants_frames)

    def written(self):
        return self.sink.stat().st_size if self.sink.exists() else 0

    def feed(self, jpeg, frames, interval=0.03):
        for _ in range(frames):
            self.processor.submit(jpeg, 320)
            time.sleep(interval)
            self.app.processEvents()

    def settle(self):
        """Wait until the writer and the fake ffmpeg have flushed everything."""
        last = -1
        while self.written() != last:
            last = self.written()
            self.wait_until(lambda: False, 0.15)

    def test_waiting_screen_keeps_the_virtual_camera_alive(self):
        stats = []
        self.processor.output_stats.connect(stats.append)
        self.start()
        self.assertTrue(self.wait_until(lambda: self.written() >= 2 * self.FRAME, 3.0))
        self.assertTrue(self.processor.showing_placeholder)
        self.assertEqual(self.written() % self.FRAME, 0)
        self.assertIn(0.0, stats)

    def test_camera_frames_replace_the_waiting_screen(self):
        self.start()
        self.assertTrue(self.wait_until(lambda: self.processor.showing_placeholder, 3.0))
        self.feed(encode(split_frame()), 5)
        self.assertFalse(self.processor.showing_placeholder)

    def test_no_waiting_screen_without_output(self):
        self.processor.set_stabilization(True)
        self.wait_until(lambda: False, 1.5)
        self.assertFalse(self.processor.showing_placeholder)

    def test_written_stream_is_whole_yuv420_frames(self):
        self.start()
        self.feed(encode(split_frame()), 10)
        self.settle()
        self.processor.stop_output()
        size = self.written()
        self.assertGreater(size, 0)
        self.assertEqual(size % self.FRAME, 0)
        self.assertIsNone(self.processor.output_pid)

    def test_crop_is_applied_to_output(self):
        self.processor.set_crop(Crop(0.25, 0.5, 2.0))      # red half only
        self.start()
        self.feed(encode(split_frame()), 4)
        self.settle()
        self.processor.stop_output()
        data = self.sink.read_bytes()[-self.FRAME:]
        yuv = np.frombuffer(data, np.uint8).reshape(self.HEIGHT * 3 // 2, self.WIDTH)
        frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
        self.assertTrue((frame[:, :, 2] > 200).all())
        self.assertTrue((frame[:, :, 0] < 50).all())

    def test_output_reports_frame_rate(self):
        stats = []
        self.processor.output_stats.connect(stats.append)
        self.start()
        jpeg = encode(split_frame())
        deadline = time.monotonic() + 3.0
        while not stats and time.monotonic() < deadline:
            self.feed(jpeg, 1, 0.02)
        self.assertTrue(stats)
        self.assertGreater(stats[0], 5.0)
        self.assertLess(stats[0], 100.0)

    def test_restarting_output_replaces_process(self):
        self.start()
        first = self.processor.output_pid
        self.start()
        self.assertNotEqual(self.processor.output_pid, first)


if __name__ == "__main__":
    unittest.main()
