# Installation

[← README](../../README.de.md) · [English](../en/installation.md) · **Deutsch**

PixyDeck braucht Linux mit systemd, eine EMEET PIXY (USB `328f:00c0`) und – für die virtuelle Kamera – das Kernelmodul `v4l2loopback`.

## Ubuntu, Pop!_OS, Linux Mint (Basis 24.04)

1. `pixydeck_<version>_amd64.deb` (optional auch `SHA256SUMS`, prüfen mit `sha256sum -c --ignore-missing SHA256SUMS`) von der [Release-Seite](https://github.com/dalu951/pixydeck/releases) herunterladen. Das Paket ist für die Basis **24.04** (Python 3.12) gebaut; auf anderen Versionen das Installationsskript unten nutzen.
2. Mit apt installieren – FFmpeg, v4l-utils und `v4l2loopback-dkms` kommen automatisch mit:

   ```bash
   sudo apt install ./pixydeck_*_amd64.deb
   ```

3. **EMEET PixyDeck** im Anwendungsmenü starten.

Das Paket bringt seine Python-Bibliotheken (Qt, OpenCV, ONNX Runtime) in `/opt/pixydeck` mit und kommt den Python-Paketen des Systems nicht in die Quere. Der Dienst `pixydeck-virtual-camera` wird automatisch aktiviert.

## Arch Linux, CachyOS, EndeavourOS, Manjaro

Bis das Paket im AUR veröffentlicht ist, wird es aus den Release-Dateien gebaut:

```bash
mkdir pixydeck-pkg && cd pixydeck-pkg
curl -LO https://github.com/dalu951/pixydeck/releases/latest/download/PKGBUILD
curl -LO https://github.com/dalu951/pixydeck/releases/latest/download/pixydeck.install
makepkg -si
```

Das Paket nutzt die offiziellen Arch-Pakete (`pyside6`, `python-opencv`, `python-onnxruntime`, …). Wie unter Arch üblich werden Dienste nicht automatisch aktiviert: Einmal in PixyDeck **⚙ Setup** öffnen und bei *Virtuelle Kamera* auf **Fix** klicken – oder `sudo systemctl enable --now pixydeck-virtual-camera.service` ausführen.

Bringt dein Kernel kein `v4l2loopback` mit, zusätzlich `v4l2loopback-dkms` und die passenden Kernel-Header installieren.

## Jede andere Distribution (Installationsskript)

Python 3.10+, `python3-venv`, `v4l-utils`, FFmpeg und `v4l2loopback` (Modul + `v4l2loopback-ctl`) über den Paketmanager installieren, dann:

```bash
git clone https://github.com/dalu951/pixydeck.git
cd pixydeck
./install.sh
```

Das Skript installiert PixyDeck in eine eigene Python-Umgebung unter `~/.local/share/pixydeck`, legt den Menüeintrag an und fragt einmal per `sudo` nach dem Passwort, um udev-Regeln, Polkit-Aktion, Setup-Helfer und den Dienst für die virtuelle Kamera einzurichten. Eine ältere *emeet-pixy-control*-Installation wird ersetzt, ihre Einstellungen werden übernommen.

### Optionale NVIDIA-Beschleunigung

Auf einem Rechner mit passendem NVIDIA-Treiber und CUDA-12-Laufzeit `./install.sh --gpu` verwenden. ONNX Runtime berechnet dann die KI-Personenfreistellung mit CUDA; ein kleiner CuPy-Renderer hält Greenscreen-Keying, Weichzeichnung, Compositing, Stabilisierungstransformation, Crop/Resize und I420-Konvertierung auf der GPU. JPEG-Dekodierung, Gesichtserkennung, Messung der Kamerabewegung und die abschließende Übergabe an `v4l2loopback` bleiben auf der CPU. Es ist nur ein CUDA-Render gleichzeitig aktiv und der CuPy-Speicherpool ist auf 25 % des VRAM begrenzt, damit genug Ressourcen für Meeting-Apps bleiben. Bei einem CUDA-Fehler wechselt die laufende Sitzung auf den CPU-Renderer, statt die Kamera zu stoppen.

Den lokalen Hardwarepfad nach der Installation prüfen:

```bash
~/.local/share/pixydeck/venv/bin/pixydeck-gpu-benchmark
```

Der Befehl zeigt erkannte GPU, CPU-/CUDA-Bildzeiten, Beschleunigung und den gehaltenen CuPy-Speicherpool. Mit `PIXYDECK_CUDA_MEMORY_FRACTION=0.15` lässt sich das CuPy-Limit senken, mit `PIXYDECK_ORT_GPU_MEMORY_MB=512` das standardmäßig 1 GiB große ONNX-Limit; `PIXYDECK_DISABLE_CUDA=1` erzwingt den CPU-Pfad.

## Erster Start

Beim Start prüft PixyDeck das System. Fehlt etwas, öffnet sich der Dialog **⚙ Setup**:

<img src="../media/setup.png" width="560" alt="Einrichtungsdialog">

| Prüfung | Was „Fix“ tut |
| --- | --- |
| Kamerasteuerung | wendet die udev-Regel an, damit deine Desktop-Sitzung mit der PIXY sprechen darf |
| Kernelmodul v4l2loopback | nicht automatisch lösbar – das im Dialog genannte Paket installieren |
| Virtuelle Kamera | lädt das Modul und aktiviert `pixydeck-virtual-camera.service` |
| Recht, die virtuelle Kamera zu beliefern | normalerweise per udev; als Rückfall wirst du zur Gruppe `video` hinzugefügt (danach ab- und wieder anmelden) |

Jede Reparatur fragt im Polkit-Dialog deines Systems nach dem Passwort und führt nur den angezeigten Schritt aus – sonst nichts.

## Aktualisieren

- **.deb:** das neuere `.deb` genauso installieren.
- **AUR:** dein AUR-Helfer aktualisiert es mit dem System.
- **Skript:** `git pull && ./install.sh` (oder `./install.sh --gpu`, um die CUDA-Variante beizubehalten).

## Deinstallieren

| Installiert über | Befehl |
| --- | --- |
| .deb | `sudo apt remove pixydeck` |
| AUR | `sudo pacman -R pixydeck` |
| install.sh | `./uninstall.sh` (mit `--purge` werden auch die Einstellungen gelöscht) |

Die Einstellungen liegen in `~/.config/pixydeck/pixydeck.conf`. Systempakete wie FFmpeg oder v4l2loopback werden nie entfernt.
