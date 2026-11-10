"""The tape files as the tools read them (docs/INTERNALS.md, Tape files, and
docs/FORMATS.md, CAS data and TSX data): the readers of CAS and TSX files, the
tape model, the tape service's tape, and a load that starts at a later file.
The tests write each tape's bytes. Pure tier."""
import os
import re
import struct
import unittest

import support
import build
import capture
from cas import HEADER as CAS_HEADER
import gamefile
import tape
import tsx


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
        self.assertEqual(service, CAS_HEADER + b"\xD0" * 10 + b"GAME  " + CAS_HEADER + b"\x03" * 5)
        self.assertEqual(tape.load_command(service), 'BLOAD"CAS:",R')

    def test_an_unknown_block_or_file_is_refused(self):
        with self.assertRaisesRegex(tape.TapeError, "block 19h"):
            tape.read("GAME.TSX", tsx_file(b"\x19\x00\x00\x00\x00"))
        with self.assertRaisesRegex(tape.TapeError, "no ZXTape! signature"):
            tape.read("GAME.TSX", b"not a tape")
        with self.assertRaisesRegex(tape.TapeError, "not a CAS or TSX file"):
            tape.read("GAME.WAV", b"")

    def test_a_block_that_the_files_end_cuts_is_refused(self):
        whole = (kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02"), b"\x13\x02\x10\x00\x20\x00",
                 b"\x21\x04name", b"\x10" + struct.pack("<HH", 1000, 2) + b"\x01\x02")
        for block in whole:
            tape.read("GAME.TSX", tsx_file(block))
            for cut in range(1, len(block)):
                with self.subTest(block=block[0], cut=cut):
                    with self.assertRaisesRegex(tape.TapeError, f"block {block[0]:02X}h at Ah goes past the file's end"):
                        tape.read("GAME.TSX", tsx_file(block[:cut]))
        # A block 4Bh whose length leaves out a part of its settings.
        with self.assertRaisesRegex(tape.TapeError, "block 4Bh at Ah is shorter than its 12 bytes"):
            tape.read("GAME.TSX", tsx_file(b"\x4B" + struct.pack("<I", 11) + bytes(11)))


class Model(unittest.TestCase):
    def test_a_tape_that_starts_with_a_turbo_block_needs_a_load_line(self):
        data = tsx_file(turbo(b"\x01\x02"), kcs(b"\xEA" * 10 + b"GAME  "))
        game = gamefile.read_game(support.game_folder(os.path.join(support.temp(self), "GAME"), "tsx GAME.TSX\n"))
        self.assertIsNone(capture.load_command(game, data))
        game.load = 'RUN"CAS:"'
        self.assertEqual(capture.load_command(game, data), 'RUN"CAS:"')

    def test_a_turbo_block_after_the_snapshot_stops_the_build(self):
        blocks = tape.read("GAME.TSX", tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02")))
        names = ("GAME.TSX", "")
        state = {"tapetime": f"{blocks[1].start - 1:.2f}", "tapeside": "1"}
        with self.assertRaisesRegex(build.BuildError, f"GAME.TSX: the non-standard block at {blocks[1].offset:X}h"):
            build.check_unread(state, (blocks, []), names, False)
        build.check_unread(state, (blocks, []), names, True)
        state["tapetime"] = f"{blocks[1].end:.2f}"
        build.check_unread(state, (blocks, []), names, False)

    def test_the_unread_blocks_are_those_of_the_side_that_the_tape_is_on_and_after(self):
        side1 = tape.read("GAME.TSX", tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02")))
        side2 = tape.read("GAMEB.TSX", tsx_file(turbo(b"\x03\x04")))
        names = ("GAME.TSX", "GAMEB.TSX")
        # On side 1 after its turbo block, side 2's is still to come.
        state = {"tapetime": f"{side1[1].end:.2f}", "tapeside": "1"}
        with self.assertRaisesRegex(build.BuildError, f"GAMEB.TSX: the non-standard block at {side2[0].offset:X}h, "
                                    r"\d+\.\d seconds into the tape, comes after the snapshot, and the tape service "
                                    "cannot serve it. The game file needs service no if the game never reads it"):
            build.check_unread(state, (side1, side2), names, False)
        # On side 2 after its block, side 1 is behind: nothing is unread.
        state = {"tapetime": f"{side2[0].end:.2f}", "tapeside": "2"}
        build.check_unread(state, (side1, side2), names, False)
        # On side 2 before its block.
        state["tapetime"] = "0.00"
        with self.assertRaisesRegex(build.BuildError, "GAMEB.TSX: the non-standard block"):
            build.check_unread(state, (side1, side2), names, False)

    def test_a_snapshot_without_the_tapes_time_stops_the_build_only_for_a_non_standard_block(self):
        standard = tape.read("GAME.TSX", tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), kcs(b"\x01\x02")))
        build.check_unread({}, (standard, []), ("GAME.TSX", ""), False)
        build.check_unread({}, (tape.read("GAME.CAS", CAS_HEADER + b"\xD0" * 10 + b"GAME  "), []), ("GAME.CAS", ""), False)
        turbo_tape = tape.read("GAME.TSX", tsx_file(turbo(b"\x01\x02")))
        with self.assertRaisesRegex(build.BuildError, "the snapshot has no tapetime: capture the game again"):
            build.check_unread({}, (turbo_tape, []), ("GAME.TSX", ""), False)
        build.check_unread({}, (turbo_tape, []), ("GAME.TSX", ""), True)
        # A turbo block without bytes, as a tone, is nothing to read.
        build.check_unread({}, (tape.read("GAME.TSX", tsx_file(turbo(b""))), []), ("GAME.TSX", ""), False)

    def test_an_offset_in_the_service_tape_is_an_offset_in_the_file(self):
        data = tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02"), kcs(b"\x11\x22\x33"))
        blocks = tape.read("GAME.TSX", data)
        service = tape.service(blocks)
        at = service.index(b"\x11\x22\x33")
        self.assertEqual(data[tape.file_offset(blocks, at):][:3], b"\x11\x22\x33")
        self.assertIsNone(tape.file_offset(blocks, 0))


class Start(unittest.TestCase):
    def test_the_cas_header_is_the_tape_services(self):
        # CAS_HEADER is the tools' one copy, and D_HEADER the assembly's.
        with open(os.path.join(support.ROOT, "src", "tape.inc")) as f:
            line = next(line for line in f if line.startswith("D_HEADER:"))
        values = re.findall(r"\b0?([0-9A-F]{2})h", line.split(";")[0])
        self.assertEqual(bytes.fromhex("".join(values)), CAS_HEADER)

    def test_a_cas_header_off_the_grid_starts_a_block(self):
        data = CAS_HEADER + b"\xEA" * 10 + b"FIRST " + b"\x1A" * 3 + CAS_HEADER + b"\x11\x22"
        blocks = tape.read("GAME.CAS", data)
        self.assertEqual([b.data for b in blocks], [b"\xEA" * 10 + b"FIRST " + b"\x1A" * 3, b"\x11\x22"])
        self.assertEqual(blocks[1].offset, data.rindex(b"\x11\x22"))

    def test_a_cas_copy_starts_at_the_named_file_on_the_grid(self):
        second = b"\xD0" * 10 + b"SKY   "
        data = (CAS_HEADER + b"\xEA" * 10 + b"FIRST " + b"\x1A" * 3
                + CAS_HEADER + second + CAS_HEADER + b"\x00\x80\x01\x80\x00\x80\xC9")
        copy = tape.start_copy("GAME.CAS", data, "SKY")
        self.assertEqual(copy, CAS_HEADER + second + CAS_HEADER + b"\x00\x80\x01\x80\x00\x80\xC9")
        self.assertEqual(tape.load_command(copy), 'BLOAD"CAS:",R')

    def test_a_tsx_copy_starts_at_the_named_files_block(self):
        data = tsx_file(kcs(b"\xEA" * 10 + b"FIRST "), kcs(b"\x1A" * 8), kcs(b"\xD0" * 10 + b"SKY   "), kcs(b"\xC9"))
        copy = tape.start_copy("GAME.TSX", data, "SKY")
        self.assertEqual(copy[:10], data[:10])
        self.assertEqual([b.data for b in tape.read("GAME.TSX", copy)], [b"\xD0" * 10 + b"SKY   ", b"\xC9"])

    def test_an_offset_in_a_copys_tape_is_an_offset_in_the_downloaded_file(self):
        # scan.txt gives a finding's place for a patch line, which is applied
        # to the downloaded file, before the copy.
        call = b"\xCD\xE1\x00"
        cas = (CAS_HEADER + b"\xEA" * 10 + b"FIRST " + b"\x1A" * 3
               + CAS_HEADER + b"\xD0" * 10 + b"SKY   " + CAS_HEADER + b"\x00\x80" + call)
        tsx_data = tsx_file(kcs(b"\xEA" * 10 + b"FIRST "), kcs(b"\x1A" * 8), kcs(b"\xD0" * 10 + b"SKY   "),
                            kcs(b"\x00\x80" + call))
        for name, data in (("GAME.CAS", cas), ("GAME.TSX", tsx_data)):
            with self.subTest(name=name):
                copy = tape.start_copy(name, data, "SKY")
                at = tape.service(tape.read(name, copy)).index(call)
                self.assertEqual(tape.file_offset(tape.start_blocks(name, data, "SKY"), at), data.index(call))
                self.assertNotEqual(tape.file_offset(tape.read(name, copy), at), data.index(call))

    def test_a_name_that_is_no_files_block_is_refused(self):
        data = CAS_HEADER + b"\xEA" * 10 + b"FIRST " + b"\xD0" * 10 + b"SKY   "
        with self.assertRaisesRegex(tape.TapeError, "SKY is inside a block"):
            tape.start_copy("GAME.CAS", data, "SKY")
        with self.assertRaisesRegex(tape.TapeError, "no file named MOON"):
            tape.start_copy("GAME.CAS", data, "MOON")


if __name__ == "__main__":
    unittest.main()
