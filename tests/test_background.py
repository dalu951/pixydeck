import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

import cv2

from pixydeck.background import (
    DEFAULT_KEY, MATTING_SIZE, Background, Matting, blurred, composite, cover, despill,
    detect_green_screen, gradient_background, key_alpha, matting_available,
    matting_provider_options, matting_providers,
)

GREEN = (64, 177, 0)       # BGR chroma-key green
SKIN = (120, 150, 200)


def green_screen_with_person(width=320, height=180):
    image = np.empty((height, width, 3), np.uint8)
    # Uneven lighting across the screen.
    shade = np.linspace(0.6, 1.0, width, dtype=np.float32)[None, :, None]
    image[:] = (np.array(GREEN, np.float32) * shade).astype(np.uint8)
    image[60:, 120:200] = SKIN
    return image


class GreenScreenTest(unittest.TestCase):
    def test_detects_green_screen(self):
        self.assertIsNotNone(detect_green_screen(green_screen_with_person()))

    def test_grey_room_is_not_a_green_screen(self):
        room = np.full((180, 320, 3), (110, 115, 112), np.uint8)
        self.assertIsNone(detect_green_screen(room))

    def test_key_separates_person_from_screen(self):
        image = green_screen_with_person()
        alpha = key_alpha(image, detect_green_screen(image))
        self.assertLess(alpha[10:40, 10:100].mean(), 0.05)
        self.assertGreater(alpha[90:170, 135:185].mean(), 0.95)

    def test_despill_removes_green_cast_only(self):
        image = np.array([[[100, 180, 120], [120, 150, 200]]], np.uint8)
        out = despill(image, 1.0)
        self.assertEqual(out[0, 0, 1], 120)            # green limited to max(R, B)
        self.assertEqual(out[0, 1].tolist(), [120, 150, 200])  # skin untouched

    def test_background_replaces_screen(self):
        background = Background(mode="auto", fill="color", color=(0, 0, 255))
        image = green_screen_with_person()
        background.key = detect_green_screen(image)
        out = background.apply(image)
        self.assertEqual(out[20, 20].tolist(), [0, 0, 255])
        self.assertEqual(out[120, 160].tolist(), list(SKIN))

    def test_chroma_mode_needs_a_detected_screen(self):
        self.assertFalse(Background(mode="chroma").active)
        self.assertTrue(Background(mode="chroma", key=(64.0, 85.0)).active)
        self.assertFalse(Background(mode="off", key=(64.0, 85.0)).active)

    def test_auto_prefers_green_screen_over_ai(self):
        self.assertFalse(Background(mode="auto", key=(64.0, 85.0)).uses_matting)

    def test_matte_composites_with_blur(self):
        image = np.zeros((90, 160, 3), np.uint8)
        image[:, 80:] = 255
        matte = np.zeros((45, 80), np.float32)
        matte[:, 60:] = 1.0                      # right quarter is "person"
        out = Background(mode="ai", fill="color", color=(0, 0, 255)).apply(image, matte)
        self.assertEqual(out[45, 10].tolist(), [0, 0, 255])
        self.assertEqual(out[45, 150].tolist(), [255, 255, 255])

    def test_cover_fills_target(self):
        self.assertEqual(cover(np.zeros((100, 400, 3), np.uint8), 160, 90).shape, (90, 160, 3))


def checkerboard(width=160, height=90, cell=4):
    ys, xs = np.mgrid[0:height, 0:width]
    board = (((xs // cell) + (ys // cell)) % 2 * 255).astype(np.uint8)
    return cv2.merge([board, board, board])


class HelperTest(unittest.TestCase):
    def test_despill_strength_zero_is_a_no_op(self):
        image = np.full((4, 4, 3), (10, 200, 10), np.uint8)
        self.assertIs(despill(image, 0.0), image)

    def test_partial_despill_scales_correction(self):
        image = np.array([[[100, 180, 120]]], np.uint8)
        self.assertEqual(int(despill(image, 0.5)[0, 0, 1]), 150)   # 180 - 0.5 * 60

    def test_composite_blends_by_alpha(self):
        fg = np.full((2, 2, 3), 200, np.uint8)
        bg = np.zeros((2, 2, 3), np.uint8)
        alpha = np.array([[1.0, 0.0], [0.5, 0.25]], np.float32)
        out = composite(fg, alpha, bg)
        self.assertEqual(out[:, :, 0].tolist(), [[200, 0], [100, 50]])

    def test_gradient_background_is_a_calm_vignette(self):
        image = gradient_background(320, 180)
        self.assertEqual(image.shape, (180, 320, 3))
        self.assertEqual(image.dtype, np.uint8)
        # Brightest around the upper centre, darker at the bottom edge.
        glow = int(image[63, 160].sum())
        self.assertGreater(glow, int(image[179, 160].sum()))
        self.assertGreater(glow, int(image[63, 0].sum()))
        # Horizontally symmetric and blue-tinted (B >= R everywhere).
        np.testing.assert_allclose(image[:, :10].astype(int), image[:, -1:-11:-1].astype(int), atol=1)
        self.assertTrue((image[:, :, 0] >= image[:, :, 2]).all())

    def test_cover_upscales_small_images(self):
        small = np.zeros((9, 16, 3), np.uint8)
        small[:] = (1, 2, 3)
        out = cover(small, 320, 180)
        self.assertEqual(out.shape, (180, 320, 3))
        self.assertEqual(out[90, 160].tolist(), [1, 2, 3])

    def test_cover_crops_the_centre_of_a_wide_image(self):
        wide = np.zeros((100, 400, 3), np.uint8)
        wide[:, :100] = (0, 0, 255)          # red left quarter
        wide[:, 100:300] = (0, 255, 0)       # green middle
        wide[:, 300:] = (255, 0, 0)          # blue right quarter
        out = cover(wide, 100, 100)          # square -> only the middle survives
        self.assertTrue((out[:, 5:-5] == (0, 255, 0)).all())

    def test_blurred_keeps_size_and_removes_detail(self):
        board = checkerboard()
        out = blurred(board, 6.0)
        self.assertEqual(out.shape, board.shape)
        self.assertLess(out.std(), board.std() * 0.2)

    def test_blurred_leaves_flat_images_flat(self):
        flat = np.full((90, 160, 3), (30, 60, 90), np.uint8)
        self.assertTrue((blurred(flat, 3.0) == flat).all())


class BackdropTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_image(self, image, name="bg.png"):
        path = Path(self.tmp.name) / name
        self.assertTrue(cv2.imwrite(str(path), image))
        return str(path)

    def test_color_fill(self):
        backdrop = Background(fill="color", color=(1, 2, 3)).backdrop(32, 18)
        self.assertEqual(backdrop.shape, (18, 32, 3))
        self.assertTrue((backdrop == (1, 2, 3)).all())

    def test_image_fill_is_scaled_to_cover(self):
        source = np.full((50, 50, 3), (0, 200, 100), np.uint8)
        background = Background(fill="image", image_path=self.write_image(source))
        backdrop = background.backdrop(64, 36)
        self.assertEqual(backdrop.shape, (36, 64, 3))
        self.assertEqual(backdrop[18, 32].tolist(), [0, 200, 100])

    def test_missing_image_falls_back_to_gradient(self):
        background = Background(fill="image", image_path=str(Path(self.tmp.name) / "missing.png"))
        np.testing.assert_array_equal(background.backdrop(64, 36), gradient_background(64, 36))

    def test_unreadable_image_falls_back_to_gradient(self):
        path = Path(self.tmp.name) / "broken.png"
        path.write_bytes(b"not an image")
        background = Background(fill="image", image_path=str(path))
        np.testing.assert_array_equal(background.backdrop(64, 36), gradient_background(64, 36))

    def test_gradient_fill(self):
        np.testing.assert_array_equal(Background(fill="gradient").backdrop(40, 30), gradient_background(40, 30))

    def test_backdrop_is_cached_per_size(self):
        background = Background(fill="color", color=(9, 9, 9))
        first = background.backdrop(32, 18)
        self.assertIs(background.backdrop(32, 18), first)
        self.assertIsNot(background.backdrop(64, 36), first)
        self.assertEqual(background.backdrop(64, 36).shape, (36, 64, 3))

    def test_blur_fill_without_matte_uses_gradient_not_green_blur(self):
        image = green_screen_with_person()
        background = Background(mode="chroma", fill="blur", key=detect_green_screen(image))
        out = background.apply(image)
        expected = gradient_background(320, 180)
        np.testing.assert_allclose(out[10, 10].astype(int), expected[10, 10].astype(int), atol=2)

    def test_blur_fill_with_matte_shows_blurred_room(self):
        room = checkerboard(160, 90)
        matte = np.zeros((45, 80), np.float32)           # nobody in frame
        out = Background(mode="ai", fill="blur", blur=4.0).apply(room, matte)
        np.testing.assert_array_equal(out, blurred(room, 4.0))

    def test_default_key_is_used_before_detection(self):
        image = green_screen_with_person()
        out = Background(mode="chroma", fill="color", color=(0, 0, 255)).apply(image)
        alpha = key_alpha(image, DEFAULT_KEY)
        self.assertLess(alpha[10:40, 10:100].mean(), 0.05)
        self.assertEqual(out[20, 300].tolist(), [0, 0, 255])


class ModeTest(unittest.TestCase):
    def test_off_is_never_active(self):
        self.assertFalse(Background(mode="off").active)
        self.assertFalse(Background(mode="off").uses_matting)

    @unittest.skipUnless(matting_available(), "RVM model / onnxruntime not installed")
    def test_ai_mode_uses_matting(self):
        self.assertTrue(Background(mode="ai").uses_matting)
        self.assertTrue(Background(mode="ai").active)
        # Auto falls back to AI matting while no green screen is detected.
        self.assertTrue(Background(mode="auto").uses_matting)
        self.assertFalse(Background(mode="chroma").uses_matting)

    def test_matting_prefers_cuda_then_cpu(self):
        with mock.patch("pixydeck.background.onnxruntime.get_available_providers",
                        return_value=["CPUExecutionProvider", "CUDAExecutionProvider"]):
            self.assertEqual(matting_providers(), ["CUDAExecutionProvider", "CPUExecutionProvider"])

    def test_gpu_matting_memory_is_bounded(self):
        with mock.patch.dict("os.environ", {"PIXYDECK_ORT_GPU_MEMORY_MB": "512"}):
            options = matting_provider_options(["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.assertEqual(options[0]["gpu_mem_limit"], str(512 * 1024 * 1024))
        self.assertEqual(options[1], {})


@unittest.skipUnless(matting_available(), "RVM model / onnxruntime not installed")
class MattingTest(unittest.TestCase):
    def test_alpha_has_model_size_and_range(self):
        matting = Matting(threads=1)
        image = np.full((180, 320, 3), 128, np.uint8)
        alpha = matting.alpha(image)
        self.assertEqual(alpha.shape, (MATTING_SIZE[1], MATTING_SIZE[0]))
        self.assertEqual(alpha.dtype, np.float32)
        self.assertGreaterEqual(float(alpha.min()), 0.0)
        self.assertLessEqual(float(alpha.max()), 1.0)
        self.assertLess(float(alpha.mean()), 0.1)        # a flat grey wall is no person

    def test_recurrent_state_is_kept_and_reset(self):
        matting = Matting(threads=1)
        initial = matting._state
        matting.alpha(np.full((90, 160, 3), 100, np.uint8))
        self.assertEqual(len(matting._state), 4)
        self.assertIsNot(matting._state[0], initial[0])
        self.assertGreater(matting._state[0].size, 1)    # real recurrent tensors now
        matting.reset()
        self.assertEqual([s.shape for s in matting._state], [(1, 1, 1, 1)] * 4)


if __name__ == "__main__":
    unittest.main()
