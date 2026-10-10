# Fehlerbehebung

[← README](../../README.de.md) · [English](../en/troubleshooting.md) · **Deutsch**

Erste Anlaufstelle ist **⚙ Setup** in PixyDeck: Der Dialog prüft Berechtigungen, Kernelmodul und virtuelle Kamera und behebt die meisten Probleme mit einem Klick.

| Problem | Lösung |
| --- | --- |
| **Die Meeting-App sieht die Kamera nicht**, während PixyDeck eine Vorschau zeigt | In der App **PixyDeck Virtual Camera** wählen – oder in PixyDeck **Release camera** klicken und die echte EMEET PIXY auswählen. Ein Webcam-Stream kann immer nur von einem Programm gelesen werden. |
| **„PixyDeck Virtual Camera“ fehlt** | ⚙ Setup → *Virtuelle Kamera* → **Fix**. Meldet der Dialog, dass das Modul `v4l2loopback` fehlt: `v4l2loopback-dkms` (und Kernel-Header) installieren. Nach einem Kernel-Update zuerst neu starten. |
| **Tracking-, Privacy- oder Fokus-Buttons reagieren nicht** / „Permission denied“ bei `/dev/hidraw*` | ⚙ Setup → *Kamerasteuerung* → **Fix**, oder die PIXY einmal aus- und wieder einstecken. |
| **Vorschau eingefroren** | PixyDeck startet einen hängenden Stream nach drei Sekunden selbst neu; *Release camera* → *Resume preview* hilft ebenfalls. |
| **Zoom-Regler ausgegraut** | Die Kamera ist an eine andere App freigegeben und deren Videomodus ignoriert den Hardware-Zoom (über 1080p oder 1080p mit 60 fps). Für Digitalzoom die verarbeitete virtuelle Kamera nutzen. |
| **KI-Optionen ausgegraut** | OpenCV/ONNX Runtime fehlen. Die Pakete installieren sie mit; bei `install.sh` im Quellordner `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'` ausführen. |
| **Niedrige Bildrate mit KI-Hintergrund** | Die KI-Freistellung braucht etwa 30 ms pro Bild auf der CPU. 1080p statt 4K nutzen oder einen Green Screen. |
| **Kamera kippt in ihren Sockel** | Positionen unter −52° sind seit 0.3.0 gesperrt; die Position neu speichern. |
| **Warnung zu `libvdpau_nvidia.so`** | Qt sucht nach optionalen Hardware-Decodern; harmlos, wenn die Vorschau läuft. |

## Informationen für einen Fehlerbericht

```bash
pixydeck-cli status
systemctl status pixydeck-virtual-camera.service
journalctl -u pixydeck-virtual-camera.service -b
v4l2-ctl --list-devices
```

PixyDeck schreibt ein Protokoll nach `~/.local/state/pixydeck/pixydeck.log` (der Pfad erscheint, wenn man mit der Maus über die Versionsnummer in der Kopfzeile fährt); `PIXYDECK_DEBUG=1` liefert mehr Details. Beim [Issue](https://github.com/dalu951/pixydeck/issues) bitte Protokoll, die Ausgabe oben, Distribution und Kernel-Version anhängen. Weitere Details für den Betrieb stehen im [Runbook](../RUNBOOK.md) (Englisch).
