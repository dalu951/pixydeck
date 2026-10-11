# Benutzerhandbuch

[← README](../../README.de.md) · [English](../en/user-guide.md) · **Deutsch**

<img src="../media/camera.png" width="860" alt="PixyDeck-Hauptfenster">

Links liegt die Live-Vorschau, rechts sechs Tabs. Die Kopfzeile zeigt die Kamera, Statusanzeigen (Tracking, virtuelle Kamera, Apps, die gerade die Kamera nutzen) und **⚙ Setup**.

## Tab „Camera“ – ausrichten, zoomen, Positionen

- **Schwenk-Feld:** klicken oder ziehen, um die Kamera auszurichten; der Punkt zeigt, wohin sie schaut. Nach unten geht es nur bis −52°, darunter würde die Kamera nur in ihre Ruheposition fahren.
- **Pfeiltasten / Pfeil-Buttons:** gedrückt halten zum Gleiten – je länger, desto schneller.
- **Im Vorschaubild:** ziehen zum Ausrichten (bzw. zum Verschieben des Ausschnitts beim Digitalzoom), Doppelklick zentriert eine Stelle, Mausrad zoomt.
- **Motorgeschwindigkeit:** wie schnell die Kamera dreht (1–240 °/s, Standard 60) – langsam für ruhige Schwenks im Livestream, schnell zum Anfahren einer Position. Das Tracking der Kamera nutzt sie ebenfalls; verliert es dich beim Gehen, einen hohen Wert wählen.
- **Zoom-Regler (1×–4×):** nutzt den Hardware-Zoom der PIXY (bis 1,5×), wo der Videomodus ihn unterstützt – unter 1080p und bei 1080p30 – und darüber digitalen Zoom.
- **Positionen 1–4:** leeren Platz anklicken speichert die aktuelle Position, ein belegter fährt sie an; Rechtsklick für mehr.
- **Startup position** (eingeklappt): wohin die Kamera beim Start von PixyDeck fährt; **Save as camera power-on position** speichert die aktuelle Ausrichtung in der Kamera selbst – sie startet dann dort, auch ohne PixyDeck oder an einem anderen Rechner.

Selten gebrauchte Einstellungen liegen in eingeklappten Karten (▸); ein Klick auf den Titel öffnet sie. PixyDeck merkt sich, welche Karten offen sind, und den zuletzt benutzten Tab.

## Tab „Tracking“

<img src="../media/ai.png" width="860" alt="Tab Tracking">

- **Camera tracking:** *Off*, *Face tracking* (die Kamera folgt dir mechanisch) oder *Privacy* (die Linse dreht weg). *Keep in frame* bestimmt, worauf das Tracking achtet: *Auto*, *Face* (Gesicht) oder *Upper body* (Oberkörper) – der Oberkörper klappt beim Gehen besser. Änderungen per Handgeste erscheinen nach etwa drei Sekunden auch in der App.
- **Focus:** *Center*, *Face* oder *Click point* – dann irgendetwas im Vorschaubild anklicken, z. B. einen Gegenstand, den du in die Kamera hältst; die zweite Linse der PIXY stellt darauf scharf (gelbe Markierung).
- **Auto-Framing (Software):** zoomt digital und folgt Gesichtern. *Wide*, *Medium*, *Tight* bestimmen, wie nah; *Show detected faces* zeigt die erkannten Gesichter.

<img src="../media/autoframe.gif" width="640" alt="Auto-Framing">

## Tab „Image“

Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, Gamma und Verstärkung mit *Reset to camera defaults*; **Stabilisierung** (*Steady picture*, nutzt 8 % digitale Reserve gegen Wackeln). Eingeklappt: Weißabgleich, Belichtung und Fokus automatisch oder manuell, Gegenlichtausgleich und **Sperren**, die Belichtung, Weißabgleich oder Fokus beim aktuellen Wert festhalten (damit das Bild nicht pumpt, wenn du dich vorbeugst oder etwas in die Kamera hältst); Spiegeln, vertikal Kippen, automatisches Drehen bei Überkopf-Montage und Flimmerschutz (50/60 Hz).

## Tab „Effects“

<img src="../media/background.gif" width="640" alt="Hintergrund ersetzen">

| Modus | Was passiert |
| --- | --- |
| **AI** | Robust Video Matting stellt dich in jedem Raum frei (bis etwa 30 fps, mehr CPU) |
| **Green screen** | stanzt genau den Grünton aus, der am Bildrand erkannt wird; Ähnlichkeit, Kantenweichheit und Grünstich-Entfernung lassen sich nachregeln (eingeklappt) |
| **Auto** | Green Screen, solange einer im Bild ist, sonst KI |

Gefüllt wird mit **Unschärfe**, **Verlauf**, **Farbe** oder einem eigenen **Bild**. Die Effekte erscheinen in der Vorschau, in Schnappschüssen und in der verarbeiteten virtuellen Kamera – eine App, die die PIXY direkt öffnet, sieht sie nicht.

## Tab „Calls“

- **Anrufe:** Mit *Detect calls* bemerkt PixyDeck, wenn Meet, Zoom, Teams, WhatsApp, OBS … die PIXY oder die virtuelle Kamera öffnen (oben steht dann *📞 Call*). Zu Beginn schaltet es das Face-Tracking ein (mit *Keep mode* verlässt es nur den Privacy-Modus) und kann das PIXY-Mikrofon zum Standard-Eingang machen; ein paar Sekunden nachdem die letzte App die Kamera freigibt, dreht die Linse weg (*Privacy when the call ends*) und das vorherige Mikrofon wird wiederhergestellt. Ein kurzer Gerätetest des Browsers zählt nicht als Anruf. Liest die App die PIXY direkt, während Effekte aktiv sind, weist PixyDeck auf die virtuelle Kamera hin.
- **Privacy-Timer:** geht nach der eingestellten Leerlaufzeit in den Privacy-Modus und verlässt ihn, sobald eine andere App die Kamera öffnet. Solange die Vorschau sichtbar ist, pausiert er.
- **Mikrofon:** DSP-Modus der PIXY (Geräuschunterdrückung, Live, Original) und Stummschalten im Privacy-Modus.

## Tab „Output“ – PixyDeck in anderen Apps nutzen

<img src="../media/output.png" width="860" alt="Tab Ausgabe">

| Option | Wann |
| --- | --- |
| **Processed** (virtuelle Kamera) | In Meet, Zoom, Teams, WhatsApp oder OBS *PixyDeck Virtual Camera* wählen. Was du in PixyDeck siehst – Zoom, Auto-Framing, Hintergrund, Stabilisierung – sehen auch die anderen. Mit *Start with PixyDeck* ist sie immer verfügbar; solange PixyDeck kein Kamerabild hat (eine andere App hält die PIXY), zeigt sie einen Wartebildschirm, und dein Bild folgt, sobald die Kamera frei ist. |
| **Direct** (virtuelle Kamera) | Geringste CPU-Last: FFmpeg reicht das Kamerabild unverändert durch; nur Hardware-Zoom. Bei 1080p 30 fps wählen, damit der Hardware-Zoom funktioniert. |
| **Release camera** | Andere Apps öffnen die echte EMEET PIXY direkt; PixyDeck steuert Schwenken, KI und Bild weiter. |

**Snapshot** speichert das aktuelle Bild (mit Effekten) unter `~/Pictures/EMEET PIXY`.

## Tastenkürzel

<!-- AUTO-GENERATED:shortcuts -->
| Key | Action |
| --- | --- |
| Arrow keys | Pan / tilt while held |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| Mouse wheel on the preview | Zoom |
| `C` | Center camera and reset zoom |
| `F` | Toggle auto-framing |
| `T` | Toggle face tracking |
| `P` | Toggle privacy mode |
| `S` | Save snapshot |
| `1`–`4` | Recall preset |
| `Ctrl+1`–`Ctrl+4` | Store preset |
| `Ctrl+Q` | Quit |
<!-- /AUTO-GENERATED:shortcuts -->

## Kommandozeile

<!-- AUTO-GENERATED:cli -->
`pixydeck-cli` is on your `PATH` with the .deb and AUR packages; after `./install.sh` it is `~/.local/share/pixydeck/venv/bin/pixydeck-cli`.

| Command | Description |
| --- | --- |
| `pixydeck-cli status` | Show device, pan, tilt and zoom |
| `pixydeck-cli center` | Pan/tilt to 0° and zoom out |
| `pixydeck-cli left` | Pan 2° left |
| `pixydeck-cli right` | Pan 2° right |
| `pixydeck-cli up` | Tilt 2° up |
| `pixydeck-cli down` | Tilt 2° down |
| `pixydeck-cli pan DEGREES` | Pan to an absolute angle (-150…150) |
| `pixydeck-cli tilt DEGREES` | Tilt to an absolute angle (-52…90) |
| `pixydeck-cli zoom 100-150` | Set hardware zoom |
| `pixydeck-cli zoom-in` | Hardware zoom +10 |
| `pixydeck-cli zoom-out` | Hardware zoom -10 |
| `pixydeck-cli track` | Enable face tracking |
| `pixydeck-cli idle` | Disable tracking |
| `pixydeck-cli privacy` | Enter privacy mode |
| `pixydeck-cli gesture-on` | Enable gesture control |
| `pixydeck-cli gesture-off` | Disable gesture control |
| `pixydeck-cli audio nc\|live\|org` | Microphone mode: noise cancel, live, original |
| `pixydeck-cli auto-privacy SECONDS` | Camera-side auto-privacy delay (0 = off; experimental) |
| `pixydeck-cli flicker off\|50\|60` | Anti-flicker frequency |
| `pixydeck-cli target auto\|face\|upper-body` | What tracking keeps in frame |
| `pixydeck-cli pan-speed [DEG/S]` | Show or set the pan motor speed (1…240) |
| `pixydeck-cli tilt-speed [DEG/S]` | Show or set the tilt motor speed (1…240) |
| `pixydeck-cli wb-lock on\|off` | Lock the white balance |
| `pixydeck-cli exposure-lock on\|off` | Lock the exposure |
| `pixydeck-cli focus-lock on\|off` | Lock the focus |
| `pixydeck-cli power-on-position [show\|save]` | Show, or store the current pan/tilt as the camera's power-on position |
| `pixydeck-cli state` | Show the camera's on-board settings |
<!-- /AUTO-GENERATED:cli -->
