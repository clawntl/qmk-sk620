# Cooler Master SK620

60% low-profile keyboard with per-key RGB (UK ISO layout).

* Keyboard Maintainer: [clawntl](https://github.com/clawntl)
* Hardware Supported: Cooler Master SK620 (SK-620), wired
* Hardware Availability: [Cooler Master](https://www.coolermaster.com/)

Hardware: Holtek HT32F52352 (printed HT50F52352), 3x Macroblock MBIA043GP, 512 KiB SPI flash.
Pin map and how it was found: https://github.com/clawntl/qmk-sk620

Make example for this keyboard (after setting up your build environment):

    make cm/sk620:default

Flashing example for this keyboard (or use `tools/flash/sk620_flash.py`, no dependencies, Windows and Linux):

    make cm/sk620:default:flash

## Bootloader

Enter the bootloader in 4 ways:

* **Flasher**: `tools/flash/sk620_flash.py` sends a raw HID command that restarts the keyboard into the bootloader

* **Bootmagic reset**: Hold down Esc and plug in the keyboard
* **Keycode in layout**: Press Fn+B (`QK_BOOT`)
* **Physical reset**: Bridge the SEL2 pads on the PCB and plug in the keyboard

The first flash over stock firmware must mass-erase the read-protected chip:
`ht32-dfu-tool -w write -m -v 0 cm_sk620_default.bin` (SEL2 bridged).
