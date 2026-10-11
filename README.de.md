<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="EMEET PixyDeck Icon">

# EMEET PixyDeck

**Die Linux-Steuerzentrale für die Webcam EMEET PIXY.**<br>
Schwenken, Neigen und Zoomen, das Tracking der Kamera, Auto-Framing, KI-Hintergrund, Green Screen,<br>
Stabilisierung, Anruf-Erkennung und eine virtuelle Kamera für Meet, Zoom, Teams, WhatsApp und OBS – in einer nativen App.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
![Plattform](https://img.shields.io/badge/platform-Linux-informational)
[![Lizenz: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

[English](README.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md)

<img src="docs/media/background.gif" width="860" alt="PixyDeck wechselt zwischen ohne Effekt, KI-Unschärfe, Verlauf und Farbe">

</div>

> **Inoffizielles Community-Projekt** – nicht mit EMEET verbunden oder von EMEET unterstützt. EMEET und PIXY sind Marken ihres jeweiligen Inhabers. Alle Bilder hier zeigen eine gezeichnete Demo-Szene, dargestellt von der echten App.

## In 30 Sekunden

1. **Installieren** – das Paket für dein System ([unten](#installation)), danach den Rechner einmal neu starten.
2. **EMEET PixyDeck öffnen** – aus dem Anwendungsmenü. Fehlt etwas, repariert es der Einrichtungsdialog nach einer Passwortabfrage.
3. **Telefonieren** – in WhatsApp, Meet, Zoom oder Teams. Sie nehmen *EMEET PIXY (PixyDeck)* von selbst, mit Zoom, Hintergrund und Stabilisierung.

Das war's. Alles Weitere ist optional.

## Was PixyDeck kann

<table>
<tr>
<td width="33%"><img src="docs/media/zoom.gif" alt="Ausrichten und Zoomen"></td>
<td width="33%"><img src="docs/media/autoframe.gif" alt="Auto-Framing folgt einer Person"></td>
<td width="33%"><img src="docs/media/stabilize.gif" alt="Wackelnde Kamera ohne und mit Steady picture"></td>
</tr>
<tr>
<td><b>Ausrichten und Zoomen bis 4×</b><br>Klicken, ziehen oder Pfeile gedrückt halten; Mausrad zoomt – Hardware-Zoom, wo die PIXY ihn kann, darüber scharfer Digitalzoom.</td>
<td><b>Auto-Framing</b><br>Lokale Gesichtserkennung hält dich mittig und gut im Bild, auch in der virtuellen Kamera.</td>
<td><b>Ruhiges Bild</b><br>Entfernt das Wackeln von Monitor oder Tisch – und hält dich nicht für Wackeln, wenn du dich bewegst.</td>
</tr>
</table>

**Kamera steuern**

| | |
| --- | --- |
| 🎯 **Tracking** | Die PIXY folgt dir selbst; wähle *Auto*, *Gesicht* oder *Oberkörper*. **Find me** neigt die Kamera zurück zu deinem Platz, wenn das Tracking dich beim Hinsetzen verliert |
| ⚡ **Geschwindigkeit** | Getrennt fürs Schwenken und Neigen – langsam für ruhige Bewegungen im Stream, schnell, damit sie mit dir mitkommt |
| 📍 **Positionen** | Vier Positionen auf den Tasten 1–4, eine Startposition und eine Einschaltposition, die in der Kamera selbst gespeichert wird |
| 🔍 **Fokus** | Mitte, Gesicht oder **irgendetwas im Bild anklicken**, damit die zweite Linse darauf scharf stellt |

**Besser aussehen**

| | |
| --- | --- |
| 🪄 **Hintergrund** | KI-Unschärfe oder -Ersatz ohne Green Screen; automatisches Freistellen, sobald ein Green Screen im Bild ist |
| 🫨 **Stabilisierung** | Optical-Flow-Stabilisierung mit RANSAC – Wackeln raus, du und gewollte Kamerabewegungen bleiben |
| 🎛️ **Bild** | Helligkeit, Farbe, Schärfe, Gamma, Verstärkung; Weißabgleich, Belichtung und Fokus automatisch, von Hand oder gesperrt; Flimmerschutz |

**In Anrufen**

| | |
| --- | --- |
| 🎥 **Virtuelle Kamera** | *EMEET PIXY (PixyDeck)* bringt jeden Effekt in jede App, auch in mehrere gleichzeitig. Sie steht in jeder Kameraliste an erster Stelle, sodass Apps sie ohne Nachfrage nehmen, und zeigt einen Wartebildschirm statt zu verschwinden, solange PixyDeck kein Bild hat |
| 📞 **Anruf-Erkennung** | Öffnet eine App die Kamera, geht das Tracking an; endet der Anruf, dreht die Linse weg. Auf Wunsch wird für den Anruf das PIXY-Mikrofon genutzt und danach zurückgeschaltet |
| 🎙️ **Mikrofon** | Geräuschunterdrückung, Live- oder Original-Modus der PIXY |

**Privatsphäre und Einrichtung**

| | |
| --- | --- |
| 🔒 **Privatsphäre** | Der Privacy-Modus dreht die Linse weg; der Leerlauf-Timer macht das automatisch und wacht auf, sobald eine App die Kamera braucht; das Mikrofon kann dabei stummgeschaltet werden |
| 🛠️ **Geführte Einrichtung** | Prüft Berechtigungen, Kernelmodul und virtuelle Kamera und behebt Probleme mit einem Klick |
| ⌨️ **Kommandozeile** | `pixydeck-cli` für Skripte und Tastenkürzel – Schwenken, Neigen, Zoom, Tracking, Geschwindigkeit, Sperren, Status |

## GUI-Tour

<img src="docs/media/tour.png" width="860" alt="PixyDeck-Hauptfenster mit nummerierten Markierungen">

| | |
| --- | --- |
| **①** Status | Tracking-Modus, virtuelle Kamera und die App, die gerade die Kamera nutzt (*📞 Call* während eines Anrufs) |
| **②** Setup | Wird zu **⚠ Setup**, wenn etwas repariert werden muss |
| **③** Vorschau | Ziehen zum Ausrichten, Doppelklick zentriert eine Stelle, Mausrad zoomt; bei *Click point*-Fokus klicken zum Scharfstellen |
| **④** Werkzeugleiste | Auflösung, Zoom, Schnappschuss und *Release camera*, um die echte Kamera an eine andere App abzugeben |
| **⑤** Tabs | Nach Aufgaben sortiert – siehe unten |
| **⑥** Karten | Einstellungen; selten gebrauchte sind eingeklappt (▸) – Titel anklicken zum Öffnen |

| Tab | Wofür |
| --- | --- |
| **Camera** | Ausrichten, Schwenk-/Neigegeschwindigkeit, Positionen, Start- und Einschaltposition |
| **Tracking** | Das Tracking der Kamera und worauf es achtet, *Find me*, Gesten, Fokus, Auto-Framing |
| **Image** | Bildregler, Stabilisierung; eingeklappt: Automatik-Modi und Sperren, Ausrichtung und Flimmerschutz |
| **Effects** | Hintergrund ersetzen; eingeklappt: Green-Screen-Feineinstellung |
| **Calls** | Anruf-Erkennung, Privacy-Timer, Mikrofon |
| **Output** | Virtuelle Kamera, *Start with PixyDeck* |

Jede Einstellung erklärt, Tab für Tab: **[GUI-Tour](docs/de/gui-tour.md)**.

<details>
<summary><b>Alle Screenshots</b></summary>

| Camera | Tracking | Image |
| --- | --- | --- |
| <img src="docs/media/camera.png" alt="Tab Camera"> | <img src="docs/media/ai.png" alt="Tab Tracking"> | <img src="docs/media/image.png" alt="Tab Image"> |
| **Effects** | **Calls** | **Output** |
| <img src="docs/media/background.png" alt="Tab Effects"> | <img src="docs/media/calls.png" alt="Tab Calls"> | <img src="docs/media/output.png" alt="Tab Output"> |
| **Setup** | | |
| <img src="docs/media/setup.png" alt="Einrichtungsdialog"> | | |

</details>

## Welche Kamera wähle ich?

| In der App wählen | Ergebnis |
| --- | --- |
| **EMEET PIXY (PixyDeck)** – empfohlen | Das Bild von PixyDeck mit allen Effekten; mehrere Apps können es gleichzeitig nutzen |
| **EMEET PIXY** | Die rohe Kamera – nur solange PixyDeck geschlossen ist oder du *Release camera* geklickt hast, denn eine Webcam bedient immer nur ein Programm |

Die meisten Apps nehmen automatisch die erste Kamera, und das ist *EMEET PIXY (PixyDeck)*. Getestet mit Google Meet in Firefox und WhatsApp ([Whatsie](https://flathub.org/apps/com.ktechpit.whatsie)); Erfahrungen mit anderen Apps sind willkommen.

## Installation

| System | Befehl |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | `pixydeck_<version>_amd64.deb` aus den [Releases](https://github.com/dalu951/pixydeck/releases) laden, dann `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | `PKGBUILD` und `pixydeck.install` aus dem [neuesten Release](https://github.com/dalu951/pixydeck/releases/latest) laden, dann `makepkg -si` (AUR-Paket folgt) |
| **Jede Distribution** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Danach einmal neu starten, damit die virtuelle Kamera vor der echten angelegt wird. **EMEET PixyDeck** aus dem Anwendungsmenü starten; fehlt etwas – Kamerarechte, das Modul `v4l2loopback` oder die virtuelle Kamera –, zeigt der Dialog **⚙ Setup** das an und behebt es nach einer Passwortabfrage.

Details, Voraussetzungen und Deinstallation: **[Installationsanleitung](docs/de/installation.md)**.

## Dokumentation

| | Deutsch | English |
| --- | --- | --- |
| Installation | [installation.md](docs/de/installation.md) | [installation.md](docs/en/installation.md) |
| GUI-Tour (jede Einstellung) | [gui-tour.md](docs/de/gui-tour.md) | [gui-tour.md](docs/en/gui-tour.md) |
| Benutzerhandbuch (Funktionen, Tastenkürzel, Kommandozeile) | [benutzerhandbuch.md](docs/de/benutzerhandbuch.md) | [user-guide.md](docs/en/user-guide.md) |
| Fehlerbehebung | [fehlerbehebung.md](docs/de/fehlerbehebung.md) | [troubleshooting.md](docs/en/troubleshooting.md) |
| FAQ | [faq.md](docs/de/faq.md) | [faq.md](docs/en/faq.md) |
| Betriebshandbuch | | [RUNBOOK.md](docs/RUNBOOK.md) |
| Mitwirken | | [CONTRIBUTING.md](docs/CONTRIBUTING.md) |

## Privatsphäre und Sicherheit

- Alle KI-Funktionen (Gesichtserkennung, Freistellung, Stabilisierung) laufen **lokal**; kein Bild verlässt deinen Rechner, es gibt keinen Netzwerkcode.
- Schritte mit Admin-Rechten laufen über ein kleines Hilfsprogramm mit festen Aktionen, bestätigt über den polkit-Dialog deines Systems.
- Kamerabefehle, die die PIXY neu starten, zurücksetzen oder neu flashen könnten, werden blockiert, bevor sie die Kamera erreichen.
- Die udev-Regeln betreffen nur die PIXY (`328f:00c0`) und die virtuelle Kamera von PixyDeck.

## Mitwirken

Fehlerberichte, Rückmeldungen zu Distributionen und Pull Requests sind willkommen – siehe [CONTRIBUTING.md](docs/CONTRIBUTING.md). Freigeschaltet werden nur Kamerabefehle, die an echter Hardware geprüft sind; die Testsuite (über 500 Tests, 98 % Abdeckung) enthält eine simulierte PIXY und einen optionalen Hardware-Check.

## Danksagung und Lizenz

PixyDeck begann als Fork von [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) von Rolf Obermaier. Es baut auf dem Reverse Engineering des PIXY-Protokolls durch die Community auf (u. a. [emeet-pixyd](https://github.com/LarsArtmann/emeet-pixyd)), auf YuNet (OpenCV Zoo) und Robust Video Matting – siehe [CREDITS.md](CREDITS.md).

Lizenz: **GNU GPL v3 only** – siehe [LICENSE](LICENSE).
