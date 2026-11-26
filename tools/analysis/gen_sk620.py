#!/usr/bin/env python3
"""Generate qmk/keyboards/cm/sk620/keyboard.json and the default keymap from the stock firmware.

usage: python3 gen_sk620.py EU_Layout.bin OUTDIR

Matrix pins and keycodes per matrix position come from the firmware; physical
x/y and the Fn layer are hand-written below (from the keycap legends).
"""
import json, os, struct, sys
from common import *
OUT = os.path.join(sys.argv[2], "")
fw = load_app(sys.argv[1]); B = APP_BASE
led_tab = fw[LED_POS_TABLE - B:LED_POS_TABLE - B + 128]
# (label, keycode, (row, col), x, y, w, h)  -- matrix + keycodes from the stock EU firmware keymap,
# physical x/y are a best guess of the SK620 UK ISO layout.
K = [
 ("Esc","KC_ESC",(0,0),0,0),("1","KC_1",(0,1),1,0),("2","KC_2",(0,2),2,0),("3","KC_3",(0,3),3,0),
 ("4","KC_4",(0,4),4,0),("5","KC_5",(0,5),5,0),("6","KC_6",(0,6),6,0),("7","KC_7",(0,7),7,0),
 ("8","KC_8",(4,3),8,0),("9","KC_9",(4,4),9,0),("0","KC_0",(4,5),10,0),("-","KC_MINS",(4,6),11,0),
 ("=","KC_EQL",(5,2),12,0),("Backspace","KC_BSPC",(4,7),13,0,2),
 ("Tab","KC_TAB",(1,0),0,1,1.5),("Q","KC_Q",(1,1),1.5,1),("W","KC_W",(1,2),2.5,1),("E","KC_E",(1,3),3.5,1),
 ("R","KC_R",(1,4),4.5,1),("T","KC_T",(1,5),5.5,1),("Y","KC_Y",(1,6),6.5,1),("U","KC_U",(1,7),7.5,1),
 ("I","KC_I",(5,3),8.5,1),("O","KC_O",(5,4),9.5,1),("P","KC_P",(5,5),10.5,1),("[","KC_LBRC",(5,6),11.5,1),
 ("]","KC_RBRC",(6,2),12.5,1),("Enter","KC_ENT",(6,7),13.75,1,1.25,2),
 ("Caps","KC_CAPS",(2,0),0,2,1.75),("A","KC_A",(2,1),1.75,2),("S","KC_S",(2,2),2.75,2),("D","KC_D",(2,3),3.75,2),
 ("F","KC_F",(2,4),4.75,2),("G","KC_G",(2,5),5.75,2),("H","KC_H",(2,6),6.75,2),("J","KC_J",(2,7),7.75,2),
 ("K","KC_K",(6,3),8.75,2),("L","KC_L",(6,4),9.75,2),(";","KC_SCLN",(6,5),10.75,2),("'","KC_QUOT",(6,6),11.75,2),
 ("#","KC_NUHS",(6,0),12.75,2),
 ("LShift","KC_LSFT",(3,0),0,3),("\\","KC_NUBS",(7,0),1,3),("Z","KC_Z",(3,1),2,3),("X","KC_X",(3,2),3,3),
 ("C","KC_C",(3,3),4,3),("V","KC_V",(3,4),5,3),("B","KC_B",(3,5),6,3),("N","KC_N",(3,6),7,3),
 ("M","KC_M",(3,7),8,3),(",","KC_COMM",(7,3),9,3),(".","KC_DOT",(7,4),10,3),("/","KC_SLSH",(7,5),11,3),
 ("RShift","KC_RSFT",(7,6),12,3),("Up","KC_UP",(7,1),13,3),("Del","KC_DEL",(8,6),14,3),
 ("LCtrl","KC_LCTL",(4,0),0,4,1.25),("LWin","KC_LGUI",(4,1),1.25,4,1.25),("LAlt","KC_LALT",(4,2),2.5,4,1.25),
 ("Space","KC_SPC",(7,2),3.75,4,6.25),("RAlt","KC_RALT",(8,3),10,4),("Fn","MO(1)",(8,4),11,4),
 ("Left","KC_LEFT",(7,7),12,4),("Down","KC_DOWN",(5,0),13,4),("Right","KC_RGHT",(6,1),14,4),
]
FN = {"KC_ESC":"KC_GRV","KC_BSPC":"KC_EJCT","KC_1":"KC_F1","KC_2":"KC_F2","KC_3":"KC_F3","KC_4":"KC_F4","KC_5":"KC_F5","KC_6":"KC_F6",
      "KC_7":"KC_F7","KC_8":"KC_F8","KC_9":"KC_F9","KC_0":"KC_F10","KC_MINS":"KC_F11","KC_EQL":"KC_F12",
      "KC_U":"KC_PSCR","KC_I":"KC_SCRL","KC_O":"KC_PAUS","KC_P":"KC_INS","KC_LBRC":"KC_HOME","KC_RBRC":"KC_PGUP",
      "KC_SCLN":"KC_END","KC_QUOT":"KC_PGDN",
      "KC_J":"KC_MPLY","KC_K":"KC_MPRV","KC_L":"KC_MNXT","KC_COMM":"KC_VOLD","KC_DOT":"KC_VOLU","KC_SLSH":"KC_MUTE",
      "KC_RSFT":"GU_TOGG","KC_TAB":"RM_TOGG","KC_UP":"RM_VALU","KC_DOWN":"RM_VALD","KC_LEFT":"RM_PREV","KC_RGHT":"RM_NEXT",
      "KC_Q":"RM_HUEU","KC_W":"RM_SATU","KC_E":"RM_SPDU","KC_A":"RM_HUED","KC_S":"RM_SATD","KC_D":"RM_SPDD",
      "KC_B":"QK_BOOT"}
seen = set()
layout = []
for k in K:
    label, code, rc = k[0], k[1], k[2]
    assert rc not in seen; seen.add(rc)
    e = {"label": label, "matrix": list(rc), "x": k[3], "y": k[4]}
    if len(k) > 5 and k[5] != 1: e["w"] = k[5]
    if len(k) > 6: e["h"] = k[6]
    layout.append(e)
n_led = max(v for v in led_tab if v != 255) + 1
rgb_layout = [{"x": (i // 7) * 14, "y": round((i % 7) * 64 / 6), "flags": 4} for i in range(n_led)]
kb = {
  "manufacturer": "Cooler Master", "keyboard_name": "SK620", "maintainer": "clawntl",
  "processor": "HT32F52352", "board": "GENERIC_HT32_F52342_52", "bootloader": "ht32-dfu",
  "build": {"firmware_format": "bin"},
  "diode_direction": "COL2ROW",
  "matrix_pins": {"rows": ["B7","B8","B11","D0","B13","B14","B15","C0","C13"],
                  "cols": ["A1","A2","A3","A4","A5","A6","A7","A8"]},
  "usb": {"vid": "0xFEED", "pid": "0x0620", "device_version": "1.0.0"},
  "features": {"bootmagic": True, "extrakey": True, "mousekey": False, "nkro": True, "rgb_matrix": True, "command": False, "console": False},
  "bootmagic": {"matrix": [0, 0]},
  "eeprom": {"driver": "wear_leveling", "wear_leveling": {"driver": "spi_flash", "backing_size": 8192}},
  "rgb_matrix": {"driver": "mbi", "sleep": True, "max_brightness": 200,
                 "animations": {"alphas_mods": True, "breathing": True, "band_val": True, "cycle_all": True,
                                "cycle_left_right": True, "cycle_up_down": True, "cycle_out_in": True,
                                "rainbow_moving_chevron": True, "dual_beacon": True, "rainbow_beacon": True,
                                "raindrops": True, "jellybean_raindrops": True, "pixel_rain": True},
                 "layout": rgb_layout},
  "layouts": {"LAYOUT_iso": {"layout": layout}},
}
os.makedirs(OUT + 'keymaps/default', exist_ok=True)
json.dump(kb, open(OUT + 'keyboard.json', 'w'), indent=4)
rows = {}
for k in K: rows.setdefault(k[4], []).append(k[1])
def fmt(m): return ",\n".join("        " + ", ".join(m(c) for c in rows[y]) for y in sorted(rows))
open(OUT + 'keymaps/default/keymap.c', 'w').write(
 "// SK620 UK ISO default keymap. Base layer = Cooler Master's stock EU keymap.\n"
 "#include QMK_KEYBOARD_H\n#include \"keymap_uk.h\"\n\n"
 "const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {\n"
 f"    [0] = LAYOUT_iso(\n{fmt(lambda c: c)}\n    ),\n"
 f"    [1] = LAYOUT_iso(\n{fmt(lambda c: FN.get(c, '_______'))}\n    ),\n}};\n")
# LED table straight from the stock firmware (LED row x MBIA channel -> LED index)
rows_c = []
for r in range(8):
    rows_c.append("    { " + ", ".join(f"{v:3d}" if v != 255 else "NLD" for v in led_tab[r*16:r*16+16]) + " },")
print("g_mbi_led_matrix_co (should match sk620.c):")
print("\n".join(rows_c))
print(len(K), "keys;", n_led, "LED slots;", sum(1 for v in led_tab if v != 255), "LEDs wired")
