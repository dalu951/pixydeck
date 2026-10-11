"""Behaviour tests for the custom widgets – headless, no camera, no video."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QSizeF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from pixydeck import widgets  # noqa: E402
from pixydeck.vision import Crop  # noqa: E402

APP = QApplication.instance() or QApplication([])


def send_mouse(widget, kind, pos, button=Qt.LeftButton):
    """Deliver a synthetic mouse event straight to ``widget``."""
    pos = QPointF(*pos)
    held = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
    if kind == QEvent.MouseMove:
        button = Qt.NoButton
    event = QMouseEvent(kind, pos, QPointF(widget.mapToGlobal(pos.toPoint())), button, held, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def send_wheel(widget, delta_y):
    pos = QPointF(10, 10)
    event = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, delta_y),
                        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


class Recorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


class HelpersTest(unittest.TestCase):
    def test_set_state_updates_pill_property(self):
        label = QLabel("Tracking", objectName="pill")
        label.setStyleSheet(widgets.THEME)
        widgets.set_state(label, "warn")
        self.assertEqual(label.property("state"), "warn")
        widgets.set_state(label, "ok")
        self.assertEqual(label.property("state"), "ok")

    def test_section_title_is_uppercase_and_styled(self):
        label = widgets.section_title("Image")
        self.assertEqual(label.text(), "IMAGE")
        self.assertEqual(label.objectName(), "sectionTitle")

    def test_theme_uses_accent_and_applies(self):
        self.assertIn(widgets.ACCENT, widgets.THEME)
        self.assertIn("QPushButton#primary", widgets.THEME)
        card = widgets.Card("Camera")
        card.setStyleSheet(widgets.THEME)
        card.ensurePolished()
        self.assertEqual(card.styleSheet(), widgets.THEME)

    def test_card_with_and_without_title(self):
        titled = widgets.Card("Camera")
        self.assertEqual(titled.objectName(), "card")
        self.assertEqual(titled.body.count(), 1)
        self.assertEqual(titled.body.itemAt(0).widget().text(), "CAMERA")
        untitled = widgets.Card()
        self.assertEqual(untitled.body.count(), 0)


class ToggleSwitchTest(unittest.TestCase):
    def test_click_toggles_and_emits(self):
        switch = widgets.ToggleSwitch()
        rec = Recorder(switch.toggled)
        switch.setChecked(True)
        self.assertEqual(rec.calls, [(True,)])
        self.assertEqual(switch._anim.endValue(), 1.0)
        switch.setChecked(False)
        self.assertEqual(rec.calls, [(True,), (False,)])
        self.assertEqual(switch._anim.endValue(), 0.0)

    def test_set_silently_does_not_emit_and_jumps(self):
        switch = widgets.ToggleSwitch()
        rec = Recorder(switch.toggled)
        switch.set_silently(True)
        self.assertTrue(switch.isChecked())
        self.assertEqual(rec.calls, [])
        self.assertEqual(switch.offset, 1.0)
        switch.set_silently(False)
        self.assertFalse(switch.isChecked())
        self.assertEqual(switch.offset, 0.0)

    def test_offset_property_and_paint(self):
        switch = widgets.ToggleSwitch()
        self.assertEqual(switch.sizeHint().width(), 42)
        switch.resize(switch.sizeHint())
        switch.offset = 0.5
        self.assertEqual(switch.offset, 0.5)
        on = switch.grab().toImage()
        switch.setEnabled(False)
        off = switch.grab().toImage()
        self.assertFalse(on.isNull())
        # Disabled track is drawn grey instead of the blended accent.
        self.assertNotEqual(on.pixelColor(4, 12), off.pixelColor(4, 12))


class RowsTest(unittest.TestCase):
    def test_setting_row_hint(self):
        row = widgets.SettingRow("Mirror", widgets.ToggleSwitch(), hint="Flip the image")
        self.assertEqual(row.label.text(), "Mirror")
        self.assertEqual(row.hint.text(), "Flip the image")
        self.assertEqual(row.hint.objectName(), "subtle")
        plain = widgets.SettingRow("Mirror", widgets.ToggleSwitch())
        self.assertIsNone(plain.hint)

    def test_slider_row_emits_and_formats(self):
        row = widgets.SliderRow("Zoom", 100, 400, 100, fmt=lambda v: f"{v / 100:.1f}x")
        self.assertEqual(row.value_label.text(), "1.0x")
        rec = Recorder(row.value_changed)
        row.slider.setValue(250)
        self.assertEqual(rec.calls, [(250,)])
        self.assertEqual(row.value_label.text(), "2.5x")
        self.assertEqual(row.value(), 250)

    def test_slider_row_silent_updates(self):
        row = widgets.SliderRow("Brightness", 0, 255, 128)
        rec = Recorder(row.value_changed)
        row.set_value_silently(200)
        self.assertEqual(row.value(), 200)
        self.assertEqual(row.value_label.text(), "200")
        row.set_value_silently(999)  # clamped to the range
        self.assertEqual(row.value_label.text(), "255")
        row.set_range(0, 100)
        self.assertEqual(row.value(), 100)
        self.assertEqual(row.value_label.text(), "100")
        self.assertEqual(rec.calls, [])


class SegmentedTest(unittest.TestCase):
    def setUp(self):
        self.seg = widgets.Segmented([("Off", "off"), ("Upper", "upper"), ("Full", "full")])

    def test_buttons_and_edge_properties(self):
        self.assertEqual(list(self.seg.buttons), ["off", "upper", "full"])
        self.assertTrue(self.seg.buttons["off"].property("first"))
        self.assertFalse(self.seg.buttons["off"].property("last"))
        self.assertTrue(self.seg.buttons["full"].property("last"))
        self.assertIsNone(self.seg.current())

    def test_click_emits_data(self):
        rec = Recorder(self.seg.selected)
        self.seg.buttons["upper"].click()
        self.assertEqual(rec.calls, [("upper",)])
        self.assertEqual(self.seg.current(), "upper")

    def test_set_current_is_exclusive_and_silent(self):
        rec = Recorder(self.seg.selected)
        self.seg.set_current("off")
        self.seg.set_current("full")
        self.assertEqual(self.seg.current(), "full")
        self.assertFalse(self.seg.buttons["off"].isChecked())
        self.seg.set_current("unknown")
        self.assertEqual(self.seg.current(), "full")
        self.assertEqual(rec.calls, [])


class PtzPadTest(unittest.TestCase):
    def setUp(self):
        self.pad = widgets.PtzPad()
        # Field = widget minus 6 px margin -> 300 x 150 starting at (6, 6).
        self.pad.resize(312, 162)
        self.rec = Recorder(self.pad.target_changed)

    def test_size_hint(self):
        self.assertEqual(self.pad.sizeHint().width(), 300)

    def test_click_corners_map_to_range_limits(self):
        send_mouse(self.pad, QEvent.MouseButtonPress, (6, 156))
        send_mouse(self.pad, QEvent.MouseButtonRelease, (6, 156))
        send_mouse(self.pad, QEvent.MouseButtonPress, (306, 6))
        send_mouse(self.pad, QEvent.MouseButtonRelease, (306, 6))
        self.assertEqual(self.rec.calls, [(-150, -52), (150, 90)])
        self.assertEqual(self.pad.target, (150, 90))

    def test_click_outside_field_is_clamped(self):
        send_mouse(self.pad, QEvent.MouseButtonPress, (-50, 500))
        self.assertEqual(self.rec.calls, [(-150, -52)])

    def test_centre_maps_to_mid_range(self):
        send_mouse(self.pad, QEvent.MouseButtonPress, (156, 81))
        pan, tilt = self.rec.calls[-1]
        self.assertEqual(pan, 0)
        self.assertEqual(tilt, 19)  # midpoint of -52..90

    def test_drag_emits_until_release(self):
        send_mouse(self.pad, QEvent.MouseButtonPress, (156, 81))
        self.assertTrue(self.pad.dragging)
        send_mouse(self.pad, QEvent.MouseMove, (306, 81))
        send_mouse(self.pad, QEvent.MouseButtonRelease, (306, 81))
        self.assertFalse(self.pad.dragging)
        send_mouse(self.pad, QEvent.MouseMove, (6, 81))
        self.assertEqual([call[0] for call in self.rec.calls], [0, 150])

    def test_move_without_press_and_right_click_ignored(self):
        send_mouse(self.pad, QEvent.MouseMove, (100, 100))
        send_mouse(self.pad, QEvent.MouseButtonPress, (100, 100), Qt.RightButton)
        self.assertEqual(self.rec.calls, [])
        self.assertFalse(self.pad.dragging)

    def test_target_cleared_when_camera_arrives(self):
        self.pad.target = (30, 10)
        self.pad.set_position(0, 0)
        self.assertEqual(self.pad.target, (30, 10))
        self.pad.set_position(29, 11)
        self.assertIsNone(self.pad.target)
        self.assertEqual(self.pad.position, (29, 11))

    def test_target_kept_while_dragging(self):
        self.pad.target = (30, 10)
        self.pad.dragging = True
        self.pad.set_position(30, 10)
        self.assertEqual(self.pad.target, (30, 10))

    def test_paint_with_target(self):
        self.pad.set_position(20, -10)
        self.pad.target = (-60, 40)
        image = self.pad.grab().toImage()
        self.assertFalse(image.isNull())
        centre = self.pad._to_point(20, -10).toPoint()
        self.assertEqual(image.pixelColor(centre).name(), widgets.ACCENT)


class PreviewViewTest(unittest.TestCase):
    def setUp(self):
        self.view = widgets.PreviewView()
        self.view.resize(640, 360)
        self.view.show()
        APP.processEvents()
        self.vp = self.view.viewport()
        self.assertEqual((self.vp.width(), self.vp.height()), (640, 360))

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()

    def test_initial_frame_size(self):
        self.assertEqual(self.view.frame_size(), (1920.0, 1080.0))

    def test_click_reports_normalized_position(self):
        rec = Recorder(self.view.clicked)
        send_mouse(self.vp, QEvent.MouseButtonPress, (160, 90))
        send_mouse(self.vp, QEvent.MouseButtonRelease, (162, 91))
        self.assertEqual(len(rec.calls), 1)
        nx, ny = rec.calls[0]
        self.assertAlmostEqual(nx, 162 / 640, places=2)
        self.assertAlmostEqual(ny, 91 / 360, places=2)
        self.assertIsNone(self.view._press_at)

    def test_drag_emits_delta_not_click(self):
        clicks = Recorder(self.view.clicked)
        drags = Recorder(self.view.drag_by)
        send_mouse(self.vp, QEvent.MouseButtonPress, (300, 200))
        send_mouse(self.vp, QEvent.MouseMove, (364, 200))
        send_mouse(self.vp, QEvent.MouseButtonRelease, (364, 200))
        self.assertEqual(clicks.calls, [])
        self.assertEqual(len(drags.calls), 1)
        dx, dy = drags.calls[0]
        # Dragging right moves the crop left: 64 px of a 640 px wide frame.
        self.assertAlmostEqual(dx, -0.1, places=3)
        self.assertAlmostEqual(dy, 0.0, places=6)

    def test_move_without_press_and_right_button_ignored(self):
        drags = Recorder(self.view.drag_by)
        send_mouse(self.vp, QEvent.MouseMove, (100, 100))
        send_mouse(self.vp, QEvent.MouseButtonPress, (100, 100), Qt.RightButton)
        send_mouse(self.vp, QEvent.MouseMove, (150, 100))
        self.assertEqual(drags.calls, [])

    def test_click_outside_frame_ignored(self):
        self.view.resize(800, 360)  # letterboxed: 80 px bars left and right
        APP.processEvents()
        rec = Recorder(self.view.clicked)
        send_mouse(self.vp, QEvent.MouseButtonPress, (10, 180))
        send_mouse(self.vp, QEvent.MouseButtonRelease, (10, 180))
        self.assertEqual(rec.calls, [])

    def test_double_click(self):
        rec = Recorder(self.view.double_clicked)
        send_mouse(self.vp, QEvent.MouseButtonDblClick, (320, 180))
        nx, ny = rec.calls[0]
        self.assertAlmostEqual(nx, 0.5, places=2)
        self.assertAlmostEqual(ny, 0.5, places=2)

    def test_wheel_zoom_steps(self):
        rec = Recorder(self.view.wheel_zoom)
        send_wheel(self.vp, 240)
        send_wheel(self.vp, -120)
        send_wheel(self.vp, 30)  # less than one notch: ignored
        self.assertEqual(rec.calls, [(2,), (-1,)])

    def test_crop_zoom_centres_view(self):
        self.view.set_crop(Crop(0.25, 0.25, 2.0))
        centre = self.view.mapToScene(self.vp.rect().center())
        self.assertAlmostEqual(centre.x() / 1920, 0.25, places=2)
        self.assertAlmostEqual(centre.y() / 1080, 0.25, places=2)
        self.assertAlmostEqual(self.view.transform().m11(), 2 / 3, places=4)

    def test_crop_is_clamped(self):
        self.view.set_crop(Crop(0.0, 1.0, 10.0))
        self.assertEqual(self.view.crop, Crop(0.125, 0.875, 4.0))

    def test_native_size_change(self):
        self.view._native_size_changed(QSizeF(1280, 720))
        self.assertEqual(self.view.frame_size(), (1280.0, 720.0))
        self.view._native_size_changed(QSizeF())
        self.assertEqual(self.view.frame_size(), (1280.0, 720.0))

    def test_processed_frame_covers_video(self):
        image = QImage(192, 108, QImage.Format_RGB32)
        image.fill(QColor("red"))
        self.view.set_processed(image)
        self.assertTrue(self.view.processed.isVisible())
        self.assertFalse(self.view.video.isVisible())
        self.assertAlmostEqual(self.view.processed.scale(), 10.0)
        self.view.set_processed(None)
        self.assertFalse(self.view.processed.isVisible())
        self.assertTrue(self.view.video.isVisible())
        self.view.set_processed(QImage())
        self.assertTrue(self.view.video.isVisible())

    def test_faces_only_shown_when_enabled(self):
        self.view.set_faces([(0.1, 0.2, 0.3, 0.4)])
        self.assertEqual(len(self.view._face_items), 1)
        self.assertFalse(self.view._face_items[0].isVisible())
        self.view.show_faces = True
        self.view.set_faces([(0.1, 0.2, 0.3, 0.4), (0.9, 0.9, 0.5, 0.5)])
        first, second = self.view._face_items
        rect = first.rect()
        self.assertAlmostEqual(rect.x(), 192)
        self.assertAlmostEqual(rect.height(), 432)
        # Boxes leaving the frame are clipped to it.
        self.assertAlmostEqual(second.rect().right(), 1920)
        self.assertTrue(second.isVisible())
        self.view.set_faces([])
        self.assertFalse(any(item.isVisible() for item in self.view._face_items))

    def test_focus_marker(self):
        self.view.show_focus_point(0.5, 0.5)
        rect = self.view.focus_marker.rect()
        self.assertAlmostEqual(rect.center().x(), 960)
        self.assertAlmostEqual(rect.width(), 1080 * 0.08)
        self.assertTrue(self.view.focus_marker.isVisible())
        self.assertTrue(self.view._marker_timer.isActive())
        self.view._marker_timer.timeout.emit()
        self.assertFalse(self.view.focus_marker.isVisible())

    def test_hud_labels(self):
        self.view.set_hud("1080p", "")
        self.assertEqual(self.view.hud_left.text(), "1080p")
        self.assertTrue(self.view.hud_left.isVisible())
        self.assertFalse(self.view.hud_right.isVisible())
        self.view.set_hud("1080p", "2.0x")
        self.assertTrue(self.view.hud_right.isVisible())
        self.assertEqual(self.view.hud_right.geometry().right(), self.vp.width() - 13)
        self.view.set_hud("1080p", "2.0x")  # unchanged: no relayout
        self.view.scrollContentsBy(0, 0)
        self.assertEqual(self.view.hud_left.pos(), QPoint(12, 12))

    def test_flash_shows_and_hides(self):
        self.view.flash("2.5x")
        self.assertEqual(self.view.hud_center.text(), "2.5x")
        self.assertTrue(self.view.hud_center.isVisible())
        self.assertEqual(self.view._flash_timer.interval(), 900)
        self.view._flash_timer.timeout.emit()
        self.assertFalse(self.view.hud_center.isVisible())


class InfoPanelTest(unittest.TestCase):
    def test_show_message_and_paint(self):
        panel = widgets.InfoPanel()
        panel.show_message("📷", "Camera in use", "Another program is using the camera.")
        self.assertEqual(panel.icon.text(), "📷")
        self.assertEqual(panel.heading.text(), "Camera in use")
        self.assertEqual(panel.text.text(), "Another program is using the camera.")
        panel.resize(400, 300)
        image = panel.grab().toImage()
        self.assertEqual(image.pixelColor(200, 290).name(), "#0b0d11")


class ButtonsInThemeTest(unittest.TestCase):
    def test_primary_button_gets_accent_background(self):
        button = QPushButton("Fix", objectName="primary")
        button.setStyleSheet(widgets.THEME)
        button.resize(80, 30)
        image = button.grab().toImage()
        self.assertEqual(image.pixelColor(12, 15).name(), widgets.ACCENT)


class WheelGuardTest(unittest.TestCase):
    """Scrolling a page over a slider scrolls the page, not the slider."""

    def setUp(self):
        from PySide6.QtWidgets import QComboBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget
        self.guard = widgets.WheelGuard()
        APP.installEventFilter(self.guard)
        self.addCleanup(APP.removeEventFilter, self.guard)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.row = widgets.SliderRow("Speed", 0, 100, 50)
        self.spin = QSpinBox()
        self.combo = QComboBox()
        self.combo.addItems(["a", "b", "c"])
        for widget in (self.row, self.spin, self.combo):
            layout.addWidget(widget)
        layout.addSpacing(3000)
        self.area.setWidget(page)
        self.area.resize(300, 200)
        self.area.show()
        APP.processEvents()
        self.row.slider.clearFocus()  # show() hands focus to the first focusable control
        APP.processEvents()
        self.addCleanup(self.area.deleteLater)
        self.addCleanup(self.area.close)

    def test_unfocused_controls_scroll_the_page(self):
        bar = self.area.verticalScrollBar()
        send_wheel(self.row.slider, -120)
        self.assertEqual(self.row.slider.value(), 50)
        self.assertGreater(bar.value(), 0)
        before = bar.value()
        send_wheel(self.spin, -120)
        send_wheel(self.combo, -120)
        self.assertEqual(self.spin.value(), 0)
        self.assertEqual(self.combo.currentIndex(), 0)
        self.assertGreater(bar.value(), before)

    def test_clicked_slider_takes_the_wheel(self):
        self.assertEqual(self.row.slider.focusPolicy(), Qt.StrongFocus)
        self.row.slider.setFocus()
        APP.processEvents()
        send_wheel(self.row.slider, 120)
        self.assertNotEqual(self.row.slider.value(), 50)
        self.assertEqual(self.area.verticalScrollBar().value(), 0)

    def test_controls_outside_a_scroll_area_are_untouched(self):
        row = widgets.SliderRow("Zoom", 0, 100, 50)
        row.show()
        self.addCleanup(row.close)
        send_wheel(row.slider, 120)
        self.assertNotEqual(row.slider.value(), 50)

    def test_other_events_pass(self):
        event = QEvent(QEvent.Enter)
        self.assertFalse(self.guard.eventFilter(self.row.slider, event))
        self.assertFalse(self.guard.eventFilter(self.area.verticalScrollBar(), event))


if __name__ == "__main__":
    unittest.main()
