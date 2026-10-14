# User guide

[← README](../../README.md) · **English** · [Deutsch](../de/benutzerhandbuch.md)

<img src="../media/camera.png" width="860" alt="PixyDeck main window">

The window has the live preview on the left and six tabs on the right. The header shows the camera, status pills (tracking, virtual camera, apps using the camera) and **⚙ Setup**.

## Camera tab – aim, zoom, presets

- **Pan/tilt pad:** click or drag to aim; the dot shows where the camera points. Tilt is limited to −52° … +90° because lower angles only park the camera.
- **Arrow buttons / arrow keys:** hold to glide; movement accelerates the longer you hold.
- **On the preview:** drag to aim (or to move the digital crop when zoomed), double-click to centre a spot, scroll to zoom.
- **Pan speed / Tilt speed:** how fast the camera turns sideways and up/down (1–240 °/s, default 60) – slow for smooth moves on a live stream, fast to snap to a preset. The camera's own tracking uses them too: raise *Tilt speed* if it loses you when you stand up or sit down, *Pan speed* if it loses you when you walk. PixyDeck sets them again if the camera falls back to its own speed.
- **Zoom slider (1×–4×):** uses the PIXY's hardware zoom (up to 1.5×) where the video mode supports it – below 1080p and at 1080p30 – and digital zoom beyond.
- **Presets 1–4:** click an empty slot to store the current position, a filled one to recall it; right-click for more.
- **Startup position** (folded): where the camera goes when PixyDeck starts; **Save as camera power-on position** stores the current pan/tilt in the camera itself, so it starts there even without PixyDeck or on another computer.

Rarely used settings sit in folded cards (▸); click the title to open them. PixyDeck remembers which cards are open and the last tab.

## Tracking tab

<img src="../media/ai.png" width="860" alt="Tracking tab">

- **Camera tracking:** *Off*, *Face tracking* (the camera follows you physically) or *Privacy* (the lens turns away). *Keep in frame* chooses what tracking follows: *Auto*, *Face* or *Upper body* – the upper body copes better when you walk. **Find me when I sit down** helps the camera's tracking, which tilts too slowly to follow you when you sit: PixyDeck learns where you usually sit and tilts back there when it loses your face. It needs PixyDeck's own picture (preview or virtual camera). Changes made by hand gestures appear in the app within about three seconds.
- **Focus:** *Center*, *Face*, or *Click point* – then click anything in the preview, e.g. an object you hold up, and the PIXY's second lens focuses on it (yellow marker).
- **Auto-framing (software):** digitally zooms and follows faces. *Wide*, *Medium*, *Tight* set how close; *Show detected faces* draws the detection boxes.

<img src="../media/autoframe.gif" width="640" alt="Auto-framing">

## Image tab

Brightness, contrast, saturation, hue, sharpness, gamma and gain, with *Reset to camera defaults*; **stabilization** (*Steady picture*, uses an 8 % digital reserve to cancel shake). Folded: automatic or manual white balance, exposure and focus, backlight compensation and **locks** that hold exposure, white balance or focus at the current value (so the picture does not pump when you lean in or hold something up); mirror, vertical flip, auto-rotate for upside-down mounting and anti-flicker (50/60 Hz).

## Effects tab

<img src="../media/background.gif" width="640" alt="Background replacement">

| Mode | What happens |
| --- | --- |
| **AI** | Robust Video Matting cuts you out of any room (up to ~30 fps, more CPU) |
| **Green screen** | keys the exact shade detected at the picture's edges; fine-tune similarity, edge softness and spill removal (folded) |
| **Auto** | green screen while one is in view, AI otherwise |

Fill with **blur**, a **gradient**, a **colour** or your own **image**. Effects appear in the preview, in snapshots and in the processed virtual camera – an app that opens the PIXY directly does not see them.

## Calls tab

- **Calls:** with *Detect calls* on, PixyDeck notices when Meet, Zoom, Teams, WhatsApp, OBS … open the PIXY or the virtual camera (the header then shows *📞 Call*). At the start it turns face tracking on (or only leaves privacy with *Keep mode*), can make the PIXY microphone the default input and can lock the current focus to prevent hunting; a few seconds after the last app lets go, the lens turns away (*Privacy when the call ends*), the previous microphone is restored and only a focus lock set by the call is released. A quick device check by a browser does not count as a call. If the app reads the PIXY directly while effects are on, PixyDeck points you to the virtual camera.
- **Privacy timer:** enters privacy mode after the idle time and wakes up as soon as another app opens the camera. It pauses while the preview is visible.
- **Microphone:** the PIXY's DSP mode (noise cancel, live, original) and muting it in privacy mode.

## Output tab – using PixyDeck in other apps

<img src="../media/output.png" width="860" alt="Output tab">

| Option | When to use |
| --- | --- |
| **Processed virtual camera** | Select *EMEET PIXY (PixyDeck)* in Meet, Zoom, Teams, WhatsApp or OBS. Everything you see in PixyDeck – zoom, auto-framing, background, stabilization – is what others see. It is created at boot as the first camera, so most apps pick it without asking, and *Start with PixyDeck* (on by default) keeps it running; while PixyDeck has no camera picture (another app holds the PIXY) it shows a waiting screen, and your picture follows as soon as the camera is free. |
| **Direct virtual camera** | Lowest CPU: FFmpeg forwards the camera unchanged; hardware zoom only. Choose 30 fps at 1080p to keep hardware zoom. |
| **Release camera** | Other apps open the physical EMEET PIXY directly; PixyDeck keeps controlling PTZ, AI and picture settings. |

**Snapshot** saves the current view (including effects) to `~/Pictures/EMEET PIXY`.

## Keyboard shortcuts

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

## Command line

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
