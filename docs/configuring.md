# Changing settings from the PC

The SK620 firmware has **VIA** built in: QMK's standard way for a PC app to read and change a keyboard's keymap, macros and lighting while it is plugged in. Changes are stored on the keyboard itself, so they work on any PC with nothing installed or running.

Two apps can do it:

- **[OpenPeriph](https://github.com/clawntl/openperiph)**: a desktop app for Windows and Linux that recognises the SK620 straight away (its definition is built in), and works with any other QMK keyboard with VIA too.
- **[usevia.app](https://usevia.app)**: VIA's own web page, in Chrome, Edge or another Chromium browser (not Firefox). It needs the SK620's definition loaded once per browser (below).

## What you can change

- **Keys:** remap any key on 4 layers (layer 1 is the Fn layer; layers 2 and 3 start empty). Any QMK keycode: other keys, shortcuts, media and mouse keys, layer keys, tap-hold keys, lighting keys, macros.
- **Macros:** 16 macros that type text, press shortcuts or wait.
- **Lighting:** effect (the firmware's 30, by name), brightness, speed, and colour for the effects that use one.

The lock indicators (Caps Lock white, Windows-key lock red) aren't settings.

Flashing a new firmware build resets the keymap and macros to the build's defaults. Save a backup first (OpenPeriph: Settings, Save to file; usevia.app: Save + Load).

## OpenPeriph

1. Download it from its [releases](https://github.com/clawntl/openperiph/releases) and run it.
2. **Linux:** if the SK620 shows **Needs access**, click **Allow access** (it adds a udev rule and asks for your password), then unplug and replug the keyboard. If you already let `sk620_flash` install its rule, this isn't needed.
3. Pick **Cooler Master SK620** in the list. The **Keymap**, **Lighting**, **Macros** and **Settings** pages change the keyboard as you click.

**Settings, Restart into bootloader** puts the keyboard into flashing mode, like `sk620_flash` does.

## usevia.app

1. **Linux only:** the browser needs the same permission as above: `sudo python3 sk620_flash.py --install-udev` once, then replug.
2. Open <https://usevia.app> in Chrome, Chromium, Edge or Brave.
3. Load the SK620 definition, once per browser: **Settings** (gear icon), turn on **Show Design tab**, then **Design**, **Load**, and pick `via/sk620_iso.json` (also in the release zip).
4. Go to **Configure**, click **Authorize device +**, and pick the SK620.

## Notes

- The keyboard's own shortcuts (Fn+arrow keys and so on) and the apps change the same lighting settings, so whichever you used last wins.
- `via/sk620_iso.json` is generated from `qmk/keyboards/cm/sk620/keyboard.json` by `tools/via/gen_via_json.py`. Its lighting menu lists exactly the effects compiled into the firmware, numbered the way QMK numbers them.
- `sk620_flash` still puts the keyboard into bootloader mode by itself with this firmware.
