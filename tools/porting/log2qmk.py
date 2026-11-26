#!/usr/bin/env python3
"""Turn a pin-finder log plus a layout file into QMK keyboard files.

usage: python3 log2qmk.py LAYOUT.txt PINLOG.txt OUTDIR

LAYOUT.txt: one keyboard row per line, keys left to right, each
            KEYCODE[:width][x2]. Lines starting with # are ignored.
PINLOG.txt: what the pin finder typed, one "PXn to PYm" line per key,
            in the same order as the keys in LAYOUT.txt.
OUTDIR:     gets keyboard.json and keymaps/default/keymap.c
"""
import json, os, re, sys

FN_LAYER = {  # Fn layer: base keycode -> Fn keycode
    "KC_ESC": "KC_GRV", "KC_1": "KC_F1", "KC_2": "KC_F2", "KC_3": "KC_F3",
    "KC_4": "KC_F4", "KC_5": "KC_F5", "KC_6": "KC_F6", "KC_7": "KC_F7",
    "KC_8": "KC_F8", "KC_9": "KC_F9", "KC_0": "KC_F10", "KC_MINS": "KC_F11",
    "KC_EQL": "KC_F12", "KC_BSPC": "KC_DEL", "KC_B": "QK_BOOT",
    "KC_UP": "KC_PGUP", "KC_DOWN": "KC_PGDN", "KC_LEFT": "KC_HOME",
    "KC_RGHT": "KC_END",
}


def pin_key(p):  # "PB10" -> ("B", 10) for sorting
    return (p[1], int(p[2:]))


def main(layout_path, log_path, outdir):
    rows = []
    for line in open(layout_path):
        line = line.split("#", 1)[0].strip()
        if line:
            rows.append(line.split())
    keys = []
    for y, row in enumerate(rows):
        x = 0.0
        for tok in row:
            m = re.fullmatch(r"(.+?)(?::([\d.]+))?(x2)?", tok)
            code, w, tall = m.group(1), float(m.group(2) or 1), bool(m.group(3))
            keys.append({"code": code, "x": x, "y": float(y), "w": w, "h": 2.0 if tall else 1.0})
            x += w

    pairs = re.findall(r"\b(P[A-D]\d{1,2}) to (P[A-D]\d{1,2})\b", open(log_path).read())
    if len(pairs) != len(keys):
        sys.exit(f"layout has {len(keys)} keys but the log has {len(pairs)} 'to' lines; "
                 "fix bounces or missed keys so there is exactly one line per key, in order")

    drive = sorted({d for d, _ in pairs}, key=pin_key)
    sense = sorted({s for _, s in pairs}, key=pin_key)
    if set(drive) & set(sense):
        sys.exit(f"pins appear on both sides: {sorted(set(drive) & set(sense))}; "
                 "check the log for a key pressed with another held down")
    seen = {}
    for k, (d, s) in zip(keys, pairs):
        pos = (drive.index(d), sense.index(s))
        if pos in seen:
            sys.exit(f"{k['code']} and {seen[pos]} both read {d} to {s}")
        seen[pos] = k["code"]
        k["matrix"] = list(pos)

    esc = next((k for k in keys if k["code"] == "KC_ESC"), keys[0])
    layout = []
    for k in keys:
        e = {"label": k["code"].removeprefix("KC_"), "matrix": k["matrix"], "x": k["x"], "y": k["y"]}
        if k["w"] != 1:
            e["w"] = k["w"]
        if k["h"] != 1:
            e["h"] = k["h"]
        layout.append(e)

    kb = {
        "manufacturer": "Cooler Master",
        "keyboard_name": "SK620",
        "maintainer": "you",
        "processor": "HT32F52352",
        "board": "GENERIC_HT32_F52342_52",
        "bootloader": "ht32-dfu",
        "build": {"firmware_format": "bin"},
        "diode_direction": "COL2ROW",
        "matrix_pins": {"rows": [p[1:] for p in drive], "cols": [p[1:] for p in sense]},
        "usb": {"vid": "0xFEED", "pid": "0x0620", "device_version": "1.0.0"},
        "features": {"bootmagic": True, "extrakey": True, "mousekey": False, "nkro": True},
        "bootmagic": {"matrix": esc["matrix"]},
        "layouts": {"LAYOUT": {"layout": layout}},
    }
    os.makedirs(os.path.join(outdir, "keymaps", "default"), exist_ok=True)
    with open(os.path.join(outdir, "keyboard.json"), "w") as f:
        json.dump(kb, f, indent=4)
        f.write("\n")

    def fmt(codes):
        out, i = [], 0
        for row in rows:
            out.append("        " + ", ".join(codes[i:i + len(row)]))
            i += len(row)
        return ",\n".join(out)

    base = [k["code"] for k in keys]
    fn = [FN_LAYER.get(c, "_______") for c in base]
    keymap = (
        "#include QMK_KEYBOARD_H\n"
        "#include \"keymap_uk.h\"\n\n"
        "const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {\n"
        f"    [0] = LAYOUT(\n{fmt(base)}\n    ),\n"
        f"    [1] = LAYOUT(\n{fmt(fn)}\n    ),\n"
        "};\n"
    )
    with open(os.path.join(outdir, "keymaps", "default", "keymap.c"), "w") as f:
        f.write(keymap)
    print(f"{len(keys)} keys, matrix {len(drive)} rows x {len(sense)} cols")
    print("rows:", " ".join(drive))
    print("cols:", " ".join(sense))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
