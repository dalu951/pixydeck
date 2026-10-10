<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="Icono de EMEET PixyDeck">

# EMEET PixyDeck

**La suite de control para Linux de la webcam EMEET PIXY.**<br>
Giro, inclinación y zoom, la IA de la cámara, encuadre automático, desenfoque de fondo con IA, pantalla verde,<br>
estabilización y una cámara virtual para Meet, Zoom, Teams y OBS – en una sola aplicación nativa.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

[English](README.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · **Español**

<img src="docs/media/background.gif" width="860" alt="PixyDeck alterna entre sin efecto, desenfoque con IA, degradado y color">

</div>

> **Proyecto comunitario no oficial**: sin relación con EMEET ni respaldado por EMEET. EMEET y PIXY son marcas de su respectivo titular. Todas las imágenes muestran una escena de demostración dibujada, renderizada por la aplicación real.

## Lo más destacado

<table>
<tr>
<td width="50%"><img src="docs/media/zoom.gif" alt="Zoom y orientación"></td>
<td width="50%"><img src="docs/media/autoframe.gif" alt="Encuadre automático"></td>
</tr>
</table>

- 🎯 **IA integrada de la PIXY**: seguimiento facial, modo privacidad, gestos, **enfoque con un clic**, cancelación de ruido del micrófono
- 🔍 **Zoom hasta 4×**: zoom por hardware donde la PIXY lo admite y zoom digital nítido más allá, incluso en 4K
- 🪄 **Fondo**: desenfoque o sustitución con IA sin pantalla verde; detección automática de pantalla verde
- 🎥 **Cámara virtual** *PixyDeck Virtual Camera* con todos los efectos, para cualquier aplicación de vídeo
- 🫨 **Estabilización**, 🔒 **temporizador de privacidad**, 🎛️ **control de imagen**, 🛠️ **asistente de configuración**

## Instalación

| Sistema | Comando |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | descarga el `.deb` desde las [releases](https://github.com/dalu951/pixydeck/releases) y ejecuta `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | descarga `PKGBUILD` y `pixydeck.install` de la [última release](https://github.com/dalu951/pixydeck/releases/latest) y ejecuta `makepkg -si` (paquete AUR próximamente) |
| **Cualquier distribución** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Abre **EMEET PixyDeck** desde el menú de aplicaciones; el diálogo **⚙ Setup** corrige lo que falte. Documentación detallada (en inglés): [instalación](docs/en/installation.md) · [guía](docs/en/user-guide.md) · [solución de problemas](docs/en/troubleshooting.md) · [FAQ](docs/en/faq.md).

## Privacidad y licencia

Toda la IA se ejecuta **localmente**; ninguna imagen sale del ordenador. Nació como fork de [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) de Rolf Obermaier ([CREDITS.md](CREDITS.md)). Licencia: **GNU GPL v3 only**.
