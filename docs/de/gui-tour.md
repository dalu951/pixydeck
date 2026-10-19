# GUI-Tour

[← README](../../README.de.md) · [English](../en/gui-tour.md) · **Deutsch**

Jedes Bedienelement von EMEET PixyDeck, Tab für Tab. Hintergründe und Tipps stehen im [Benutzerhandbuch](benutzerhandbuch.md). Die Oberfläche selbst ist englisch; die Namen unten sind so geschrieben, wie sie in der App stehen.

<img src="../media/tour.png" width="860" alt="PixyDeck-Hauptfenster mit nummerierten Markierungen">

## Das Fenster

| | Was es ist | Was du damit machst |
| --- | --- | --- |
| **①** | Statusanzeigen | *Tracking off / Face tracking / Privacy*, *Virtual cam on/off* und – solange eine andere App die Kamera nutzt – *In use: App* oder *📞 Call: App* |
| **②** | ⚙ Setup | Öffnet die Einrichtungsprüfung. Wird zu **⚠ Setup**, wenn Berechtigungen, Kernelmodul oder virtuelle Kamera repariert werden müssen |
| **③** | Vorschau | Ziehen zum Ausrichten (bzw. zum Verschieben des Ausschnitts beim Zoomen) · Doppelklick zentriert eine Stelle · Mausrad zoomt · bei *Click point*-Fokus: klicken zum Scharfstellen. Oben stehen LIVE, Auflösung und Zoom |
| **④** | Werkzeugleiste | Aufnahmeauflösung · Zoom-Regler (1×–4×) · **Snapshot** (gespeichert unter `~/Pictures/EMEET PIXY`) · **Release camera** / **Resume preview** |
| **⑤** | Tabs | Camera · Tracking · Image · Effects · Calls · Output – PixyDeck öffnet den zuletzt benutzten |
| **⑥** | Karten | Gruppen von Einstellungen. ▸ heißt eingeklappt, ▾ offen; ein Klick auf den Titel klappt sie auf oder zu – PixyDeck merkt sich das |

Mit der Maus über einem Element erscheint eine kurze Erklärung.

## Camera

<img src="../media/camera.png" width="860" alt="Tab Camera">

| Element | Was es tut |
| --- | --- |
| **Schwenk-Feld** | Klicken oder ziehen zum Ausrichten; der Punkt zeigt, wohin die Kamera schaut. Nach unten geht es bis −52° (tiefer würde sie nur parken) |
| **▲ ◀ ▶ ▼** | Gedrückt halten zum Gleiten – je länger, desto schneller. Die Pfeiltasten machen dasselbe |
| **● Center** | Schwenken und Neigen auf 0°, Zoom zurück (Taste `C`) |
| **Pan speed / Tilt speed** | Wie schnell die Motoren seitlich bzw. hoch/runter drehen, 1–240 °/s. Das Tracking der Kamera nutzt sie ebenfalls: verliert es dich beim Aufstehen oder Hinsetzen, *Tilt speed* erhöhen. Fällt die Kamera auf ihre eigene Geschwindigkeit zurück, stellt PixyDeck sie wieder ein |
| **Presets 1–4** | Leeren Platz anklicken speichert die aktuelle Position, ein belegter fährt sie an. Rechtsklick: *Go to preset*, *Store current position here*, *Use as startup position*, *Clear*. Tasten `1`–`4` anfahren, `Strg+1`–`4` speichern |
| ▸ **Startup position** → *When PixyDeck starts* | *Last position* oder eine der Positionen |
| ▸ **Startup position** → *Save as camera power-on position* | Speichert die aktuelle Ausrichtung in der Kamera selbst: Sie startet dann dort, auch ohne PixyDeck und an anderen Rechnern |

## Tracking

<img src="../media/ai.png" width="860" alt="Tab Tracking">

| Element | Was es tut |
| --- | --- |
| **Camera tracking** | *Off* · *Face tracking* – die PIXY dreht sich mit dir mit · *Privacy* – die Linse dreht weg (Taste `T` schaltet Tracking, `P` Privacy) |
| **Keep in frame** | Worauf das Tracking achtet: *Auto*, *Face* (Gesicht) oder *Upper body* (Oberkörper) |
| **Find me when I sit down** | Beim Hinsetzen neigt die Kamera zu langsam nach unten und schaut dann nicht mehr hin. PixyDeck lernt, wo du normalerweise sitzt, und neigt nach etwa einer Sekunde ohne Gesicht dorthin zurück. Braucht das Bild in PixyDeck (Vorschau oder virtuelle Kamera) |
| **Gesture control** | Kamera mit Handgesten steuern; Änderungen erscheinen nach etwa drei Sekunden in PixyDeck |
| **Focus** | *Center* · *Face* · *Click point* – irgendetwas im Vorschaubild anklicken, die zweite Linse der PIXY stellt darauf scharf (gelbe Markierung) |
| ▾ **Auto-framing** → *Digital auto-framing* | Zoomt in Software und folgt Gesichtern (Taste `F`). Läuft das Tracking der Kamera, zoomt es nur noch und überlässt das Ausrichten der Kamera |
| ▾ **Auto-framing** → *Wide / Medium / Tight* | Wie nah |
| ▾ **Auto-framing** → *Show detected faces* | Zeigt die erkannten Gesichter in der Vorschau |

<img src="../media/autoframe.gif" width="640" alt="Auto-Framing">

## Image

<img src="../media/image.png" width="860" alt="Tab Image">

| Element | Was es tut |
| --- | --- |
| **Picture** | Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, Gamma, Verstärkung – gehen beim Ziehen direkt an die Kamera |
| **Reset to camera defaults** | Setzt alle Bildeinstellungen auf die Werte der Kamera zurück |
| **Steady picture** | Entfernt Wackeln von Tisch oder Monitor. Nutzt 8 % digitale Reserve; deine eigenen Bewegungen und gewollte Schwenks bleiben erhalten |
| ▸ **Exposure, white balance, focus** | *Auto white balance* / *Temperature*, *Auto exposure* / *Exposure time*, *Autofocus* / *Focus*: Automatik aus, dann von Hand einstellen · *Backlight compensation* (Gegenlicht) · *Lock exposure / white balance / focus* – hält den aktuellen Wert fest, damit das Bild nicht pumpt, wenn du dich vorbeugst oder etwas in die Kamera hältst |
| ▸ **Orientation and flicker** | *Mirror horizontally* (spiegeln) · *Flip vertically* (kippen) · *Auto-rotate when upside down* (Überkopf- oder Unter-Monitor-Montage) · *Anti-flicker* aus / 50 Hz / 60 Hz – bei flackerndem Licht auf die Netzfrequenz stellen (Deutschland: 50 Hz) |

<img src="../media/stabilize.gif" width="640" alt="Wackelnde Kamera ohne und mit Steady picture">

## Effects

<img src="../media/background.png" width="860" alt="Tab Effects">

| Element | Was es tut |
| --- | --- |
| **Background** | *Off* · *Auto* – Green Screen, solange einer im Bild ist, sonst KI · *Green screen* · *AI* – stellt dich in jedem Raum frei (mehr CPU) |
| **Replace with** | *Blur* (mit *Blur strength*) · *Gradient* (Verlauf) · *Color* (*Choose color…*) · *Image* (*Choose image…*) |
| ▸ **Green screen fine-tuning** | *Similarity* – höher, wenn Grün übrig bleibt, niedriger, wenn Teile von dir verschwinden · *Edge softness* (Kantenweichheit) · *Green spill removal* – nimmt den Grünstich von Haaren und Kanten |

Die Effekte erscheinen in der Vorschau, in Schnappschüssen und in *EMEET PIXY (PixyDeck)*. Eine App, die die echte Kamera direkt öffnet, sieht sie nicht.

<img src="../media/background.gif" width="640" alt="Hintergrund ersetzen">

## Calls

<img src="../media/calls.png" width="860" alt="Tab Calls">

| Element | Was es tut |
| --- | --- |
| **Detect calls** | Bemerkt, wenn Meet, Zoom, Teams, WhatsApp, OBS … die Kamera öffnen. Ein kurzer Gerätetest des Browsers zählt nicht |
| **At the start** | *Face tracking* – Tracking einschalten · *Keep mode* – nur den Privacy-Modus verlassen |
| **Privacy when the call ends** | Die Linse dreht ein paar Sekunden, nachdem die letzte App losgelassen hat, weg |
| **Use the PIXY microphone** | Macht die PIXY während des Anrufs zum Standard-Mikrofon und schaltet danach zurück |
| **Keep focus steady during calls** | Sperrt den aktuellen Fokus beim Anrufstart gegen Pumpen und löst danach nur diese vorübergehende Sperre |
| **Privacy when idle** / **Idle time** | Nach der eingestellten Zeit ohne App an der Kamera in den Privacy-Modus (pausiert, solange die Vorschau sichtbar ist) |
| **Wake when an app needs the camera** | Privacy-Modus verlassen, sobald eine App die Kamera öffnet |
| **Privacy when PixyDeck closes** | Dreht die Linse weg, wenn du PixyDeck schließt – nicht, solange eine andere App die echte Kamera nutzt. Beim nächsten Start geht es im vorherigen Modus weiter |
| **Microphone** | Klang der PIXY: *Noise cancel* (Geräuschunterdrückung) · *Live* · *Original* |
| **Mute in privacy mode** | Schaltet das PIXY-Mikrofon stumm, solange die Linse weggedreht ist |

## Output

<img src="../media/output.png" width="860" alt="Tab Output">

| Element | Was es tut |
| --- | --- |
| **Processed** | Die virtuelle Kamera zeigt genau, was PixyDeck zeigt – Zoom, Ausschnitt, Hintergrund, Stabilisierung. *Output size* legt ihre Auflösung fest |
| **Direct** | Das Kamerabild läuft unverändert durch, geringste CPU-Last; *Frame rate* – 30 fps hält den Hardware-Zoom bei 1080p nutzbar |
| **Start / Stop** | Startet bzw. stoppt die virtuelle Kamera |
| **Start with PixyDeck** | Standardmäßig an: Die virtuelle Kamera ist immer da, Apps können fest auf sie eingestellt bleiben. Solange PixyDeck kein Bild hat, zeigt sie einen Wartebildschirm |
| ▸ **Direct use by other apps** | Wann stattdessen *Release camera* sinnvoll ist |

## Einrichtungsdialog

<img src="../media/setup.png" width="620" alt="Einrichtungsdialog">

Listet jede Voraussetzung mit ✅, ⚠️ oder ❌. **Fix**-Knöpfe führen genau eine festgelegte, per polkit bestätigte Aktion aus – Kamerarechte, Dienst der virtuellen Kamera oder Videogruppe; *Check again* prüft erneut.
