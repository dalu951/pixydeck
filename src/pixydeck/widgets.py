"""Custom widgets and the application theme."""

from __future__ import annotations

from PySide6.QtCore import (
    Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
    QTimer, Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from .vision import Crop

ACCENT = "#5b8cff"
ACCENT_SOFT = "rgba(91, 140, 255, 0.18)"

THEME = f"""
* {{ font-size: 10pt; }}
QMainWindow, QDialog, QWidget#root {{ background: #0f1115; color: #e6e8ee; }}
QWidget {{ color: #e6e8ee; }}
QLabel#title {{ font-size: 15pt; font-weight: 700; letter-spacing: 0.5px; }}
QLabel#subtle {{ color: #8b93a7; }}
QLabel#sectionTitle {{ color: #8b93a7; font-size: 8.5pt; font-weight: 700;
    letter-spacing: 1px; padding-top: 4px; }}
QFrame#card {{ background: #171a21; border: 1px solid #232733; border-radius: 14px; }}
QFrame#previewCard {{ background: #08090b; border: 1px solid #232733; border-radius: 14px; }}
QLabel#pill {{ background: #1f2430; border-radius: 10px; padding: 3px 10px; color: #c4cad8; }}
QLabel#pill[state="on"] {{ background: {ACCENT_SOFT}; color: #a9c2ff; }}
QLabel#pill[state="warn"] {{ background: rgba(255, 93, 108, 0.18); color: #ff9aa4; }}
QLabel#pill[state="ok"] {{ background: rgba(61, 220, 151, 0.16); color: #8ff0c4; }}
QPushButton {{ background: #222734; border: 1px solid #2c3242; border-radius: 9px;
    padding: 7px 12px; }}
QPushButton:hover {{ background: #2a3040; border-color: #3a4256; }}
QPushButton:pressed {{ background: #1b1f29; }}
QPushButton:disabled {{ color: #5c6273; background: #191c24; border-color: #222631; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #6d99ff; }}
QPushButton#primary:disabled {{ background: #2a3350; border-color: #2a3350; color: #7d88a8; }}
QPushButton#danger {{ background: rgba(255, 93, 108, 0.16); border-color: rgba(255, 93, 108, 0.4); color: #ffb3ba; }}
QPushButton#danger:disabled {{ background: #191c24; border-color: #222631; color: #5c6273; }}
QLabel:disabled {{ color: #5c6273; }}
QPushButton[segment="true"] {{ border-radius: 0; margin: 0; padding: 6px 8px; }}
QPushButton[segment="true"]:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton[first="true"] {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
QPushButton[last="true"] {{ border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}
QPushButton#preset {{ min-width: 44px; min-height: 34px; font-weight: 600; }}
QPushButton#preset[filled="true"] {{ border-color: {ACCENT}; }}
QPushButton#preset[startup="true"] {{ background: {ACCENT_SOFT}; }}
QComboBox, QSpinBox {{ background: #222734; border: 1px solid #2c3242; border-radius: 9px;
    padding: 5px 10px; }}
QComboBox:disabled, QSpinBox:disabled {{ color: #5c6273; background: #191c24; border-color: #222631; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #1c2029; border: 1px solid #2c3242;
    selection-background-color: {ACCENT}; outline: none; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a2f3d; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #f2f4f8; width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a3f4c; }}
QSlider::handle:horizontal:disabled {{ background: #5c6273; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: #8b93a7; padding: 8px 7px; margin-right: 1px;
    border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: #e6e8ee; border-bottom-color: {ACCENT}; }}
QTabBar::tab:hover {{ color: #c4cad8; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #2c3242; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: #0f1115; color: #8b93a7; }}
QToolTip {{ background: #1c2029; color: #e6e8ee; border: 1px solid #2c3242; padding: 4px; }}
QMenu {{ background: #1c2029; border: 1px solid #2c3242; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
"""


def set_state(label: QLabel, state: str) -> None:
    """Restyle a pill label after changing its ``state`` property."""
    label.setProperty("state", state)
    label.style().unpolish(label)
    label.style().polish(label)


def section_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionTitle")
    return label


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 10, 14, 14)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(section_title(title))


class ToggleSwitch(QAbstractButton):
    """Animated on/off switch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(42, 24)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_silently(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._anim.stop()
        self._offset = 1.0 if checked else 0.0
        self.update()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on, t = QColor("#2c3242"), QColor(ACCENT), self._offset
        track = QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            track = QColor("#23262f")
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        d = rect.height() - 6
        x = rect.left() + 3 + (rect.width() - d - 6) * t
        p.setBrush(QColor("#f2f4f8") if self.isEnabled() else QColor("#5c6273"))
        p.drawEllipse(QRectF(x, rect.top() + 3, d, d))


class SettingRow(QWidget):
    """Label (+ optional hint) on the left, control on the right."""

    def __init__(self, text: str, control: QWidget, hint: str | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        self.label = QLabel(text)
        labels.addWidget(self.label)
        self.hint = None
        if hint:
            self.hint = QLabel(hint)
            self.hint.setObjectName("subtle")
            self.hint.setWordWrap(True)
            labels.addWidget(self.hint)
        layout.addLayout(labels, 1)
        layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)


class SliderRow(QWidget):
    """Name, live value and slider; emits ``value_changed`` while dragging."""

    value_changed = Signal(int)

    def __init__(self, text: str, minimum: int, maximum: int, value: int,
                 fmt=str, parent=None) -> None:
        super().__init__(parent)
        self._fmt = fmt
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        top = QHBoxLayout()
        self.label = QLabel(text)
        self.value_label = QLabel()
        self.value_label.setObjectName("subtle")
        top.addWidget(self.label)
        top.addStretch()
        top.addWidget(self.value_label)
        layout.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.slider.valueChanged.connect(self._changed)
        layout.addWidget(self.slider)
        self._update_label(value)

    def _changed(self, value: int) -> None:
        self._update_label(value)
        self.value_changed.emit(value)

    def _update_label(self, value: int) -> None:
        self.value_label.setText(self._fmt(value))

    def set_value_silently(self, value: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self._update_label(self.slider.value())

    def value(self) -> int:
        return self.slider.value()

    def set_range(self, minimum: int, maximum: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(minimum, maximum)
        self.slider.blockSignals(False)
        self._update_label(self.slider.value())


class Segmented(QWidget):
    """Row of mutually exclusive buttons; emits the data of the chosen one."""

    selected = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for index, (label, data) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setProperty("first", index == 0)
            button.setProperty("last", index == len(options) - 1)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _=False, d=data: self.selected.emit(d))
            self.group.addButton(button)
            self.buttons[data] = button
            layout.addWidget(button)

    def set_current(self, data: str) -> None:
        button = self.buttons.get(data)
        if button is not None:
            button.setChecked(True)

    def current(self) -> str | None:
        for data, button in self.buttons.items():
            if button.isChecked():
                return data
        return None


class PtzPad(QWidget):
    """Pan/tilt field: shows where the camera points; click or drag to aim."""

    target_changed = Signal(int, int)  # pan, tilt in degrees

    def __init__(self, pan_range=(-150, 150), tilt_range=(-52, 90), parent=None) -> None:
        super().__init__(parent)
        self.pan_range = pan_range
        self.tilt_range = tilt_range
        self.position = (0, 0)
        self.target: tuple[int, int] | None = None
        self.dragging = False
        self.setMinimumHeight(150)
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setToolTip("Click or drag to aim the camera")

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(300, 170)

    def set_position(self, pan: int, tilt: int) -> None:
        self.position = (pan, tilt)
        if self.target and not self.dragging:
            if abs(self.target[0] - pan) <= 1 and abs(self.target[1] - tilt) <= 1:
                self.target = None
        self.update()

    def _field(self) -> QRectF:
        return QRectF(self.rect()).adjusted(6, 6, -6, -6)

    def _to_point(self, pan: float, tilt: float) -> QPointF:
        f = self._field()
        x = f.left() + (pan - self.pan_range[0]) / (self.pan_range[1] - self.pan_range[0]) * f.width()
        y = f.bottom() - (tilt - self.tilt_range[0]) / (self.tilt_range[1] - self.tilt_range[0]) * f.height()
        return QPointF(x, y)

    def _from_point(self, point: QPointF) -> tuple[int, int]:
        f = self._field()
        nx = min(max((point.x() - f.left()) / f.width(), 0.0), 1.0)
        ny = min(max((f.bottom() - point.y()) / f.height(), 0.0), 1.0)
        pan = self.pan_range[0] + nx * (self.pan_range[1] - self.pan_range[0])
        tilt = self.tilt_range[0] + ny * (self.tilt_range[1] - self.tilt_range[0])
        return round(pan), round(tilt)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self._aim(event.position())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.dragging:
            self._aim(event.position())

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802 - Qt API
        self.dragging = False

    def _aim(self, point: QPointF) -> None:
        self.target = self._from_point(point)
        self.target_changed.emit(*self.target)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = self._field()
        p.setPen(QPen(QColor("#2a2f3d"), 1))
        p.setBrush(QColor("#12151b"))
        p.drawRoundedRect(f, 12, 12)
        p.setPen(QPen(QColor("#1f2430"), 1))
        for pan in range(-120, 121, 30):
            p.drawLine(self._to_point(pan, self.tilt_range[0]), self._to_point(pan, self.tilt_range[1]))
        for tilt in range(-90, 91, 30):
            if not self.tilt_range[0] < tilt < self.tilt_range[1]:
                continue
            p.drawLine(self._to_point(self.pan_range[0], tilt), self._to_point(self.pan_range[1], tilt))
        p.setPen(QPen(QColor("#343a4a"), 1, Qt.DashLine))
        p.drawLine(self._to_point(0, self.tilt_range[0]), self._to_point(0, self.tilt_range[1]))
        p.drawLine(self._to_point(self.pan_range[0], 0), self._to_point(self.pan_range[1], 0))

        if self.target is not None:
            p.setPen(QPen(QColor(ACCENT), 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(self._to_point(*self.target), 9, 9)

        c = self._to_point(*self.position)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(91, 140, 255, 60))
        p.drawEllipse(c, 14, 14)
        p.setBrush(QColor(ACCENT))
        p.drawEllipse(c, 6, 6)

        p.setPen(QColor("#8b93a7"))
        pan, tilt = self.position
        text_rect = f.adjusted(10, 6, -10, -6)
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, f"Pan {pan:+d}°")
        p.drawText(text_rect, Qt.AlignRight | Qt.AlignTop, f"Tilt {tilt:+d}°")


class PreviewView(QGraphicsView):
    """GPU-rendered live preview with digital zoom, drag and face overlay.

    Digital zoom is a view transform over the full-resolution video item,
    so at 4K a 2x zoom still shows native pixels.
    """

    wheel_zoom = Signal(int)               # +1 / -1 steps
    clicked = Signal(float, float)         # normalized position, no drag
    drag_by = Signal(float, float)         # normalized delta of the frame
    double_clicked = Signal(float, float)  # normalized position in the frame

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(QColor("#08090b")))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.video = QGraphicsVideoItem()
        self.video.setAspectRatioMode(Qt.IgnoreAspectRatio)
        self.video.setSize(QSize(1920, 1080))
        self.scene().addItem(self.video)
        self.video.nativeSizeChanged.connect(self._native_size_changed)
        # Keyed frames (background replacement) are drawn over the live video.
        self.processed = QGraphicsPixmapItem()
        self.processed.setTransformationMode(Qt.SmoothTransformation)
        self.processed.setZValue(1)
        self.processed.hide()
        self.scene().addItem(self.processed)

        self.crop = Crop()
        self._face_items: list[QGraphicsRectItem] = []
        self.show_faces = False
        self._drag_from = None
        self._press_at = None
        self.setCursor(Qt.OpenHandCursor)

        pen = QPen(QColor("#ffd166"))
        pen.setCosmetic(True)
        pen.setWidth(2)
        self.focus_marker = QGraphicsRectItem()
        self.focus_marker.setPen(pen)
        self.focus_marker.setZValue(2)
        self.focus_marker.hide()
        self.scene().addItem(self.focus_marker)
        self._marker_timer = QTimer(self)
        self._marker_timer.setSingleShot(True)
        self._marker_timer.timeout.connect(self.focus_marker.hide)

        self.hud_left = self._hud_label()
        self.hud_right = self._hud_label()
        self.hud_center = self._hud_label()
        self.hud_center.setStyleSheet(self.hud_center.styleSheet() + "font-size: 14pt; padding: 8px 18px;")
        self.hud_center.hide()
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.hud_center.hide)

    def _hud_label(self) -> QLabel:
        label = QLabel(self.viewport())
        label.setStyleSheet(
            "background: rgba(8, 9, 11, 0.62); color: #e6e8ee; border-radius: 9px;"
            "padding: 4px 10px; font-weight: 600;"
        )
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        return label

    def flash(self, text: str) -> None:
        """Short centred overlay, e.g. the zoom factor while scrolling."""
        self.hud_center.setText(text)
        self.hud_center.adjustSize()
        self.hud_center.show()
        self._place_hud()
        self._flash_timer.start(900)

    def set_hud(self, left: str, right: str) -> None:
        for label, text in ((self.hud_left, left), (self.hud_right, right)):
            label.setText(text)
            label.setVisible(bool(text))
            label.adjustSize()
        self._place_hud()

    def _place_hud(self) -> None:
        w, h = self.viewport().width(), self.viewport().height()
        self.hud_left.move(12, 12)
        self.hud_right.move(w - self.hud_right.width() - 12, 12)
        self.hud_center.move((w - self.hud_center.width()) // 2, (h - self.hud_center.height()) // 2)

    def _native_size_changed(self, size) -> None:
        if size.isValid() and not size.isEmpty():
            self.video.setSize(size)
            self.apply_crop()

    def set_processed(self, image) -> None:
        """Show a processed full frame instead of the raw video, or None to stop."""
        if image is None or image.isNull():
            self.processed.hide()
            return
        w, _h = self.frame_size()
        self.processed.setPixmap(QPixmap.fromImage(image))
        self.processed.setScale(w / image.width())
        self.processed.show()

    def frame_size(self) -> tuple[float, float]:
        size = self.video.size()
        return max(size.width(), 1.0), max(size.height(), 1.0)

    def _scale(self) -> float:
        w, h = self.frame_size()
        return min(self.viewport().width() / w, self.viewport().height() / h) * self.crop.zoom

    def set_crop(self, crop: Crop) -> None:
        self.crop = crop.clamped()
        self.apply_crop()

    def apply_crop(self) -> None:
        w, h = self.frame_size()
        vw, vh = self.viewport().width(), self.viewport().height()
        scale = self._scale()
        # Scene rect == visible area in scene coordinates, so the view
        # never scrolls on its own; the crop centre lands mid-viewport.
        sw, sh = vw / scale, vh / scale
        self.setSceneRect(QRectF(self.crop.cx * w - sw / 2, self.crop.cy * h - sh / 2, sw, sh))
        self.setTransform(QTransform.fromScale(scale, scale))
        self.centerOn(self.crop.cx * w, self.crop.cy * h)

    def set_faces(self, faces: list[tuple[float, float, float, float]]) -> None:
        w, h = self.frame_size()
        while len(self._face_items) < len(faces):
            pen = QPen(QColor(ACCENT))
            pen.setCosmetic(True)
            pen.setWidth(2)
            item = QGraphicsRectItem()
            item.setPen(pen)
            item.setZValue(2)
            self.scene().addItem(item)
            self._face_items.append(item)
        for index, item in enumerate(self._face_items):
            if index < len(faces) and self.show_faces:
                x, y, fw, fh = faces[index]
                frame = QRectF(0, 0, w, h)
                item.setRect(QRectF(x * w, y * h, fw * w, fh * h).intersected(frame))
                item.show()
            else:
                item.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.apply_crop()
        self._place_hud()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - Qt API
        # QGraphicsView scrolls viewport children too; keep the HUD pinned.
        super().scrollContentsBy(dx, dy)
        self._place_hud()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        steps = event.angleDelta().y() // 120
        if steps:
            self.wheel_zoom.emit(steps)

    def show_focus_point(self, nx: float, ny: float) -> None:
        w, h = self.frame_size()
        size = min(w, h) * 0.08
        self.focus_marker.setRect(QRectF(nx * w - size / 2, ny * h - size / 2, size, size))
        self.focus_marker.show()
        self._marker_timer.start(1500)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._drag_from = event.position()
            self._press_at = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag_from is None:
            return
        delta = event.position() - self._drag_from
        self._drag_from = event.position()
        w, h = self.frame_size()
        scale = self._scale()
        self.drag_by.emit(-delta.x() / scale / w, -delta.y() / scale / h)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._press_at is not None:
            moved = event.position() - self._press_at
            if abs(moved.x()) + abs(moved.y()) < 5:
                point = self.mapToScene(event.position().toPoint())
                w, h = self.frame_size()
                nx, ny = point.x() / w, point.y() / h
                if 0 <= nx <= 1 and 0 <= ny <= 1:
                    self.clicked.emit(nx, ny)
        self._drag_from = None
        self._press_at = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        point = self.mapToScene(event.position().toPoint())
        w, h = self.frame_size()
        self.double_clicked.emit(point.x() / w, point.y() / h)


class InfoPanel(QWidget):
    """Shown instead of the video when another program owns the stream."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet("font-size: 40pt;")
        self.heading = QLabel()
        self.heading.setAlignment(Qt.AlignCenter)
        self.heading.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self.text = QLabel()
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setObjectName("subtle")
        self.text.setMaximumWidth(520)
        layout.addWidget(self.icon)
        layout.addWidget(self.heading)
        layout.addWidget(self.text, 0, Qt.AlignHCenter)

    def show_message(self, icon: str, heading: str, text: str) -> None:
        self.icon.setText(icon)
        self.heading.setText(heading)
        self.text.setText(text)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        p.fillPath(path, QColor("#0b0d11"))
