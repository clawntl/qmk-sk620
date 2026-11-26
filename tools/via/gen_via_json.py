#!/usr/bin/env python3
"""Generate the VIA definition (via/sk620_iso.json) from qmk/keyboards/cm/sk620/keyboard.json.

VIA (https://usevia.app) needs a JSON file describing the keyboard: its USB IDs, matrix size,
which lighting menus to show, and the physical layout in KLE format where each key's label is
its "row,col" matrix position. Re-run this after changing keyboard.json:

    python3 tools/via/gen_via_json.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KB = ROOT / "qmk/keyboards/cm/sk620/keyboard.json"
OUT = ROOT / "via/sk620_iso.json"
EFFECTS_INC = ROOT / "qmk_firmware/quantum/rgb_matrix/animations/rgb_matrix_effects.inc"


def rgb_effects(enabled):
    """The RGB Matrix effects this firmware has, as (label, mode number) in QMK's order.

    QMK numbers only the effects that are compiled in (0 = off, then SOLID_COLOR = 1, ...), so a
    generic effect list would show the wrong names. This reads QMK's own order and keeps the
    animations enabled in keyboard.json.
    """
    anim_dir = EFFECTS_INC.parent
    names = []
    for line in EFFECTS_INC.read_text().splitlines():
        m = re.match(r'#include "([\w.]+)"', line.strip())
        if m:
            names += re.findall(r"RGB_MATRIX_EFFECT\((\w+)\)", (anim_dir / m[1]).read_text())
    on = {"SOLID_COLOR"} | {k.upper() for k, v in enabled.items() if v}
    out = [["All off", 0]]
    for n in names:
        if n in on:
            out.append([n.replace("_", " ").capitalize(), len(out)])
    return out


def lighting_menu(kb):
    effects = rgb_effects(kb["rgb_matrix"].get("animations", {}))
    # effects that use the colour setting (the rest are rainbow or ignore it)
    no_colour = {"All off", "Cycle all", "Cycle left right", "Cycle up down", "Rainbow moving chevron",
                 "Cycle out in", "Cycle out in dual", "Cycle pinwheel", "Cycle spiral", "Dual beacon",
                 "Rainbow beacon", "Rainbow pinwheels", "Jellybean raindrops", "Typing heatmap", "Digital rain"}
    colour_ids = [v for n, v in effects if n not in no_colour]
    show_colour = " || ".join(f"{{id_qmk_rgb_matrix_effect}} == {v}" for v in colour_ids)
    return [{
        "label": "Lighting",
        "content": [{
            "label": "Backlight",
            "content": [
                {"label": "Brightness", "type": "range", "options": [0, 255],
                 "content": ["id_qmk_rgb_matrix_brightness", 3, 1]},
                {"label": "Effect", "type": "dropdown", "options": effects,
                 "content": ["id_qmk_rgb_matrix_effect", 3, 2]},
                {"showIf": "{id_qmk_rgb_matrix_effect} != 0", "label": "Effect speed", "type": "range",
                 "options": [0, 255], "content": ["id_qmk_rgb_matrix_effect_speed", 3, 3]},
                {"showIf": show_colour, "label": "Colour", "type": "color",
                 "content": ["id_qmk_rgb_matrix_color", 3, 4]},
            ],
        }],
    }]


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
        "name": "Cooler Master SK620",
        "vendorId": kb["usb"]["vid"],
        "productId": kb["usb"]["pid"],
        "matrix": {"rows": rows, "cols": cols},
        "keycodes": ["qmk_lighting"],
        "menus": lighting_menu(kb),
        "layouts": {"keymap": kle_rows(kb["layouts"]["LAYOUT_iso"]["layout"])},
    }
    OUT.parent.mkdir(exist_ok=True)
    text = json.dumps(definition, indent=2)
    # keep each KLE row on one line so the file is readable
    text = re.sub(r"\[\n\s+(\"[^\]]*?|\{[^\]]*?)\n\s+\]",
                  lambda m: "[" + re.sub(r"\s*\n\s*", " ", m.group(1)) + "]", text)
    OUT.write_text(text + "\n")
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
