#!/usr/bin/env python3
"""Render README screenshots and animations from the real UI – without a camera.

Nothing here touches hardware or shows a real picture:
  * the camera feed is a painted demo scene (room + avatar),
  * camera control is a fake controller (no ioctl/HID),
  * system-derived data (apps using the camera, setup checks, device paths)
    is replaced with neutral demo values,
  * settings live in a throw-away config directory.

Usage: python tools/make_media.py [output-dir]   (default: docs/media)
Needs ffmpeg for the GIFs.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CONFIG = tempfile.mkdtemp(prefix="pixydeck-media-")
os.environ["XDG_CONFIG_HOME"] = CONFIG  # never read or write the user's settings

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient  # noqa: E402
from PySide6.QtMultimedia import QVideoFrame  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pixydeck import gui, privacy, setup, virtual_camera  # noqa: E402
from pixydeck.background import Background  # noqa: E402
from pixydeck.vision import Crop, Smoother, Stabilizer, framing_target, shift_image  # noqa: E402
from pixydeck.widgets import set_state  # noqa: E402

W, H = 1920, 1080
WINDOW = (1440, 880)


# ----------------------------------------------------------------------
# Painted demo scene
# ----------------------------------------------------------------------

def paint_room(p: QPainter) -> None:
    wall = QLinearGradient(0, 0, 0, H)
    wall.setColorAt(0, QColor("#3b4a5e"))
    wall.setColorAt(1, QColor("#26303d"))
    p.fillRect(0, 0, W, H, wall)
    glow = QRadialGradient(QPointF(1480, 330), 520)
    glow.setColorAt(0, QColor(255, 236, 200, 120))
    glow.setColorAt(1, QColor(255, 236, 200, 0))
    p.fillRect(0, 0, W, H, glow)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#c9d6e3"))                       # window
    p.drawRoundedRect(QRectF(1260, 120, 440, 420), 10, 10)
    p.setBrush(QColor("#9fb4c8"))
    p.drawRect(QRectF(1475, 120, 10, 420))
    p.drawRect(QRectF(1260, 325, 440, 10))
    p.setBrush(QColor("#6b4f3a"))                       # shelf with books
    p.drawRect(QRectF(150, 420, 520, 18))
    colors = ["#c0504d", "#4f81bd", "#9bbb59", "#f2c14e", "#8064a2", "#4bacc6", "#f79646"]
    x = 170
    for i, color in enumerate(colors * 2):
        height = 110 + (i * 37) % 60
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(x, 420 - height, 28 + (i % 3) * 6, height), 3, 3)
        x += 34 + (i % 3) * 6
    p.setBrush(QColor("#7a5c45"))                       # plant
    p.drawRoundedRect(QRectF(1720, 780, 120, 130), 12, 12)
    p.setBrush(QColor("#4f8a5b"))
    for angle in range(0, 360, 30):
        r = math.radians(angle)
        p.drawEllipse(QPointF(1780 + 70 * math.cos(r), 700 + 60 * math.sin(r)), 48, 26)
    p.setBrush(QColor("#2b2118"))                       # desk edge
    p.drawRect(QRectF(0, 980, W, 100))


def paint_avatar(p: QPainter, cx: float, scale: float = 1.0) -> QRectF:
    """Flat-design person with headphones; returns the face box in pixels."""
    s = scale
    head_r = 120 * s
    head = QPointF(cx, 470 * s + (1 - s) * 520)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2f6db5"))                       # shirt
    p.drawRoundedRect(QRectF(cx - 330 * s, head.y() + 190 * s, 660 * s, 520 * s), 180 * s, 180 * s)
    p.setBrush(QColor("#e8b796"))                       # neck + face
    p.drawRoundedRect(QRectF(cx - 50 * s, head.y() + 90 * s, 100 * s, 130 * s), 30 * s, 30 * s)
    p.drawEllipse(head, head_r * 0.92, head_r)
    p.setBrush(QColor("#3a2a22"))                       # hair
    hair = QPainterPath()
    hair.moveTo(cx - head_r * 0.95, head.y() - head_r * 0.05)
    hair.cubicTo(cx - head_r, head.y() - head_r * 1.35, cx + head_r, head.y() - head_r * 1.35,
                 cx + head_r * 0.95, head.y() - head_r * 0.05)
    hair.cubicTo(cx + head_r * 0.5, head.y() - head_r * 0.7, cx - head_r * 0.5, head.y() - head_r * 0.7,
                 cx - head_r * 0.95, head.y() - head_r * 0.05)
    p.drawPath(hair)
    p.setBrush(QColor("#2b2b33"))                       # eyes
    for dx in (-42, 42):
        p.drawEllipse(QPointF(cx + dx * s, head.y() + 5 * s), 11 * s, 13 * s)
    pen = QPen(QColor("#a5634e"), 7 * s)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(cx - 45 * s, head.y() + 20 * s, 90 * s, 60 * s), 200 * 16, 140 * 16)
    p.setPen(QPen(QColor("#1d1f26"), 22 * s))           # headphones
    p.drawArc(QRectF(cx - head_r * 1.08, head.y() - head_r * 1.15, head_r * 2.16, head_r * 1.9), 20 * 16, 140 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1d1f26"))
    for side in (-1, 1):
        p.drawRoundedRect(QRectF(cx + side * head_r * 0.98 - 28 * s, head.y() - 40 * s, 56 * s, 95 * s), 20 * s, 20 * s)
    return QRectF(cx - head_r * 0.92, head.y() - head_r, head_r * 1.84, head_r * 2)


def scene(cx: float = 960, scale: float = 1.0, room: bool = True) -> tuple[QImage, QRectF]:
    image = QImage(W, H, QImage.Format_RGB32)
    image.fill(QColor("#000000"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    if room:
        paint_room(p)
    face = paint_avatar(p, cx, scale)
    p.end()
    return image, face


def qimage_to_bgr(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format_BGR888)
    data = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    return data[:, : image.width() * 3].reshape(image.height(), image.width(), 3).copy()


def bgr_to_qimage(array: np.ndarray) -> QImage:
    h, w = array.shape[:2]
    return QImage(array.data, w, h, array.strides[0], QImage.Format_BGR888).copy()


def background_variant(fill: str, cx: float = 960) -> QImage:
    """Real compositing code; the matte is the avatar's exact shape."""
    frame, _ = scene(cx)
    person, _ = scene(cx, room=False)
    matte = (qimage_to_bgr(person).max(axis=2) > 0).astype(np.float32)
    matte = cv2.resize(matte, (960, 540), interpolation=cv2.INTER_AREA)
    background = Background(mode="ai", fill=fill, color=(90, 60, 40), blur=8)
    return bgr_to_qimage(background.apply(qimage_to_bgr(frame), matte))


# ----------------------------------------------------------------------
# Demo app: the real PixyGUI with fake hardware and neutral system data
# ----------------------------------------------------------------------

class FakeController:
    RANGES = {"white_balance_temperature": (2300, 7500, 4600), "exposure_time_absolute": (1, 5000, 300),
              "focus_absolute": (0, 1023, 365), "gain": (0, 100, 12), "backlight_compensation": (1, 2, 1),
              "white_balance_automatic": (0, 1, 1), "focus_automatic_continuous": (0, 1, 1),
              "auto_exposure": (0, 3, 3)}

    def position(self):
        return 12, -4, 100

    def query(self, name):
        low, high, value = self.RANGES.get(name, (0, 255, 140))
        return {"min": low, "max": high, "step": 1, "default": value, "inactive": False}

    def get(self, name):
        return self.query(name)["default"]

    def state(self):
        return {}

    def __getattr__(self, _name):  # move_to, set_zoom, tracking, focus_mode, … do nothing
        return lambda *args, **kwargs: None


class DemoCamera(QObject):
    def isActive(self) -> bool:  # noqa: N802 - Qt API
        return True

    def stop(self) -> None:
        pass


def demo_checks(all_ok: bool = False) -> list:
    rows = [("camera", "EMEET PIXY connected", "USB 328f:00c0 found"),
            ("hid", "Camera controls (tracking, privacy, focus …)", "/dev/hidraw0 is accessible"),
            ("module", "v4l2loopback kernel module", "available"),
            ("virtual", "Virtual camera for Meet, Zoom, Teams, OBS", "EMEET PIXY (PixyDeck) at /dev/video20"),
            ("group", "Permission to feed the virtual camera", "PixyDeck can send video to it."),
            ("ffmpeg", "FFmpeg", "installed"),
            ("ai", "AI features (auto-framing, background)", "OpenCV and ONNX Runtime available")]
    checks = [setup.Check(key, title, True, detail) for key, title, detail in rows]
    if not all_ok:
        checks[3] = setup.Check("virtual", rows[3][1], False, "EMEET PIXY (PixyDeck) does not exist yet.",
                                fix="virtual-camera")
    return checks


def make_window():
    gui.PixyController = FakeController
    privacy.camera_users = lambda *_args, **_kwargs: []
    privacy.pixy_video_nodes = lambda: []
    virtual_camera.find_virtual_camera_device = lambda: "/dev/video20"
    gui.run_checks = lambda: demo_checks(all_ok=True)
    setup.run_checks = demo_checks

    def start_camera(self):
        self.device_label.setText("EMEET PIXY")
        if self.resolution.count() == 0:
            for key, fps in (("3840x2160", 30), ("2560x1440", 30), ("1920x1080", 60), ("1280x720", 60)):
                width, height = key.split("x")
                self.resolution.addItem(f"{width} × {height} · {fps} fps", key)
        self.camera = DemoCamera(self)
        self.preview_stack.setCurrentWidget(self.view)
        self.arm_frame_watchdog()

    gui.PixyGUI.start_camera = start_camera
    gui.PixyGUI.stop_camera = lambda self: None
    # Never feed a real virtual camera from the demo (autostart is on by default).
    gui.PixyGUI.autostart_virtual_camera = lambda self: None
    window = gui.PixyGUI()
    window.resize(*WINDOW)
    window.show()
    # The demo drives the crop itself; the live 60 Hz crop timer would override it.
    for timer in (window.state_timer, window.privacy_timer, window.poll_timer, window.watchdog_timer, window.crop_timer):
        timer.stop()
    return window


def show_frame(window, image: QImage) -> None:
    window.view.video.videoSink().setVideoFrame(QVideoFrame(image))
    window.mark_frame(None)


def settle(rounds: int = 6) -> None:
    for _ in range(rounds):
        QApplication.processEvents()


def grab(window, path: Path) -> None:
    window.update_hud()
    settle()
    window.grab().save(str(path))


def gif(frames_dir: Path, out: Path, fps: int = 12, width: int = 960) -> None:
    pattern = str(frames_dir / "%04d.png")
    palette = frames_dir / "palette.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", pattern,
                    "-vf", f"scale={width}:-1:flags=lanczos,palettegen=stats_mode=diff", str(palette)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", pattern, "-i", str(palette),
                    "-lavfi", f"scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    "-loop", "0", str(out)], check=True)


# ----------------------------------------------------------------------
# Media
# ----------------------------------------------------------------------

def screenshots(window, out: Path) -> None:
    frame, face = scene()
    show_frame(window, frame)
    window.pad.set_position(12, -4)

    window.tabs.setCurrentIndex(0)
    grab(window, out / "camera.png")
    tour(window, out / "tour.png")

    window.tabs.setCurrentIndex(1)
    window.focus_mode.set_current("area")
    window.view.show_faces = True
    window.view.set_faces([(face.x() / W, face.y() / H, face.width() / W, face.height() / H)])
    window.view.show_focus_point(0.13, 0.33)
    window.view._marker_timer.stop()
    grab(window, out / "ai.png")
    window.view.set_faces([])
    window.view.focus_marker.hide()

    window.tabs.setCurrentIndex(2)
    grab(window, out / "image.png")

    window.tabs.setCurrentIndex(3)
    window.bg_mode.set_current("ai")
    window.bg_fill.set_current("blur")
    window.view.set_processed(background_variant("blur"))
    window.bg_status.setText("🧠 AI cutout active")
    grab(window, out / "background.png")
    window.view.set_processed(None)
    window.bg_mode.set_current("off")

    window.tabs.setCurrentIndex(4)
    window.calls_enabled.set_silently(True)
    window.calls_status.setText("📞 In a call – zoom")
    window.pill_users.setText("📞 Call: zoom")
    window.pill_users.show()
    set_state(window.pill_users, "ok")
    window.privacy_enabled.set_silently(True)
    window.privacy_status.setText("Camera in use – timer paused")
    grab(window, out / "calls.png")
    window.pill_users.hide()
    window.calls_enabled.set_silently(False)
    window.privacy_enabled.set_silently(False)

    window.tabs.setCurrentIndex(5)
    window.pill_virtual.setText("Virtual cam on")
    set_state(window.pill_virtual, "on")
    window.virtual_status.setText("Pipeline: processed – 1920 × 1080")
    window.virtual_device_status.setText("Device: ready – /dev/video20")
    window.virtual_start.setEnabled(False)
    window.virtual_stop.setEnabled(True)
    grab(window, out / "output.png")
    window.pill_virtual.setText("Virtual cam off")
    set_state(window.pill_virtual, "")

    dialog = setup.SetupDialog(window)
    dialog.resize(620, 600)
    dialog.show()
    settle()
    dialog.grab().save(str(out / "setup.png"))
    dialog.close()


def tour(window, path: Path) -> None:
    """The main window with numbered markers for the README's GUI tour."""
    window.update_hud()
    settle()
    image = window.grab().toImage()
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    font = QFont()
    font.setPixelSize(17)
    font.setBold(True)
    p.setFont(font)

    def corner(widget, dx=0, dy=0):
        point = widget.mapTo(window, QPoint(0, 0))
        return QPointF(point.x() + dx, point.y() + dy)

    setup = window.setup_button
    markers = [
        corner(window.pill_tracking, -14, 4),                         # 1 status pills
        corner(setup, setup.width() // 2, setup.height() + 14),       # 2 setup
        corner(window.preview_stack, 30, 70),                         # 3 preview
        corner(window.zoom_slider, 40, -16),                          # 4 toolbar
        corner(window.tabs, -8, 14),                                  # 5 tabs
        corner(window.speed_sliders["pan"], -24, 10),                 # 6 settings cards
    ]
    for number, centre in enumerate(markers, 1):
        p.setPen(QPen(QColor("#0b0d11"), 3))
        p.setBrush(QColor("#ffb020"))
        p.drawEllipse(centre, 16, 16)
        p.setPen(QColor("#0b0d11"))
        p.drawText(QRectF(centre.x() - 16, centre.y() - 16, 32, 32), Qt.AlignCenter, str(number))
    p.end()
    image.save(str(path))


def animation_stabilize(out: Path) -> None:
    """Side by side: a shaking camera without and with "Steady picture".

    The right half runs the real Stabilizer on the painted scene; both
    halves get the same 8 % reserve crop the app uses, so only the shake
    differs.
    """
    frame, _ = scene()
    base = cv2.resize(qimage_to_bgr(frame), (960, 540), interpolation=cv2.INTER_AREA)
    stabilizer = Stabilizer()
    zoom = 1.0 + 2 * stabilizer.margin
    crop_w, crop_h = round(960 / zoom), round(540 / zoom)
    x0, y0 = (960 - crop_w) // 2, (540 - crop_h) // 2
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(72):
            t = i / 12
            sx = 7 * math.sin(2 * math.pi * 1.3 * t) + 3 * math.sin(2 * math.pi * 3.1 * t)
            sy = 5 * math.sin(2 * math.pi * 1.1 * t + 1)
            shaken = cv2.warpAffine(base, np.float32([[1, 0, sx], [0, 1, sy]]), (960, 540),
                                    borderMode=cv2.BORDER_REPLICATE)
            steady = shift_image(shaken, stabilizer.update(shaken))
            halves = []
            for image, label in ((shaken, "Without"), (steady, "Steady picture")):
                half = cv2.resize(image[y0:y0 + crop_h, x0:x0 + crop_w], (480, 270), interpolation=cv2.INTER_AREA)
                cv2.rectangle(half, (10, 10), (24 + 11 * len(label), 40), (17, 13, 11), -1)
                cv2.putText(half, label, (17, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1, cv2.LINE_AA)
                halves.append(half)
            divider = np.full((270, 6, 3), (17, 13, 11), np.uint8)
            cv2.imwrite(str(Path(tmp) / f"{i:04d}.png"), np.hstack([halves[0], divider, halves[1]]))
        gif(Path(tmp), out / "stabilize.gif", fps=12, width=966)


def animation_zoom(window, out: Path) -> None:
    frame, _ = scene()
    show_frame(window, frame)
    window.tabs.setCurrentIndex(0)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(54):
            t = i / 53
            ease = 0.5 - 0.5 * math.cos(math.pi * min(1.0, t * 1.7))
            zoom = 1.0 + 1.4 * ease
            pan = 0.5 + (0.1 * math.sin(math.pi * (t - 0.6) / 0.4) if t > 0.6 else 0.0)
            window.zoom_value = round(zoom * 100)
            window.sync_zoom_widgets()
            window.view.set_crop(Crop(pan, 0.47, zoom))
            window.pad.set_position(round(12 + 16 * ease), round(-4 + 5 * ease))
            grab(window, Path(tmp) / f"{i:04d}.png")
        gif(Path(tmp), out / "zoom.gif")


def animation_autoframe(window, out: Path) -> None:
    window.tabs.setCurrentIndex(1)
    window.autoframe.set_silently(True)
    smoother = Smoother(speed=3.5, dead_zone=0.01)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(66):
            cx = 960 + 560 * math.sin(i / 65 * 2 * math.pi)
            frame, face = scene(cx, scale=0.42)
            show_frame(window, frame)
            box = (face.x() / W, face.y() / H, face.width() / W, face.height() / H)
            smoother.set_target(framing_target([box], fill=0.55))
            crop = smoother.step(1 / 12)
            window.view.set_crop(crop)
            window.zoom_value = round(crop.zoom * 100)
            window.sync_zoom_widgets()
            grab(window, Path(tmp) / f"{i:04d}.png")
        gif(Path(tmp), out / "autoframe.gif")
    window.autoframe.set_silently(False)
    window.view.set_crop(Crop())
    window.zoom_value = 100
    window.sync_zoom_widgets()


def animation_background(window, out: Path) -> None:
    frame, _ = scene()
    show_frame(window, frame)
    window.tabs.setCurrentIndex(3)
    variants = [("off", None), ("blur", background_variant("blur")),
                ("gradient", background_variant("gradient")), ("color", background_variant("color"))]
    with tempfile.TemporaryDirectory() as tmp:
        index = 0
        for fill, image in variants:
            window.bg_mode.set_current("off" if image is None else "ai")
            if image is not None:
                window.bg_fill.set_current(fill)
            window.bg_status.setText("" if image is None else "🧠 AI cutout active")
            window.view.set_processed(image)
            for _ in range(13):
                grab(window, Path(tmp) / f"{index:04d}.png")
                index += 1
        gif(Path(tmp), out / "background.gif", fps=10)
    window.view.set_processed(None)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "media"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(gui.THEME)
    window = make_window()
    settle(20)
    screenshots(window, out)
    if shutil.which("ffmpeg"):
        animation_zoom(window, out)
        animation_autoframe(window, out)
        animation_background(window, out)
        animation_stabilize(out)
    else:
        print("ffmpeg not found – skipping GIFs")
    window.close()
    shutil.rmtree(CONFIG, ignore_errors=True)
    print("Media written to", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
