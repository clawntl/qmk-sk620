"""Minimal HT32F52352 board model for running Cooler Master SK620 firmware in Unicorn.

Models: GPIO ports A-D (direction, pulls, set/reset, input levels with an
optional closed key switch), AFIO pin functions, the clock controller ready
flags, SysTick counting, and a GD25Q40-style SPI flash on SPI1.

Note: flash chip-select is modelled on PB7. On the real board CS is PA9; with
PA9 modelled, the blank emulated flash sends the firmware down a path that
crashes the emulation. Nothing in the pin analysis depends on flash contents.
"""
import sys, struct, collections
from unicorn import *
from unicorn.arm_const import *

class Board:
    PORTS = {0x400B0000: 'A', 0x400B2000: 'B', 0x400B4000: 'C', 0x400B6000: 'D'}
    GREG = ['DIRCR','INER','PUR','PDR','ODR','DRVR','LOCKR','DINR','DOUTR','SRR','RR']
    def __init__(self, fw, switch=None):
        self.fw = fw; self.switch = switch  # switch: ((port,bit),(port,bit)) closed key
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        mu.mem_map(0, 0x40000); mu.mem_write(0x3200, fw)
        mu.mem_map(0x20000000, 0x10000); mu.mem_map(0x1FF00000, 0x10000)
        mu.mem_write(0x1FF00000, b'\xff' * 0x10000)
        mu.mem_map(0x40000000, 0x100000); mu.mem_map(0xE0000000, 0x100000)
        mu.mem_map(0xFFFF0000, 0x10000)  # magic return area
        self.regs = {}; self.gpio = {p: collections.defaultdict(int) for p in 'ABCD'}
        self.afio = {}; self.log = []; self.in_isr = None; self.tick = 0x100000
        self.flash = bytearray(b'\xff' * 0x80000); self.spi_q = collections.deque(); self.spi_cmd = []
        self.cs_low = False; self.dinr_reads = collections.Counter()
        mu.hook_add(UC_HOOK_MEM_WRITE, self.w, begin=0x40000000, end=0x400FFFFF)
        mu.hook_add(UC_HOOK_MEM_READ, self.r, begin=0x40000000, end=0x400FFFFF)
        mu.hook_add(UC_HOOK_MEM_READ, self.scs, begin=0xE000E000, end=0xE000EFFF)
        sp, rst = struct.unpack_from('<II', fw, 0)
        mu.reg_write(UC_ARM_REG_SP, sp); self.pc = rst
        self.vec = struct.unpack_from('<48I', fw, 0)
    # ---------- SPI flash model (GD25Q40 style) ----------
    def spi_byte(self, b):
        if not self.cs_low: return 0xFF
        c = self.spi_cmd; c.append(b)
        op = c[0]
        if op == 0x9F: return [0xFF, 0xC8, 0x40, 0x13][min(len(c)-1, 3)]
        if op == 0x05: return 0x00 if len(c) > 1 else 0xFF
        if op in (0x03, 0x0B):
            hdr = 4 if op == 0x03 else 5
            if len(c) > hdr:
                a = ((c[1] << 16) | (c[2] << 8) | c[3]) + (len(c) - hdr - 1)
                return self.flash[a % len(self.flash)]
            return 0xFF
        if op == 0x02 and len(c) > 4:
            a = ((c[1] << 16) | (c[2] << 8) | c[3]) + (len(c) - 5)
            self.flash[a % len(self.flash)] &= b
        return 0xFF
    def cs_edge(self, low):
        if self.cs_low and not low:
            c = self.spi_cmd
            if c and c[0] == 0x20 and len(c) >= 4:
                a = ((c[1] << 16) | (c[2] << 8) | c[3]) & ~0xFFF
                self.flash[a:a+0x1000] = b'\xff' * 0x1000
            self.spi_cmd = []
        if low and not self.cs_low: self.spi_cmd = []
        self.cs_low = low
    # ---------- GPIO electrical model ----------
    def pin_level(self, p, b):
        g = self.gpio[p]
        if g['DIRCR'] >> b & 1: return g['DOUTR'] >> b & 1
        if self.switch:
            for (p1, b1), (p2, b2) in (self.switch, self.switch[::-1]):
                if (p, b) == (p1, b1):
                    g2 = self.gpio[p2]
                    if g2['DIRCR'] >> b2 & 1 and not (g2['DOUTR'] >> b2 & 1): return 0
        if g['PDR'] >> b & 1: return 0
        return 1
    def w(self, uc, access, addr, size, value, ud):
        a = addr & ~3
        self.regs[a] = value
        for pb, pn in self.PORTS.items():
            if pb <= a < pb + 0x2C:
                r = self.GREG[(a - pb) // 4]; g = self.gpio[pn]
                if r == 'SRR':
                    g['DOUTR'] = (g['DOUTR'] | (value & 0xFFFF)) & ~((value >> 16) & 0xFFFF)
                elif r == 'RR':
                    g['DOUTR'] &= ~(value & 0xFFFF)
                else:
                    g[r] = value
                self.log.append((self.in_isr, pn, r, value, g['DOUTR']))
                if pn == 'B': self.cs_edge(not (g['DOUTR'] >> 7 & 1) if g['DIRCR'] >> 7 & 1 else False)
        if 0x40022020 <= a < 0x40022040:
            idx = (a - 0x40022020) // 4; self.afio[('ABCD'[idx // 2], idx % 2)] = value
        if a == 0x40044010:
            self.spi_q.append(self.spi_byte(value & 0xFF))
    def r(self, uc, access, addr, size, value, ud):
        a = addr & ~3; v = self.regs.get(a, 0)
        if 0x40088000 <= a < 0x40089000 and a in (0x40088004, 0x40088008): v = 0xFFFFFFFF
        for pb, pn in self.PORTS.items():
            if a == pb + 0x1C:
                self.dinr_reads[(self.in_isr, pn)] += 1
                v = sum(self.pin_level(pn, b) << b for b in range(16))
        if a == 0x40044010: v = self.spi_q.popleft() if self.spi_q else 0xFF
        if a == 0x4004401C: v = min(len(self.spi_q), 8) << 4
        if a == 0x40044014: v = 0x3 | (0x4 if self.spi_q else 0)
        uc.mem_write(a, struct.pack('<I', v))
    def scs(self, uc, access, addr, size, value, ud):
        a = addr & ~3
        if a == 0xE000E018:
            self.tick = (self.tick - 997) % 0x1000000; uc.mem_write(a, struct.pack('<I', self.tick))
        if a == 0xE000E014: uc.mem_write(a, struct.pack('<I', 0xFFFFFF))
    # ---------- run ----------
    def run(self, n):
        try:
            self.mu.emu_start(self.pc | 1, 0xFFFFFFFF, count=n)
        except UcError as e:
            print("main stopped:", e, hex(self.mu.reg_read(UC_ARM_REG_PC)))
        self.pc = self.mu.reg_read(UC_ARM_REG_PC)
    def isr(self, vec_index, n=200000, tag=None):
        mu = self.mu
        saved = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4,
                 UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
                 UC_ARM_REG_R11, UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_XPSR)]
        mu.reg_write(UC_ARM_REG_SP, saved[13] - 0x40)
        mu.reg_write(UC_ARM_REG_LR, 0xFFFF0001)
        self.in_isr = tag or vec_index
        try:
            mu.emu_start(self.vec[vec_index] | 1, 0xFFFF0000, count=n)
        except UcError as e:
            print("isr stopped:", e, hex(mu.reg_read(UC_ARM_REG_PC)))
        self.in_isr = None
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                         UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                         UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_XPSR), saved):
            mu.reg_write(r, v)

