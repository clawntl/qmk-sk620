#!/usr/bin/env python3
"""Print the keymap, LED row table and LED position table from an SK620 app image.

usage: python3 dump_tables.py EU_Layout.bin
"""
import struct, sys
from common import *

HID = {0x04 + i: chr(ord('A') + i) for i in range(26)}
HID.update({0x1e + i: str((i + 1) % 10) for i in range(10)})
HID.update({0x28: 'Ent', 0x29: 'Esc', 0x2a: 'Bsp', 0x2b: 'Tab', 0x2c: 'Spc', 0x2d: '-', 0x2e: '=', 0x2f: '[',
            0x30: ']', 0x31: '\\', 0x32: '#(NUHS)', 0x33: ';', 0x34: "'", 0x35: '`', 0x36: ',', 0x37: '.',
            0x38: '/', 0x39: 'Caps', 0x4c: 'Del', 0x4f: 'Right', 0x50: 'Left', 0x51: 'Down', 0x52: 'Up',
            0x64: '|(NUBS)', 0xe0: 'LCtl', 0xe1: 'LSft', 0xe2: 'LAlt', 0xe3: 'LGui', 0xe4: 'RCtl', 0xe5: 'RSft',
            0xe6: 'RAlt', 0xe7: 'RGui', 0xd8: 'Fn', 0x00: '-'})
PORT = {0x400B0000: 'A', 0x400B2000: 'B', 0x400B4000: 'C', 0x400B6000: 'D'}

fw = load_app(sys.argv[1])
at = lambda a: a - APP_BASE

print("Keymap (rows = scan order", ' '.join(f"P{p}{b}" for p, b in ROW_PINS), "; cols = PA1..PA8)")
km = fw[at(KEYMAP_ADDR):at(KEYMAP_ADDR) + 72]
for r in range(9):
    print(f"  row {r} P{ROW_PINS[r][0]}{ROW_PINS[r][1]:<3}", ' '.join(f"{HID.get(b, hex(b)):>8}" for b in km[r * 8:r * 8 + 8]))

print("\nLED row switches (BFTM0 order; SRR = set high = row on)")
for i in range(8):
    a, v = struct.unpack_from('<II', fw, at(LED_ROW_TABLE) + 8 * i)
    print(f"  LED row {i}: P{PORT.get(a & ~0x1fff, '?')}{v.bit_length() - 1}")

print("\nLED position table (LED row x MBIA channel -> LED index, '.' = unused)")
t = fw[at(LED_POS_TABLE):at(LED_POS_TABLE) + 128]
for r in range(8):
    print(f"  {r}", ' '.join(f"{v:3d}" if v != 255 else '  .' for v in t[r * 16:r * 16 + 16]))
