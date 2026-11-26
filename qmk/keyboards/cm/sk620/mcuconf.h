// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// 8 MHz crystal, PLL x6 = 48 MHz: same as the stock firmware's CKCU setup.
#include_next <mcuconf.h>

#ifdef RGB_MATRIX_ENABLE
#    undef HT32_PWM_USE_GPTM1
#    define HT32_PWM_USE_GPTM1 TRUE
#    undef HT32_GPT_USE_BFTM0
#    define HT32_GPT_USE_BFTM0 TRUE
#endif

#ifdef EEPROM_DRIVER
#    undef HT32_SPI_USE_SPI1
#    define HT32_SPI_USE_SPI1 TRUE
#endif
