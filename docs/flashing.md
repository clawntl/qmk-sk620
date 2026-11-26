# Flashing

## The easy way: `sk620_flash`

`tools/flash/sk620_flash.py` is a single-file flasher that runs on **Windows and Linux** using only Python's standard library. On Linux it uses the kernel's hidraw interface; on Windows it uses the HID API built into Windows. It needs no drivers, no libusb and no pip packages. Each [release](https://github.com/clawntl/qmk-sk620/releases) also includes it as a standalone `sk620_flash.exe` for Windows, together with the firmware. Release builds come from GitHub Actions.

| Situation | Windows | Linux |
| --- | --- | --- |
| Update (keyboard already runs this QMK) | double-click `sk620_flash.exe` | `python3 sk620_flash.py` |
| Flash a specific file | `sk620_flash.exe firmware.bin` | `python3 sk620_flash.py firmware.bin` |
| Show bootloader/protection info | `sk620_flash.exe --info` | `python3 sk620_flash.py --info` |

The tool goes through these steps:

1. Finds the keyboard. If it's running this QMK firmware, the tool restarts it into the bootloader with a raw-HID command, so you don't need Fn+B.
2. Reads the chip's protection settings.
3. Erases only what's needed. A locked chip with stock firmware needs a mass erase, and the tool asks you to type `ERASE` first.
4. Writes in 52-byte blocks, then verifies every block.
5. Restarts the keyboard.

**First flash over stock firmware:** bridge the SEL2 pads, plug in, then run the tool. Keep SEL2 bridged until it says "Done".

**Linux permissions:** run it once with `sudo`, or install a udev rule so your user can flash without sudo: `sudo python3 sk620_flash.py --install-udev`.

**Windows SmartScreen** may warn that the `.exe` comes from an unknown publisher. Choose "More info" and then "Run anyway", or run `sk620_flash.py` with Python instead.

The flasher follows the same Holtek ISP protocol as hansemro's `ht32-dfu-tool`: the same commands, the same CRC16 and the same `O`/`F` status checks. Its tests run it against a simulated bootloader (`python3 tools/flash/test_sk620_flash.py`).

---

## Building the firmware yourself

The rest of this page is only needed to build the firmware from source, or to flash with hansemro's `ht32-dfu-tool` instead.

### 1. Install the tools without touching system Python

These rules keep the install from interfering with your system:

- Only install official-repo packages, with a full upgrade first. Never run a partial `pacman -Sy <pkg>`.
- Install no `sudo pip` packages and nothing from the AUR.
- Keep the QMK CLI in its own virtual environment.

```sh
sudo pacman -Syu
sudo pacman -S --needed git make python base-devel libusb \
    arm-none-eabi-gcc arm-none-eabi-binutils arm-none-eabi-newlib

python -m venv ~/.venvs/qmk
~/.venvs/qmk/bin/pip install qmk
```

Activate the environment in every new terminal before building. In fish, use `source ~/.venvs/qmk/bin/activate.fish`; in bash or zsh, use `source ~/.venvs/qmk/bin/activate`.

Next, get the QMK fork and add this keyboard. Don't run `qmk setup`: it would clone upstream QMK, which lacks the HT32 and MBIA043 support.

```sh
git clone -b cmmkprosrgb_mbi_preview https://github.com/hansemro/qmk_firmware ~/qmk_sk620
cd ~/qmk_sk620
git submodule update --init --recursive
qmk config user.qmk_home=$HOME/qmk_sk620
cp -r /path/to/this/repo/qmk/keyboards/cm/sk620 keyboards/cm/
make cm/sk620:default
```

Install the flasher. It goes into `~/.cargo/bin`, so no system files change:

```sh
command -v cargo || sudo pacman -S --needed rust   # skip if you use rustup
cargo install --git https://github.com/hansemro/ht32-dfu-tool
```

So you can flash without sudo, add a udev rule. It only matches the Holtek bootloader's USB ID:

```sh
echo 'ACTION!="remove", SUBSYSTEMS=="usb", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="8010", MODE="0660", TAG+="uaccess"' \
    | sudo tee /etc/udev/rules.d/50-ht32-dfu.rules
sudo udevadm control --reload && sudo udevadm trigger
```

> [!NOTE]
> Version v103 of the SK620's ROM bootloader isn't decoded by `ht32-dfu-tool` yet, so it prints `Model: unknown`. To see the model, build the tool from source after running `sed -i 's/0x101 => {/0x101 | 0x102 | 0x103 => {/' src/device.rs`. Flashing works either way.

### 2. First flash with ht32-dfu-tool (erases the stock firmware)

1. Open the case. Unplug the keyboard and put the PCB on a non-conductive surface.
2. Bridge the two **SEL2** pads with tweezers and keep them bridged until step 5 finishes.
3. Plug in. `ht32-dfu-tool list` should show `[04d9:8010] Model=HT32F52352`.
4. Run `ht32-dfu-tool info`. On a stock board it reports `Flash security: true`. Nothing can be backed up; see [stock-firmware.md](stock-firmware.md) for the way back.
5. Run `ht32-dfu-tool -w write -m -v 0 cm_sk620_default.bin`. It mass-erases the chip, resets into the ROM bootloader (because SEL2 is still bridged), writes and verifies.
6. Remove the tweezers, unplug, and plug back in. `lsusb` should show `feed:0620 Cooler Master SK620`.

### 3. Later flashes with ht32-dfu-tool

Press **Fn+B**, or hold **Esc** while plugging in, then run:

```sh
make cm/sk620:default
ht32-dfu-tool -w -r write -v 0 cm_sk620_default.bin
```

Leave out `-m`: the chip is already unlocked. `-r` restarts the keyboard into the new firmware. `make cm/sk620:default:flash` also works; it waits for the bootloader and then writes.

## Recovery

Nothing you flash can remove the ROM bootloader. If the keyboard stops responding, bridge SEL2, plug in, and flash a working `.bin` again. If you use SEL2 together with `-r`, take the tweezers off before the write finishes. Otherwise the reset lands back in the bootloader.
