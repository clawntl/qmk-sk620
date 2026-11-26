#!/usr/bin/env python3
"""Extract the keyboard firmware from a Cooler Master SK620 updater .exe.

usage: python3 cm_fw_extract.py SK620_xxx_FW_xxxx.exe OUTDIR

Reads the updater as data only (never runs it). The firmware images are
appended after the PE sections, encoded with the updater byte scrambler used
by Cooler Master/Vortex tools (see pok3rtool's decode_package_data) and then
XORed with the 52-byte CYKB key (pok3rtool's ProtoCYKB::decode_firmware).
Writes <layout>.bin (app, linked at 0x3200) and <layout>_restore.bin
(vector table at 0x0 + app at 0x3200, flashable with ht32-dfu-tool -m).
"""
import os, re, struct, sys

CYKB = [0xe7c29474, 0x79084b10, 0x53d54b0d, 0xfc1e8f32, 0x48e81a9b, 0x773c808e, 0xb7483552,
        0xd9cb8c76, 0x2a8c8bc6, 0x0967ada8, 0xd4520f5c, 0xd0c3279d, 0xeac091c5]
BASE = 0x3200


def decode_pkg(b):
    b = bytearray(b)
    for i in range(4, len(b), 5):
        b[i - 4], b[i] = b[i], b[i - 4]
    for i in range(1, len(b), 2):
        b[i - 1], b[i] = b[i], b[i - 1]
    for i in range(len(b)):
        x = b[i]
        b[i] = (((x - 7) << 4) + (x >> 4)) & 0xFF
    return bytes(b)


def unxor(b):
    n = len(b) // 4
    w = struct.unpack('<%dI' % n, b[:n * 4])
    return struct.pack('<%dI' % n, *[w[i] ^ CYKB[i % 13] for i in range(n)]) + b[n * 4:]


def pe_end(d):
    pe = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = struct.unpack_from('<H', d, pe + 20)[0]
    sec = pe + 24 + opt
    return max(struct.unpack_from('<I', d, sec + 40 * i + 20)[0] + struct.unpack_from('<I', d, sec + 40 * i + 16)[0]
               for i in range(nsec))


def main(exe, outdir):
    d = open(exe, 'rb').read()
    ov = d[pe_end(d):]
    # Find the decoded string table: it lists each layout as <fw len><info len><UTF-16 name>.
    def entries(s):
        out = []
        for m in re.finditer(rb'((?:[\x20-\x7e]\x00){2,32}?L\x00a\x00y\x00o\x00u\x00t\x00)', s):
            if m.start() < 8:
                continue
            fwl, infl = struct.unpack_from('<II', s, m.start() - 8)
            if 4096 <= fwl <= 0x20000 and 0 < infl <= 4096:
                out.append((m.group(1).decode('utf-16le').replace(' ', '_'), fwl, infl))
        return out
    layouts = None
    for slen in range(0x200, min(0x4000, len(ov))):
        if entries(decode_pkg(d[-slen:])):
            # Same alignment (period 10), longer window: picks up every layout entry.
            big = slen + 10 * ((min(0x4000, len(ov)) - slen) // 10)
            layouts = entries(decode_pkg(d[-big:]))
            break
    if not layouts:
        sys.exit("no layout table found: not a supported updater")
    os.makedirs(outdir, exist_ok=True)
    pos = 0
    for name, fwl, infl in layouts:
        app = unxor(decode_pkg(ov[pos:pos + fwl]))
        pos += fwl + infl
        sp, rst = struct.unpack_from('<II', app)
        ok = 0x20000000 < sp <= 0x20004000 and rst & 1 and BASE < rst < BASE + len(app)
        print(f"{name}: {fwl} bytes, SP {sp:#x}, reset {rst:#x}, {'OK' if ok else 'NOT A VALID IMAGE'}")
        if not ok:
            continue
        open(os.path.join(outdir, name + '.bin'), 'wb').write(app)
        img = bytearray(b'\xff' * BASE)
        img[:0xC0] = app[:0xC0]
        open(os.path.join(outdir, name + '_restore.bin'), 'wb').write(bytes(img) + app)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
