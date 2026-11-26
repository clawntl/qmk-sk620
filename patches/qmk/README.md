# Patches on top of official QMK

`build.sh` applies these, in order, to a copy of the `qmk_firmware` submodule
(official QMK, pinned to `542440eac5f6d0788fcc496fc1ef2b7e4301a175`). The submodule
itself is never modified.

| Patch | What it adds | Author |
|---|---|---|
| `0001-Add-HT32F1653-4-HT32F52342-52-MCU-support.patch` | Holtek HT32F52342/52 MCU support in QMK (board files, `ht32-dfu` bootloader target, bumps `lib/chibios` to `be44b3305f9a`, a commit in qmk/ChibiOS) | Hansem Ro |
| `0002-Preview-Add-MBIA04X-MBI504X-RGB-and-LED-Matrix-Drive.patch` | The `mbi` RGB Matrix / LED Matrix driver for the MBIA043 LED drivers | Hansem Ro |

Both come unchanged from Hansem Ro's
[`cmmkprosrgb_mbi_preview`](https://github.com/hansemro/qmk_firmware/tree/cmmkprosrgb_mbi_preview)
branch (commits `6e26139c` and `14d5521b`), exported with

```sh
git format-patch 542440ea..14d5521b -- . ':!keyboards'
```

so only the core changes are included, not his keyboard folders. They are GPL-2.0-or-later like
the rest of QMK, and the `From:` headers keep his authorship.

Checked result: official QMK + these two patches + `qmk/keyboards/cm/sk620` builds a
byte-identical `cm_sk620_default.bin` to the one built from Hansem Ro's branch.

## Updating QMK

1. Move the submodule: `git -C qmk_firmware fetch --depth 1 origin <commit> && git -C qmk_firmware checkout <commit>`
2. Run `./build.sh`. If a patch no longer applies, `git am --3way` stops in
   `.build/qmk_firmware`; fix it there, then export the fixed patches back here with
   `git -C .build/qmk_firmware format-patch -o ../../patches/qmk <new base>..HEAD`.
3. `git add qmk_firmware patches` and commit.
