#!/usr/bin/env bash
# Build the SK620 QMK firmware from this repository alone.
#
#   ./build.sh            -> out/cm_sk620_default.bin
#   ./build.sh via        -> out/cm_sk620_via.bin
#   ./build.sh clean      -> remove .build/ (the patched QMK copy and the Python venv)
#
# What it does (nothing outside this folder is touched, no sudo):
#   1. checks out the qmk_firmware submodule (official QMK, pinned commit)
#   2. copies it to .build/qmk_firmware and applies patches/qmk/*.patch
#   3. fetches the three QMK submodules the build needs (ChibiOS, ChibiOS-Contrib, printf)
#   4. copies qmk/keyboards/cm/sk620 into the copy
#   5. makes a Python venv in .build/venv with QMK's Python requirements
#   6. runs make and copies the .bin to out/
#
# Needs: git, make, python3 (with venv), arm-none-eabi-gcc + newlib. See docs/flashing.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/.build"
TREE="$BUILD/qmk_firmware"
VENV="$BUILD/venv"
OUT="$ROOT/out"
KEYMAP="${1:-default}"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

if [ "$KEYMAP" = clean ]; then
    rm -rf "$BUILD"
    say "removed .build/"
    exit 0
fi
[ -d "$ROOT/qmk/keyboards/cm/sk620/keymaps/$KEYMAP" ] \
    || die "no keymap '$KEYMAP' (have: $(ls "$ROOT/qmk/keyboards/cm/sk620/keymaps" | tr '\n' ' '))"

# ---- 0. tools -----------------------------------------------------------------------------
missing=()
for t in git make python3 arm-none-eabi-gcc; do
    command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ ${#missing[@]} -gt 0 ]; then
    cat >&2 <<EOF
Missing: ${missing[*]}

Install them from your distribution's official packages, e.g.
  Arch / CachyOS:  sudo pacman -Syu
                   sudo pacman -S --needed git make python arm-none-eabi-gcc arm-none-eabi-newlib
  Debian / Ubuntu: sudo apt install git make python3-venv gcc-arm-none-eabi libnewlib-arm-none-eabi
  Fedora:          sudo dnf install git make python3 arm-none-eabi-gcc-cs arm-none-eabi-newlib
EOF
    exit 1
fi

# ---- 1. pinned official QMK ---------------------------------------------------------------
if [ -d "$ROOT/.git" ] || [ -f "$ROOT/.git" ]; then
    say "checking out qmk_firmware submodule"
    git -C "$ROOT" submodule update --init qmk_firmware
fi
[ -f "$ROOT/qmk_firmware/Makefile" ] \
    || die "qmk_firmware/ is empty. Clone with: git clone --recurse-submodules https://github.com/clawntl/qmk-sk620"
BASE="$(git -C "$ROOT/qmk_firmware" rev-parse HEAD)"

# ---- 2. patched copy (rebuilt only when the base commit or the patches change) ------------
STAMP="$BASE $(cat "$ROOT"/patches/qmk/*.patch | sha256sum | cut -d' ' -f1)"
if [ ! -f "$TREE/.sk620-stamp" ] || [ "$(cat "$TREE/.sk620-stamp")" != "$STAMP" ]; then
    say "preparing patched QMK in .build/qmk_firmware (base ${BASE:0:12})"
    rm -rf "$TREE"
    mkdir -p "$BUILD"
    git clone -q --no-checkout "$ROOT/qmk_firmware" "$TREE" 2>/dev/null \
        || git clone -q --no-checkout "file://$ROOT/qmk_firmware" "$TREE"
    git -C "$TREE" checkout -q --detach "$BASE"
    git -C "$TREE" remote set-url origin https://github.com/qmk/qmk_firmware
    for p in "$ROOT"/patches/qmk/*.patch; do
        say "  applying $(basename "$p")"
        git -C "$TREE" -c user.name=sk620-build -c user.email=build@localhost \
            am -q --3way --committer-date-is-author-date "$p" \
            || die "patch $(basename "$p") does not apply; see patches/qmk/README.md"
    done
    say "fetching ChibiOS, ChibiOS-Contrib and printf (pinned by the patched tree)"
    git -C "$TREE" submodule update --init --depth 1 lib/chibios lib/chibios-contrib lib/printf
    echo "$STAMP" > "$TREE/.sk620-stamp"
fi

# ---- 3. keyboard --------------------------------------------------------------------------
rm -rf "$TREE/keyboards/cm/sk620"
mkdir -p "$TREE/keyboards/cm"
cp -r "$ROOT/qmk/keyboards/cm/sk620" "$TREE/keyboards/cm/sk620"

# ---- 4. Python venv (local to this folder) -----------------------------------------------
REQ_STAMP="$(sha256sum "$TREE/requirements.txt" | cut -d' ' -f1)+qmk-cli"
if [ ! -x "$VENV/bin/python" ] || [ "$(cat "$VENV/.sk620-stamp" 2>/dev/null)" != "$REQ_STAMP" ]; then
    say "creating Python venv in .build/venv"
    rm -rf "$VENV"
    python3 -m venv "$VENV" || die "python3 -m venv failed (Debian/Ubuntu: install python3-venv)"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r "$TREE/requirements.txt" qmk   # qmk = the CLI the Makefile calls
    echo "$REQ_STAMP" > "$VENV/.sk620-stamp"
fi
export PATH="$VENV/bin:$PATH"
export QMK_HOME="$TREE"
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH

# ---- 5. build -----------------------------------------------------------------------------
say "building cm/sk620:$KEYMAP"
make -C "$TREE" -j"$(nproc 2>/dev/null || echo 2)" "cm/sk620:$KEYMAP"

mkdir -p "$OUT"
cp "$TREE/cm_sk620_$KEYMAP.bin" "$OUT/"
say "done: out/cm_sk620_$KEYMAP.bin"
( cd "$OUT" && sha256sum "cm_sk620_$KEYMAP.bin" )
echo "Flash it with:  python3 tools/flash/sk620_flash.py out/cm_sk620_$KEYMAP.bin"
