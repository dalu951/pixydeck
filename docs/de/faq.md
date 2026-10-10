# Häufige Fragen

[← README](../../README.de.md) · [English](../en/faq.md) · **Deutsch**

**Ist das eine offizielle EMEET-App?**
Nein. PixyDeck ist ein unabhängiges, inoffizielles Community-Projekt und steht in keiner Verbindung zu EMEET.

**Verlässt irgendein Videobild meinen Computer?**
Nein. Gesichtserkennung, Hintergrund-Freistellung und Stabilisierung laufen lokal; PixyDeck enthält keinerlei Netzwerkcode.

**Welche Kameras werden unterstützt?**
Die EMEET PIXY (USB `328f:00c0`). Einfache UVC-Funktionen können mit ähnlichen EMEET-Kameras gehen, getestet ist aber nur die PIXY.

**Warum steuert PixyDeck den Motor nicht über die PIXY-eigenen Befehle oder speichert Positionen in der Kamera?**
Die Kamera führt diese Befehle aus, meldet danach aber keine Position mehr – PixyDeck wüsste nicht mehr, wohin sie schaut. Das normale UVC-Schwenken ist präzise und hält gespeicherte Positionen zuverlässig.

**Warum fehlen Halbkörper-Tracking, HDR oder Objekt-Tracking?**
Die aktuelle PIXY-Firmware ignoriert diese Befehle oder antwortet nicht. PixyDeck bietet nur an, was auf echter Hardware geprüft ist.

**Brauche ich einen Green Screen für Hintergrund-Effekte?**
Nein. Der *AI*-Modus funktioniert in jedem Raum. Ein Green Screen liefert die saubersten Kanten bei der geringsten CPU-Last.

**Kann ich PixyDeck und Zoom gleichzeitig nutzen?**
Ja – in Zoom *PixyDeck Virtual Camera* wählen (mit Effekten), oder *Release camera* klicken und die echte Kamera direkt nutzen, während PixyDeck sie weiter steuert.

**Braucht PixyDeck Root-Rechte?**
Nur einmal für die Systemintegration (udev-Regeln, Dienst der virtuellen Kamera). Die App selbst läuft als dein Benutzer; Reparaturen laufen über einen kleinen Helfer mit festen Aktionen hinter dem Polkit-Passwortdialog.

**Wo liegen meine Einstellungen?**
In `~/.config/pixydeck/pixydeck.conf`. Einstellungen aus *emeet-pixy-control* werden beim ersten Start übernommen.
