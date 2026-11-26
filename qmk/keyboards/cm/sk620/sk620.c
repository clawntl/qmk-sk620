// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"

// The stock firmware switches PB10-PB14 to GPIO (AFIO function 1) before
// scanning. PB13/PB14 (matrix rows 4 and 5) don't default to GPIO, so set the
// GPIO function on every matrix pin once; QMK's later mode changes keep it.
static const pin_t sk620_matrix_pins[] = {B7, B8, B11, D0, B13, B14, B15, C0, C13,
                                          A1, A2, A3, A4, A5, A6, A7, A8};

void keyboard_pre_init_kb(void) {
    for (uint8_t i = 0; i < ARRAY_SIZE(sk620_matrix_pins); i++) {
        palSetLineMode(sk620_matrix_pins[i], PAL_MODE_INPUT_PULLUP | PAL_MODE_HT32_AF(AFIO_GPIO));
    }
    keyboard_pre_init_user();
}

#ifdef RAW_ENABLE
#    include <string.h>
#    include "raw_hid.h"
// tools/flash/sk620_flash.py sends this over QMK's raw HID interface to restart
// the keyboard into the ROM bootloader, so flashing needs no Fn+B or tweezers.
static const uint8_t sk620_boot_magic[] = {0x5B, 'S', 'K', '6', '2', '0', '-', 'B', 'O', 'O', 'T', 'L', 'O', 'A', 'D', 'E', 'R'};

static bool sk620_handle_raw(uint8_t *data, uint8_t length) {
    if (length >= sizeof(sk620_boot_magic) && memcmp(data, sk620_boot_magic, sizeof(sk620_boot_magic)) == 0) {
        reset_keyboard();
        return true;
    }
    return false;
}

#    ifdef VIA_ENABLE
void raw_hid_receive_kb(uint8_t *data, uint8_t length) {
    sk620_handle_raw(data, length);
}
#    else
void raw_hid_receive(uint8_t *data, uint8_t length) {
    sk620_handle_raw(data, length);
}
#    endif
#endif

#ifdef RGB_MATRIX_ENABLE
#    include "mbi.h"

#    ifndef NLD
#        define NLD NO_LED
#    endif

// Each MBIA043 output drives one LED column in one colour (stock firmware order).
#    define R_(c) {MBI_RED_CH, c}
#    define G_(c) {MBI_GREEN_CH, c}
#    define B_(c) {MBI_BLUE_CH, c}
// clang-format off
const mbi_channel_t g_mbi_channels[MBI_NUM_DRIVER][MBI_NUM_CHANNELS] = {
    { R_(0), R_(1), R_(2), R_(3), R_(4), R_(5), R_(6), R_(7), R_(8), R_(9), R_(10), R_(11), R_(12), R_(13), R_(14), R_(15) },
    { G_(0), G_(1), G_(2), G_(3), G_(4), G_(5), G_(6), G_(7), G_(8), G_(9), G_(10), G_(11), G_(12), G_(13), G_(14), G_(15) },
    { B_(0), B_(1), B_(2), B_(3), B_(4), B_(5), B_(6), B_(7), B_(8), B_(9), B_(10), B_(11), B_(12), B_(13), B_(14), B_(15) },
};

// LED row x MBIA column -> LED index. Copied from the stock firmware's table
// at 0xC946. Index i sits at grid position x = i / 7, y = i % 7.
const uint8_t g_mbi_led_matrix_co[MBI_NUM_LED_GPIO_PINS][MBI_NUM_CHANNELS] = {
    {   8,   9,  10,  11,  12,  40, 101, NLD, NLD,  84,  70, 116,   7, NLD,  41, NLD },
    {  15,  23,  24,  25,  19, 103, 110, 102, NLD,  91,  63,  97,   1,  62,  34, NLD },
    {  22,  30,  31,  32,  26,  92, 100,  54, NLD, 105,  35, 115,   2, NLD,  48, NLD },
    {  29,  37,  38,  39,  64,  72,  73,  74,  82,  98,  49, 118,   3,  76,  20, NLD },
    {  36,  44,  45,  46,  71,  79,  80,  81, 106,  77,  56, 114,   6, NLD,  27, NLD },
    {  43,  51,  52,  53,  78,  86,  87,  88,  89, 113,  21, 111,  14,  83,  55, NLD },
    {  50,  58,  59,  60,  85,  93,  94,  95, 109, 112,  28, 104,   4, NLD, NLD, NLD },
    {  57,  65,  66,  67,  18, 107, 108, NLD,  96, NLD,  42,  90,   0,  69, NLD, NLD },
};
// clang-format on
#endif
