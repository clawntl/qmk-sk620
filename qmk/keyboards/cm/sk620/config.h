// Cooler Master SK620 (HT32F52352). Every pin below was read out of
// Cooler Master's own SK620 firmware V1.01.00 (see readme.md).
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include_next "config.h"

#define MATRIX_IO_DELAY 5

#ifdef EEPROM_DRIVER
// GD25Q40-class SPI flash. CS is PA9 (also the SEL2/BOOT pin).
#    define EXTERNAL_FLASH_SPI_SLAVE_SELECT_PIN A9
#    define EXTERNAL_FLASH_CLOCK_DIVISOR 8
#    define EXTERNAL_FLASH_SIZE (512 * 1024)
#    define EXTERNAL_FLASH_PAGE_SIZE 256
#    define EXTERNAL_FLASH_SECTOR_SIZE 4096
#    define EXTERNAL_FLASH_BLOCK_SIZE (64 * 1024)
// Keep QMK's settings in the last 64 KiB block, away from stock profile data.
#    define WEAR_LEVELING_EXTERNAL_FLASH_BLOCK_OFFSET 7

#    define SPI_DRIVER SPID1
#    define SPI_SCK_PIN C2
#    define SPI_MOSI_PIN C3
#    define SPI_MISO_PIN B6
#    define SPI_CS_PIN A9
#endif

#ifdef RGB_MATRIX_ENABLE
#    define HAL_USE_PWM TRUE
#    define HAL_USE_GPT TRUE
#endif

/* 3x MBIA043GP: chip 0 = red, chip 1 = green, chip 2 = blue (stock shift order) */
#define MBI_NUM_CHANNELS 16
#define MBI_SHIFT_REG_WIDTH 10
#define MBI_DATA_LATCH 1
#define MBI_GLOBAL_LATCH 2
#define MBI_READ_CONFIGURATION 4
#define MBI_WRITE_CONFIGURATION 8
#define MBI_ENABLE_WRITE_CONFIGURATION 18
#define MBI_NUM_DRIVER 3
#define MBI_LED_DIRECTION ROW2COL
#define MBI_PWM_DRIVER PWMD_GPTM1
#define MBI_PWM_CHANNEL 0
#define MBI_TIMER_DRIVER GPTD_BFTM0
#define MBI_CONFIGURATION 0xc

#define MBI_GCLK_PIN C10
#define MBI_GCLK_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_TM))
#define MBI_DCLK_PIN A14
#define MBI_DCLK_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))
#define MBI_SDI_PIN C12
#define MBI_SDI_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))
#define MBI_SDO_PIN B0 /* not used by the stock firmware; same as Pro S White */
#define MBI_SDO_INPUT_MODE (PAL_MODE_INPUT | PAL_MODE_HT32_AF(AFIO_GPIO))
#define MBI_LE_PIN A15
#define MBI_LE_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))
/* LED supply on when PC11 is low (stock: LEDs on = clear PC11) */
#define MBI_POWER_ENABLE_PIN C11
#define MBI_POWER_ACTIVE_STATE ACTIVE_LOW
#define MBI_POWER_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))

/* 8 LED rows, switched active-high in this order by the stock BFTM0 interrupt */
#define MBI_LED_GPIO_PINS \
    { C15, C14, B5, B4, B3, B2, D3, D2 }
#define MBI_NUM_LED_GPIO_PINS 8
#define MBI_LED_GPIO_ACTIVE_STATE ACTIVE_HIGH
#define MBI_LED_GPIO_OUTPUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))

/* Firmware version for VIA (major << 16 | minor << 8 | patch), so apps like OpenPeriph can tell
 * which release is installed. build.sh writes sk620_version.h from the repository's VERSION. */
#if __has_include("sk620_version.h")
#    include "sk620_version.h"
#endif
