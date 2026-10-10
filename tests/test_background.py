import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from pixydeck.background import (
    Background, cover, despill, detect_green_screen, key_alpha,
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


if __name__ == "__main__":
    unittest.main()
