# How the pin map was found

The SK620's MCU is read-protected, so the stock firmware can't be dumped. Cooler Master's updater carries the same firmware, though, and once decoded (see [stock-firmware.md](stock-firmware.md)) it can run in an emulator. Watching what the firmware does to the GPIO registers gave every pin without probing the board. The results were then confirmed on hardware.

All scripts are in `tools/analysis/` and need `pip install unicorn capstone`. Each one takes the extracted `EU_Layout.bin` (or `EU_Layout_restore.bin`) as its argument. Addresses are for firmware V1.01.00. Other versions will differ.

## Emulator setup (`ht32emu.py`)

The firmware runs in [Unicorn](https://www.unicorn-engine.org/) with:

- **Memory:** flash at 0x0 (application at 0x3200), 16 KiB of RAM, and the peripheral and system regions mapped.
- **GPIO model:** ports A–D track direction, pulls, and set/reset writes. Input reads return real pin levels, including an optional closed key switch between two pins.
- **AFIO:** pin-function writes are recorded.
- **Clock controller:** reports every clock as ready.
- **SysTick:** its counter counts down, so delay loops finish.
- **SPI flash:** a GD25Q40-style chip on SPI1, answering the ID, status, read, program and erase commands.
- **Interrupts:** handlers are called directly as functions, with a magic return address, because Unicorn doesn't deliver Cortex-M exceptions. The key scan runs in **SysTick** (vector 15) and the LED refresh in **BFTM0** (vector 33).

## What each script showed

| Script | Finding |
| --- | --- |
| `dump_tables.py` | **Keymap:** 9 x 8 HID codes at 0xCF1C. **LED rows:** a table at 0xC9D0 of 8 `{GPIO SRR address, mask}` pairs. **LED positions:** an 8 x 16 table at 0xC946. |
| `matrix_scan.py` | For every row pin x column pin, it closes a switch and runs the SysTick scan, then diffs RAM. Each pair sets one distinct bit in a 3-byte-per-row matrix buffer at 0x200000E3. This gives the row scan order (PB7, PB8, PB11, PD0, PB13, PB14, PB15, PC0, PC13) and the columns (PA1–PA8). |
| `led_stream.py` | Captures the bit stream the BFTM0 handler sends: 482 DCLK pulses per LED row, with 18 of them while LE is high. That means 3 chips x 16 channels x 10 bits, plus the latches. The handler toggles PA14 (DCLK), PA15 (LE), PC12 (SDI) and the 8 row pins. |
| `spi_cs.py` | PA9 goes low around every SPI1 transfer: 0xAB, then 0x9F (JEDEC ID). That makes PA9 the flash chip-select. |
| `gen_sk620.py` | Regenerates `keyboard.json` and the default keymap from the firmware. Keycodes per matrix position come straight from the stock table; the physical x/y and the Fn layer are written by hand. |

The rest came from disassembling the firmware with Capstone:

- **Pin functions** (logged from AFIO writes):
  - PC10 → timer (GCLK).
  - PC2, PC3 and PB6 → SPI.
  - PB10–PB14 → GPIO. QMK has to repeat this one.
- **LED power polarity:** the LEDs-on routine (0x7E6C) writes PC11 to the GPIO *reset* register, so the power enable is active low.
- **Colour order:** the shift routine (0x7EF0) sends each channel's three colour values in the order blue, green, red. Red therefore ends up in chip 0.
- **Clock:** the firmware writes `PLLCFGR = 0x03000000`, which is 8 MHz x 6.

## Mistakes worth knowing about

- The MasterKeys Pro S White uses PB7 as its flash chip-select. On the SK620, PB7 is matrix row 0 and the chip-select is PA9.
- The first build left out the AFIO GPIO setting, which made rows 4 and 5 (PB13, PB14) dead on hardware. The stock firmware's AFIO writes pointed straight to the fix.
- `ht32-dfu-tool` prints `Model: unknown` for this chip's ROM bootloader (ISP v103), even though the chip is a normal HT32F52352.

## Porting other Cooler Master HT32 boards

If Cooler Master publishes an updater for the board, use the same route:

1. Run `cm_fw_extract.py` on the updater.
2. Find the vector table to get the application's link address. Look for the run of `b .` default handlers right after a 4-instruction reset handler.
3. Load the image into `ht32emu.py`, then repeat the SysTick and timer-interrupt experiments.

With no updater available, use `tools/porting/`. It has a pin-finder QMK firmware that types which pins each key connects, and a script that turns that log into QMK keyboard files.
