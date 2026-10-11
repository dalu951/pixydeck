<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="Icono de EMEET PixyDeck">

# EMEET PixyDeck

**La suite de control para Linux de la webcam EMEET PIXY.**<br>
Giro, inclinación y zoom, la IA de la cámara, encuadre automático, desenfoque de fondo con IA, pantalla verde,<br>
estabilización, detección de llamadas y una cámara virtual para Meet, Zoom, Teams, WhatsApp y OBS – en una sola aplicación nativa.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

[English](README.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · **Español**

<img src="docs/media/background.gif" width="860" alt="PixyDeck alterna entre sin efecto, desenfoque con IA, degradado y color">

</div>

> **Proyecto comunitario no oficial**: sin relación con EMEET ni respaldado por EMEET. EMEET y PIXY son marcas de su respectivo titular. Todas las imágenes muestran una escena de demostración dibujada, renderizada por la aplicación real.

## En 30 segundos

1. **Instala** el paquete para tu sistema ([abajo](#instalación)) y reinicia una vez.
2. **Abre EMEET PixyDeck** desde el menú de aplicaciones. Si falta algo, el asistente lo arregla tras pedir la contraseña.
3. **Llama** con WhatsApp, Meet, Zoom o Teams: eligen *EMEET PIXY (PixyDeck)* por sí solos, con zoom, fondo y estabilización.

Eso es todo. Lo demás es opcional.

## Lo más destacado

<table>
<tr>
<td width="33%"><img src="docs/media/zoom.gif" alt="Zoom y orientación"></td>
<td width="33%"><img src="docs/media/autoframe.gif" alt="Encuadre automático"></td>
<td width="33%"><img src="docs/media/stabilize.gif" alt="Cámara que tiembla, sin y con estabilización"></td>
</tr>
</table>

- 🎯 **Seguimiento**: la PIXY te sigue sola (*Auto*, *cara* o *torso*); **Find me** vuelve a inclinar la cámara hacia tu asiento cuando te pierde al sentarte
- ⚡ **Velocidad** de giro e inclinación por separado · 📍 **posiciones** en las teclas 1–4, posición de inicio y de encendido
- 🔍 **Zoom hasta 4×** y **enfoque con un clic** sobre cualquier objeto
- 🪄 **Fondo**: desenfoque o sustitución con IA sin pantalla verde; detección automática de pantalla verde
- 🫨 **Estabilización** por flujo óptico: el temblor desaparece, tus movimientos se mantienen
- 🎥 **Cámara virtual** *EMEET PIXY (PixyDeck)*: todos los efectos, para varias aplicaciones a la vez; es la primera cámara de la lista, así que se elige sola; muestra una pantalla de espera en lugar de desaparecer
- 📞 **Detección de llamadas**: el seguimiento empieza con la llamada y el objetivo se aparta al terminar; micrófono PIXY opcional
- 🔒 **Privacidad**, 🎛️ **control de imagen** y bloqueos, 🛠️ **asistente de configuración**, ⌨️ `pixydeck-cli`

<img src="docs/media/tour.png" width="860" alt="Ventana principal de PixyDeck">

Cada ajuste explicado (en inglés): **[recorrido por la interfaz](docs/en/gui-tour.md)**. En tu aplicación elige **EMEET PIXY (PixyDeck)**; probado con Google Meet en Firefox y WhatsApp (Whatsie).

## Instalación

| Sistema | Comando |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | descarga el `.deb` desde las [releases](https://github.com/dalu951/pixydeck/releases) y ejecuta `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | descarga `PKGBUILD` y `pixydeck.install` de la [última release](https://github.com/dalu951/pixydeck/releases/latest) y ejecuta `makepkg -si` (paquete AUR próximamente) |
| **Cualquier distribución** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Reinicia una vez y abre **EMEET PixyDeck** desde el menú de aplicaciones; el diálogo **⚙ Setup** corrige lo que falte. Documentación detallada (en inglés): [instalación](docs/en/installation.md) · [recorrido](docs/en/gui-tour.md) · [guía](docs/en/user-guide.md) · [solución de problemas](docs/en/troubleshooting.md) · [FAQ](docs/en/faq.md).

## Privacidad y licencia

Toda la IA se ejecuta **localmente**; ninguna imagen sale del ordenador. Nació como fork de [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) de Rolf Obermaier ([CREDITS.md](CREDITS.md)). Licencia: **GNU GPL v3 only**.
