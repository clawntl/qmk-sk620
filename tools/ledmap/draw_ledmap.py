#!/usr/bin/env python3
"""Draw the LED map as an SVG for the docs (light and dark mode).

    python3 tools/ledmap/draw_ledmap.py tools/ledmap/sk620_iso_ledmap.txt docs/images/led-map.svg

Top: the keyboard, each key showing the stock LED number under it.
Bottom: the stock firmware's 17 x 7 LED grid (column = n // 7, row = n % 7), showing which
positions have a key LED, which are empty, and which were corrected by hand.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORRECTED = {14, 27}  # recorded as Space by too-short skip holds, fixed to dark by hand

SHORT = {"Backspace": "Bksp", "LShift": "Shift", "RShift": "Shift", "LCtrl": "Ctrl", "LWin": "Win",
         "LAlt": "Alt", "RAlt": "AltGr", "Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}
TINY = {"Space": "Spc", "AltGr": "AGr", "Enter": "Ent", "Shift": "Sft", "Caps": "Cap", "Bksp": "Bks", "Ctrl": "Ctl"}

STYLE = """<style>
text{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;font-size:12px;fill:#444441}
.n{font-weight:600;fill:#085041}.k{fill:#0F6E56}
.key{fill:#E1F5EE;stroke:#0F6E56;stroke-width:.6}
.bad{fill:#FCEBEB;stroke:#A32D2D;stroke-width:1}.bad+text,.badt{fill:#791F1F}
.empty{fill:none;stroke:#888780;stroke-width:.6;stroke-dasharray:3 2}
@media (prefers-color-scheme:dark){
text{fill:#D3D1C7}.n{fill:#E1F5EE}.k{fill:#9FE1CB}
.key{fill:#085041;stroke:#5DCAA5}.bad{fill:#791F1F;stroke:#F09595}.badt{fill:#FCEBEB}
.empty{stroke:#888780}}
</style>"""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    text = pathlib.Path(sys.argv[1]).read_text()
    leds = {}
    for line in text.splitlines():
        m = re.fullmatch(r"(\d+) (\d+),(\d+)", line.strip())
        if m:
            leds[(int(m[2]), int(m[3]))] = int(m[1])
    dark = {int(v) for v in re.search(r"^dark (.*)$", text, re.M)[1].split()}
    kb = json.loads((ROOT / "qmk/keyboards/cm/sk620/keyboard.json").read_text())
    keys = kb["layouts"]["LAYOUT_iso"]["layout"]

    U, X0, Y0 = 40, 40, 40
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="680" height="H" viewBox="0 0 680 H">', STYLE,
         f'<text x="{X0}" y="{Y0 - 14}">Keyboard: number = stock LED under the key</text>']
    for k in keys:
        x, y = X0 + k["x"] * U, Y0 + k["y"] * U
        w, h = k.get("w", 1) * U, k.get("h", 1) * U
        lab = SHORT.get(k["label"], k["label"])
        led = leds[tuple(k["matrix"])]
        if k["label"] == "Enter" and k.get("h", 1) == 2:  # ISO Enter: wide top, narrow bottom
            x1, x2 = X0 + 13.5 * U + 2, x + w - 2
            o.append(f'<path class="key" d="M{x1} {y + 2} H{x2} V{y + h - 2} H{x + 2} V{y + U - 2} H{x1} Z"/>')
            cx, ty = x + w / 2, y + U
        else:
            o.append(f'<rect class="key" x="{x + 2}" y="{y + 2}" width="{w - 4}" height="{h - 4}" rx="4"/>')
            cx, ty = x + w / 2, y
        o.append(f'<text class="k" x="{cx}" y="{ty + 17}" text-anchor="middle">{lab}</text>')
        o.append(f'<text class="n" x="{cx}" y="{ty + 32}" text-anchor="middle">{led}</text>')

    GX, GY, CW, CH = 34, Y0 + 5 * U + 50, 36, 26
    o.append(f'<text x="{GX}" y="{GY - 14}">Stock LED grid: column = n / 7, row = n mod 7</text>')
    by_led = {v: k for k, v in leds.items()}
    labels = {tuple(k["matrix"]): SHORT.get(k["label"], k["label"]) for k in keys}
    for n in range(17 * 7):
        x, y = GX + (n // 7) * CW, GY + (n % 7) * CH
        cell = f'x="{x + 1}" y="{y + 1}" width="{CW - 2}" height="{CH - 2}" rx="3"'
        tx = f'x="{x + CW / 2}" y="{y + CH / 2 + 4}" text-anchor="middle"'
        if n in CORRECTED:
            o.append(f'<rect class="bad" {cell}/><text class="badt" {tx}>{n}</text>')
        elif n in by_led:
            lab = labels[by_led[n]]
            o.append(f'<rect class="key" {cell}/><text class="k" {tx}>{TINY.get(lab, lab)}</text>')
        elif n in dark:
            o.append(f'<rect class="empty" {cell}/>')
    ly = GY + 7 * CH + 24
    o.append(f'<rect class="key" x="{GX}" y="{ly}" width="14" height="14" rx="3"/><text x="{GX + 20}" y="{ly + 11}">LED under a key</text>')
    o.append(f'<rect class="empty" x="{GX + 150}" y="{ly}" width="14" height="14" rx="3"/><text x="{GX + 170}" y="{ly + 11}">Empty (nothing fitted)</text>')
    o.append(f'<rect class="bad" x="{GX + 330}" y="{ly}" width="14" height="14" rx="3"/><text x="{GX + 350}" y="{ly + 11}">Empty, first recorded as Space by mistake</text>')
    o.append("</svg>")
    svg = "\n".join(o).replace('"H"', f'"{ly + 34}"')
    pathlib.Path(sys.argv[2]).write_text(svg + "\n")
    print("wrote", sys.argv[2])


if __name__ == "__main__":
    main()
