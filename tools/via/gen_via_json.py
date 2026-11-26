#!/usr/bin/env python3
"""Generate the VIA definition (via/sk620_iso.json) from qmk/keyboards/cm/sk620/keyboard.json.

VIA (https://usevia.app) needs a JSON file describing the keyboard: its USB IDs, matrix size,
which lighting menus to show, and the physical layout in KLE format where each key's label is
its "row,col" matrix position. Re-run this after changing keyboard.json:

    python3 tools/via/gen_via_json.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KB = ROOT / "qmk/keyboards/cm/sk620/keyboard.json"
OUT = ROOT / "via/sk620_iso.json"


def kle_rows(layout):
    rows = {}
    for k in layout:
        rows.setdefault(k["y"], []).append(k)
    out = []
    for y in sorted(rows):
        row, cursor = [], 0.0
        for k in sorted(rows[y], key=lambda k: k["x"]):
            props = {}
            if abs(k["x"] - cursor) > 1e-9:
                props["x"] = round(k["x"] - cursor, 4)
            w, h = k.get("w", 1), k.get("h", 1)
            if w != 1:
                props["w"] = w
            if h != 1:
                props["h"] = h
            if k.get("label") == "Enter" and h == 2:
                # ISO enter: the top part is 1.5u wide and sticks out 0.25u to the left
                props.update({"w2": 1.5, "h2": 1, "x2": -0.25})
            if props:
                row.append(props)
            row.append("{},{}".format(*k["matrix"]))
            cursor = k["x"] + w
        out.append(row)
    return out


def main():
    kb = json.loads(KB.read_text())
    rows, cols = len(kb["matrix_pins"]["rows"]), len(kb["matrix_pins"]["cols"])
    definition = {
        "name": "Cooler Master SK620 (ISO, QMK)",
        "vendorId": kb["usb"]["vid"],
        "productId": kb["usb"]["pid"],
        "matrix": {"rows": rows, "cols": cols},
        "keycodes": ["qmk_lighting"],
        "menus": ["qmk_rgb_matrix"],
        "layouts": {"keymap": kle_rows(kb["layouts"]["LAYOUT_iso"]["layout"])},
    }
    OUT.parent.mkdir(exist_ok=True)
    text = json.dumps(definition, indent=2)
    # keep each KLE row on one line so the file is readable
    import re
    text = re.sub(r"\[\n\s+(\"[^\]]*?|\{[^\]]*?)\n\s+\]",
                  lambda m: "[" + re.sub(r"\s*\n\s*", " ", m.group(1)) + "]", text)
    OUT.write_text(text + "\n")
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
