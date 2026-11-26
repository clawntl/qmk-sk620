#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sk620_flash: flash QMK (or any firmware) onto a Cooler Master SK620.

Single file, Python 3.8+ standard library only. Works on Linux (hidraw) and
Windows (built-in HID API); no drivers, libusb or pip packages needed.

    python3 sk620_flash.py                     # flash cm_sk620_default.bin next to this script
    python3 sk620_flash.py firmware.bin        # flash a specific file
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


_last_pct = [None]


def progress_bar(done, total, what):
    pct = done * 100 // total
    if (what, pct) == _last_pct[0]:
        return
    _last_pct[0] = (what, pct)
    width = 40
    fill = done * width // total
    sys.stdout.write(f"\r  {what:<9} [{'#' * fill}{'.' * (width - fill)}] {done * 100 // total:3d}%")
    if done >= total:
        sys.stdout.write("\n")
    sys.stdout.flush()


def wait_for(fn, seconds, message=None):
    if message:
        print(message)
    deadline = time.time() + seconds
    while time.time() < deadline:
        r = fn()
        if r:
            return r
        time.sleep(0.3)
    return None


def enter_bootloader():
    path = find_hid(ISP_VID, ISP_PID)
    if path:
        return path
    qmk = find_hid(QMK_VID, QMK_PID, QMK_RAW_USAGE_PAGE)
    if qmk:
        print("Found the SK620 running QMK; asking it to restart into the bootloader...")
        d = HidDevice(qmk, 32)
        try:
            d.write(BOOT_MAGIC.ljust(32, b'\x00'))
        except FlashError:
            pass  # the keyboard may drop off USB before the write completes
        d.close()
        path = wait_for(lambda: find_hid(ISP_VID, ISP_PID), 10)
        if path:
            return path
        print("It didn't restart by itself.")
    return wait_for(lambda: find_hid(ISP_VID, ISP_PID), 120,
                    "Put the keyboard in bootloader mode now:\n"
                    "  - running QMK: press Fn+B (or hold Esc while plugging it in)\n"
                    "  - stock firmware / first flash: bridge the SEL2 pads and plug it in\n"
                    "Waiting up to 2 minutes...")


def load_image(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    if not data or len(data) > FLASH_SIZE - 512:
        raise FlashError(f"{path}: {len(data)} bytes doesn't fit the 127.5 KiB application flash")
    sp, rst = struct.unpack_from('<II', data, 0)
    if not (0x20000000 < sp <= 0x20004000 and rst & 1 and rst < len(data)):
        raise FlashError(f"{path} doesn't start with a valid vector table (is it a .bin for address 0?)")
    return data


def install_udev():
    rules = ('# Cooler Master SK620: Holtek ROM ISP and QMK raw HID, for sk620_flash.py\n'
             f'KERNEL=="hidraw*", ATTRS{{idVendor}}=="{ISP_VID:04x}", ATTRS{{idProduct}}=="{ISP_PID:04x}", MODE="0660", TAG+="uaccess"\n'
             f'KERNEL=="hidraw*", ATTRS{{idVendor}}=="{QMK_VID:04x}", ATTRS{{idProduct}}=="{QMK_PID:04x}", MODE="0660", TAG+="uaccess"\n')
    with open(UDEV_RULES, 'w') as f:
        f.write(rules)
    os.system('udevadm control --reload && udevadm trigger')
    print(f"Wrote {UDEV_RULES}. Unplug and replug the keyboard; then flash without sudo.")


def main():
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    ap = argparse.ArgumentParser(description="Flash firmware onto a Cooler Master SK620.")
    ap.add_argument('firmware', nargs='?', default=os.path.join(here, 'cm_sk620_default.bin'))
    ap.add_argument('--info', action='store_true', help="only show bootloader and protection info")
    ap.add_argument('--yes', action='store_true', help="don't ask before erasing stock firmware")
    ap.add_argument('--install-udev', action='store_true', help="Linux: install a udev rule (run with sudo)")
    args = ap.parse_args()

    if args.install_udev:
        return install_udev()
    image = None if args.info else load_image(args.firmware)
    if image:
        print(f"Firmware: {args.firmware} ({len(image)} bytes)")

    path = enter_bootloader()
    if not path:
        raise FlashError("no bootloader found (USB 04d9:8010)")
    isp = Isp(path)
    prot = isp.protection()
    model = f"HT32F{isp.model:x}" if isp.model else "HT32 (model not reported)"
    print(f"Bootloader: {model}, ISP v{isp.version:x}, {isp.flash_size} B flash, {isp.page_size} B pages")
    print(f"Protection: flash security {'ON' if prot['flash_security'] else 'off'}, "
          f"option bytes {'locked' if prot['ob_protection'] else 'unlocked'}, "
          f"page protection {' '.join(f'{p:08x}' for p in prot['page_protection'])}")
    if args.info:
        isp.close()
        return

    pages = range(0, (len(image) + isp.page_size - 1) // isp.page_size)
    locked = prot['flash_security'] or any(not (prot['page_protection'][p // 32] >> (p % 32) & 1) for p in pages)
    if locked:
        print("\nThe chip is read-protected (stock firmware). Flashing needs a MASS ERASE, which permanently\n"
              "deletes Cooler Master's firmware and updater. Keep SEL2 bridged until flashing finishes.\n"
              "(docs/stock-firmware.md explains how to rebuild stock firmware from Cooler Master's updater.)")
        if not args.yes and input("Type ERASE to continue: ").strip() != 'ERASE':
            isp.close()
            raise FlashError("cancelled, nothing was changed")
        print("Mass-erasing...")
        isp.dev.write(CMD_MASS_ERASE())
        time.sleep(5)
        isp.dev.write(CMD_RESET_ISP())  # reset so the cleared protection takes effect
        isp.close()
        time.sleep(3)
        path = wait_for(lambda: find_hid(ISP_VID, ISP_PID), 15)
        if not path:
            raise FlashError("the bootloader didn't come back after the erase: keep SEL2 bridged, "
                             "replug, and run the tool again")
        isp = Isp(path)
    else:
        print("Erasing...")
        isp.dev.write(CMD_PAGE_ERASE(0, len(image)))
        time.sleep(5)

    isp.stream(image, 0, CMD_WRITE, "Writing", progress_bar)
    isp.stream(image, 0, CMD_CHECK, "Verifying", progress_bar)
    print("Done. Restarting the keyboard...")
    isp.dev.write(CMD_RESET_APP())
    isp.close()
    if locked:
        print("Remove the tweezers from SEL2 if they're still there.")


if __name__ == '__main__':
    try:
        main()
    except FlashError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        # Keep the console window open when the .exe was double-clicked.
        if sys.platform == 'win32' and getattr(sys, 'frozen', False) and sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close...")
