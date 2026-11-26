# QMK for the Cooler Master SK620

QMK firmware for the **Cooler Master SK620** 60% low-profile keyboard (UK ISO), plus everything learned while porting it: the full pin map, the format of Cooler Master's firmware updaters, and the tools used to read the hardware layout out of the stock firmware.

The pins were never probed by hand. They were read out of Cooler Master's own SK620 firmware by decoding the official updater and running the firmware in an emulator (see [docs/reverse-engineering.md](docs/reverse-engineering.md)).

## Status

| Feature | Status |
| --- | --- |
| All 65 keys (UK ISO) | Working, confirmed on hardware |
| Fn layer from the keycap legends | Working |
| Per-key RGB (MBIA043 driver) | Lights and animates, confirmed on hardware |
| RGB effects that react to key presses | Not linked yet (LED-to-key mapping still to be done) |
| Settings saved across unplugs (SPI flash) | Configured, not yet confirmed |
| ANSI (US) SK620 | Matrix is the same; needs an ANSI layout and keymap |
| SK622 (Bluetooth model) | Not supported |
| Going back to stock firmware | Possible from Cooler Master's updater, untested (see [docs/stock-firmware.md](docs/stock-firmware.md)) |

## Hardware at a glance

| Part | What |
| --- | --- |
| MCU | Holtek HT32F52352 (Cortex-M0+, 128 KiB flash, 16 KiB RAM), printed "HT50F52352" |
| LED drivers | 3 x Macroblock MBIA043GP (one per colour), 8 LED rows |
| Storage | 512 KiB SPI NOR flash (GD25Q40 class) |
| Bootloader | Holtek ROM ISP over USB, entered by bridging the SEL2 pads |
| Key matrix | 9 rows x 8 columns, COL2ROW |

The full pin map is in [docs/hardware.md](docs/hardware.md).

## Quick start

This needs a Linux PC (tested on CachyOS), the QMK fork with HT32 and MBIA043 support, and [`ht32-dfu-tool`](https://github.com/hansemro/ht32-dfu-tool). Full steps, including an install that doesn't touch system Python, are in [docs/flashing.md](docs/flashing.md).

```sh
# QMK fork with HT32F52352 + MBIA043 support (tested at commit 162faf96)
git clone -b cmmkprosrgb_mbi_preview https://github.com/hansemro/qmk_firmware ~/qmk_sk620
cd ~/qmk_sk620 && git submodule update --init --recursive

# Add this keyboard and build
cp -r /path/to/this/repo/qmk/keyboards/cm/sk620 keyboards/cm/
make cm/sk620:default

# First flash: bridge SEL2, plug in, then (-m mass-erases the locked stock firmware)
ht32-dfu-tool -w write -m -v 0 cm_sk620_default.bin
```

After the first flash, press **Fn+B** (or hold Esc while plugging in) to enter the bootloader, then run:

```sh
ht32-dfu-tool -w -r write -v 0 cm_sk620_default.bin
```

> [!WARNING]
> The first flash permanently erases Cooler Master's firmware and its updater. The chip is read-protected, so it can't be backed up first. [docs/stock-firmware.md](docs/stock-firmware.md) describes how to rebuild a bootable stock image from Cooler Master's official updater. That restore image is untested.

## Default keymap

Layer 0 is the stock UK layout, taken directly from Cooler Master's firmware. The Fn layer follows the keycap legends:

| Fn + | Action | Fn + | Action |
| --- | --- | --- | --- |
| Esc | ` (with Shift: ¬) | J / K / L | Play-pause / previous / next track |
| 1 … = | F1 … F12 | , / . / / | Volume down / up / mute |
| Backspace | Eject | Right Shift | Windows-key lock |
| U / I / O | Print Screen / Scroll Lock / Pause | Tab | RGB on/off |
| P | Insert | ↑ / ↓ | RGB brightness up / down |
| [ / ] | Home / Page Up | ← / → | Previous / next RGB effect |
| ; / ' | End / Page Down | Q W E / A S D | Hue, saturation, speed up / down |
| B | Bootloader | | |

## Repository layout

```
qmk/keyboards/cm/sk620/   QMK keyboard definition (copy into the QMK fork)
docs/hardware.md           pin map, matrix, LED driver wiring, protection bits
docs/flashing.md           setup and flashing on Linux, recovery
docs/stock-firmware.md     Cooler Master updater format, extracting and restoring stock firmware
docs/reverse-engineering.md how the pin map was read out of the stock firmware
tools/cm_fw_extract.py     extract firmware images from a Cooler Master SK620 updater .exe
tools/analysis/            Unicorn-based emulator and the scripts that produced the pin map
tools/porting/             pin-finder firmware and log-to-QMK script for boards without stock firmware
```

## Credits

- **hansemro** for HT32 support in QMK and ChibiOS, the MBIA043 driver, the MasterKeys ports this builds on, and `ht32-dfu-tool`.
- **ChaoticEnigma** and the pok3rtool project for documenting the Vortex/Cooler Master updater encoding and the CYKB firmware XOR key.
- **mateuszradomski/re-masterkeys** for the MasterKeys Pro S White reverse-engineering notes and schematic.

## Licence

GPL-2.0-or-later, matching QMK. This repository contains no Cooler Master code or firmware. The extractor works on an updater you download yourself.

This project is not affiliated with or endorsed by Cooler Master. Flashing third-party firmware may void your warranty.
