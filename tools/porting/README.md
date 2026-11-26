# Porting tools (for boards without usable stock firmware)

Not needed for the SK620, whose pin map came from its stock firmware.

- `sk620_pinfinder/` is a throwaway QMK keyboard for HT32F52352. It drives each candidate pin low in turn and *types* `PXn to PYm` into any text editor whenever a key connects two pins. Comment out non-matrix pins (crystal, LED driver, flash, SEL2) in `pinfinder.c` first.
- `log2qmk.py` turns that typed log plus a layout description (`sk620_layout.txt` format) into `keyboard.json` and a keymap. Driven pins become rows and read pins become columns, with `COL2ROW`.

    python3 log2qmk.py layout.txt pinlog.txt OUTDIR
