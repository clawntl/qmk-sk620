# SK620 hardware

Everything here comes from Cooler Master's SK620 firmware V1.01.00 (EU layout), unless it says otherwise. Each value was read out by running that firmware in an emulator; [reverse-engineering.md](reverse-engineering.md) explains how. The key matrix and RGB output have also been confirmed on a real UK SK620.

## Chips

| Part | Marking / type | Notes |
| --- | --- | --- |
| MCU | HT32F52352, printed **HT50F52352** | Cortex-M0+, 48 MHz, 128 KiB flash (512 B pages), 16 KiB RAM, LQFP64. The ROM bootloader reports ISP v103. |
| LED drivers | 3 x MBIA043GP | 16-channel constant-current drivers, daisy-chained. Chip 0 = red, 1 = green, 2 = blue. |
| SPI flash | 512 KiB, JEDEC ID read with 0x9F | The firmware also sends 0xAB (release from power-down) first. |
| Crystal | 8 MHz | PLL x6 = 48 MHz (`PLLCFGR = 0x03000000`), same as QMK's default HT32F52342/52 board. |

## Pin map

| Function | Pin(s) | Notes |
| --- | --- | --- |
| Matrix rows (scan order 0–8) | PB7, PB8, PB11, PD0, PB13, PB14, PB15, PC0, PC13 | Driven low one at a time |
| Matrix columns 0–7 | PA1–PA8 | Inputs with pull-ups; diodes are COL2ROW |
| MBIA SDI | PC12 | Data in to chip 0 |
| MBIA DCLK | PA14 | Bit-banged |
| MBIA LE | PA15 | Latch enable |
| MBIA GCLK | PC10 | Timer output (AFIO function 4, GPTM1 channel 0) |
| MBIA SDO | (PB0?) | The stock firmware never reads it. PB0 is assumed from the MasterKeys Pro S White. |
| MBIA power | PC11 | **Active low**: the firmware clears PC11 to turn the LEDs on |
| LED rows 0–7 | PC15, PC14, PB5, PB4, PB3, PB2, PD3, PD2 | **Active high**, push-pull. Switched in this order by the BFTM0 timer interrupt. |
| SPI flash CS | PA9 | Also the **BOOT** pin that the SEL2 pads pull low |
| SPI flash SCK / MOSI / MISO | PC2 / PC3 / PB6 | SPI1, AFIO function 5 |
| USB D− / D+ | PC6 / PC7 | |
| SWD | PA12 (SWCLK) / PA13 (SWDIO) | Locked while flash security is on |

> [!IMPORTANT]
> PB13 and PB14 don't come up as GPIO after reset. The stock firmware explicitly sets PB10–PB14 to AFIO function 1 (GPIO). QMK doesn't do this by itself, so without the `keyboard_pre_init_kb()` in `sk620.c`, matrix rows 4 and 5 stay dead.

## Key matrix

The stock keymap is a 9 x 8 table of HID usage codes in the firmware. Rows follow the scan order above, and columns are PA1–PA8.

| Row (pin) | PA1 | PA2 | PA3 | PA4 | PA5 | PA6 | PA7 | PA8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 (PB7) | Esc | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| 1 (PB8) | Tab | Q | W | E | R | T | Y | U |
| 2 (PB11) | Caps | A | S | D | F | G | H | J |
| 3 (PD0) | LShift | Z | X | C | V | B | N | M |
| 4 (PB13) | LCtrl | LWin | LAlt | 8 | 9 | 0 | - | Backspace |
| 5 (PB14) | Down | – | = | I | O | P | [ | \ (ANSI only) |
| 6 (PB15) | # (ISO) | Right | ] | K | L | ; | ' | Enter |
| 7 (PC0) | \| (ISO) | Up | Space | , | . | / | RShift | Left |
| 8 (PC13) | – | – | – | RAlt | Fn | RWin (not fitted on UK) | Del | – |

The ANSI and EU firmware builds use the same matrix. ANSI boards use row 5 column 7 (`\`), and ISO boards use row 6 column 0 (`#`) and row 7 column 0 (`|`).

## LED matrix

Each LED refresh interrupt does three things:

- It shifts 16 channels x 3 chips x 10 bits into the MBIA chain: 482 DCLK pulses per LED row, 18 of them with LE high.
- It latches the data, then switches one of the 8 LED rows on.
- The data for channel 15 is sent first. Within each channel the order is blue, then green, then red, so red ends up in chip 0, the one nearest the MCU.

That matches hansemro's `mbi` driver ordering. `g_mbi_channels` is therefore an identity map: chip *n* = colour *n*, output *c* = column *c*.

The firmware's LED position table (at 0xC946) maps LED row x MBIA channel to an LED index. 108 of the 128 positions are wired. An LED index *i* sits on a 17 x 7 grid at x = *i* / 7, y = *i* % 7. That grid is larger than the 65 keys, so it probably includes the edge lighting. `sk620.c` uses this table unchanged, and `keyboard.json` places LED *i* at (14·x, 10.7·y).

Which LED belongs to which key hasn't been worked out yet, so effects that react to key presses don't follow the keys.

## Bootloader and protection

- **SEL2 pads:** bridging them pulls PA9/BOOT low at reset, which starts the Holtek ROM ISP: USB `04d9:8010`, driven with `ht32-dfu-tool`. This ROM can't be erased, so the board can always be recovered.
- **Stock protection settings** (from `ht32-dfu-tool info`):
  - Flash security: on.
  - Option-byte protection: on.
  - Page protection: `0xfffff000`, so pages 0–11 are protected.
- **What that means:** neither ISP nor SWD can read the flash. Only a mass erase (`-m`) clears these settings, and it wipes the flash with them.
- **Stock flash layout:**
  - 0x0000–0x31FF: Cooler Master's in-application updater (IAP V1.0.1), not included in the updater package.
  - 0x3200 onwards: the application.
