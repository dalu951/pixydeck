# Fehlerbehebung

[← README](../../README.de.md) · [English](../en/troubleshooting.md) · **Deutsch**

Erste Anlaufstelle ist **⚙ Setup** in PixyDeck: Der Dialog prüft Berechtigungen, Kernelmodul und virtuelle Kamera und behebt die meisten Probleme mit einem Klick.

| Problem | Lösung |
| --- | --- |
| **Die Meeting-App sieht die Kamera nicht**, während PixyDeck eine Vorschau zeigt | In der App **EMEET PIXY (PixyDeck)** wählen – oder in PixyDeck **Release camera** klicken und die echte EMEET PIXY auswählen. Ein Webcam-Stream kann immer nur von einem Programm gelesen werden. |
| **„EMEET PIXY (PixyDeck)“ fehlt** | ⚙ Setup → *Virtuelle Kamera* → **Fix**. Meldet der Dialog, dass das Modul `v4l2loopback` fehlt: `v4l2loopback-dkms` (und Kernel-Header) installieren. Nach einem Kernel-Update zuerst neu starten. |
| **Apps zeigen noch „PixyDeck Virtual Camera“** | Das ist dieselbe virtuelle Kamera unter ihrem Namen vor 0.5.0. Sie wird beim nächsten Anlegen umbenannt – nach einem Neustart oder mit ⚙ Setup → *Virtuelle Kamera* → **Fix**, solange keine App sie nutzt. Danach in den Apps neu auswählen. |
| **Tracking-, Privacy- oder Fokus-Buttons reagieren nicht** / „Permission denied“ bei `/dev/hidraw*` | ⚙ Setup → *Kamerasteuerung* → **Fix**, oder die PIXY einmal aus- und wieder einstecken. |
| **Vorschau eingefroren** | PixyDeck startet einen hängenden Stream nach drei Sekunden selbst neu; *Release camera* → *Resume preview* hilft ebenfalls. |
| **Zoom-Regler ausgegraut** | Die Kamera ist an eine andere App freigegeben und deren Videomodus ignoriert den Hardware-Zoom (über 1080p oder 1080p mit 60 fps). Für Digitalzoom die verarbeitete virtuelle Kamera nutzen. |
| **KI-Optionen ausgegraut** | OpenCV/ONNX Runtime fehlen. Die Pakete installieren sie mit; bei `install.sh` im Quellordner `~/.local/share/pixydeck/venv/bin/pip install 'pixydeck[ai]'` ausführen. |
| **Niedrige Bildrate mit KI-Hintergrund** | Mit `--gpu` läuft ONNX-Matting nach Möglichkeit über CUDA. Dauert die Inferenz trotzdem länger als ein Bild, hält PixyDeck die Ausgaberate mit der neuesten fertigen Maske; im HUD steht *AI BACKGROUND EASED* und Kanten können schnellen Bewegungen leicht folgen. Andere GPU-intensive Programme schließen, 1080p oder einen Green Screen nutzen. |
| **`--gpu` nutzt trotzdem die CPU** | Erst `nvidia-smi`, dann `~/.local/share/pixydeck/venv/bin/pixydeck-gpu-benchmark` ausführen. Das Protokoll nennt die CUDA-GPU oder den Grund für den Rückfall. `PIXYDECK_DISABLE_CUDA=1` erzwingt den CPU-Pfad. |
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
