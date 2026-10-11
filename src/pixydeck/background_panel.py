"""Background replacement (green screen and AI matting) and its tab.

Mixed into ``PixyGUI``; methods use the window's widgets and state via ``self``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from . import VIRTUAL_CAMERA_NAME
from .vision import Background, matting_available, vision_available
from .widgets import Card, Segmented, SliderRow


NEEDS_AI = "Needs the optional AI extra: pip install 'pixydeck[ai]'"


class BackgroundMixin:
    """Background replacement (green screen and AI matting) and its tab."""

    def build_background_tab(self) -> QWidget:
        page, layout = self.tab_page()

        screen = Card("Background")
        self.bg_mode = Segmented([("Off", "off"), ("Auto", "auto"), ("Green screen", "chroma"), ("AI", "ai")])
        self.bg_mode.selected.connect(lambda _m: self.apply_background())
        screen.body.addWidget(self.bg_mode)
        self.bg_status = QLabel("", objectName="subtle")
        self.bg_status.setWordWrap(True)
        screen.body.addWidget(self.bg_status)
        self.bg_mode.setToolTip(
            "Green screen keys the shade it detects at the picture's edges. AI cuts you out of any "
            "room (more CPU, up to 30 fps). Auto uses the green screen when one is in view, AI otherwise.")
        screen.body.addWidget(self.hint(f"Shown in the preview and in “{VIRTUAL_CAMERA_NAME}”."))
        layout.addWidget(screen)

        fill = Card("Replace with")
        self.bg_fill = Segmented([("Blur", "blur"), ("Gradient", "gradient"), ("Color", "color"), ("Image", "image")])
        self.bg_fill.selected.connect(self.background_fill_selected)
        fill.body.addWidget(self.bg_fill)
        buttons = QHBoxLayout()
        self.bg_color_button = QPushButton("Choose color…")
        self.bg_color_button.clicked.connect(self.choose_background_color)
        self.bg_image_button = QPushButton("Choose image…")
        self.bg_image_button.clicked.connect(self.choose_background_image)
        buttons.addWidget(self.bg_color_button)
        buttons.addWidget(self.bg_image_button)
        fill.body.addLayout(buttons)
        self.bg_image_label = QLabel("", objectName="subtle")
        self.bg_image_label.setWordWrap(True)
        fill.body.addWidget(self.bg_image_label)
        self.bg_blur = SliderRow("Blur strength", 1, 20, 6)
        self.bg_blur.slider.valueChanged.connect(lambda _v: self.background_timer.start())
        fill.body.addWidget(self.bg_blur)
        layout.addWidget(fill)

        tuning = Card("Green screen fine-tuning", key="chroma", collapsed=True)
        self.bg_similarity = SliderRow("Similarity", 5, 45, 20, fmt=lambda v: f"{v}%")
        self.bg_smoothness = SliderRow("Edge softness", 2, 40, 10, fmt=lambda v: f"{v}%")
        self.bg_spill = SliderRow("Green spill removal", 0, 100, 70, fmt=lambda v: f"{v}%")
        for row in (self.bg_similarity, self.bg_smoothness, self.bg_spill):
            row.slider.sliderReleased.connect(self.apply_background)
            row.slider.valueChanged.connect(lambda _v: self.background_timer.start())
            tuning.body.addWidget(row)
        self.bg_similarity.setToolTip("Raise if green remains, lower if parts of you disappear")
        self.bg_spill.setToolTip("Takes the green tint off hair and edges")
        layout.addWidget(tuning)

        self.background_timer = QTimer(self, singleShot=True, interval=120)
        self.background_timer.timeout.connect(self.apply_background)
        self.bg_color = (40, 40, 40)
        self.bg_image_path = ""
        if not vision_available():
            for widget in (self.bg_mode, self.bg_fill, self.bg_color_button, self.bg_image_button,
                           self.bg_similarity, self.bg_smoothness, self.bg_spill, self.bg_blur):
                widget.setEnabled(False)
            self.bg_status.setText(NEEDS_AI)
        layout.addStretch()
        return page

    def apply_background(self) -> None:
        if not vision_available():
            return
        mode = self.bg_mode.current() or "off"
        fill = self.bg_fill.current() or "gradient"
        background = Background(
            mode=mode, fill=fill, color=self.bg_color, image_path=self.bg_image_path,
            similarity=self.bg_similarity.value() / 100,
            smoothness=self.bg_smoothness.value() / 100,
            spill=self.bg_spill.value() / 100,
            blur=float(self.bg_blur.value()),
        )
        self.processor.set_background(background)
        for key, value in (("mode", mode), ("fill", fill), ("color", ",".join(map(str, self.bg_color))),
                           ("image", self.bg_image_path), ("similarity", self.bg_similarity.value()),
                           ("smoothness", self.bg_smoothness.value()), ("spill", self.bg_spill.value()),
                           ("blur", self.bg_blur.value())):
            self.settings.setValue(f"background/{key}", value)
        if mode == "off":
            self.view.set_processed(None)
        self.update_background_status()

    def background_fill_selected(self, fill: str) -> None:
        if fill == "image" and not self.bg_image_path:
            self.choose_background_image()
        self.apply_background()

    def choose_background_color(self) -> None:
        b, g, r = self.bg_color
        color = QColorDialog.getColor(QColor(r, g, b), self, "Background color")
        if color.isValid():
            self.bg_color = (color.blue(), color.green(), color.red())
            self.bg_fill.set_current("color")
            self.apply_background()

    def choose_background_image(self) -> None:
        start = str(Path(self.bg_image_path).parent if self.bg_image_path else Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(self, "Background image", start,
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.bg_image_path = path
            self.bg_fill.set_current("image")
            self.apply_background()
        elif not self.bg_image_path:
            self.bg_fill.set_current("gradient")

    def update_background_status(self) -> None:
        mode = self.bg_mode.current() or "off"
        name = Path(self.bg_image_path).name if self.bg_image_path else "no image chosen"
        self.bg_image_label.setText(f"Image: {name}" if self.bg_fill.current() == "image" else "")
        self.bg_blur.setVisible(self.bg_fill.current() == "blur")
        green = self.processor.key is not None
        if not vision_available():
            text = NEEDS_AI
        elif mode == "off":
            text = ""
        elif mode in ("auto", "chroma") and green:
            text = "🟢 Green screen detected – keying it"
        elif mode in ("auto", "ai") and not matting_available():
            text = "AI cutout needs onnxruntime: pip install 'pixydeck[ai]'"
        elif mode in ("auto", "ai"):
            text = "🧠 AI cutout active" + (" – no green screen in view" if mode == "auto" else "")
        else:
            text = "Waiting for a green screen in the picture…"
        if mode != "off" and not self.digital_zoom_allowed():
            text = "Only in the preview and the processed virtual camera"
        self.bg_status.setText(text)

    def on_green_screen(self, key) -> None:
        if key is None and self.bg_mode.current() == "chroma":
            self.view.set_processed(None)
        self.notify("Green screen detected" if key is not None else "Green screen no longer in view")
        self.update_background_status()

    def on_processed_preview(self) -> None:
        image = self.processor.take_preview()
        processed = self.processor.background_active or self.processor.stabilizing
        if processed and self.digital_zoom_allowed():
            self.view.set_processed(image)
        else:
            self.view.set_processed(None)