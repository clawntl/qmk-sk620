QMK firmware for the Cooler Master SK620 (UK ISO), with a one-click flasher for Windows and Linux.

**Download `sk620-qmk-v*.zip`**: it has everything below plus instructions (`FLASHING.txt`).

| File | What |
| --- | --- |
| `cm_sk620_default.bin` | The firmware. All 65 keys, the Fn layer from the keycap legends, per-key RGB with 30 effects (including ones that react to typing), Caps Lock and Windows-key lock indicators, settings kept across unplugs, and VIA |
| `sk620_flash.exe` | Flasher for Windows: double-click, then **Flash firmware**. No install, no drivers |
| `sk620_flash.py` | The same flasher for Linux (needs only Python 3): `python3 sk620_flash.py` |
| `cm_sk620_ledmap.bin` | (in the zip) one-off tool used to map which LED is under which key; not needed |
| `sk620_iso.json` | VIA definition, only for usevia.app |

**First flash over Cooler Master's firmware:** bridge the SEL2 pads on the PCB, plug in, run the flasher and type `ERASE` when asked. This permanently replaces the stock firmware (see the README). **Updates:** just run the flasher; it switches the keyboard into bootloader mode by itself.

**Changing keys, macros and lighting from the PC:** use [OpenPeriph](https://github.com/clawntl/openperiph) (Windows and Linux, knows the SK620 out of the box) or usevia.app. See `docs/configuring.md`.

Flashing resets keys and macros changed through VIA to the firmware's defaults; save a backup first.
