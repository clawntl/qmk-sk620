// SK620 pin finder for QMK (HT32F52352)
// Types "PXn to PYm" into any text editor each time a key closes a path
// between two MCU pins. "to" means: PXn was driven low, PYm read low.
// Put every first pin in "rows", every second pin in "cols", and use
// "diode_direction": "COL2ROW".
// SPDX-License-Identifier: GPL-2.0-or-later

#include "quantum.h"

typedef struct {
    pin_t       pin;
    const char *name;
} pf_pin_t;

// ---------------------------------------------------------------------------
// Candidate pins. COMMENT OUT every pin you traced to something that is not
// the key matrix: the crystal, the SPI flash, the MBIA043 lines (SDI, DCLK,
// LE, GCLK, SDO), the MBIA power switch, the LED row transistors and SEL2.
// USB (PC6/PC7) and SWD (PA12/PA13) are already left out.
// ---------------------------------------------------------------------------
static const pf_pin_t pf_pins[] = {
    {A0, "PA0"},   {A1, "PA1"},   {A2, "PA2"},   {A3, "PA3"},
    {A4, "PA4"},   {A5, "PA5"},   {A6, "PA6"},   {A7, "PA7"},
    {A8, "PA8"},   {A9, "PA9"},   {A10, "PA10"}, {A11, "PA11"},
    /* A12 SWCLK, A13 SWDIO */    {A14, "PA14"}, {A15, "PA15"},
    {B0, "PB0"},   {B1, "PB1"},   {B2, "PB2"},   {B3, "PB3"},
    {B4, "PB4"},   {B5, "PB5"},   {B6, "PB6"},   {B7, "PB7"},
    {B8, "PB8"},   {B10, "PB10"}, {B11, "PB11"}, {B12, "PB12"},
    {B13, "PB13"}, {B14, "PB14"}, {B15, "PB15"},
    {C0, "PC0"},   {C1, "PC1"},   {C2, "PC2"},   {C3, "PC3"},
    {C4, "PC4"},   {C5, "PC5"},   /* C6 USBDM, C7 USBDP */
    {C8, "PC8"},   {C9, "PC9"},   {C10, "PC10"}, {C11, "PC11"},
    {C12, "PC12"}, {C13, "PC13"}, {C14, "PC14"}, {C15, "PC15"},
    {D0, "PD0"},   {D1, "PD1"},   {D2, "PD2"},   {D3, "PD3"},
};

#define PF_N ((uint8_t)ARRAY_SIZE(pf_pins))
_Static_assert(ARRAY_SIZE(pf_pins) <= 64, "pin list too long");

#define PF_IN_MODE (PAL_MODE_INPUT_PULLUP | PAL_MODE_HT32_AF(AFIO_GPIO))
#define PF_OUT_MODE (PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_HT32_AF(AFIO_GPIO))

static uint64_t pf_active[ARRAY_SIZE(pf_pins)]; // bit j set: i->j closed last scan
static uint64_t pf_idle_low;                     // pins low with nothing driven
static uint8_t  pf_last_i = 0xFF, pf_last_j = 0xFF;
static uint32_t pf_last_time;
static bool     pf_ready;

static void pf_all_inputs(void) {
    for (uint8_t i = 0; i < PF_N; i++) {
        palSetLineMode(pf_pins[i].pin, PF_IN_MODE);
    }
}

static void pf_type_pin_list(uint64_t mask) {
    for (uint8_t i = 0; i < PF_N; i++) {
        if (mask & (1ULL << i)) {
            send_string(pf_pins[i].name);
            send_string(" ");
        }
    }
}

void matrix_init_custom(void) {
    pf_all_inputs();
}

bool matrix_scan_custom(matrix_row_t current_matrix[]) {
    return false; // no real keys: all work happens in housekeeping
}

void housekeeping_task_kb(void) {
    if (!pf_ready) {
        // Give the host time to enumerate before typing anything.
        if (timer_read32() < 3000) return;
        wait_us(50);
        for (uint8_t i = 0; i < PF_N; i++) {
            if (!gpio_read_pin(pf_pins[i].pin)) pf_idle_low |= (1ULL << i);
        }
        send_string("pin finder ready, ");
        send_string(get_u8_str(PF_N, ' '));
        send_string(" pins\n");
        if (pf_idle_low) {
            send_string("ignored, low at rest: ");
            pf_type_pin_list(pf_idle_low);
            send_string("\n");
        }
        pf_ready = true;
        return;
    }

    for (uint8_t i = 0; i < PF_N; i++) {
        if (pf_idle_low & (1ULL << i)) continue;
        palSetLineMode(pf_pins[i].pin, PF_OUT_MODE);
        gpio_write_pin_low(pf_pins[i].pin);
        wait_us(20);

        uint64_t now = 0;
        for (uint8_t j = 0; j < PF_N; j++) {
            if (j == i || (pf_idle_low & (1ULL << j))) continue;
            if (!gpio_read_pin(pf_pins[j].pin)) now |= (1ULL << j);
        }
        palSetLineMode(pf_pins[i].pin, PF_IN_MODE);
        wait_us(20); // let the line pull back up before the next pin

        uint64_t fresh = now & ~pf_active[i];
        pf_active[i]   = now;
        for (uint8_t j = 0; j < PF_N && fresh; j++) {
            if (!(fresh & (1ULL << j))) continue;
            fresh &= ~(1ULL << j);
            // Skip switch bounce: same pair again within half a second.
            if (i == pf_last_i && j == pf_last_j && timer_elapsed32(pf_last_time) < 500) continue;
            pf_last_i    = i;
            pf_last_j    = j;
            pf_last_time = timer_read32();
            send_string(pf_pins[i].name);
            send_string(" to ");
            send_string(pf_pins[j].name);
            send_string("\n");
        }
    }
}
