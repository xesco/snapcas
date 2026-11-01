"""Step 15 (docs/PLAN.md): TSX tape files, read into the tape model
(DESIGN.md, Tape files and TSX data)."""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import msx  # noqa: E402
import tape  # noqa: E402
import tsx  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402

TSX_DIR = os.path.join(test_step4.CAS_DIR, "tsx")
COLLECTION = os.path.join(test_step4.CAS_DIR, "collection")


def kcs(data, byte_cfg=0x54, zero=1458, one=729, pilots=100, pause=1000):
    """A block 4Bh: the BIOS's bits, with byte_cfg's start and stop bits."""
    body = struct.pack("<HHHHHBB", pause, one, pilots, zero, one, 0x24, byte_cfg) + data
    return b"\x4B" + struct.pack("<I", len(body)) + body


def turbo(data, pilot=600, sync1=200, sync2=250, zero=300, one=600, pilots=1000, pause=500):
    """A block 11h, with all bits of the last byte."""
    return (b"\x11" + struct.pack("<HHHHHHBH", pilot, sync1, sync2, zero, one, pilots, 8, pause)
            + len(data).to_bytes(3, "little") + data)


def tsx_file(*blocks):
    return tsx.SIGNATURE + b"\x01\x15" + b"".join(blocks)


class Reader(unittest.TestCase):
    def test_blocks_kinds_offsets_and_times(self):
        header = b"\xD0" * 10 + b"GAME  "
        data = tsx_file(kcs(header), b"\x20" + struct.pack("<H", 2000), turbo(b"\x00\xFF"),
                        b"\x30\x04text", kcs(b"\x00", byte_cfg=0x5C), kcs(b"\x00", byte_cfg=0x44))
        blocks = tape.read("GAME.TSX", data)
        self.assertEqual([b.standard for b in blocks], [True, False, True, False])
        self.assertEqual(blocks[0].data, header)
        for b in blocks:
            self.assertEqual(data[b.offset:b.offset + len(b.data)], b.data)
        # The header block: 100 pilot pulses, then each byte's start bit 0, 8
        # bits and 2 stop bits 1, a 0 bit as 2 pulses and a 1 bit as 4.
        ones = sum(bin(b).count("1") for b in header)
        t = 100 * 729 + 16 * (2 * 1458 + 2 * 4 * 729) + ones * 4 * 729 + (128 - ones) * 2 * 1458
        self.assertAlmostEqual(blocks[0].end, t / 3500000)
        # Its pause of 1 second and block 20h's of 2 come before the turbo
        # block: 1000 pilot pulses, the syncs, then 8 bits 0 and 8 bits 1.
        self.assertAlmostEqual(blocks[1].start, blocks[0].end + 3)
        t = 1000 * 600 + 200 + 250 + 8 * 2 * 300 + 8 * 2 * 600
        self.assertAlmostEqual(blocks[1].end - blocks[1].start, t / 3500000)

    def test_the_service_tape_holds_only_the_standard_blocks(self):
        data = tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02"), kcs(b"\x03" * 5))
        service = tape.service(tape.read("GAME.TSX", data))
        self.assertEqual(service, tape.HEADER + b"\xD0" * 10 + b"GAME  " + tape.HEADER + b"\x03" * 5)
        self.assertEqual(tape.load_command(service), 'BLOAD"CAS:",R')

    def test_an_unknown_block_or_file_is_refused(self):
        with self.assertRaisesRegex(tape.TapeError, "block 19h"):
            tape.read("GAME.TSX", tsx_file(b"\x19\x00\x00\x00\x00"))
        with self.assertRaisesRegex(tape.TapeError, "no ZXTape! signature"):
            tape.read("GAME.TSX", b"not a tape")
        with self.assertRaisesRegex(tape.TapeError, "not a CAS or TSX file"):
            tape.read("GAME.WAV", b"")


@unittest.skipUnless(os.path.isfile(os.path.join(TSX_DIR, "LAZERBYK.TSX")), "CAS_DIR holds no tsx/LAZERBYK.TSX")
class Files(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(TSX_DIR, name), "rb") as f:
            return tape.read(name, f.read())

    @unittest.skipUnless(os.path.isfile(os.path.join(COLLECTION, "035-EDGY.CAS")), "no collection/035-EDGY.CAS")
    def test_a_tsx_file_of_standard_blocks_gives_its_cas_files_tape(self):
        with open(os.path.join(COLLECTION, "035-EDGY.CAS"), "rb") as f:
            cas_data = f.read()
        blocks = self.read("LAZERBYK.TSX")
        self.assertTrue(all(b.standard for b in blocks))
        self.assertEqual(tape.service(blocks).rstrip(b"\0"), cas_data.rstrip(b"\0"))

    def test_the_times_end_where_openmsx_ends_the_tape(self):
        names = [n for n in ("LAZERBYK.TSX", "LICENCE.TSX", "4X4OFFRO.TSX") if os.path.isfile(os.path.join(TSX_DIR, n))]
        out = os.path.join(ROOT, "out", "test", "step15", "lengths.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        script = f"set f [open {msx.tcl_word(out)} w]\n"
        for n in names:
            script += f"cassetteplayer insert {msx.tcl_word(os.path.join(TSX_DIR, n))}\nputs $f [cassetteplayer getlength]\n"
        msx.run(["-machine", "Sanyo_PHC-28S"], script + "close $f\nexit\n", timeout=120)
        with open(out) as f:
            lengths = [float(v) for v in f.read().split()]
        for n, length in zip(names, lengths):
            with self.subTest(name=n):
                self.assertAlmostEqual(self.read(n)[-1].end, length, delta=0.05)


if __name__ == "__main__":
    unittest.main()
