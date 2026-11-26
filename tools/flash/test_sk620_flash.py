#!/usr/bin/env python3
"""Tests for sk620_flash.py against a simulated HT32 ROM bootloader (no hardware needed).

    python3 tools/flash/test_sk620_flash.py
"""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sk620_flash as f


class FakeIsp:
    """Simulates the HT32F52352 ROM ISP as seen over HID."""

    def __init__(self, secured=True):
        self.flash = bytearray(b'\xA5' * f.FLASH_SIZE)    # "stock" contents
        self.secured = secured
        self.pp = [0xFFFFF000 if secured else 0xFFFFFFFF] + [0xFFFFFFFF] * 3
        self.present = True
        self.status = bytearray()
        self.inq = []
        self.booted_app = False
        self.commands = []

    def handle(self, pkt):
        assert len(pkt) == 64, len(pkt)
        crc = struct.unpack_from('<H', pkt, 2)[0]
        zeroed = bytearray(pkt)
        zeroed[2:4] = b'\0\0'
        assert f.crc16_xmodem(zeroed) == crc, "bad CRC"
        cmd, sub = pkt[0], pkt[1]
        a1, a2 = struct.unpack_from('<II', pkt, 4)
        data = pkt[12:]
        self.commands.append((cmd, sub))
        if (cmd, sub) == (0x03, 0x00):          # info: v103, 512 B pages, 255 pages, model at 16
            info = bytearray(64)
            struct.pack_into('<HHHH', info, 0, 0, 0x103, 0, 512)
            struct.pack_into('<H', info, 8, 255)
            struct.pack_into('<I', info, 16, 0x52352)
            self.inq.append(bytes(info))
        elif (cmd, sub) == (0x01, 0x02):        # read
            if a1 == f.OB_ADDR:
                ob = bytearray(b'\xff' * 64)
                struct.pack_into('<4I', ob, 0, *self.pp)
                ob[16] = 0xFC if self.secured else 0xFF
                self.inq.append(bytes(ob))
            else:
                self.inq.append(bytes(64) if self.secured else bytes(self.flash[a1:a1 + 64]))
        elif (cmd, sub) == (0x01, 0x01):        # write
            n = a2 - a1 + 1
            ok = not self.secured and all(self.flash[a1 + i] == 0xFF for i in range(n))
            if ok:
                self.flash[a1:a1 + n] = data[:n]
            self.status.append(0x4F if ok else 0x46)
        elif (cmd, sub) == (0x01, 0x00):        # check
            n = a2 - a1 + 1
            self.status.append(0x4F if self.flash[a1:a1 + n] == data[:n] else 0x46)
        elif (cmd, sub) == (0x00, 0x0A):        # mass erase clears everything
            self.flash[:] = b'\xff' * len(self.flash)
            self.secured = False
            self.pp = [0xFFFFFFFF] * 4
        elif (cmd, sub) == (0x00, 0x08):        # page erase
            if not self.secured:
                p0, p1 = a1 // 512, a2 // 512
                self.flash[p0 * 512:(p1 + 1) * 512] = b'\xff' * ((p1 - p0 + 1) * 512)
        elif (cmd, sub) == (0x04, 0x00):
            self.booted_app = True
            self.present = False
        elif (cmd, sub) == (0x04, 0x01):
            self.present = True             # SEL2 still bridged: back into ISP


class FakeDev:
    def __init__(self, isp):
        self.isp = isp

    def write(self, data):
        self.isp.handle(bytes(data).ljust(64, b'\0')[:64])

    def read(self, timeout=1.0):
        if not self.isp.inq:
            raise f.FlashError("timeout")
        return self.isp.inq.pop(0)

    def get_input_report(self):
        r = bytes(self.isp.status).ljust(64, b'\0')[:64]
        self.isp.status = bytearray()
        return r

    def close(self):
        pass


def image(size=33844):
    img = bytearray(os.urandom(size))
    struct.pack_into('<II', img, 0, 0x20003FE0, 0x1235)
    return bytes(img)


class FlashTests(unittest.TestCase):
    def run_tool(self, isp, img, answer='ERASE'):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_test.bin')
        with open(path, 'wb') as fh:
            fh.write(img)
        try:
            with mock.patch.object(f, 'find_hid', lambda vid, pid, up=None: 'isp' if (vid, pid) == (f.ISP_VID, f.ISP_PID) and isp.present else None), \
                 mock.patch.object(f, 'HidDevice', lambda path, n=64: FakeDev(isp)), \
                 mock.patch.object(f.time, 'sleep', lambda s: None), \
                 mock.patch('builtins.input', lambda prompt='': answer), \
                 mock.patch.object(sys, 'argv', ['sk620_flash.py', path]):
                f.main()
        finally:
            os.remove(path)

    def test_crc_reference(self):
        self.assertEqual(f.crc16_xmodem(b'123456789'), 0x31C3)

    def test_first_flash_mass_erases_and_writes(self):
        isp, img = FakeIsp(secured=True), image()
        self.run_tool(isp, img)
        self.assertEqual(bytes(isp.flash[:len(img)]), img)
        self.assertIn((0x00, 0x0A), isp.commands)
        self.assertTrue(isp.booted_app)

    def test_cancel_leaves_stock_untouched(self):
        isp = FakeIsp(secured=True)
        with self.assertRaises(f.FlashError):
            self.run_tool(isp, image(), answer='no')
        self.assertNotIn((0x00, 0x0A), isp.commands)
        self.assertEqual(isp.flash[0], 0xA5)

    def test_update_uses_page_erase_only(self):
        isp = FakeIsp(secured=False)
        isp.flash[:] = b'\xff' * len(isp.flash)
        old, new = image(40000), image(33844)
        isp.flash[:len(old)] = old
        self.run_tool(isp, new)
        self.assertNotIn((0x00, 0x0A), isp.commands)
        self.assertIn((0x00, 0x08), isp.commands)
        self.assertEqual(bytes(isp.flash[:len(new)]), new)

    def test_write_failure_is_reported(self):
        isp = FakeIsp(secured=False)            # not erased by page erase below 0? force a failure:
        isp.flash[:] = b'\x00' * len(isp.flash)
        with mock.patch.object(f, 'CMD_PAGE_ERASE', lambda a, n: f.isp_cmd(0x07, 0x07)):
            with self.assertRaises(f.FlashError):
                self.run_tool(isp, image())

    def test_rejects_non_firmware(self):
        with self.assertRaises(f.FlashError):
            path = 'notfw.bin'
            with open(path, 'wb') as fh:
                fh.write(b'hello' * 100)
            try:
                f.load_image(path)
            finally:
                os.remove(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
