// SK620 LED mapper: finds which LED sits under which key. Not a keymap for daily use.
//
// The firmware lights one LED at a time (bright white). You tap the key under it.
//   tap the lit key           -> recorded, the next LED lights up; done keys turn dim green
//   nothing lit? hold any key -> after 0.6 s that LED is recorded as "no LED", next one lights
//   two keys at once          -> undo: go back one step
//   key flashes red           -> that key was already recorded for an earlier LED;
//                                tap it again straight away if it really has a second LED
// When every LED has been done, all recorded keys glow green (review mode):
//   press a key               -> its LED turns white, so you can check it
//   hold Enter for 1 s        -> types the result into whatever text editor has focus
//
// No key presses reach the PC except the typed result. Guide: docs/led-mapping.md
#include QMK_KEYBOARD_H
#include <string.h>
#include "mbi.h"

#define HOLD_MS 600
#define FLASH_MS 400
#define NO_KEY 0xFF

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    // Only used to recognise Enter and to list which keys exist (Fn is KC_APP here; nothing is sent).
    [0] = LAYOUT_iso(
        KC_ESC, KC_1, KC_2, KC_3, KC_4, KC_5, KC_6, KC_7, KC_8, KC_9, KC_0, KC_MINS, KC_EQL, KC_BSPC,
        KC_TAB, KC_Q, KC_W, KC_E, KC_R, KC_T, KC_Y, KC_U, KC_I, KC_O, KC_P, KC_LBRC, KC_RBRC, KC_ENT,
        KC_CAPS, KC_A, KC_S, KC_D, KC_F, KC_G, KC_H, KC_J, KC_K, KC_L, KC_SCLN, KC_QUOT, KC_NUHS,
        KC_LSFT, KC_NUBS, KC_Z, KC_X, KC_C, KC_V, KC_B, KC_N, KC_M, KC_COMM, KC_DOT, KC_SLSH, KC_RSFT, KC_UP, KC_DEL,
        KC_LCTL, KC_LGUI, KC_LALT, KC_SPC, KC_RALT, KC_APP, KC_LEFT, KC_DOWN, KC_RGHT
    ),
};

static uint8_t  leds[RGB_MATRIX_LED_COUNT];   // LED indices wired in g_mbi_led_matrix_co, ascending
static uint8_t  n_leds;
static uint8_t  assigned[RGB_MATRIX_LED_COUNT]; // per step: (row << 4) | col, or NO_KEY
static uint8_t  step;                         // index into leds[] of the LED being asked about
static bool     review;
static uint8_t  down_count;
static bool     chord;     // two keys went down together; ignore input until all are released
static bool     consumed;  // the held key already did its hold action
static keypos_t held;
static uint16_t held_since;
static uint16_t flash_since;
static uint8_t  flash_led = NO_LED;
static uint8_t  dup_code  = NO_KEY; // key that just flashed red; a second tap records it anyway

static uint8_t pos_code(keypos_t k) {
    return (uint8_t)((k.row << 4) | k.col);
}

void keyboard_post_init_user(void) {
    bool wired[RGB_MATRIX_LED_COUNT] = {0};
    for (uint8_t r = 0; r < MBI_NUM_LED_GPIO_PINS; r++) {
        for (uint8_t c = 0; c < MBI_NUM_CHANNELS; c++) {
            uint8_t v = g_mbi_led_matrix_co[r][c];
            if (v < RGB_MATRIX_LED_COUNT) wired[v] = true;
        }
    }
    for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        if (wired[i]) leds[n_leds++] = i;
    }
    memset(assigned, NO_KEY, sizeof(assigned));
    // Don't touch the saved lighting settings; just make sure rendering runs.
    rgb_matrix_enable_noeeprom();
    rgb_matrix_mode_noeeprom(RGB_MATRIX_SOLID_COLOR);
    rgb_matrix_sethsv_noeeprom(0, 0, 0);
}

static void advance(void) {
    step++;
    if (step >= n_leds) review = true;
}

static void go_back(void) {
    dup_code = NO_KEY;
    review   = false;
    if (step > 0) step--;
    assigned[step] = NO_KEY;
}

static void record_key(keypos_t k) {
    uint8_t code = pos_code(k);
    if (code != dup_code) {
        for (uint8_t i = 0; i < step; i++) {
            if (assigned[i] == code) {
                flash_led   = leds[i];
                flash_since = timer_read();
                dup_code    = code;
                return;
            }
        }
    }
    dup_code       = NO_KEY;
    assigned[step] = code;
    advance();
}

// ---- typing the result -------------------------------------------------------------------
// Only characters that are on the same keys in UK and US layouts: a-z 0-9 space , - newline.
static char   out[2048];
static size_t out_len;

static void put(const char *s) {
    while (*s && out_len < sizeof(out) - 1) out[out_len++] = *s++;
    out[out_len] = 0;
}

static void put_u8(uint8_t v) {
    char b[4];
    uint8_t n = 0;
    do {
        b[n++] = '0' + v % 10;
        v /= 10;
    } while (v);
    char s[4];
    for (uint8_t i = 0; i < n; i++) s[i] = b[n - 1 - i];
    s[n] = 0;
    put(s);
}

static void type_result(void) {
    out_len = 0;
    out[0]  = 0;
    put("\nsk620 ledmap 1\nleds ");
    put_u8(n_leds);
    put("\n");
    for (uint8_t i = 0; i < n_leds; i++) {
        if (assigned[i] == NO_KEY) continue;
        put_u8(leds[i]);
        put(" ");
        put_u8(assigned[i] >> 4);
        put(",");
        put_u8(assigned[i] & 0x0F);
        put("\n");
    }
    put("dark");
    for (uint8_t i = 0; i < n_leds; i++) {
        if (assigned[i] != NO_KEY) continue;
        put(" ");
        put_u8(leds[i]);
    }
    put("\nmissing");
    for (uint8_t r = 0; r < MATRIX_ROWS; r++) {
        for (uint8_t c = 0; c < MATRIX_COLS; c++) {
            keypos_t k = {.row = r, .col = c};
            if (keymap_key_to_keycode(0, k) == KC_NO) continue;
            bool found = false;
            for (uint8_t i = 0; i < n_leds; i++) {
                if (assigned[i] == pos_code(k)) found = true;
            }
            if (!found) {
                put(" ");
                put_u8(r);
                put(",");
                put_u8(c);
            }
        }
    }
    put("\nend\n");
    send_string_with_delay(out, 8);
}

// ---- input --------------------------------------------------------------------------------
bool process_record_user(uint16_t keycode, keyrecord_t *record) {
    keypos_t k = record->event.key;
    if (record->event.pressed) {
        down_count++;
        if (down_count >= 2) {
            if (!chord) {
                chord = true;
                go_back();
            }
            return false;
        }
        held       = k;
        held_since = timer_read();
        consumed   = false;
    } else {
        if (down_count) down_count--;
        if (chord) {
            if (down_count == 0) chord = false;
            return false;
        }
        if (!consumed && KEYEQ(k, held) && !review) record_key(k);
    }
    return false; // nothing reaches the PC
}

void housekeeping_task_user(void) {
    if (down_count != 1 || chord || consumed || timer_elapsed(held_since) < HOLD_MS) return;
    consumed = true;
    if (!review) {
        dup_code       = NO_KEY;
        assigned[step] = NO_KEY; // "nothing lit here"
        advance();
    } else if (keymap_key_to_keycode(0, held) == KC_ENT) {
        type_result();
    }
}

// ---- lights -------------------------------------------------------------------------------
static uint8_t led_for(uint8_t code) {
    for (uint8_t i = 0; i < n_leds; i++) {
        if (assigned[i] == code) return leds[i];
    }
    return NO_LED;
}

bool rgb_matrix_indicators_user(void) {
    rgb_matrix_set_color_all(0, 0, 0);
    for (uint8_t i = 0; i < step && i < n_leds; i++) {
        if (assigned[i] != NO_KEY) rgb_matrix_set_color(leds[i], 0, 40, 0);
    }
    if (review) {
        if (down_count == 1 && !chord) {
            uint8_t led = led_for(pos_code(held));
            if (led != NO_LED) rgb_matrix_set_color(led, 200, 200, 200);
        }
        return false;
    }
    rgb_matrix_set_color(leds[step], 200, 200, 200);
    if (flash_led != NO_LED) {
        if (timer_elapsed(flash_since) < FLASH_MS) {
            rgb_matrix_set_color(flash_led, 200, 0, 0);
        } else {
            flash_led = NO_LED;
        }
    }
    return false;
}
