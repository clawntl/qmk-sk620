#!/usr/bin/env python3
"""Show that PA9 frames the SPI flash commands (it is the flash chip-select).

usage: python3 spi_cs.py EU_Layout.bin
"""
import sys
from common import *
from ht32emu import Board
fw = load_app(sys.argv[1])
class C(Board):
    def w(self, uc, access, addr, size, value, ud):
        a = addr & ~3
        before = self.gpio['A']['DOUTR'] >> 9 & 1
        super().w(uc, access, addr, size, value, ud)
        after = self.gpio['A']['DOUTR'] >> 9 & 1
        if a == 0x40044010: self.ev.append(('spi', value & 0xFF))
        elif before != after: self.ev.append(('PA9', after))
bd = C(fw); bd.ev = []; bd.run(1_500_000)
grp = []; cur = None
for e in bd.ev:
    if e == ('PA9', 0): cur = []
    elif e == ('PA9', 1):
        if cur is not None: grp.append(cur)
        cur = None
    elif e[0] == 'spi' and cur is not None: cur.append(e[1])
print("PA9 low->high framed transactions:", len(grp))
print([bytes(g[:5]).hex() for g in grp[:12]])
