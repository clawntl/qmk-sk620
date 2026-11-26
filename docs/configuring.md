# Changing settings from the PC (VIA)

[VIA](https://usevia.app) is QMK's standard way to change a keyboard's settings while it is plugged in, without rebuilding or reflashing. It is a web page that talks to the keyboard over QMK's raw HID interface (the same one `sk620_flash` uses to enter the bootloader). Changes are written to the keyboard's own flash, so they follow the keyboard to any PC, and nothing has to stay installed or running.

## What it can change

- **Keys:** remap any key on 4 layers, including the Fn layer. Layers 2 and 3 start empty.
- **Macros:** 16 text/key macros, assigned to any key.
- **Lighting:** effect, brightness, speed, and colour (hue and saturation) for the RGB effects.

Per-key colours (a different colour on each key, or effects that light up the key you press) are not possible yet. They need the LED-to-key mapping, which is still to be done.

## Setup

1. **Flash the VIA firmware.** In the flasher, click **Browse…**, choose `cm_sk620_via.bin` from the release (or `out/` if you built it yourself), and click **Flash firmware**. It keeps the same keymap as the default firmware.
2. **Linux only:** the browser needs permission to talk to the keyboard. If you already let the flasher install its udev rule, you're done. Otherwise run `sudo python3 sk620_flash.py --install-udev` once, then unplug and replug the keyboard.
3. **Open <https://usevia.app> in Chrome, Chromium, Edge or Brave.** Firefox can't be used: it has no WebHID.
4. **Load the SK620 definition.** VIA only knows keyboards that are in its own list, and this one isn't yet. Do this once per browser:
   1. Open **Settings** (gear icon) and turn on **Show Design tab**.
   2. Open the **Design** tab and **Load** `via/sk620_iso.json` (it is also in the release zip).
5. Go back to **Configure**, click **Authorize device +**, and pick the SK620 in the browser's list.

Your changes take effect immediately and are saved straight away. **Save + Load** on the Configure page backs up your layout to a file.

## Notes

- The keyboard's own shortcuts (Fn+arrow keys and so on) and VIA change the same settings, so whichever you used last wins.
- Flashing a different firmware build resets VIA's keymap and macros to the defaults in that build. Save a backup in VIA first.
- `sk620_flash` works the same with the VIA firmware: it still restarts the keyboard into the bootloader by itself.
- `via/sk620_iso.json` is generated from `qmk/keyboards/cm/sk620/keyboard.json` by `tools/via/gen_via_json.py`.
