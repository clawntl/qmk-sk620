#!/usr/bin/env python3
"""Find the key matrix by 'pressing' every row/column pair in the emulator.

Boots the firmware, then for each candidate pair closes a switch between the two
pins, runs the SysTick key scan a few times, and reports which RAM bit changed.
One distinct bit per pair = a real matrix position.

usage: python3 matrix_scan.py EU_Layout.bin   (takes a few seconds)
"""
import copy, sys
from common import *
from ht32emu import Board

fw = load_app(sys.argv[1])
bd = Board(fw)
bd.run(3_000_000)
ram0 = bytes(bd.mu.mem_read(0x20000000, 0x4000))
state = copy.deepcopy({k: getattr(bd, k) for k in ('regs', 'gpio', 'afio', 'tick')})


def scan(switch, n=12):
    bd.mu.mem_write(0x20000000, ram0)
    for k, v in copy.deepcopy(state).items():
        setattr(bd, k, v)
    bd.switch = switch
    for _ in range(n):
        bd.isr(VEC_SYSTICK, tag='SysTick')
    return bytes(bd.mu.mem_read(0x20000000, 0x4000))


base, base2 = scan(None), scan(None, 13)
noise = {i for i in range(len(base)) if base[i] != base2[i]}
for rp in ROW_PINS:
    out = []
    for cp in COL_PINS:
        m = scan((rp, cp))
        d = [(i, base[i] ^ m[i]) for i in range(len(m)) if m[i] != base[i] and i not in noise]
        out.append(f"P{cp[0]}{cp[1]}:{'+'.join(f'{0x20000000 + i:#x}/{x:#04x}' for i, x in d) or 'none'}")
    print(f"P{rp[0]}{rp[1]}", ' '.join(out))
