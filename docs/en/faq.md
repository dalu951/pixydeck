# FAQ

[← README](../../README.md) · **English** · [Deutsch](../de/faq.md)

**Is this an official EMEET app?**
No. PixyDeck is an independent, unofficial community project and is not affiliated with or endorsed by EMEET.

**Does any video leave my computer?**
No. Face detection, background matting and stabilization run locally; PixyDeck contains no network code.

**Which cameras are supported?**
The EMEET PIXY (USB `328f:00c0`). Basic UVC controls may work with similar EMEET cameras, but only the PIXY is tested.

**Why can't PixyDeck move the camera with the PIXY's own motor commands or store presets in the camera?**
The camera accepts those commands but then reports no position, so PixyDeck would lose track of where it points. Standard UVC pan/tilt is precise and keeps presets reliable.

**Why is half-body tracking, HDR or object tracking missing?**
Current PIXY firmware ignores or does not answer those vendor commands. PixyDeck only exposes features verified on real hardware.

**Do I need a green screen for background effects?**
No. *AI* mode works in any room. A green screen gives the cleanest edges with the least CPU.

**Can I use PixyDeck and Zoom at the same time?**
Yes – select *EMEET PIXY (PixyDeck)* in Zoom (effects included), or click *Release camera* and use the physical camera directly while PixyDeck keeps controlling it.

**Does PixyDeck need root?**
Only once, for system integration (udev rules, the virtual-camera service). The app itself runs as your user; repairs go through a small helper with fixed actions behind the polkit password dialog.

**Where are my settings?**
In `~/.config/pixydeck/pixydeck.conf`. Settings from *emeet-pixy-control* are imported on first start.
