#!/usr/bin/env python3
"""Apply an LED map typed by the ledmap firmware to the SK620 keyboard definition.

    python3 tools/ledmap/apply_ledmap.py tools/ledmap/sk620_iso_ledmap.txt

Rewrites, in qmk/keyboards/cm/sk620/:
  keyboard.json  rgb_matrix.layout: one entry per fitted LED, in physical order (row by row,
                 left to right), with its key's matrix position, x/y from the key's centre and
                 a flag (1 = modifier, 4 = normal key).
  sk620.c        g_mbi_led_matrix_co: stock LED numbers replaced by the new indices; positions
                 the map marks as dark become NLD and are no longer driven.

A key with several LEDs (the space bar has three) gets them spread across its width. The LED whose
stock grid column is closest to the key's centre goes in the middle and carries the matrix
position, since QMK links each key to one LED.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KBDIR = ROOT / "qmk/keyboards/cm/sk620"
GRID_ROWS = 7  # stock firmware: LED n sits at grid column n // 7, row n % 7


def parse_map(path):
    text = pathlib.Path(path).read_text()
    if "sk620 ledmap 1" not in text or "\nend" not in text:
        sys.exit(f"{path}: not a complete 'sk620 ledmap 1' result")
    leds, dark = {}, set()
    for line in text.splitlines():
        m = re.fullmatch(r"\s*(\d+) (\d+),(\d+)\s*", line)
        if m:
            leds[int(m[1])] = (int(m[2]), int(m[3]))
        elif line.startswith("dark"):
            dark = {int(v) for v in line.split()[1:]}
        elif line.startswith("missing") and line.split()[1:]:
            sys.exit(f"{path}: keys were not mapped: {' '.join(line.split()[1:])}")
    return leds, dark


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    leds, dark = parse_map(sys.argv[1])

    kb_path = KBDIR / "keyboard.json"
    kb = json.loads(kb_path.read_text())
    keys = kb["layouts"]["LAYOUT_iso"]["layout"]

    def centre(k):
        return k["x"] + k.get("w", 1) / 2, k["y"] + k.get("h", 1) / 2

    cxs = [centre(k)[0] for k in keys]
    cys = [centre(k)[1] for k in keys]
    minx, maxx, miny, maxy = min(cxs), max(cxs), min(cys), max(cys)

    def scale(x, y):
        return round((x - minx) / (maxx - minx) * 224), round((y - miny) / (maxy - miny) * 64)

    by_key = {}
    for led, pos in leds.items():
        by_key.setdefault(pos, []).append(led)

    entries = []  # (stock led, layout entry)
    for k in sorted(keys, key=lambda k: (k["y"], k["x"])):
        pos = tuple(k["matrix"])
        stock = by_key.get(pos, [])
        if not stock:
            sys.exit(f"key {k.get('label')} {pos} has no LED in the map")
        cx, cy = centre(k)
        label = k.get("label", "")
        flags = 1 if len(label) > 1 and label != "Space" else 4
        if len(stock) == 1:
            x, y = scale(cx, cy)
            entries.append((stock[0], {"matrix": list(pos), "x": x, "y": y, "flags": flags}))
            continue
        # several LEDs under one key: middle one by stock grid column, others alternate left/right
        col = round(cx)
        stock = sorted(stock, key=lambda n: (abs(n // GRID_ROWS - col), n))
        main_led, rest = stock[0], stock[1:]
        order = rest[0::2][::-1] + [main_led] + rest[1::2]
        w = k.get("w", 1)
        for i, n in enumerate(order):
            x, y = scale(k["x"] + w * (i + 0.5) / len(order), cy)
            e = {"x": x, "y": y, "flags": flags}
            if n == main_led:
                e = {"matrix": list(pos), **e}
            entries.append((n, e))

    new_index = {stock: i for i, (stock, _) in enumerate(entries)}
    kb["rgb_matrix"]["layout"] = [e for _, e in entries]
    text = json.dumps(kb, indent=4)
    # one LED per line
    text = re.sub(r"\{\s+(\"matrix\": \[)\s*(\d+),\s*(\d+)\s*\],\s+\"x\": (\d+),\s+\"y\": (\d+),\s+\"flags\": (\d+)\s+\}",
                  r'{"matrix": [\2, \3], "x": \4, "y": \5, "flags": \6}', text)
    text = re.sub(r"\{\s+\"x\": (\d+),\s+\"y\": (\d+),\s+\"flags\": (\d+)\s+\}",
                  r'{"x": \1, "y": \2, "flags": \3}', text)
    kb_path.write_text(text + "\n")

    # LED driver table
    c_path = KBDIR / "sk620.c"
    src = c_path.read_text()
    m = re.search(r"(const uint8_t g_mbi_led_matrix_co\[[^\]]+\]\[[^\]]+\] = \{\n)(.*?)(\n\};)", src, re.S)
    if not m:
        sys.exit("g_mbi_led_matrix_co not found in sk620.c")
    rows = []
    for line in m[2].splitlines():
        vals = re.findall(r"\d+|NLD", line)
        if not vals:
            continue
        out = []
        for v in vals:
            if v == "NLD":
                out.append("NLD")
            elif int(v) in new_index:
                out.append(str(new_index[int(v)]))
            elif int(v) in dark:
                out.append("NLD")
            else:
                sys.exit(f"stock LED {v} is neither mapped nor dark")
        rows.append("    { " + ", ".join(f"{x:>3}" for x in out) + " },")
    src = src[: m.start(2)] + "\n".join(rows) + src[m.end(2):]
    src = re.sub(r"// LED row x MBIA column -> LED index\..*?\n(?=const uint8_t g_mbi_led_matrix_co)",
                 "// LED row x MBIA column -> LED index (rgb_matrix.layout order in keyboard.json).\n"
                 "// Generated by tools/ledmap/apply_ledmap.py from the ledmap firmware's result;\n"
                 "// NLD = no LED fitted at that driver output.\n", src, flags=re.S)
    c_path.write_text(src)
    print(f"{len(entries)} LEDs on {len(keys)} keys; {len(dark)} empty driver positions dropped")


if __name__ == "__main__":
    main()
