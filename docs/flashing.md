# Flashing

## The easy way: `sk620_flash`

`tools/flash/sk620_flash.py` is a single-file flasher with a window and a command line that runs on **Windows and Linux** using only Python's standard library. On Linux it uses the kernel's hidraw interface; on Windows it uses the HID API built into Windows. It needs no drivers, no libusb and no pip packages. Each [release](https://github.com/clawntl/qmk-sk620/releases) also includes it as a standalone `sk620_flash.exe` for Windows, together with the firmware. Release builds come from GitHub Actions.

| Situation | Windows | Linux |
| --- | --- | --- |
| Open the flasher window | double-click `sk620_flash.exe` | `python3 sk620_flash.py` |
| Flash from the command line | `python sk620_flash.py --cli` | `python3 sk620_flash.py --cli` |
| Flash a specific file (command line) | `python sk620_flash.py firmware.bin` | `python3 sk620_flash.py firmware.bin` |
| Show bootloader/protection info | "Check keyboard" button | `python3 sk620_flash.py --info` |

The window shows whether the keyboard is connected and in which mode, lets you pick a different `.bin`, and shows progress and a log. It asks before any mass erase: first a confirmation, then you type `ERASE`.

The window uses Tkinter, which comes with Python on Windows and inside `sk620_flash.exe`. Some Linux distros package it separately: on Arch/CachyOS run `sudo pacman -S --needed tk`, on Debian/Ubuntu `sudo apt install python3-tk`. Without it the tool says so and you can use `--cli`.

The tool goes through these steps:

1. Finds the keyboard. If it's running this QMK firmware, the tool restarts it into the bootloader with a raw-HID command, so you don't need Fn+B.
2. Reads the chip's protection settings.
3. Erases only what's needed. A locked chip with stock firmware needs a mass erase, and the tool asks you to type `ERASE` first.
4. Writes in 52-byte blocks, then verifies every block.
5. Restarts the keyboard.

**First flash over stock firmware:** bridge the SEL2 pads, plug in, then click "Flash firmware". Keep SEL2 bridged until it says it's finished.

**Linux permissions:** the first time, the window offers to install a udev rule. It asks for your password through `pkexec`. From a terminal, run `sudo python3 sk620_flash.py --install-udev`. Either way, unplug and replug the keyboard afterwards.

**Windows SmartScreen** may warn that the `.exe` comes from an unknown publisher. Choose "More info" and then "Run anyway", or run `sk620_flash.py` with Python instead.

The flasher follows the same Holtek ISP protocol as hansemro's `ht32-dfu-tool`: the same commands, the same CRC16 and the same `O`/`F` status checks. Its tests run it against a simulated bootloader (`python3 tools/flash/test_sk620_flash.py`). CI also runs them on Windows.

---

## Building the firmware yourself

Everything needed to build is in this repository: official QMK is a submodule pinned to a tested commit, the HT32 and MBIA043 support is applied from [`patches/qmk`](../patches/qmk/README.md), and `build.sh` does the rest. No QMK fork, no `qmk setup`, no global QMK CLI.

### 1. Install the compiler (official packages only)

These rules keep the install from interfering with your system:

- Only install official-repo packages, with a full upgrade first. Never run a partial `pacman -Sy <pkg>`.
- Install no `sudo pip` packages and nothing from the AUR.

```sh
sudo pacman -Syu
sudo pacman -S --needed git make python arm-none-eabi-gcc arm-none-eabi-newlib
```

(Debian/Ubuntu: `sudo apt install git make python3-venv gcc-arm-none-eabi libnewlib-arm-none-eabi`.)

### 2. Build

```sh
git clone --recurse-submodules https://github.com/clawntl/qmk-sk620
cd qmk-sk620
./build.sh            # out/cm_sk620_default.bin (VIA enabled, see configuring.md)
./build.sh ledmap     # out/cm_sk620_ledmap.bin, the LED mapper (see led-mapping.md)
```

`build.sh` works the same in fish, bash or zsh, since it runs under bash itself. It writes only inside the repository:

| Path | What |
| --- | --- |
| `qmk_firmware/` | the official QMK submodule, never modified |
| `.build/qmk_firmware/` | a copy with the patches applied and the keyboard copied in; also fetches QMK's ChibiOS, ChibiOS-Contrib and printf submodules at the commits QMK pins |
| `.build/venv/` | Python packages QMK's build scripts need |
| `out/` | the finished `.bin` files |

The first run takes a minute or two; later runs only recompile. `./build.sh clean` deletes `.build/`. The output is reproducible: `./build.sh` gives the same `cm_sk620_default.bin` (SHA-256 `6f9b61d3…`) as building in Hansem Ro's QMK branch.

Then flash `out/cm_sk620_*.bin` with `python3 tools/flash/sk620_flash.py`, browsing to the file, or with `ht32-dfu-tool` as below.

### 3. Optional: ht32-dfu-tool

`sk620_flash` does everything this tool does. Use this only if you prefer hansemro's tool; it installs into `~/.cargo/bin`, so no system files change:

```sh
sudo pacman -S --needed libusb rust   # leave out rust if you use rustup
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

### 4. First flash with ht32-dfu-tool (erases the stock firmware)

1. Open the case. Unplug the keyboard and put the PCB on a non-conductive surface.
2. Bridge the two **SEL2** pads with tweezers and keep them bridged until step 5 finishes.
3. Plug in. `ht32-dfu-tool list` should show `[04d9:8010] Model=HT32F52352`.
4. Run `ht32-dfu-tool info`. On a stock board it reports `Flash security: true`. Nothing can be backed up; see [stock-firmware.md](stock-firmware.md) for the way back.
5. Run `ht32-dfu-tool -w write -m -v 0 out/cm_sk620_default.bin`. It mass-erases the chip, resets into the ROM bootloader (because SEL2 is still bridged), writes and verifies.
6. Remove the tweezers, unplug, and plug back in. `lsusb` should show `feed:0620 Cooler Master SK620`.

### 5. Later flashes with ht32-dfu-tool

Press **Fn+B**, or hold **Esc** while plugging in, then run:

```sh
./build.sh
ht32-dfu-tool -w -r write -v 0 out/cm_sk620_default.bin
```

Leave out `-m`: the chip is already unlocked. `-r` restarts the keyboard into the new firmware.

## Recovery

Nothing you flash can remove the ROM bootloader. If the keyboard stops responding, bridge SEL2, plug in, and flash a working `.bin` again. If you use SEL2 together with `-r`, take the tweezers off before the write finishes. Otherwise the reset lands back in the bootloader.
