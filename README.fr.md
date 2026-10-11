<div align="center">

<img src="src/pixydeck/assets/pixydeck.svg" width="96" alt="Icône EMEET PixyDeck">

# EMEET PixyDeck

**La suite de contrôle Linux pour la webcam EMEET PIXY.**<br>
Orientation et zoom, l'IA de la caméra, cadrage automatique, flou d'arrière-plan par IA, fond vert,<br>
stabilisation, détection d'appel et une caméra virtuelle pour Meet, Zoom, Teams, WhatsApp et OBS – dans une seule application native.

[![Tests](https://github.com/dalu951/pixydeck/actions/workflows/python.yml/badge.svg)](https://github.com/dalu951/pixydeck/actions/workflows/python.yml)
[![Licence : GPL v3](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

[English](README.md) · [Deutsch](README.de.md) · **Français** · [Español](README.es.md)

<img src="docs/media/background.gif" width="860" alt="PixyDeck alterne entre sans effet, flou IA, dégradé et couleur">

</div>

> **Projet communautaire non officiel** – sans lien avec EMEET ni approuvé par EMEET. EMEET et PIXY sont des marques de leur propriétaire. Toutes les images montrent une scène de démonstration dessinée, rendue par la vraie application.

## En 30 secondes

1. **Installez** le paquet de votre système ([ci-dessous](#installation)) et redémarrez une fois.
2. **Ouvrez EMEET PixyDeck** depuis le menu des applications. S'il manque quelque chose, l'assistant le corrige après un mot de passe.
3. **Appelez** avec WhatsApp, Meet, Zoom ou Teams – ils choisissent *EMEET PIXY (PixyDeck)* d'eux-mêmes, avec zoom, arrière-plan et stabilisation.

C'est tout. Le reste est facultatif.

## Points forts

<table>
<tr>
<td width="33%"><img src="docs/media/zoom.gif" alt="Zoom et orientation"></td>
<td width="33%"><img src="docs/media/autoframe.gif" alt="Cadrage automatique"></td>
<td width="33%"><img src="docs/media/stabilize.gif" alt="Caméra qui tremble, sans et avec stabilisation"></td>
</tr>
</table>

- 🎯 **Suivi** : la PIXY vous suit elle-même (*Auto*, *visage* ou *buste*) ; **Find me** réoriente la caméra vers votre siège quand elle vous perd en vous asseyant
- ⚡ **Vitesse** de panoramique et d'inclinaison séparées · 📍 **positions** sur les touches 1–4, position de démarrage et de mise sous tension
- 🔍 **Zoom jusqu'à 4×** et **mise au point par clic** sur n'importe quel objet
- 🪄 **Arrière-plan** : flou ou remplacement par IA sans fond vert ; détection automatique d'un fond vert
- 🫨 **Stabilisation** par flux optique – le tremblement disparaît, vos mouvements restent
- 🎥 **Caméra virtuelle** *EMEET PIXY (PixyDeck)* : tous les effets, pour plusieurs applications à la fois ; première caméra de la liste, donc choisie automatiquement ; écran d'attente au lieu de disparaître
- 📞 **Détection d'appel** : le suivi démarre avec l'appel, l'objectif se détourne à la fin ; micro PIXY en option
- 🔒 **Confidentialité**, 🎛️ **réglages d'image** et verrous, 🛠️ **assistant de configuration**, ⌨️ `pixydeck-cli`

<img src="docs/media/tour.png" width="860" alt="Fenêtre principale de PixyDeck">

Chaque réglage expliqué (en anglais) : **[visite guidée](docs/en/gui-tour.md)**. Dans votre application, choisissez **EMEET PIXY (PixyDeck)** – testé avec Google Meet dans Firefox et WhatsApp (Whatsie).

## Installation

| Système | Commande |
| --- | --- |
| **Ubuntu / Pop!_OS 24.04** | télécharger le `.deb` depuis les [releases](https://github.com/dalu951/pixydeck/releases), puis `sudo apt install ./pixydeck_*_amd64.deb` |
| **Arch / CachyOS / Manjaro** | télécharger `PKGBUILD` et `pixydeck.install` depuis la [dernière release](https://github.com/dalu951/pixydeck/releases/latest), puis `makepkg -si` (paquet AUR à venir) |
| **Toute distribution** | `git clone https://github.com/dalu951/pixydeck.git && cd pixydeck && ./install.sh` |

Redémarrez une fois, puis lancez **EMEET PixyDeck** depuis le menu des applications ; la boîte de dialogue **⚙ Setup** corrige ce qui manque. Documentation détaillée (en anglais) : [installation](docs/en/installation.md) · [visite guidée](docs/en/gui-tour.md) · [guide](docs/en/user-guide.md) · [dépannage](docs/en/troubleshooting.md) · [FAQ](docs/en/faq.md).

## Confidentialité et licence

Toute l'IA fonctionne **localement** ; aucune image ne quitte l'ordinateur. Issu d'un fork de [emeet-pixy-control](https://github.com/rolfobermaier/emeet-pixy-control) de Rolf Obermaier ([CREDITS.md](CREDITS.md)). Licence : **GNU GPL v3 only**.
