#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sk620_flash: flash QMK (or any firmware) onto a Cooler Master SK620.

Single file, Python 3.8+ standard library only (the window uses Tkinter). Works on Linux (hidraw) and
Windows (built-in HID API); no drivers, libusb or pip packages needed.

    python3 sk620_flash.py                     # open the flasher window (falls back to the command line)
    python3 sk620_flash.py --cli               # flash cm_sk620_default.bin next to this script, no window
    python3 sk620_flash.py firmware.bin        # flash a specific file from the command line
    python3 sk620_flash.py --info              # show bootloader / protection info
    sudo python3 sk620_flash.py --install-udev # Linux: allow flashing without sudo

The tool puts a running SK620 QMK firmware into its bootloader by itself. A board
still on stock firmware needs the SEL2 pads bridged while plugging in, and the
first flash has to mass-erase the read-protected chip (the tool asks first).

The ISP protocol is Holtek's HT32 USB ISP, as implemented by hansemro's
ht32-dfu-tool (GPL-2.0-or-later): 64-byte commands with a CRC16-XMODEM in bytes
2-3, sent as HID output reports; results come back as HID input reports, and
pass/fail status ('O'/'F' per queued command) via HID GET_REPORT.
"""
import argparse
import os
import struct
import sys
import time

ISP_VID, ISP_PID = 0x04D9, 0x8010          # Holtek HT32 ROM ISP
QMK_VID, QMK_PID = 0xFEED, 0x0620          # this project's QMK firmware
QMK_RAW_USAGE_PAGE = 0xFF60                 # QMK raw HID interface
BOOT_MAGIC = b'\x5b' + b'SK620-BOOTLOADER'  # handled in qmk/keyboards/cm/sk620/sk620.c
OB_ADDR = 0x1FF00000                        # option bytes (protection settings)
FLASH_SIZE = 128 * 1024
UDEV_RULES = '/etc/udev/rules.d/50-sk620-flash.rules'


class FlashError(Exception):
    pass


# --------------------------------------------------------------------------
# HT32 ISP command encoding
# --------------------------------------------------------------------------

def crc16_xmodem(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def isp_cmd(command, sub, arg1=0, arg2=0, data=b''):
    pkt = bytearray(64)
    pkt[0], pkt[1] = command, sub
    struct.pack_into('<II', pkt, 4, arg1 & 0xFFFFFFFF, arg2 & 0xFFFFFFFF)
    pkt[12:12 + len(data)] = data[:52]
    struct.pack_into('<H', pkt, 2, crc16_xmodem(pkt))
    return bytes(pkt)


CMD_INFO = lambda: isp_cmd(0x03, 0x00)
CMD_READ = lambda addr, n: isp_cmd(0x01, 0x02, addr, addr + n - 1)
CMD_WRITE = lambda addr, data: isp_cmd(0x01, 0x01, addr, addr + len(data) - 1, data)
CMD_CHECK = lambda addr, data: isp_cmd(0x01, 0x00, addr, addr + len(data) - 1, data)
CMD_MASS_ERASE = lambda: isp_cmd(0x00, 0x0A)
CMD_PAGE_ERASE = lambda addr, n: isp_cmd(0x00, 0x08, addr, addr + n - 1)
CMD_RESET_APP = lambda: isp_cmd(0x04, 0x00)
CMD_RESET_ISP = lambda: isp_cmd(0x04, 0x01)


# --------------------------------------------------------------------------
# HID backends: each device object has write(64 bytes), read(timeout) -> bytes,
# get_input_report() -> bytes, close().
# --------------------------------------------------------------------------

if sys.platform.startswith('linux'):
    import fcntl
    import glob
    import select

    def _hidraw_devices():
        for node in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
            try:
                uevent = open(os.path.join(node, 'device', 'uevent')).read()
            except OSError:
                continue
            hid_id = next((l.split('=', 1)[1] for l in uevent.splitlines() if l.startswith('HID_ID=')), None)
            if not hid_id:
                continue
            _bus, vid, pid = hid_id.split(':')
            try:
                rdesc = open(os.path.join(node, 'device', 'report_descriptor'), 'rb').read()
            except OSError:
                rdesc = b''
            yield '/dev/' + os.path.basename(node), int(vid, 16), int(pid, 16), rdesc

    def _usage_page(rdesc):
        # first Usage Page item (0x05 = 1 byte, 0x06 = 2 bytes)
        i = 0
        while i < len(rdesc):
            p = rdesc[i]
            size = (0, 1, 2, 4)[p & 3]
            if p & 0xFC == 0x04:
                return int.from_bytes(rdesc[i + 1:i + 1 + size], 'little')
            i += 1 + size
        return None

    class HidDevice:
        def __init__(self, path, report_len=64):
            try:
                self.fd = os.open(path, os.O_RDWR)
            except PermissionError:
                raise FlashError(f"no permission to open {path}: run with sudo, or once: "
                                 f"sudo python3 {os.path.basename(sys.argv[0])} --install-udev")
            self.report_len = report_len

        def write(self, data):
            os.write(self.fd, b'\x00' + bytes(data).ljust(self.report_len, b'\x00'))

        def read(self, timeout=1.0):
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                raise FlashError("timed out waiting for the bootloader to answer")
            return os.read(self.fd, 64)

        def get_input_report(self):
            buf = bytearray(self.report_len + 1)  # [0] = report ID 0
            req = (3 << 30) | (len(buf) << 16) | (ord('H') << 8) | 0x0A  # HIDIOCGINPUT(len)
            fcntl.ioctl(self.fd, req, buf, True)
            return bytes(buf[1:])

        def close(self):
            os.close(self.fd)

    def find_hid(vid, pid, usage_page=None):
        for path, v, p, rdesc in _hidraw_devices():
            if v == vid and p == pid and (usage_page is None or _usage_page(rdesc) == usage_page):
                return path
        return None

elif sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

    _hid = ctypes.WinDLL('hid')
    _setupapi = ctypes.WinDLL('setupapi')
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                    ('Data4', ctypes.c_ubyte * 8)]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('InterfaceClassGuid', GUID), ('Flags', wintypes.DWORD),
                    ('Reserved', ctypes.c_void_p)]

    class HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('Size', wintypes.ULONG), ('VendorID', wintypes.USHORT), ('ProductID', wintypes.USHORT),
                    ('VersionNumber', wintypes.USHORT)]

    class HIDP_CAPS(ctypes.Structure):
        _fields_ = [('Usage', wintypes.USHORT), ('UsagePage', wintypes.USHORT),
                    ('InputReportByteLength', wintypes.USHORT), ('OutputReportByteLength', wintypes.USHORT),
                    ('FeatureReportByteLength', wintypes.USHORT), ('Reserved', wintypes.USHORT * 17),
                    ('Rest', wintypes.USHORT * 10)]

    class OVERLAPPED(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_void_p), ('InternalHigh', ctypes.c_void_p), ('Offset', wintypes.DWORD),
                    ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]

    _setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    _setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                      wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                           ctypes.c_void_p, wintypes.DWORD,
                                                           ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CreateEventW.restype = wintypes.HANDLE
    _k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                               ctypes.POINTER(OVERLAPPED)]
    _k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                              ctypes.POINTER(OVERLAPPED)]
    _k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.CancelIo.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    _hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    _hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
    _hid.HidD_GetInputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]

    INVALID_HANDLE = wintypes.HANDLE(-1).value
    GENERIC_RW = 0x80000000 | 0x40000000
    SHARE_RW = 0x1 | 0x2
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    ERROR_IO_PENDING = 997

    def _open(path, access):
        return _k32.CreateFileW(path, access, SHARE_RW, None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)

    def _hid_paths():
        guid = GUID()
        _hid.HidD_GetHidGuid(ctypes.byref(guid))
        info = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
        try:
            i = 0
            while True:
                iface = SP_DEVICE_INTERFACE_DATA()
                iface.cbSize = ctypes.sizeof(iface)
                if not _setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), i, ctypes.byref(iface)):
                    break
                i += 1
                need = wintypes.DWORD()
                _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value)
                ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if _setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), buf, need, None, None):
                    yield ctypes.wstring_at(ctypes.addressof(buf) + 4)
        finally:
            _setupapi.SetupDiDestroyDeviceInfoList(info)

    def _describe(path):
        h = _open(path, 0)  # attributes and caps need no access rights
        if h == INVALID_HANDLE:
            return None
        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(attrs)
            if not _hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                return None
            caps = HIDP_CAPS()
            pp = ctypes.c_void_p()
            if _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                _hid.HidP_GetCaps(pp, ctypes.byref(caps))
                _hid.HidD_FreePreparsedData(pp)
            return attrs.VendorID, attrs.ProductID, caps.UsagePage, caps.InputReportByteLength, caps.OutputReportByteLength
        finally:
            _k32.CloseHandle(h)

    class HidDevice:
        def __init__(self, path, report_len=64):
            d = _describe(path)
            self.in_len = (d[3] if d and d[3] else report_len + 1)
            self.out_len = (d[4] if d and d[4] else report_len + 1)
            self.h = _open(path, GENERIC_RW)
            if self.h == INVALID_HANDLE:
                raise FlashError(f"could not open the HID device (error {ctypes.get_last_error()})")
            self.event = _k32.CreateEventW(None, True, False, None)

        def _io(self, fn, buf, timeout):
            ov = OVERLAPPED()
            ov.hEvent = self.event
            done = wintypes.DWORD()
            if not fn(self.h, buf, len(buf), None, ctypes.byref(ov)):
                if ctypes.get_last_error() != ERROR_IO_PENDING:
                    raise FlashError(f"HID I/O failed (error {ctypes.get_last_error()})")
                if _k32.WaitForSingleObject(self.event, int(timeout * 1000)) != 0:
                    _k32.CancelIo(self.h)
                    _k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(done), True)  # let it finish
                    raise FlashError("timed out waiting for the bootloader to answer")
            if not _k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(done), True):
                raise FlashError(f"HID I/O failed (error {ctypes.get_last_error()})")
            return done.value

        def write(self, data):
            buf = ctypes.create_string_buffer((b'\x00' + bytes(data)).ljust(self.out_len, b'\x00'), self.out_len)
            self._io(_k32.WriteFile, buf, 2.0)

        def read(self, timeout=1.0):
            buf = ctypes.create_string_buffer(self.in_len)
            n = self._io(_k32.ReadFile, buf, timeout)
            return buf.raw[1:n]

        def get_input_report(self):
            buf = ctypes.create_string_buffer(self.in_len)
            if not _hid.HidD_GetInputReport(self.h, buf, self.in_len):
                raise FlashError(f"GET_REPORT failed (error {ctypes.get_last_error()})")
            return buf.raw[1:]

        def close(self):
            _k32.CloseHandle(self.event)
            _k32.CloseHandle(self.h)

    def find_hid(vid, pid, usage_page=None):
        for path in _hid_paths():
            d = _describe(path)
            if d and d[0] == vid and d[1] == pid and (usage_page is None or d[2] == usage_page):
                return path
        return None

else:
    def find_hid(*a, **k):
        raise FlashError("only Linux and Windows are supported")


# --------------------------------------------------------------------------
# Bootloader session
# --------------------------------------------------------------------------

class Isp:
    def __init__(self, path):
        self.dev = HidDevice(path)
        self.dev.write(CMD_INFO())
        info = self.dev.read(2.0)
        version = info[2] | info[3] << 8
        self.page_size = info[6] | info[7] << 8
        self.flash_size = self.page_size * (info[8] | info[9] << 8)
        self.version = version
        self.model = (info[0] | info[1] << 8) if version == 0x100 else int.from_bytes(info[16:20], 'little')

    def describe(self):
        model = f"HT32F{self.model:x}" if self.model else "HT32 (model not reported)"
        return f"{model}, ISP v{self.version:x}, {self.flash_size} B flash, {self.page_size} B pages"

    def protection(self):
        self.dev.write(CMD_READ(OB_ADDR, 64))
        ob = self.dev.read(2.0)
        pp = struct.unpack_from('<4I', ob, 0)
        return {'flash_security': not (ob[16] & 1), 'ob_protection': not (ob[16] & 2), 'page_protection': pp}

    def _status(self):
        r = self.dev.get_input_report()
        return r.count(0x4F), r.count(0x46)  # 'O' passed, 'F' failed

    def stream(self, image, base, make_cmd, what, progress):
        try:
            self._status()  # clear old status
        except Exception:
            pass
        count = 0
        end = base + len(image)
        for off in range(0, len(image), 52):
            chunk = image[off:off + 52]
            self.dev.write(make_cmd(base + off, chunk))
            count += 1
            last = base + off + len(chunk) >= end
            if last or count >= 30:
                time.sleep(0.1)
                passed, failed = self._status()
                if failed:
                    raise FlashError(f"{what} failed near 0x{base + off:05x}")
                count -= passed
            progress(min(off + 52, len(image)), len(image), what)

    def close(self):
        self.dev.close()


def describe_protection(prot):
    return (f"flash security {'ON' if prot['flash_security'] else 'off'}, "
            f"option bytes {'locked' if prot['ob_protection'] else 'unlocked'}, "
            f"page protection {' '.join(f'{p:08x}' for p in prot['page_protection'])}")


def needs_mass_erase(prot, image_len, page_size):
    pages = range(0, (image_len + page_size - 1) // page_size)
    return prot['flash_security'] or any(not (prot['page_protection'][p // 32] >> (p % 32) & 1) for p in pages)


def wait_for(fn, seconds, cancelled=lambda: False):
    deadline = time.time() + seconds
    while time.time() < deadline and not cancelled():
        r = fn()
        if r:
            return r
        time.sleep(0.3)
    return None


BOOTLOADER_HELP = ("Put the keyboard in bootloader mode:\n"
                   "  - running QMK: press Fn+B (or hold Esc while plugging it in)\n"
                   "  - stock firmware / first flash: bridge the SEL2 pads and plug it in")


def keyboard_state():
    """'bootloader', 'qmk' or None (cheap: only enumerates, opens nothing)."""
    if find_hid(ISP_VID, ISP_PID):
        return 'bootloader'
    if find_hid(QMK_VID, QMK_PID, QMK_RAW_USAGE_PAGE):
        return 'qmk'
    return None


def enter_bootloader(log, waiting, cancelled=lambda: False):
    path = find_hid(ISP_VID, ISP_PID)
    if path:
        return path
    qmk = find_hid(QMK_VID, QMK_PID, QMK_RAW_USAGE_PAGE)
    if qmk:
        log("Asking the keyboard to restart into its bootloader...")
        d = HidDevice(qmk, 32)
        try:
            d.write(BOOT_MAGIC.ljust(32, b'\x00'))
        except FlashError:
            pass  # the keyboard may drop off USB before the write completes
        d.close()
        path = wait_for(lambda: find_hid(ISP_VID, ISP_PID), 10, cancelled)
        if path:
            return path
        log("It didn't restart by itself.")
    waiting()
    return wait_for(lambda: find_hid(ISP_VID, ISP_PID), 120, cancelled)


def read_info(log, waiting, cancelled=lambda: False):
    path = enter_bootloader(log, waiting, cancelled)
    if not path:
        raise FlashError("no bootloader found (USB 04d9:8010)")
    isp = Isp(path)
    try:
        prot = isp.protection()
        log(f"Bootloader: {isp.describe()}")
        log(f"Protection: {describe_protection(prot)}")
        return isp, prot
    except Exception:
        isp.close()
        raise


def flash(image, log, progress, confirm_erase, waiting, cancelled=lambda: False):
    """Put the keyboard in its bootloader, erase as needed, write, verify, restart."""
    isp, prot = read_info(log, waiting, cancelled)
    locked = needs_mass_erase(prot, len(image), isp.page_size)
    try:
        if locked:
            if not confirm_erase():
                raise FlashError("cancelled, nothing was changed")
            log("Mass-erasing (about 5 seconds)...")
            isp.dev.write(CMD_MASS_ERASE())
            time.sleep(5)
            isp.dev.write(CMD_RESET_ISP())  # reset so the cleared protection takes effect
            isp.close()
            isp = None
            time.sleep(3)
            path = wait_for(lambda: find_hid(ISP_VID, ISP_PID), 15)
            if not path:
                raise FlashError("the bootloader didn't come back after the erase: keep SEL2 bridged, "
                                 "replug, and flash again")
            isp = Isp(path)
        else:
            log("Erasing (about 5 seconds)...")
            isp.dev.write(CMD_PAGE_ERASE(0, len(image)))
            time.sleep(5)
        log("Writing...")
        isp.stream(image, 0, CMD_WRITE, "Writing", progress)
        log("Verifying...")
        isp.stream(image, 0, CMD_CHECK, "Verifying", progress)
        log("Done. Restarting the keyboard.")
        isp.dev.write(CMD_RESET_APP())
        if locked:
            log("Remove the tweezers from SEL2 if they're still there.")
    finally:
        if isp:
            isp.close()


def load_image(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    if not data or len(data) > FLASH_SIZE - 512:
        raise FlashError(f"{os.path.basename(path)}: {len(data)} bytes doesn't fit the 127.5 KiB application flash")
    sp, rst = struct.unpack_from('<II', data, 0)
    if not (0x20000000 < sp <= 0x20004000 and rst & 1 and rst < len(data)):
        raise FlashError(f"{os.path.basename(path)} doesn't start with a valid vector table (is it a .bin for address 0?)")
    return data


def udev_rules():
    return ('# Cooler Master SK620: Holtek ROM ISP and QMK raw HID, for sk620_flash.py\n'
            f'KERNEL=="hidraw*", ATTRS{{idVendor}}=="{ISP_VID:04x}", ATTRS{{idProduct}}=="{ISP_PID:04x}", MODE="0660", TAG+="uaccess"\n'
            f'KERNEL=="hidraw*", ATTRS{{idVendor}}=="{QMK_VID:04x}", ATTRS{{idProduct}}=="{QMK_PID:04x}", MODE="0660", TAG+="uaccess"\n')


def install_udev():
    with open(UDEV_RULES, 'w') as f:
        f.write(udev_rules())
    os.system('udevadm control --reload && udevadm trigger')
    print(f"Wrote {UDEV_RULES}. Unplug and replug the keyboard; then flash without sudo.")


ERASE_WARNING = ("The chip is read-protected (stock firmware). Flashing needs a MASS ERASE, which permanently "
                 "deletes Cooler Master's firmware and updater. Keep SEL2 bridged until flashing finishes.\n"
                 "(docs/stock-firmware.md explains how to rebuild stock firmware from Cooler Master's updater.)")


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

_last_pct = [None]


def progress_bar(done, total, what):
    pct = done * 100 // total
    if (what, pct) == _last_pct[0]:
        return
    _last_pct[0] = (what, pct)
    width = 40
    fill = done * width // total
    sys.stdout.write(f"\r  {what:<9} [{'#' * fill}{'.' * (width - fill)}] {pct:3d}%")
    if done >= total:
        sys.stdout.write("\n")
    sys.stdout.flush()


def run_cli(args):
    if args.install_udev:
        return install_udev()
    say = lambda m: print(m)
    waiting = lambda: print(BOOTLOADER_HELP + "\nWaiting up to 2 minutes...")
    if args.info:
        isp, _ = read_info(say, waiting)
        isp.close()
        return
    image = load_image(args.firmware)
    print(f"Firmware: {args.firmware} ({len(image)} bytes)")

    def confirm():
        print("\n" + ERASE_WARNING)
        return args.yes or input("Type ERASE to continue: ").strip() == 'ERASE'

    flash(image, say, progress_bar, confirm, waiting)


# --------------------------------------------------------------------------
# GUI (Tkinter, part of the Python standard library)
# --------------------------------------------------------------------------

REPO_URL = 'https://github.com/clawntl/qmk-sk620'


def run_gui(default_firmware):
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

    root = tk.Tk()
    root.title("SK620 QMK Flasher")
    root.minsize(560, 460)
    style = ttk.Style()
    try:
        style.theme_use('vista' if sys.platform == 'win32' else 'clam')
    except tk.TclError:
        pass
    style.configure('SK.Horizontal.TProgressbar', background='#2b8a3e')

    events = queue.Queue()          # worker -> UI
    busy = threading.Event()
    cancel = threading.Event()
    fw_path = tk.StringVar(value=default_firmware if os.path.exists(default_firmware) else '')
    fw_info = tk.StringVar()
    kb_state = tk.StringVar(value="Looking for the keyboard...")
    phase = tk.StringVar(value="")

    pad = {'padx': 10, 'pady': 4}
    from tkinter import font as tkfont
    title_font = tkfont.nametofont('TkDefaultFont').copy()
    title_font.configure(size=13, weight='bold')
    tk.Label(root, text="Cooler Master SK620 QMK Flasher", font=title_font).pack(anchor='w', **pad)

    box = ttk.LabelFrame(root, text="Firmware")
    box.pack(fill='x', **pad)
    row = ttk.Frame(box)
    row.pack(fill='x', padx=6, pady=4)
    ttk.Entry(row, textvariable=fw_path).pack(side='left', fill='x', expand=True)

    def browse():
        p = filedialog.askopenfilename(title="Choose firmware", filetypes=[("Firmware", "*.bin"), ("All files", "*")])
        if p:
            fw_path.set(p)
    ttk.Button(row, text="Browse...", command=browse).pack(side='left', padx=(6, 0))
    ttk.Label(box, textvariable=fw_info, foreground='#555').pack(anchor='w', padx=6, pady=(0, 4))

    kb = ttk.LabelFrame(root, text="Keyboard")
    kb.pack(fill='x', **pad)
    dot = tk.Canvas(kb, width=14, height=14, highlightthickness=0)
    dot.pack(side='left', padx=(8, 4), pady=8)
    dot_id = dot.create_oval(2, 2, 12, 12, fill='#999', outline='')
    ttk.Label(kb, textvariable=kb_state, wraplength=480, justify='left').pack(side='left', fill='x', pady=6)

    btns = ttk.Frame(root)
    btns.pack(fill='x', **pad)
    flash_btn = ttk.Button(btns, text="Flash firmware")
    info_btn = ttk.Button(btns, text="Check keyboard")
    cancel_btn = ttk.Button(btns, text="Cancel", state='disabled')
    flash_btn.pack(side='left')
    info_btn.pack(side='left', padx=6)
    cancel_btn.pack(side='left')

    prog = ttk.Progressbar(root, maximum=100, style='SK.Horizontal.TProgressbar')
    prog.pack(fill='x', **pad)
    ttk.Label(root, textvariable=phase).pack(anchor='w', padx=10)

    log_box = scrolledtext.ScrolledText(root, height=10, state='disabled', font='TkFixedFont')
    log_box.pack(fill='both', expand=True, **pad)
    help_lbl = ttk.Label(root, text="First flash over stock firmware: bridge the SEL2 pads, plug in, then Flash.   "
                         "Help: " + REPO_URL, foreground='#555', wraplength=540)
    help_lbl.pack(anchor='w', padx=10, pady=(0, 8))

    def log(msg):
        log_box.configure(state='normal')
        log_box.insert('end', msg + "\n")
        log_box.see('end')
        log_box.configure(state='disabled')

    def check_firmware(*_):
        p = fw_path.get()
        if not p:
            fw_info.set("No firmware selected.")
            return None
        try:
            img = load_image(p)
            fw_info.set(f"{os.path.basename(p)}: {len(img)} bytes, looks valid.")
            return img
        except (OSError, FlashError) as e:
            fw_info.set(str(e))
            return None
    fw_path.trace_add('write', check_firmware)
    check_firmware()

    def set_state(state):
        colours = {'bootloader': '#2b8a3e', 'qmk': '#1971c2', None: '#999'}
        text = {'bootloader': "In bootloader mode, ready to flash.",
                'qmk': "SK620 running QMK found. Flashing will restart it into the bootloader automatically.",
                None: "Not found. Plug the keyboard in. For the first flash over stock firmware, "
                      "bridge the SEL2 pads while plugging in."}[state]
        dot.itemconfigure(dot_id, fill=colours[state])
        kb_state.set(text)

    def poll_keyboard():
        if not busy.is_set():
            try:
                set_state(keyboard_state())
            except Exception as e:
                kb_state.set(f"Can't look for USB devices: {e}")
        root.after(1500, poll_keyboard)

    # --- worker plumbing -------------------------------------------------
    def ui(kind, *a):
        events.put((kind, a))

    def ask(kind, *a):
        """Ask the UI thread a question from the worker and wait for the answer."""
        reply = queue.Queue()
        events.put((kind, a + (reply,)))
        return reply.get()

    def worker(job, success_message=None):
        try:
            job()
            ui('done', None, success_message)
        except FlashError as e:
            ui('done', str(e))
        except Exception as e:  # unexpected: show it rather than vanish
            ui('done', f"{type(e).__name__}: {e}")

    def start(job, success_message=None):
        busy.set()
        cancel.clear()
        prog['value'] = 0
        for b in (flash_btn, info_btn):
            b.configure(state='disabled')
        cancel_btn.configure(state='normal')
        threading.Thread(target=worker, args=(job, success_message), daemon=True).start()

    def progress(done, total, what):
        ui('progress', done * 100 // total, what)

    def waiting():
        ui('log', BOOTLOADER_HELP + "\nWaiting up to 2 minutes...")
        ui('phase', "Waiting for bootloader mode...")

    def do_flash():
        img = check_firmware()
        if img is None:
            messagebox.showerror("SK620 Flasher", fw_info.get() or "Choose a firmware file first.")
            return
        log(f"Firmware: {fw_path.get()} ({len(img)} bytes)")
        start(lambda: flash(img, lambda m: ui('log', m), progress, lambda: ask('confirm_erase'), waiting,
                            cancel.is_set),
              "Flashing finished. The keyboard is restarting with the new firmware.")

    def do_info():
        def job():
            isp, _ = read_info(lambda m: ui('log', m), waiting, cancel.is_set)
            isp.dev.write(CMD_RESET_APP())  # don't leave the keyboard stuck in the bootloader
            isp.close()
            ui('log', "Restarted the keyboard.")
        start(job)

    flash_btn.configure(command=do_flash)
    info_btn.configure(command=do_info)
    cancel_btn.configure(command=lambda: (cancel.set(), phase.set("Cancelling...")))

    def offer_udev(err):
        if not sys.platform.startswith('linux') or 'permission' not in err:
            return False
        if not messagebox.askyesno("SK620 Flasher",
                                   "Linux needs permission to talk to the keyboard.\n\n"
                                   f"Install a udev rule ({UDEV_RULES}) so your user can flash without sudo? "
                                   "You'll be asked for your password."):
            return True
        import shutil
        import subprocess
        if not shutil.which('pkexec'):
            messagebox.showinfo("SK620 Flasher", "Run this once in a terminal, then replug the keyboard:\n\n"
                                f"sudo {sys.executable} {os.path.abspath(__file__)} --install-udev")
            return True
        r = subprocess.run(['pkexec', sys.executable, os.path.abspath(__file__), '--install-udev'])
        if r.returncode == 0:
            messagebox.showinfo("SK620 Flasher", "Done. Unplug and replug the keyboard, then try again.")
        return True

    def pump():
        try:
            while True:
                kind, a = events.get_nowait()
                if kind == 'log':
                    log(a[0])
                elif kind == 'phase':
                    phase.set(a[0])
                elif kind == 'progress':
                    prog['value'] = a[0]
                    phase.set(f"{a[1]}... {a[0]}%")
                elif kind == 'confirm_erase':
                    ok = messagebox.askokcancel("Erase stock firmware?", ERASE_WARNING, icon='warning')
                    if ok:
                        typed = simpledialog.askstring("Confirm", "Type ERASE to permanently erase the chip:",
                                                       parent=root)
                        ok = (typed or '').strip() == 'ERASE'
                    a[0].put(ok)
                elif kind == 'done':
                    busy.clear()
                    for b in (flash_btn, info_btn):
                        b.configure(state='normal')
                    cancel_btn.configure(state='disabled')
                    err = a[0]
                    if err:
                        log("Error: " + err)
                        phase.set("Failed.")
                        if not offer_udev(err):
                            messagebox.showerror("SK620 Flasher", err)
                    else:
                        phase.set("Finished.")
                        if len(a) > 1 and a[1]:
                            messagebox.showinfo("SK620 Flasher", a[1])
        except queue.Empty:
            pass
        root.after(50, pump)

    root.after(50, pump)
    root.after(200, poll_keyboard)
    root.mainloop()


def gui_available():
    if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        return False
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    if sys.stdout is None:  # windowed .exe build: there is no console
        sys.stdout = sys.stderr = open(os.devnull, 'w')
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    default_fw = os.path.join(here, 'cm_sk620_default.bin')
    ap = argparse.ArgumentParser(description="Flash firmware onto a Cooler Master SK620. "
                                             "With no arguments on a desktop, opens a window.")
    ap.add_argument('firmware', nargs='?', default=None)
    ap.add_argument('--cli', action='store_true', help="use the command line even when a desktop is available")
    ap.add_argument('--gui', action='store_true', help="open the window")
    ap.add_argument('--info', action='store_true', help="only show bootloader and protection info")
    ap.add_argument('--yes', action='store_true', help="don't ask before erasing stock firmware")
    ap.add_argument('--install-udev', action='store_true', help="Linux: install a udev rule (run with sudo)")
    args = ap.parse_args()

    plain_start = not (args.firmware or args.cli or args.info or args.yes or args.install_udev)
    if args.gui or (plain_start and gui_available()):
        if not gui_available():
            raise FlashError("no GUI available: install Tkinter (Arch/CachyOS: sudo pacman -S tk; "
                             "Debian/Ubuntu: sudo apt install python3-tk), or use --cli")
        return run_gui(args.firmware or default_fw)
    args.firmware = args.firmware or default_fw
    run_cli(args)


if __name__ == '__main__':
    try:
        main()
    except FlashError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        # Keep the console window open when a console build of the .exe was double-clicked.
        if sys.platform == 'win32' and getattr(sys, 'frozen', False) and sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close...")
