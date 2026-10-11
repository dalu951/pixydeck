import math
import subprocess
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

from unittest import mock

from pixydeck.background import Background, detect_green_screen
from pixydeck.vision import (
    KEY_WIDTH, MODEL, Crop, FrameProcessor, Smoother, Stabilizer, framing_target, jpeg_complete,
    shift_image, vision_available,
)


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


def encode(image, quality=95):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return data.reshape(-1)


def split_frame(width=320, height=180):
    """Left half red, right half blue (BGR)."""
    image = np.empty((height, width, 3), np.uint8)
    image[:, : width // 2] = (0, 0, 255)
    image[:, width // 2:] = (255, 0, 0)
    return image


def decode_i420(data, width, height):
    yuv = np.frombuffer(data, np.uint8).reshape(height * 3 // 2, width)
    return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)


class JpegTest(unittest.TestCase):
    def test_complete_jpeg(self):
        self.assertTrue(jpeg_complete(encode(textured())))

    def test_truncated_jpeg_is_rejected(self):
        data = encode(textured())
        self.assertFalse(jpeg_complete(data[: len(data) // 2]))

    def test_vision_available_matches_installed_model(self):
        self.assertEqual(vision_available(), hasattr(cv2, "FaceDetectorYN") and MODEL.exists())


class CropRectTest(unittest.TestCase):
    def test_default_crop_is_full_frame(self):
        self.assertEqual(Crop().rect(), (0.0, 0.0, 1.0, 1.0))

    def test_zoom_is_capped(self):
        self.assertEqual(Crop(0.5, 0.5, 10.0).clamped(max_zoom=3.0).zoom, 3.0)
        self.assertAlmostEqual(Crop(0.5, 0.5, 10.0).rect()[2], 0.25)   # rect() caps at 4x


class FramingEdgeTest(unittest.TestCase):
    def test_tiny_face_is_limited_to_max_zoom(self):
        self.assertEqual(framing_target([(0.5, 0.4, 0.001, 0.001)], max_zoom=2.5).zoom, 2.5)

    def test_degenerate_face_does_not_divide_by_zero(self):
        crop = framing_target([(0.5, 0.5, 0.0, 0.0)])
        self.assertTrue(all(math.isfinite(v) for v in (crop.cx, crop.cy, crop.zoom)))

    def test_face_at_corner_keeps_crop_inside_frame(self):
        x, y, w, h = framing_target([(0.0, 0.0, 0.05, 0.08)]).rect()
        self.assertGreaterEqual(x, -1e-9)
        self.assertGreaterEqual(y, -1e-9)
        self.assertLessEqual(x + w, 1.0 + 1e-9)
        self.assertLessEqual(y + h, 1.0 + 1e-9)

    def test_headroom_places_face_above_centre(self):
        face = (0.45, 0.4, 0.1, 0.12)
        crop = framing_target([face])
        self.assertGreater(crop.cy, face[1] + face[3] / 2)


class SmootherStateTest(unittest.TestCase):
    def test_small_corrections_accepted_while_moving(self):
        smoother = Smoother(dead_zone=0.05)
        smoother.set_target(Crop(0.8, 0.5, 1.0))
        smoother.step(0.01)
        smoother.set_target(Crop(0.81, 0.5, 1.0))     # inside dead zone, but already moving
        self.assertEqual(smoother.target, Crop(0.81, 0.5, 1.0))

    def test_dead_zone_applies_again_after_settling(self):
        smoother = Smoother(dead_zone=0.05)
        smoother.set_target(Crop(0.8, 0.5, 1.0))
        for _ in range(300):
            smoother.step(1 / 30)
        smoother.set_target(Crop(0.82, 0.5, 1.0))      # inside the dead zone again
        self.assertEqual(smoother.target, Crop(0.8, 0.5, 1.0))
        self.assertAlmostEqual(smoother.step(1.0).cx, 0.8, places=6)

    def test_zero_dt_does_not_move(self):
        smoother = Smoother()
        smoother.set_target(Crop(0.9, 0.9, 3.0))
        self.assertEqual(smoother.step(0.0), Crop())


class StabilizerStateTest(unittest.TestCase):
    def test_first_frame_and_reset_return_no_offset(self):
        stabilizer = Stabilizer()
        base = textured()
        self.assertEqual(stabilizer.update(base), (0.0, 0.0))
        stabilizer.update(translated(base, 5, 0))
        stabilizer.reset()
        self.assertEqual(stabilizer.update(translated(base, -5, 0)), (0.0, 0.0))

    def test_static_scene_has_no_offset(self):
        stabilizer = Stabilizer()
        base = textured()
        for _ in range(5):
            offset = stabilizer.update(base)
        self.assertEqual(offset, (0.0, 0.0))

    def test_uncorrelated_frames_are_not_trusted(self):
        stabilizer = Stabilizer()
        stabilizer.update(textured(seed=1))
        with mock.patch("cv2.phaseCorrelate", return_value=((5.0, 5.0), 0.01)):
            self.assertEqual(stabilizer.update(textured(seed=2)), (0.0, 0.0))
        self.assertEqual(stabilizer._path, [0.0, 0.0])

    def test_pause_follows_deliberate_motion(self):
        stabilizer = Stabilizer(margin=0.05)
        base = textured()
        stabilizer.update(base)
        stabilizer.paused_until = time.monotonic() + 60
        self.assertEqual(stabilizer.update(translated(base, 6, 0)), (0.0, 0.0))
        self.assertEqual(stabilizer._smooth, stabilizer._path)
        self.assertNotEqual(stabilizer._path[0], 0.0)


class ShiftImageTest(unittest.TestCase):
    def test_zero_offset_returns_same_image(self):
        image = textured()
        self.assertIs(shift_image(image, (0.0, 0.0)), image)

    def test_content_moves_against_offset(self):
        image = np.zeros((100, 200, 3), np.uint8)
        image[50, 100] = 255
        out = shift_image(image, (0.05, -0.1))         # 10 px left, 10 px down
        y, x = np.unravel_index(out[:, :, 0].argmax(), out.shape[:2])
        self.assertEqual((int(y), int(x)), (60, 90))
        self.assertEqual(out.shape, image.shape)


class RenderTest(unittest.TestCase):
    """FrameProcessor._render is pure: JPEG in, (YUV420, preview) out."""

    render = staticmethod(FrameProcessor._render)

    def test_output_is_yuv420_of_requested_size(self):
        data, preview = self.render(encode(split_frame()), Crop(), (64, 36), 0, None, True)
        self.assertEqual(len(data), 64 * 36 * 3 // 2)
        self.assertIsNone(preview)
        frame = decode_i420(data, 64, 36)
        self.assertGreater(frame[18, 5, 2], 200)       # left stays red
        self.assertGreater(frame[18, 58, 0], 200)      # right stays blue

    def test_crop_selects_region(self):
        data, _ = self.render(encode(split_frame()), Crop(0.25, 0.5, 2.0), (64, 36), 0, None, True)
        frame = decode_i420(data, 64, 36)
        self.assertTrue((frame[:, :, 2] > 200).all())
        self.assertTrue((frame[:, :, 0] < 50).all())

    def test_half_resolution_decode_gives_same_framing(self):
        jpeg = encode(split_frame(640, 360))
        full, _ = self.render(jpeg, Crop(0.75, 0.5, 2.0), (64, 36), 0, None, True)
        half, _ = self.render(jpeg, Crop(0.75, 0.5, 2.0), (64, 36), 640, None, True)
        self.assertEqual(len(full), len(half))
        self.assertTrue((decode_i420(half, 64, 36)[:, :, 0] > 200).all())

    def test_preview_only(self):
        data, preview = self.render(encode(split_frame()), Crop(), (64, 36), 320, None, False,
                                    want_preview=True)
        self.assertIsNone(data)
        self.assertEqual((preview.width(), preview.height()), (320, 180))
        self.assertGreater(preview.pixelColor(10, 90).red(), 240)
        self.assertGreater(preview.pixelColor(310, 90).blue(), 240)

    def test_preview_of_4k_source_is_half_size(self):
        jpeg = encode(np.zeros((360, 640, 3), np.uint8))
        _, preview = self.render(jpeg, Crop(), (64, 36), KEY_WIDTH + 1, None, False, want_preview=True)
        self.assertEqual((preview.width(), preview.height()), (320, 180))

    def test_preview_and_output_share_background(self):
        image = np.empty((180, 320, 3), np.uint8)
        image[:] = (64, 177, 0)
        image[60:, 120:200] = (120, 150, 200)
        background = Background(mode="chroma", fill="color", color=(0, 0, 255),
                                key=detect_green_screen(image))
        data, preview = self.render(encode(image), Crop(), (320, 180), 0, background, True,
                                    want_preview=True)
        self.assertEqual(preview.pixelColor(10, 10).red(), 255)
        self.assertLess(preview.pixelColor(10, 10).green(), 30)
        frame = decode_i420(data, 320, 180)
        self.assertGreater(frame[10, 10, 2], 200)
        self.assertLess(frame[10, 10, 1], 60)

    def test_shake_is_shifted_out_of_preview(self):
        image = np.zeros((180, 320, 3), np.uint8)
        image[:, 160:] = 255
        _, preview = self.render(encode(image), Crop(), (64, 36), 0, None, False,
                                 shake=(0.1, 0.0), want_preview=True)
        # Content moved 32 px left: the bright edge now starts near x=128.
        self.assertGreater(preview.pixelColor(140, 90).red(), 200)
        self.assertLess(preview.pixelColor(110, 90).red(), 50)

    def test_matting_background_without_matte_drops_frame(self):
        background = mock.Mock(uses_matting=True)
        result = self.render(encode(split_frame()), Crop(), (64, 36), 0, background, True,
                             matte=None, want_preview=True)
        self.assertEqual(result, (None, None))
        background.apply.assert_not_called()

    def test_corrupt_jpeg_is_dropped(self):
        garbage = np.frombuffer(b"\x00" * 64 + b"\xff\xd9", np.uint8)
        self.assertEqual(self.render(garbage, Crop(), (64, 36), 0, None, True), (None, None))
        self.assertEqual(self.render(garbage, Crop(), (64, 36), 0, None, True, want_preview=True),
                         (None, None))


class ProcessorStateTest(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.processor = FrameProcessor()
        self.addCleanup(self.processor.shutdown)

    def test_idle_processor_wants_no_frames(self):
        p = self.processor
        self.assertFalse(p.wants_frames)
        self.assertFalse(p.stabilizing)
        self.assertFalse(p.background_active)
        self.assertIsNone(p.key)
        self.assertIsNone(p.output_pid)
        self.assertIsNone(p.take_preview())

    def test_each_feature_requests_frames(self):
        p = self.processor
        p.set_stabilization(True)
        self.assertTrue(p.stabilizing and p.wants_frames)
        p.set_stabilization(False)
        self.assertFalse(p.wants_frames)
        p.set_background(Background(mode="ai"))
        self.assertTrue(p.wants_frames)
        p.set_background(Background(mode="off"))
        self.assertFalse(p.wants_frames)
        p.set_detection(True)
        self.assertEqual(p.wants_frames, vision_available())

    def test_stabilization_margin_and_pause(self):
        p = self.processor
        self.assertEqual(p.stabilization_margin, Stabilizer().margin)
        before = time.monotonic()
        p.pause_stabilization(5.0)
        self.assertGreaterEqual(p._stabilizer.paused_until, before + 5.0)

    def test_enabling_stabilization_resets_filter(self):
        p = self.processor
        p._stabilizer.update(textured())
        p.set_stabilization(True)
        self.assertIsNone(p._stabilizer._previous)

    def test_new_background_keeps_detected_key(self):
        p = self.processor
        p._key = (60.0, 80.0)
        background = Background(mode="chroma")
        p.set_background(background)
        self.assertEqual(background.key, (60.0, 80.0))
        self.assertTrue(p.background_active)

    def test_green_screen_check(self):
        p = self.processor
        events = []
        p.green_screen.connect(events.append)
        background = Background(mode="auto")
        green = np.full((90, 160, 3), (64, 177, 0), np.uint8)
        room = np.full((90, 160, 3), (110, 115, 112), np.uint8)

        p._check_green_screen(None, background)          # undecodable frame: ignored
        p._check_green_screen(green, background)
        first = p.key
        self.assertIsNotNone(first)
        self.assertEqual(background.key, first)

        # A slightly different shade is blended in slowly (no event).
        p._check_green_screen(np.full((90, 160, 3), (40, 190, 30), np.uint8), background)
        self.assertNotEqual(p.key, first)
        self.assertLess(abs(p.key[0] - first[0]), 5)

        p._check_green_screen(room, background)          # screen taken down
        self.assertIsNone(p.key)
        self.assertIsNone(background.key)
        self.app.processEvents()
        self.assertEqual(len(events), 2)
        self.assertIsNotNone(events[0])
        self.assertIsNone(events[1])

    def test_chroma_mode_keeps_last_key_when_screen_is_lost(self):
        p = self.processor
        background = Background(mode="chroma")
        p._check_green_screen(np.full((90, 160, 3), (64, 177, 0), np.uint8), background)
        key = p.key
        p._check_green_screen(np.full((90, 160, 3), (110, 115, 112), np.uint8), background)
        self.assertEqual(p.key, key)
        self.assertEqual(background.key, key)

    def test_lost_screen_is_reported_once_in_chroma_mode(self):
        p = self.processor
        events = []
        p.green_screen.connect(events.append)
        background = Background(mode="chroma")
        green = np.full((90, 160, 3), (64, 177, 0), np.uint8)
        grey = np.full((90, 160, 3), (110, 115, 112), np.uint8)
        for frame in (green, grey, grey, grey, green, green):
            p._check_green_screen(frame, background)
        QCoreApplication.instance().processEvents()
        self.assertEqual([event is None for event in events], [False, True, False])

    def test_stop_output_kills_unresponsive_ffmpeg(self):
        process = mock.Mock()
        process.stdin.close.side_effect = OSError("broken")
        process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", 2)
        self.processor._output = process
        self.processor.stop_output()
        process.kill.assert_called_once()
        self.assertIsNone(self.processor.output_pid)

    def test_stop_output_without_output_is_harmless(self):
        self.processor.stop_output()
        self.processor.stop_output()


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
        with self.assertLogs("pixydeck.vision", "WARNING") as logs:
            self.processor.start_output(ffmpeg, "/dev/null", 1280, 720, 30)
            self.assertTrue(self.wait_for_error(5))
        self.assertIn("Invalid argument", self.errors[0])
        self.assertTrue(any("ffmpeg: Invalid argument" in line for line in logs.output))
        self.assertIsNone(self.processor.output_pid)

    def test_silent_exit_still_reported(self):
        with self.assertLogs("pixydeck.vision", "ERROR"):
            self.processor.start_output(self.fake_ffmpeg("exit 3"), "/dev/null", 1280, 720, 30)
            self.assertTrue(self.wait_for_error(5))
        self.assertIn("3", self.errors[0])

    def test_deliberate_stop_is_not_an_error(self):
        self.processor.start_output(self.fake_ffmpeg("cat > /dev/null"), "/dev/null", 1280, 720, 30)
        self.processor.stop_output()
        self.assertFalse(self.wait_for_error(0.5))
        self.assertEqual(self.errors, [])



class PlaceholderFrameTest(unittest.TestCase):
    def test_size_and_look(self):
        from pixydeck.vision import placeholder_frame
        width, height = 320, 180
        data = placeholder_frame(width, height)
        self.assertEqual(len(data), width * height * 3 // 2)
        luma = np.frombuffer(data[:width * height], np.uint8).reshape(height, width)
        self.assertLess(luma.mean(), 60)                 # dark, calm background
        self.assertGreater(luma[60:120].max(), 150)      # but readable text
        self.assertIs(placeholder_frame(width, height), data)  # cached

    def test_without_opencv_still_valid_i420(self):
        from pixydeck import vision
        with mock.patch.object(vision, "cv2", None):
            data = vision.placeholder_frame.__wrapped__(64, 36)
        self.assertEqual(len(data), 64 * 36 * 3 // 2)


if __name__ == "__main__":
    unittest.main()
