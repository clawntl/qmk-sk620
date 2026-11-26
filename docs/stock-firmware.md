# Cooler Master's SK620 firmware

Cooler Master publishes Windows updaters for the SK620: `SK620_Black_FW_0462_1.00_202110181013.exe` and `SK620_White_FW_0463_1.00_202110181038.exe`, both firmware V1.01.00 with IAP V1.0.1. Each updater carries two complete application images, **US Layout** (ANSI) and **EU Layout** (ISO). UK boards use the EU image.

`tools/cm_fw_extract.py` pulls these images out of an updater, reading it as data only; the `.exe` is never run. No Cooler Master files are included in this repository. Download the updater yourself.

```sh
python3 tools/cm_fw_extract.py SK620_Black_FW_0462_1.00_202110181013.exe out/
# US_Layout: 44056 bytes, SP 0x20003fe0, reset 0x32c1, OK
# EU_Layout: 44060 bytes, SP 0x20003fe0, reset 0x32c1, OK
```

## Updater format

| Part | Where | Encoding |
| --- | --- | --- |
| Updater program | PE sections | plain |
| Firmware sections | appended after the PE sections (99,572 bytes for SK620) | updater scrambler, then CYKB XOR |
| Info blocks (180 B each) | after each firmware section | updater scrambler |
| String/layout table | end of file | updater scrambler |

The **updater scrambler** is the same one pok3rtool documents for Vortex/CYKB updaters (`decode_package_data`). It works on the whole block in three steps:

1. Swap bytes *i*−4 and *i* for every *i* = 4, 9, 14, …
2. Swap each pair of bytes.
3. Map each byte with `y = ((x − 7) << 4) + (x >> 4)`.

The swaps depend on where the block starts, so each block has to be decoded from its own first byte. One sign that the right method was found: the long run of `0x07` padding decodes to `0x00`.

The **firmware XOR** is pok3rtool's 52-byte CYKB key (`ProtoCYKB::decode_firmware`), applied to every 32-bit word.

The **layout table** lists each image as `<fw length u32><info length u32><UTF-16 name>`, for example `0xAC18, 0xB4, "US Layout"`. The firmware sections are stored in that order at the start of the appended data, each followed by its info block. The info block holds the version string, the USB VID/PID (`0x2516` / `0x0157` black, `0x0159` white) and the `0x5AA5` signature.

## The decoded application

- It is linked at **0x3200**. The vector table starts with SP = 0x20003FE0 and Reset = 0x32C1, followed by Keil-style default handlers.
- The 12.5 KiB below it is Cooler Master's in-application updater (IAP). The updater package doesn't include it, and you can't read it from a locked chip.
- The application never writes VTOR. Cooler Master's IAP must redirect interrupts to it.

## Restoring stock firmware (untested)

`cm_fw_extract.py` also writes `<Layout>_restore.bin`. It puts a copy of the application's own vector table at address 0, then 0xFF padding, then the application at 0x3200. The ROM bootloader jumps straight to the application's reset handler, and every interrupt goes straight to the application's own handlers, so the missing IAP isn't needed.

```sh
# Bridge SEL2, plug in, then:
ht32-dfu-tool -w write -m -v 0 out/EU_Layout_restore.bin
```

This hasn't been tried on hardware. If it doesn't boot, nothing is damaged: bridge SEL2 and flash QMK again. Even if it works, MasterPlus+ firmware updates won't, because they need the IAP.

QMK stores its settings in the last 64 KiB block of the SPI flash, to stay clear of any data the stock firmware keeps there.

## SK622

The SK622 (Bluetooth) updater uses the same format and decodes fine, but its images are about 10 KiB larger and include the Bluetooth code. Don't flash them onto an SK620.
