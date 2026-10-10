"""Pan/tilt/zoom presets and the startup position.

Mixed into ``PixyGUI``; methods use the window's widgets and state via ``self``.
"""

from __future__ import annotations


from PySide6.QtWidgets import QMenu


class PresetsMixin:
    """Pan/tilt/zoom presets and the startup position."""

    def preset(self, slot: int) -> tuple[int, int, int] | None:
        value = self.settings.value(f"presets/{slot}")
        if not value:
            return None
        try:
            pan, tilt, zoom = (int(v) for v in str(value).split(","))
        except ValueError:
            return None
        return pan, tilt, zoom

    def startup_position_changed(self) -> None:
        self.settings.setValue("presets/startup", self.startup_position.currentData())
        self.refresh_preset_buttons()

    def refresh_preset_buttons(self) -> None:
        startup = str(self.startup_position.currentData())
        for slot, button in enumerate(self.preset_buttons, start=1):
            preset = self.preset(slot)
            is_startup = startup == str(slot)
            button.setProperty("filled", preset is not None)
            button.setProperty("startup", is_startup)
            button.setText(f"★ {slot}" if is_startup else str(slot))
            if preset is None:
                button.setToolTip(f"Preset {slot}: empty – click to store the current position")
            else:
                pan, tilt, zoom = preset
                extra = " · startup position" if is_startup else ""
                button.setToolTip(f"Preset {slot}: pan {pan:+d}°, tilt {tilt:+d}°, zoom {zoom / 100:.1f}×{extra}")
            button.style().unpolish(button)
            button.style().polish(button)

    def preset_clicked(self, slot: int) -> None:
        if self.preset(slot) is None:
            self.store_preset(slot)
        else:
            self.recall_preset(slot)

    def store_preset(self, slot: int) -> None:
        pan, tilt = self.position
        self.settings.setValue(f"presets/{slot}", f"{pan},{tilt},{self.zoom_value}")
        self.refresh_preset_buttons()
        self.notify(f"Preset {slot} stored (pan {pan:+d}°, tilt {tilt:+d}°)")

    def recall_preset(self, slot: int) -> None:
        preset = self.preset(slot)
        if preset is None:
            self.notify(f"Preset {slot} is empty")
            return
        pan, tilt, zoom = preset
        self.aim_at(pan, tilt)
        if not self.autoframe.isChecked():
            self.manual_center = (0.5, 0.5)
            self.set_zoom(zoom)
        self.notify(f"Preset {slot}")

    def preset_menu(self, slot: int) -> None:
        filled = self.preset(slot) is not None
        menu = QMenu(self)
        menu.addAction("Go to preset", lambda: self.recall_preset(slot)).setEnabled(filled)
        menu.addAction("Store current position here", lambda: self.store_preset(slot))
        menu.addAction(
            "Use as startup position",
            lambda: self.startup_position.setCurrentIndex(self.startup_position.findData(str(slot))),
        ).setEnabled(filled)

        def clear() -> None:
            self.settings.remove(f"presets/{slot}")
            if self.startup_position.currentData() == str(slot):
                self.startup_position.setCurrentIndex(0)
            self.refresh_preset_buttons()

        menu.addAction("Clear", clear).setEnabled(filled)
        menu.exec(self.cursor().pos())