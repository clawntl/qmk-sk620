"""Shared constants for SK620 firmware V1.01.00 (EU layout, black or white).

Addresses are where things sit in that build of the application, which is
linked at 0x3200. Other firmware versions will have them elsewhere.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_BASE = 0x3200
KEYMAP_ADDR = 0xCF1C      # 9 x 8 bytes, HID usage codes, matrix row-major
LED_ROW_TABLE = 0xC9D0    # 8 x {GPIO SRR address, mask}: LED row switches
LED_POS_TABLE = 0xC946    # 8 LED rows x 16 MBIA channels -> LED index (0xFF = none)
LED_ROW_PTR = 0x20000074  # RAM pointer the BFTM0 handler walks through LED_ROW_TABLE
VEC_SYSTICK = 15          # key scan runs in SysTick
VEC_BFTM0 = 33            # LED refresh runs in the BFTM0 timer interrupt

ROW_PINS = [('B', 7), ('B', 8), ('B', 11), ('D', 0), ('B', 13), ('B', 14), ('B', 15), ('C', 0), ('C', 13)]
COL_PINS = [('A', b) for b in range(1, 9)]


def load_app(path):
    data = open(path, 'rb').read()
    # Accept either the bare app (starts with its vector table) or a *_restore.bin (app at 0x3200).
    if len(data) > APP_BASE and data[:0xC0] == data[APP_BASE:APP_BASE + 0xC0]:
        data = data[APP_BASE:]
    return data
