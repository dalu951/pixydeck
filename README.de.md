<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="EMEET PixyDeck Icon">

# EMEET PixyDeck

**Die Linux-Steuerzentrale für die Webcam EMEET PIXY.**<br>
Schwenken, Neigen und Zoomen, die KI der Kamera, Auto-Framing, KI-Hintergrund, Green Screen,<br>
Stabilisierung und eine virtuelle Kamera für Meet, Zoom, Teams und OBS – in einer nativen App.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
![Plattform](https://img.shields.io/badge/platform-Linux-informational)
[![Lizenz: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

[English](README.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md)

<img src="docs/media/background.gif" width="860" alt="PixyDeck wechselt zwischen ohne Effekt, KI-Unschärfe, Verlauf und Farbe">

</div>

> **Inoffizielles Community-Projekt** – nicht mit EMEET verbunden oder von EMEET unterstützt. EMEET und PIXY sind Marken ihres jeweiligen Inhabers. Alle Bilder hier zeigen eine gezeichnete Demo-Szene, dargestellt von der echten App.

## Highlights

<table>
<tr>
<td width="50%"><img src="docs/media/zoom.gif" alt="Zoomen und Ausrichten"></td>
<td width="50%"><img src="docs/media/autoframe.gif" alt="Auto-Framing folgt einer Person"></td>
</tr>
<tr>
<td><b>Flüssiges Schwenken und Zoom bis 4×</b><br>Klicken oder ziehen zum Ausrichten, Pfeile halten zum Gleiten, Mausrad zum Zoomen. Hardware-Zoom, wo die PIXY ihn kann, darüber scharfer Digitalzoom – auch in 4K.</td>
<td><b>Auto-Framing</b><br>Lokale Gesichtserkennung hält dich mittig und gut im Bild, auch in der virtuellen Kamera.</td>
</tr>
</table>

| | |
| --- | --- |
| 🎯 **KI der PIXY** | Gesichts-Tracking, Privacy-Modus, Gesten, **Klick-Fokus** mit der zweiten Linse, Geräuschunterdrückung – Änderungen per Geste werden live übernommen |
| 🪄 **Hintergrund** | KI-Unschärfe oder -Ersatz ohne Green Screen; automatischer Green-Screen-Modus, sobald einer im Bild ist |
| 🎥 **Virtuelle Kamera** | *PixyDeck Virtual Camera* bringt Zoom, Framing und Hintergrund in jede Video-App |
| 🫨 **Stabilisierung** | gleicht Wackeln von Monitor oder Schreibtisch aus |
| 🔒 **Privacy-Timer** | Linse dreht nach Leerlauf weg und wacht auf, sobald Zoom, Teams, Meet oder OBS die Kamera öffnen |
| 🎛️ **Bildsteuerung** | Farbe, Schärfe, Gamma, Verstärkung, Weißabgleich, Belichtung, Fokus, Flimmerschutz, Positionen |
| 🛠️ **Geführte Einrichtung** | prüft Rechte, Kernelmodul und virtuelle Kamera und repariert sie mit einem Klick |

## Installation

| System | Befehl |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | `pixydeck_<version>_amd64.deb` aus den [Releases](https://github.com/dalu951/pixydeck/releases) laden, dann `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | `yay -S pixydeck` (AUR) |
| **Jede Distribution** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

**EMEET PixyDeck** im Anwendungsmenü starten. Fehlt etwas, zeigt es der Dialog **⚙ Setup** und repariert es nach einer Passwortabfrage. Details: **[Installationsanleitung](docs/de/installation.md)**.

## Dokumentation

[Installation](docs/de/installation.md) · [Benutzerhandbuch](docs/de/benutzerhandbuch.md) · [Fehlerbehebung](docs/de/fehlerbehebung.md) · [FAQ](docs/de/faq.md) · [Runbook (EN)](docs/RUNBOOK.md) · [Mitwirken (EN)](docs/CONTRIBUTING.md)

## Datenschutz

Alle KI-Funktionen laufen **lokal**, kein Bild verlässt den Computer. Systemänderungen laufen nur über einen kleinen Helfer mit festen Aktionen hinter dem Polkit-Passwortdialog.

## Herkunft und Lizenz

PixyDeck entstand als Fork von [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) von Rolf Obermaier – siehe [CREDITS.md](CREDITS.md). Lizenz: **GNU GPL v3 only** ([LICENSE](LICENSE)).
