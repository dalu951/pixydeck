"""Shared constants of the PixyDeck UI."""

from __future__ import annotations

from . import backend

# Zoom in percent: hardware up to HW_ZOOM_MAX, digital beyond.
ZOOM_MIN, HW_ZOOM_MAX, ZOOM_MAX = 100, 150, 400
PRESET_SLOTS = 4

# Pan/tilt limits in degrees (tilt floor: below it the PIXY only parks).
PAN_LIMIT = backend.PAN_MAX // backend.DEGREE_UNIT
TILT_MIN = backend.TILT_MIN // backend.DEGREE_UNIT
TILT_MAX = backend.TILT_MAX // backend.DEGREE_UNIT

# Approximate field of view at 1x, used to turn preview clicks into angles.
FOV_H, FOV_V = 70, 40

IMAGE_SLIDERS = [
    ("brightness", "Brightness"),
    ("contrast", "Contrast"),
    ("saturation", "Saturation"),
    ("hue", "Hue"),
    ("sharpness", "Sharpness"),
    ("gamma", "Gamma"),
    ("gain", "Gain"),
]

# (toggle label, auto control, (auto value, manual value), manual control, slider label, unit)
IMAGE_AUTO = [
    ("Auto white balance", "white_balance_automatic", (1, 0), "white_balance_temperature", "Temperature", " K"),
    ("Auto exposure", "auto_exposure", (backend.EXPOSURE_APERTURE_PRIORITY, backend.EXPOSURE_MANUAL),
     "exposure_time_absolute", "Exposure time", ""),
    ("Autofocus", "focus_automatic_continuous", (1, 0), "focus_absolute", "Focus", ""),
]

AUTO_CONTROLS = [entry[1] for entry in IMAGE_AUTO]

FRAMING = {"tight": 0.62, "medium": 0.45, "wide": 0.3}

# Who owns the camera stream: the preview, another app, or the virtual camera.
PREVIEW, RELEASED, VIRTUAL_DIRECT, VIRTUAL_PROCESSED = "preview", "released", "direct", "processed"
