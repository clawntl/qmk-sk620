#!/usr/bin/env python3
"""Capture what the LED refresh interrupt (BFTM0) bit-bangs to the MBIA043 chain.

Prints, per LED row, the number of DCLK pulses and how many of them happen with
LE high. 482 clocks with 18 LE clocks = 16 channels x 3 chips x 10 bits, plus
16 data latches and one 2-clock global latch -> three MBIA043 chips.

usage: python3 led_stream.py EU_Layout.bin
"""
import struct, sys, collections
from common import *
from ht32emu import Board


class Cap(Board):
    def w(self, uc, access, addr, size, value, ud):
        a = addr & ~3
        if self.in_isr == 'BFTM0' and a == 0x400B0024 and value >> 14 & 1:   # PA14 (DCLK) set
            self.bits.append((self.gpio['C']['DOUTR'] >> 12 & 1, self.gpio['A']['DOUTR'] >> 15 & 1))
        super().w(uc, access, addr, size, value, ud)


fw = load_app(sys.argv[1])
bd = Cap(fw)
bd.bits = []
bd.run(3_000_000)
bd.mu.mem_write(LED_ROW_PTR, struct.pack('<I', LED_ROW_TABLE + 8 * 7))
toggles = collections.Counter()
prev = {p: bd.gpio[p]['DOUTR'] for p in 'ABCD'}
for row in range(8):
    bd.bits = []
    start = len(bd.log)
    bd.isr(VEC_BFTM0, tag='BFTM0')
    print(f"LED row call {row}: {len(bd.bits)} DCLK pulses, {sum(le for _, le in bd.bits)} with LE high")
    for ctx, p, r, v, dout in bd.log[start:]:
        ch = prev[p] ^ dout
        prev[p] = dout
        for b in range(16):
            if ch >> b & 1:
                toggles[f"P{p}{b}"] += 1
print("pins toggled by the LED interrupt:", ', '.join(f"{k}({v})" for k, v in toggles.most_common()))
