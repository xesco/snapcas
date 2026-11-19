"""The image as tools/build.py makes it (docs/INTERNALS.md, Build, and
docs/FORMATS.md, Image, Tail, Port writes and SERVICE.BIN): its helpers, the
layout's one source, and images of the snapshot that support.snapshot writes,
through the functions and through build.py as a program. Pure tier."""
import os
import struct
import unittest

import support
import build
from cas import HEADER as CAS_HEADER
import gamefile
import msx
import patches
from snapshot import Snapshot

SERVICE = support.SERVICE
MACHINE = support.VG8020


def a_game(service=None, **values):
    """A game file's settings, without a file."""
    game = gamefile.Game("GAME")
    game.tape, game.service = "GAME.CAS", service
    for name, value in values.items():
        setattr(game, name, value)
    return game


class Crc(unittest.TestCase):
    def test_check_value(self):
        # The check value of CRC-16/CCITT-FALSE.
        self.assertEqual(build.crc16(b"123456789"), 0x29B1)


class PortWrites(unittest.TestCase):
    def state(self, v9938=True, v9958=False, **values):
        """A snapshot with the state that the test gives."""
        values = dict(dict(psgsel="0E", ppic="50", vramptr="00000", vramwrite="1"), **values)
        return Snapshot(support.snapshot(support.temp(self), v9938=v9938, v9958=v9958, **values))

    def test_psg_register_7_and_the_selected_register(self):
        w = build.port_writes(self.state(psg7="3F", psgsel="0E"), False)
        self.assertEqual(w[14:16], [(0xA0, 7), (0xA1, 0xBF)])
        self.assertEqual(w[32], (0xA0, 0x0E))
        self.assertEqual(w[33], (0xAA, 0x50))

    def test_write_setup(self):
        w = build.port_writes(self.state(vramptr="01234", vramwrite="1"), True)
        self.assertEqual(w[-2:], [(0x99, 0x34), (0x99, 0x52)])

    def test_read_setup_writes_the_pointer_minus_1(self):
        w = build.port_writes(self.state(vramptr="01234", vramwrite="0"), True)
        self.assertEqual(w[-2:], [(0x99, 0x33), (0x99, 0x12)])

    def test_read_setup_borrows_from_register_14(self):
        w = build.port_writes(self.state(vramptr="08000", vramwrite="0"), True)
        self.assertEqual(w[-4:], [(0x99, 1), (0x99, 0x8E), (0x99, 0xFF), (0x99, 0x3F)])

    def test_v9938_order(self):
        w = build.port_writes(self.state(pal1="7005"), True)
        self.assertEqual(w[34:36], [(0x99, 0), (0x99, 0x90)])
        self.assertEqual(w[38:40], [(0x9A, 0x70), (0x9A, 0x05)])
        self.assertEqual(w[68:70], [(0x99, 32), (0x99, 0x91)])
        self.assertEqual([p for p, _ in w[70:84]], [0x9B] * 14)
        self.assertEqual(len(w), 34 + 2 + 32 + 2 + 14 + 48 + 2)

    def test_v9958_registers_after_register_23(self):
        # An MSX2+'s registers 25 to 27 follow the V9938's 0 to 23, before the
        # pointer.
        w = build.port_writes(self.state(v9958=True, vdp25="03", vdp26="11", vdp27="07"), True)
        self.assertEqual(w[-8:-2], [(0x99, 0x03), (0x99, 0x99), (0x99, 0x11), (0x99, 0x9A), (0x99, 0x07), (0x99, 0x9B)])
        self.assertEqual(len(w), 34 + 2 + 32 + 2 + 14 + 48 + 6 + 2)

    def test_msx1_order(self):
        # The PSG's 16 registers, its selected register, the PPI's port C,
        # the VDP's 8 registers, each as its value and its number, and the
        # pointer: 52 writes.
        w = build.port_writes(self.state(False, psg0="11", psg15="FF", vdp0="02", vdp7="F4", vramptr="03FFF"), False)
        self.assertEqual(w[:2] + w[30:32], [(0xA0, 0), (0xA1, 0x11), (0xA0, 15), (0xA1, 0xFF)])
        self.assertEqual(w[34:36] + w[48:50], [(0x99, 0x02), (0x99, 0x80), (0x99, 0xF4), (0x99, 0x87)])
        self.assertEqual(w[50:], [(0x99, 0xFF), (0x99, 0x7F)])
        self.assertEqual(len(w), 34 + 16 + 2)

    def test_an_msx1_read_setup_wraps_at_its_14_bits(self):
        w = build.port_writes(self.state(False, vramptr="00000", vramwrite="0"), False)
        self.assertEqual(w[-2:], [(0x99, 0xFF), (0x99, 0x3F)])
        self.assertEqual(len(w), 52)


class ServiceFile(unittest.TestCase):
    """SERVICE.BIN as build.py reads it (FORMATS.md, SERVICE.BIN)."""

    def setUp(self):
        self.path = SERVICE
        with open(self.path, "rb") as f:
            self.data = bytearray(f.read())

    def changed(self):
        path = os.path.join(support.temp(self), "SERVICE.BIN")
        with open(path, "wb") as f:
            f.write(self.data)
        return path

    def test_the_symbols_give_the_assemblys_addresses_by_name(self):
        service = build.read_service(self.path)
        self.assertEqual((service.entry_page, service.moved), (0xFC, False))
        self.assertEqual(service["E_ENTRY"], 0xFCE1)
        self.assertEqual(service["t_tapion"], 0x1A63)
        self.assertEqual(service.field("D_POS", False), 0)
        self.assertEqual(service.field("D_POS", True), service["T0_CODE"])
        with self.assertRaisesRegex(build.BuildError, "SERVICE.BIN has no symbol E_NONE"):
            service["E_NONE"]

    def test_the_symbols_in_the_part_of_page_3_move_with_it(self):
        service = build.read_service(self.path)
        moved = service.at(0xF1)
        self.assertEqual((moved.entry_page, moved.moved), (0xF1, True))
        self.assertEqual(moved["E_ENTRY"], 0xF1E1)
        self.assertEqual(moved["E_FC"] - moved["E_ENTRY"], service["E_FC"] - service["E_ENTRY"])
        # The addresses outside the part stay, and the part's code follows it.
        self.assertEqual(moved["D_POS"], service["D_POS"])
        self.assertEqual(moved["P3_FREE"], 0xFCC9)
        self.assertEqual(len(moved.parts["page3"]), len(service.parts["page3"]))
        # The first entry is a jump into the part: its target's high byte moves.
        jump = service.parts["page3"][:3]
        self.assertEqual(moved.parts["page3"][:3], bytes([0xC3, jump[1], jump[2] + 0xF1 - 0xFC]))
        # T0's stubs jump into the part.
        self.assertNotEqual(moved.parts["stubs"], service.parts["stubs"])
        self.assertEqual(moved.parts["tail"], service.parts["tail"])

    def test_a_tail_of_another_length_is_refused(self):
        offset, length = struct.unpack_from("<HH", self.data, 2)
        struct.pack_into("<HH", self.data, 2, offset, length - 1)
        with self.assertRaisesRegex(build.BuildError, "a tail of 25 bytes, expected 26"):
            build.read_service(self.changed())

    def test_another_number_of_parts_is_refused(self):
        self.data[1] += 1
        with self.assertRaisesRegex(build.BuildError, "10 parts, expected 9"):
            build.read_service(self.changed())

    def test_another_version_or_an_empty_file_is_refused(self):
        self.data[0] = build.SERVICE_VERSION + 1
        with self.assertRaisesRegex(build.BuildError, f"version {build.SERVICE_VERSION + 1}, expected "
                                    f"{build.SERVICE_VERSION}: build it from this snapcas"):
            build.read_service(self.changed())
        self.data = bytearray()
        with self.assertRaisesRegex(build.BuildError, "version none"):
            build.read_service(self.changed())


class Layout(unittest.TestCase):
    """The image's layout has one source, src/service.inc, which the restorer
    and SERVICE.BIN are assembled from (FORMATS.md, Image)."""

    # The names of the fields of FORMATS.md's table of the image, in its
    # order: None for the mark and for the bytes that are zero.
    FIELDS = (None, "H_ROM", "H_SUBROM", "H_RECS", "H_WRITES", "H_FLAGS", "H_P3", "H_REGS", "H_I", "H_IM", "H_IFF",
              "H_A8", "H_SUB", "H_MAP", "H_TAIL", "H_VDP1", "H_BORROW", "H_NOEXP", "H_TAILREC", "H_P3REC",
              "H_PLACES", None, "H_TABLE")

    def setUp(self):
        self.service = build.read_service(SERVICE)

    def test_the_restorer_and_service_bin_have_the_same_layout(self):
        restorer = support.symbols("snapcas")
        shared = [name for name in self.service.symbols
                  if name.startswith(("H_", "REC_", "FLAG_", "TAIL_")) or name in ("IMAGE_FORMAT", "DATA_SIZE",
                                                                                    "WRITE_SIZE", "PLACE_SIZE")]
        self.assertGreater(len(shared), 35)
        for name in shared:
            with self.subTest(name=name):
                self.assertEqual(self.service[name], restorer[name])

    def test_the_restorer_holds_the_mark_that_the_build_writes(self):
        self.assertEqual(self.service.mark, b"SNAPCAS6")
        with open(support.COM, "rb") as f:
            self.assertIn(self.service.mark, f.read())

    def test_the_formats_page_gives_each_fields_offset(self):
        with open(os.path.join(support.ROOT, "docs", "FORMATS.md")) as f:
            section = f.read().split("\n## Image\n")[1].split("\n## ")[0]
        table = section.split("| Offset | Size | Field |\n|---|---|---|\n")[1].split("\n\n")[0]
        rows = [line.split("|")[1].strip() for line in table.splitlines()]
        self.assertIn(self.service.mark.decode(), table.splitlines()[0])
        self.assertEqual(len(rows), len(self.FIELDS) + 2)  # then the port writes and the places
        for row, name in zip(rows, self.FIELDS):
            if name:
                with self.subTest(name=name):
                    self.assertEqual(int(row), self.service[name])

    def test_the_tails_fields_are_where_the_formats_page_has_them(self):
        with open(os.path.join(support.ROOT, "docs", "FORMATS.md")) as f:
            section = f.read().split("\n## Tail\n")[1].split("\n## ")[0]
        offsets = [int(line.split("|")[1]) for line in section.splitlines() if line[:3] == "| " + line[2:3]
                   and line[2:3].isdigit()]
        # Each operand follows its opcode, at the offset of its row plus 1.
        for name, row in (("TAIL_PORT", 2), ("TAIL_STACK", 13), ("TAIL_SP", 17), ("TAIL_EI", 20), ("TAIL_JP", 21),
                          ("TAIL_AF", 24)):
            self.assertIn(row, offsets)
            self.assertEqual(self.service[name], row + (name in ("TAIL_PORT", "TAIL_STACK", "TAIL_SP")), name)
        self.assertEqual(self.service["TAIL_PC"], self.service["TAIL_JP"] + 1)
        self.assertEqual(len(self.service.parts["tail"]), build.TAIL_SIZE)


class Synthetic(unittest.TestCase):
    """Images of snapshots that the test writes, for the cases that no tape of
    the tests gives."""

    def snapshot(self, ram, **state):
        values = dict(a8="00", fc="00", fd="00", fe="00", ff="00", sp="0000", pc="0000")
        return support.snapshot(support.temp(self), ram=ram, **dict(values, **state))

    def game(self, service=None):
        return a_game(service)

    def test_a_segment_in_two_pages_has_one_record_that_the_header_names(self):
        # Segment 5 of the mapper in slot 3 is in pages 2 and 3, and the stack
        # is in page 3. The capture writes the segment once for each page.
        ram = {"3-x-1-2": bytes(build.PAGE), "3-x-2-5": bytes(build.PAGE), "3-x-3-5": bytes(build.PAGE)}
        snap = support.snapshot(support.temp(self), shared=True, service=True, pc="1234")
        self.assertEqual(sorted(os.listdir(os.path.join(snap, "ram"))), sorted(name + ".bin" for name in ram))
        header, data, _, _, checked = build.build(Snapshot(snap), SERVICE, self.game())
        h, s = support.Header(header), build.read_service(SERVICE)
        self.assertEqual(h.records[:2], [(s["REC_MAPPER"], 3, 1, 2), (s["REC_MAPPER"], 3, 2, 5)])
        self.assertEqual([r[0] for r in h.records].count(s["REC_MAPPER"]), 2)
        # Its record has the lower page, 2, and holds the tail and the
        # service's part of page 3.
        self.assertEqual((h["H_TAILREC"], h["H_P3REC"]), (1, 1))
        tail = h.word("H_TAIL")
        self.assertEqual(tail, 0xF000 - build.TAIL_SIZE)
        code = data[1][tail & 0x3FFF:][:build.TAIL_SIZE]
        self.assertEqual(struct.unpack_from("<H", code, s["TAIL_PC"])[0], 0x1234)
        self.assertEqual(code[s["TAIL_JP"]], 0xC3)
        part = s["E_ENTRY"] & 0x3FFF
        self.assertEqual(data[1][part:part + len(s.parts["page3"])][:1], s.parts["page3"][:1])
        self.assertIn(f"tail {tail} {build.TAIL_SIZE - 1} {s['TAIL_PORT']} {s['TAIL_JP']}\n", checked)

    def test_a_record_keeps_segment_255(self):
        ram = {"3-x-1-255": bytes(build.PAGE), "3-x-3-0": bytes(build.PAGE)}
        snap = self.snapshot(ram, a8="FC", fd="FF", sp="F000", **{"mapper3-x": "100"})
        self.assertEqual(Snapshot(snap).selected_ram(1).name.seg, 255)
        header, _, _, _, _ = build.build(Snapshot(snap), SERVICE, self.game())
        h, s = support.Header(header), build.read_service(SERVICE)
        self.assertEqual(h.records[0], (s["REC_MAPPER"], 3, 1, 255))
        self.assertEqual((h["H_TAILREC"], h["H_P3REC"]), (1, 0))

    # Altered Beast's stub of TAPION, which selects the ROM in page 0.
    STUB = bytes.fromhex("11 E1 00 D5 11 D9 CD D5 11 ED 69 D5 E5 D9 0E A8 ED 60 A4 6F CD 9A FC")

    def test_without_a_part_in_page_3_the_header_lists_the_stubs_value_for_the_restorer(self):
        # Page 0 is RAM of slot 1, outside a mapper, with the stub at 0100h.
        page0 = bytearray(build.PAGE)
        page0[0x100:0x100 + len(self.STUB)] = self.STUB
        snap = self.snapshot({"1-x-0-x": bytes(page0), "3-x-3-0": bytes(build.PAGE)}, a8="C1", sp="F000", service="1",
                        **{"mapper3-x": "20"})
        # The tape holds the stub too, in a block that the game has not read.
        side1 = CAS_HEADER + b"\xD0" * 10 + b"GAME  " + CAS_HEADER + self.STUB
        header, data, _, scanned, checked = build.build(Snapshot(snap), SERVICE, self.game("t0"), side1)
        h, s = support.Header(header), build.read_service(SERVICE)
        self.assertEqual(h["H_FLAGS"], s["FLAG_T0"])
        # The build writes LD L,n with n at 0, and the place of n.
        self.assertEqual(h.places, [(0, 0x100 + 19)])
        self.assertEqual(data[0][0x100 + 18:0x100 + 20], bytes([0x2E, 0x00]))
        self.assertIn("patched 1-x-0 274 275\n", checked)
        self.assertIn("page0:0112 A4 6F > 2E nn  stub's selection of the ROM in page 0\n", scanned)
        # No entries in page 3: the code that reaches the tape is only listed,
        # and so is the stub on the tape, whose bytes the restorer cannot fill.
        self.assertIn("page0:0100 11 E1 00 D5 11 D9 CD D5  stub of TAPION\n", scanned)
        self.assertIn("side1:0032 A4 6F  stub's selection of the ROM in page 0\n", scanned)
        self.assertEqual(scanned.count(" > "), 1)
        self.assertNotIn("FC D5", scanned)

    def test_with_a_part_in_page_3_the_stub_goes_to_its_entries(self):
        page0 = bytearray(build.PAGE)
        page0[0x100:0x100 + len(self.STUB)] = self.STUB
        snap = self.snapshot({"1-x-0-x": bytes(page0), "3-x-3-0": bytes(build.PAGE)}, a8="C1", sp="F000", service="1",
                        **{"mapper3-x": "20"})
        header, data, _, scanned, _ = build.build(Snapshot(snap), SERVICE, self.game())
        h = support.Header(header)
        self.assertEqual((h["H_FLAGS"], h["H_PLACES"], h.places), (0, 0, []))
        self.assertIn("page0:0100 11 E1 00 D5 11 D9 CD D5 > 11 E1 FC D5 11 D9 CD D5  stub of TAPION\n", scanned)
        self.assertEqual(data[0][0x100 + 18:0x100 + 20], bytes([0xA4, 0x6F]))

    def test_the_patched_builders_call_the_tape_service(self):
        # The capture's trampoline patch, in page 0 and in a block that the
        # game has not read, and its trampoline at FC9Ah: each calls the
        # entries in page 3, with the RAM's subslot in page 0.
        new = patches.tramp.patched(0, 1) + patches.tramp.CALL
        page0 = bytearray(build.PAGE)
        page0[0x100:0x100 + len(new)] = new
        page3 = bytearray(build.PAGE)
        page3[0x3C9A:0x3CA4] = bytes.fromhex("36 54 D9 CD E4 00 D9 71 C9 C4")
        snap = self.snapshot({"1-x-0-x": bytes(page0), "3-x-3-0": bytes(page3)}, a8="C1", sp="F000", service="1",
                             **{"mapper3-x": "20"})
        side1 = CAS_HEADER + b"\xD0" * 10 + b"GAME  " + CAS_HEADER + new
        image = build.Image(Snapshot(snap), build.read_service(SERVICE), self.game())
        tape1, _, ranges = image.serve_trampolines(side1, b"")
        served = bytearray(new)
        patches.tramp.serve(served, 0xFC)
        self.assertEqual(image.snapshot.selected_ram(0).data[0x100:0x100 + len(new)], served)
        self.assertEqual(tape1, side1[:-len(new)] + served)
        self.assertEqual(image.p3.data[0x3C9A:0x3CA0], bytes.fromhex("36 55 D9 CD E4 FC"))
        self.assertEqual(ranges, ["1-x-0 256 283", "3-x-3 15514 15519"])
        _, _, _, scanned, checked = build.build(Snapshot(snap), SERVICE, self.game(), side1)
        self.assertIn("patched 1-x-0 256 283\n", checked)
        # The stub's call already goes to the entries, so the scan lists
        # nothing of it.
        self.assertNotIn("stub of TAPION", scanned)

    def test_without_the_tape_service_the_builders_keep_the_bios(self):
        new = patches.tramp.patched(0, 1) + patches.tramp.CALL
        page0 = bytearray(build.PAGE)
        page0[0x100:0x100 + len(new)] = new
        snap = self.snapshot({"1-x-0-x": bytes(page0), "3-x-3-0": bytes(build.PAGE)}, a8="C1", sp="F000",
                             **{"mapper3-x": "20"})
        _, data, _, _, _ = build.build(Snapshot(snap), SERVICE, self.game())
        self.assertEqual(data[0][0x100:0x100 + len(new)], new)

    def test_a_record_number_is_at_most_254(self):
        # The header holds each table's length in one byte, so a record's
        # number, in the header and in a place, is below 255.
        service = build.read_service(SERVICE)
        snap = self.snapshot({"3-x-3-0": bytes(build.PAGE)}, a8="C0", sp="F000")
        image = build.Image(Snapshot(snap), service, self.game())
        image.place_tail()
        records = [bytes([service["REC_ZEROS"], 0, 0, 0])] * 255
        full = image.header(records, [(0, 0)] * 255, [(image.tail.ram_page, 0)] * 255)
        self.assertEqual(len(full), service["H_SIZE"])
        with self.assertRaisesRegex(build.BuildError, "too many records, port writes or places"):
            image.header(records + records[:1], [], [])


class ResidentCall(unittest.TestCase):
    """The call of a machine's resident program from T0's jump at 0038h
    (FILES.md, Machine file, resident; INTERNALS.md, The resident program's
    call)."""

    # In slot 2-0, with its entry in page 1.
    RESIDENT = msx.Resident(0x82, 0x4040, bytes.fromhex("F5 DB FD F5 3E 00 F1 F1 C9"))

    def page3(self, keyi=build.EMPTY_HOOK):
        """The game's page 3: SLTTBL's byte of slot 2, the BIOS's slot
        routines at F380h, and H.KEYI."""
        page3 = bytearray(build.PAGE)
        page3[(build.SLTTBL + 2) & 0x3FFF] = 0xF8
        first = build.BIOS_SLOT_CODE_AT & 0x3FFF
        page3[first:first + len(build.BIOS_SLOT_CODE)] = build.BIOS_SLOT_CODE
        at = build.H_KEYI & 0x3FFF
        page3[at:at + 5] = keyi
        return page3

    def build(self, game=None, ram=None, **state):
        ram = ram or {"3-x-3-0": bytes(self.page3())}
        values = dict(a8="C0", fc="00", fd="00", fe="00", ff="00", sp="F000", pc="0000", im="1", sub2="F8")
        service = state.pop("service", True)
        snap = support.snapshot(support.temp(self), ram=ram, service=service,
                                **dict(values, **state, **{"mapper3-x": "20"}))
        # The BIOS's jump to its interrupt routine.
        with open(os.path.join(snap, "rom.bin"), "r+b") as f:
            f.seek(0x38)
            f.write(bytes([0xC3, 0x3C, 0x0C]))
        return build.build(Snapshot(snap), SERVICE, game or a_game(), resident=self.RESIDENT)

    def t0(self, header, data):
        h, s = support.Header(header), build.read_service(SERVICE)
        types = [r[0] for r in h.records]
        first = types.index(s["REC_SERVICE"])
        return data[sum(1 for t in types[:first] if t != s["REC_ZEROS"])]

    def test_t0s_jump_at_0038h_calls_the_program_and_goes_on_to_the_bios(self):
        header, data, _, _, checked = self.build()
        s, t0 = build.read_service(SERVICE), self.t0(header, data)
        self.assertEqual(t0[0x38:0x3B], bytes([0xC3]) + struct.pack("<H", s["t_res"]))
        self.assertEqual(t0[s["t_res.jump"]:s["t_res.jump"] + 3], bytes([0xC3, 0x3C, 0x0C]))
        self.assertEqual(t0[s["t_res.call"]:s["t_res.call"] + 3], bytes([0xCD, 0x40, 0x40]))
        # Page 1: the slot register's mask, and slot 2 there.
        self.assertEqual([t0[s[f"t_res.{name}"] + 1] for name in ("mask", "slot")], [0xF3, 0x08])
        # DI / LD (.back+1),SP / LD SP,T_STACK: its stack in T0, below t_tapion.
        self.assertEqual(t0[s["t_res"]:s["t_res"] + 8], bytes([0xF3, 0xED, 0x73]) + struct.pack("<H", s["t_res.back"] + 1)
                         + bytes([0x31]) + struct.pack("<H", s["T_STACK"]))
        self.assertEqual(s["T_STACK"], s["t_tapion"])
        self.assertEqual(t0[s["T_STACK"] - 4 - s["RES_STACK"]:s["T_STACK"]], bytes(4 + s["RES_STACK"]))
        # The entry's first two bytes, at 4040h and 4041h.
        self.assertEqual((t0[s["t_res.at1"] + 1:s["t_res.at1"] + 3], t0[s["t_res.is1"] + 1]), (b"\x40\x40", 0xF5))
        self.assertEqual((t0[s["t_res.at2"] + 1:s["t_res.at2"] + 3], t0[s["t_res.is2"] + 1]), (b"\x41\x40", 0xDB))
        self.assertIn("rescall t0\n", checked)

    def test_the_programs_subslot_goes_into_its_slots_register_and_sltttbl(self):
        header, data, _, _, checked = self.build()
        h, s = support.Header(header), build.read_service(SERVICE)
        # F8h has subslot 2 in page 1, and the program is in subslot 0.
        self.assertEqual(header[s["H_SUB"] + 2], 0xF0)
        at = (build.SLTTBL + 2) & 0x3FFF
        self.assertEqual(data[0][at], 0xF0)
        self.assertIn(f"patched 3-x-3 {at} {at}\n", checked)

    def test_a_game_off_the_bioss_interrupt_routine_gets_no_call_from_t0(self):
        cases = ((dict(im="2"), None, "im2"), (dict(), a_game(rom_keep=True), "romkeep"),
                 # Page 1 in slot 2 at the snapshot, with subslot 2 there.
                 (dict(a8="C8"), None, "slotbusy"))
        for state, game, kind in cases:
            with self.subTest(kind=kind):
                header, data, _, _, checked = self.build(game=game, **state)
                self.assertIn(f"rescall {kind}\n", checked)
                self.assertEqual(header[build.read_service(SERVICE)["H_SUB"] + 2], 0xF8)
                self.assertEqual(self.t0(header, data)[0x38:0x3B], bytes([0xC3, 0x3C, 0x0C]))

    def test_rescall_no_leaves_the_call_out(self):
        header, data, _, _, checked = self.build(game=a_game(rescall="no"))
        self.assertIn("rescall off\n", checked)
        self.assertEqual(self.t0(header, data)[0x38:0x3B], bytes([0xC3, 0x3C, 0x0C]))

    def core(self, data, size, offset=0, at=None):
        at = ((build.CALL_AT if at is None else at) & 0x3FFF) + offset
        return data[0][at:at + size]

    def resb(self, s, name):
        """A field of resb, from the routine's start."""
        return s[f"resb.{name}"] - s["resb"]

    def test_without_the_tape_service_h_keyi_calls_a_routine_in_sltwrk_at_fd29h(self):
        header, data, _, _, checked = self.build(service=False)
        s = build.read_service(SERVICE)
        # Only resb, the call through the BIOS's RDSLT and CALSLT, of 55 bytes.
        routine = s.parts["call"][s["resb"]:s["res3g"]]
        self.assertEqual(len(routine), 55)
        code = self.core(data, len(routine))
        f = lambda name: self.resb(s, name)
        # The slot ID 82h for RDSLT, the entry's bytes.
        self.assertEqual([code[f(name) + 1] for name in ("id1", "is1", "id2", "is2")], [0x82, 0xF5, 0x82, 0xDB])
        # LD A,I / JP PE,.on / LD A,I / .on: DI, which keeps IFF2 for the end.
        self.assertEqual(code[4:12], bytes([0xED, 0x57, 0xEA]) + struct.pack("<H", build.CALL_AT + f("on"))
                         + bytes([0xED, 0x57, 0xF3]))
        # Its stack, RESB_STACK zeros just below its end, resbe, placed after
        # resb in SLTWRK (FD60h..FD87h) rather than dipping into SLTATR:
        # LD (resbe.back+1),SP / LD SP,resbe.
        size = s["sub0"] - s["resbe"]
        stack = build.CALL_AT + len(routine)
        end = stack + s["RESB_STACK"]
        self.assertGreaterEqual(stack, build.SLTWRK)
        self.assertEqual(code[f("save"):f("save") + 4], bytes([0xED, 0x73]) + struct.pack("<H", end + 1))
        self.assertEqual(code[f("stack"):f("stack") + 3], bytes([0x31]) + struct.pack("<H", end))
        self.assertEqual(code[f("tail"):f("tail") + 3], bytes([0xC3]) + struct.pack("<H", end))
        self.assertIn(f"resstack {stack} {end + size - 1}\n", checked)
        self.assertEqual(self.core(data, s["RESB_STACK"], at=stack), bytes(s["RESB_STACK"]))
        # resbe: LD SP,0 / POP DE, BC, HL / JP PO,.off / EI / .off: POP AF / RET.
        self.assertEqual(self.core(data, size, at=end), bytes([0x31, 0, 0, 0xD1, 0xC1, 0xE1, 0xE2])
                         + struct.pack("<H", end + 10) + bytes([0xFB, 0xF1, 0xC9]))
        self.assertIn(f"patched 3-x-3 {end & 0x3FFF} {(end & 0x3FFF) + size - 1}\n", checked)
        # The entry for the first RDSLT, and INC HL for the second.
        self.assertEqual(code[f("at1") + 1:f("at1") + 3], b"\x40\x40")
        # LD IY,8200h and LD IX,4040h for CALSLT.
        self.assertEqual(code[f("iy"):f("iy") + 4], bytes([0xFD, 0x21, 0x00, 0x82]))
        self.assertEqual(code[f("call"):f("call") + 4], bytes([0xDD, 0x21, 0x40, 0x40]))
        # H.KEYI: CALL the routine / RET.
        keyi = build.H_KEYI & 0x3FFF
        self.assertEqual(data[0][keyi:keyi + 5], bytes([0xCD]) + struct.pack("<H", build.CALL_AT) + b"\xC9\xC9")
        self.assertIn("rescall hook\n", checked)
        # The segment of the game's page 3 follows, 0 here.
        self.assertIn(f"rescode {build.CALL_AT} {build.CALL_AT + len(routine) - 1} 0\n", checked)
        self.assertEqual(header[s["H_SUB"] + 2], 0xF0)

    def test_a_hook_in_use_runs_after_the_call(self):
        keyi = build.H_KEYI & 0x3FFF
        page3 = self.page3(bytes([0xC3, 0x00, 0x90, 0xC9, 0xC9]))
        _, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)})
        s = build.read_service(SERVICE)
        size = s["res3g"] - s["resb"]
        chain = build.CALL_AT + size
        self.assertEqual(data[0][keyi:keyi + 5], bytes([0xC3]) + struct.pack("<H", chain) + b"\xC9\xC9")
        # CALL the routine / the game's old hook.
        self.assertEqual(self.core(data, 8, size), bytes([0xCD]) + struct.pack("<H", build.CALL_AT)
                         + bytes([0xC3, 0x00, 0x90, 0xC9, 0xC9]))
        self.assertIn(f"rescode {build.CALL_AT} {chain + 7} 0\n", checked)

    def test_a_games_own_routine_in_mode_2_gets_a_wrapper_without_the_tape_service(self):
        # The vector at the I register's page, FFh and 00h: in the RAM of page 3.
        page3 = self.page3()
        page3[0x3DFF] = 0x34
        page3[0x3E00] = 0x92
        header, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)}, im="2", i="FD")
        s = build.read_service(SERVICE)
        # Only res3, which selects the program's slot by the slot register.
        size = s["resb"]
        wrapper = build.CALL_AT + size
        # The vector goes to the wrapper: CALL the routine / JP the game's 9234h.
        self.assertEqual(bytes(data[0][0x3DFF:0x3E01]), struct.pack("<H", wrapper))
        self.assertEqual(self.core(data, 6, size), bytes([0xCD]) + struct.pack("<H", build.CALL_AT)
                         + bytes([0xC3, 0x34, 0x92]))
        self.assertIn(f"resvector {wrapper} {0x9234}\n", checked)
        self.assertIn("rescall im2\n", checked)

    def test_rescall_on_the_h_keyi_call_puts_the_wrapper_after_resb(self):
        # A game that writes its own routine into H.KEYI after the snapshot, as
        # Choper does: H.KEYI calls resb, and the wrapper follows resb.
        _, data, _, _, checked = self.build(service=False, game=a_game(rescall=[0x42C2]))
        s = build.read_service(SERVICE)
        size = s["res3g"] - s["resb"]
        wrapper = build.CALL_AT + size
        self.assertEqual(self.core(data, 6, size), bytes([0xCD]) + struct.pack("<H", build.CALL_AT)
                         + bytes([0xC3, 0xC2, 0x42]))
        self.assertIn(f"resvector {wrapper} {0x42C2}\n", checked)
        self.assertIn("rescall hook\n", checked)

    def test_rescall_with_two_routines_puts_a_wrapper_for_each(self):
        # A title's routine and a play's, as Police Academy installs.
        _, data, _, _, checked = self.build(service=False, game=a_game(rescall=[0xD160, 0x42A7]))
        s = build.read_service(SERVICE)
        # resb and two wrappers take 67 bytes, more than the 64 at FD29h, so
        # they go to FCC9h.
        size, at = s["res3g"] - s["resb"], s["P3_FREE"]
        first = at + size
        self.assertEqual(self.core(data, 12, size, at), bytes([0xCD]) + struct.pack("<H", at)
                         + bytes([0xC3, 0x60, 0xD1, 0xCD]) + struct.pack("<H", at) + bytes([0xC3, 0xA7, 0x42]))
        self.assertIn(f"resvector {first} {0xD160} {first + 6} {0x42A7}\n", checked)
        # With the tape service, the wrappers take 17 bytes each, and the room
        # before the part's entries holds one.
        with self.assertRaisesRegex(build.BuildError, "rescall needs 34 bytes"):
            self.build(game=a_game(rescall=[0xD160, 0x42A7]))

    def test_without_room_in_the_zeros_the_automatic_call_is_left_out(self):
        page3 = self.page3()
        for at in (build.CALL_AT, build.read_service(SERVICE)["P3_FREE"]):
            page3[at & 0x3FFF] = 0x55
        header, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)})
        self.assertIn("rescall p3busy\n", checked)
        self.assertNotIn("rescode", checked)
        keyi = build.H_KEYI & 0x3FFF
        self.assertEqual(data[0][keyi:keyi + 5], build.EMPTY_HOOK)
        self.assertEqual(header[build.read_service(SERVICE)["H_SUB"] + 2], 0xF8)

    def test_without_room_the_game_files_rescall_stops_the_build(self):
        page3 = self.page3()
        for at in (build.CALL_AT, build.read_service(SERVICE)["P3_FREE"]):
            page3[at & 0x3FFF] = 0x55
        with self.assertRaisesRegex(build.BuildError, "rescall needs .* bytes of zeros at FD29h or FCC9h"):
            self.build(game=a_game(rescall=[0x9234]), service=False, ram={"3-x-3-0": bytes(page3)})

    def test_rescode_puts_the_call_where_the_game_file_says(self):
        # Death Wish uses FD29h and FCC9h, and leaves D393h on alone.
        page3 = self.page3()
        for at in (build.CALL_AT, build.read_service(SERVICE)["P3_FREE"]):
            page3[at & 0x3FFF] = 0x55
        _, data, _, _, checked = self.build(service=False, game=a_game(rescode=0xD393),
                                            ram={"3-x-3-0": bytes(page3)})
        s = build.read_service(SERVICE)
        size = s["res3g"] - s["resb"]
        keyi = build.H_KEYI & 0x3FFF
        self.assertEqual(data[0][keyi:keyi + 5], bytes([0xCD, 0x93, 0xD3, 0xC9, 0xC9]))
        self.assertIn(f"rescode {0xD393} {0xD393 + size - 1} 0\n", checked)
        self.assertIn("rescall hook\n", checked)
        # With the tape service, the wrapper goes there too, clear of the part.
        _, data, _, _, checked = self.build(game=a_game(rescall=[0xB45B], rescode=0xD393))
        self.assertEqual(data[0][0x1393:0x1393 + 3], bytes([0xF5, 0xC5, 0xD5]))
        self.assertIn(f"resvector {0xD393} {0xB45B}\n", checked)
        # The check ignores a difference there.
        self.assertIn(f"patched 3-x-3 {0x1393} {0x1393 + 16}\n", checked)
        with self.assertRaisesRegex(build.BuildError, f"rescall needs 17 bytes of zeros at {s['E_ENTRY'] - 4:04X}h"):
            self.build(game=a_game(rescall=[0xB45B], rescode=s["E_ENTRY"] - 4))

    def test_rescode_places_the_routine_alone_for_a_game_without_interrupts(self):
        # A game with its RAM in page 0, in slot 1, calls the routine from its
        # main loop.
        ram = {"1-x-0-x": bytes(build.PAGE), "3-x-3-0": bytes(self.page3())}
        _, data, _, _, checked = self.build(service=False, game=a_game(rescode=0xD393), ram=ram, a8="C1")
        s = build.read_service(SERVICE)
        at = (0xD393 & 0x3FFF) + s["res3.call"]
        self.assertIn(bytes([0xCC, 0x40, 0x40]), [bytes(d[at:at + 3]) for d in data])
        self.assertIn(f"rescode {0xD393} {0xD393 + s['resb'] - 1} 0\n", checked)
        self.assertIn("rescall page0\n", checked)
        _, _, _, _, checked = self.build(service=False, ram=ram, a8="C1")
        self.assertNotIn("rescode", checked)

    def test_without_the_bioss_slot_routines_h_keyi_calls_res3(self):
        # Super Cobra clears F380h to F7DBh: RDSLT and CALSLT would run zeros,
        # so H.KEYI calls res3, which selects the slot by the slot register.
        page3 = self.page3()
        first = build.BIOS_SLOT_CODE_AT & 0x3FFF
        page3[first:first + len(build.BIOS_SLOT_CODE)] = bytes(len(build.BIOS_SLOT_CODE))
        _, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)})
        s = build.read_service(SERVICE)
        code = self.core(data, s["resb"])
        # CALL Z, after the test of the entry's second byte.
        self.assertEqual(code[s["res3.call"]:s["res3.call"] + 3], bytes([0xCC, 0x40, 0x40]))
        keyi = build.H_KEYI & 0x3FFF
        self.assertEqual(data[0][keyi:keyi + 5], bytes([0xCD]) + struct.pack("<H", build.CALL_AT) + b"\xC9\xC9")
        self.assertIn(f"rescode {build.CALL_AT} {build.CALL_AT + s['resb'] - 1} 0\n", checked)

    def test_without_room_in_sltwrk_the_call_goes_to_the_zeros_at_fcc9h(self):
        # A game's data at FD59h: the routine goes to SLTATR, as before SLTWRK.
        page3 = self.page3()
        page3[(build.CALL_AT & 0x3FFF) + 0x30] = 0x55
        _, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)})
        s = build.read_service(SERVICE)
        size = s["res3g"] - s["resb"]
        call = self.resb(s, "call")
        self.assertEqual(self.core(data, 4, call, at=s["P3_FREE"]), bytes([0xDD, 0x21, 0x40, 0x40]))
        keyi = build.H_KEYI & 0x3FFF
        self.assertEqual(data[0][keyi:keyi + 5], bytes([0xCD]) + struct.pack("<H", s["P3_FREE"]) + b"\xC9\xC9")
        self.assertIn(f"rescode {s['P3_FREE']} {s['P3_FREE'] + size - 1} 0\n", checked)
        # Nothing below FCC9h is SLTATR's, so the stack and resbe follow the code.
        last = s["P3_FREE"] + size + s["RESB_STACK"] + s["sub0"] - s["resbe"] - 1
        self.assertIn(f"resstack {s['P3_FREE'] + size} {last}\n", checked)

    def test_the_routine_has_its_stack_whatever_page_the_games_stack_is_in(self):
        # A game's stack in page 1, the entry's page, as Desperado's: the
        # routine's own stack takes the call, and res3 keeps its 45 bytes, so
        # the wrapper after it stays at FD56h.
        page3 = self.page3()
        page3[0x3DFF], page3[0x3E00] = 0x34, 0x92
        ram = {"3-x-3-0": bytes(page3), "3-x-1-1": bytes(build.PAGE)}
        _, data, _, _, checked = self.build(service=False, ram=ram, im="2", i="FD", sp="7CFA", a8="CC", fd="01")
        s = build.read_service(SERVICE)
        self.assertEqual(s["resb"] - s["res3"], 45)
        self.assertIn(f"resvector {0xFD56} {0x9234}\n", checked)
        # The records hold page 1's RAM, then page 3's.
        code = self.core(data[1:], 45)
        # The stack, RES3_STACK bytes, and res3e, the routine's end, below it.
        size = s["resbe"] - s["res3e"]
        end = build.CALL_AT - size
        self.assertEqual(code[s["res3.stack"]:s["res3.stack"] + 3], bytes([0x31]) + struct.pack("<H", end))
        self.assertEqual([code[s[f"res3.{n}"]:s[f"res3.{n}"] + 3] for n in ("fail", "tail")],
                         [bytes([0xC2]) + struct.pack("<H", end), bytes([0xC3]) + struct.pack("<H", end)])
        self.assertIn(f"resstack {end - s['RES3_STACK']} {build.CALL_AT - 1}\n", checked)
        # res3e: POP AF / OUT (0A8h),A / LD SP,0 / JP PO,.off / EI / .off: POP AF / RET.
        self.assertEqual(bytes(data[1][(end & 0x3FFF):(end & 0x3FFF) + size]),
                         bytes([0xF1, 0xD3, 0xA8, 0x31, 0, 0, 0xE2]) + struct.pack("<H", end + 10) + bytes([0xFB, 0xF1, 0xC9]))

    def test_without_room_for_the_stack_the_routine_runs_on_the_games_stack(self):
        # SLTATR and SLTWRK hold a game's bytes but at FD29h, so resbg takes
        # resb's place, with the test of the stack's page.
        page3 = self.page3()
        s = build.read_service(SERVICE)
        for at in range(s["P3_FREE"], s["P3_FREE_END"] + 1):
            if not build.CALL_AT <= at < build.CALL_AT + 64:
                page3[at & 0x3FFF] = 0x55
        _, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)})
        size = s["res3g"] - s["resb"]
        self.assertEqual(s["res3e"] - s["resbg"], size)
        code = self.core(data, size)
        f = lambda name: s[f"resbg.{name}"] - s["resbg"]
        self.assertEqual([code[f(name) + 1] for name in ("page", "id1", "is1")], [0x40, 0x82, 0xF5])
        self.assertEqual(code[f("call"):f("call") + 4], bytes([0xDD, 0x21, 0x40, 0x40]))
        self.assertIn("rescall hook\n", checked)
        self.assertIn(f"rescode {build.CALL_AT} {build.CALL_AT + size - 1} 0\n", checked)
        self.assertNotIn("resstack", checked)

    def test_the_stack_keeps_clear_of_the_bytes_below_the_games_stack(self):
        # The game's stack at FD88h can grow across all of SLTATR and SLTWRK
        # (FC88h..FD88h), so res3g takes res3's place.
        page3 = self.page3()
        page3[0x3DFF], page3[0x3E00] = 0x34, 0x92
        _, data, _, _, checked = self.build(service=False, ram={"3-x-3-0": bytes(page3)}, im="2", i="FD", sp="FD88")
        s = build.read_service(SERVICE)
        self.assertNotIn("resstack", checked)
        code = self.core(data, 45)
        self.assertEqual(code[s["res3g.page"] - s["res3g"] + 1], 0x40)
        self.assertIn(f"resvector {0xFD56} {0x9234}\n", checked)
        # With the game's stack at FD28h (FC28h..FD28h), below CALL_AT is taken
        # but the 24-byte stack fits after the wrapper in SLTWRK (FD5Ch..FD73h).
        _, _, _, _, checked2 = self.build(service=False, ram={"3-x-3-0": bytes(page3)}, im="2", i="FD", sp="FD28")
        size = s["RES3_STACK"] + s["resbe"] - s["res3e"]
        self.assertIn(f"resstack {0xFD5C} {0xFD5C + size - 1}\n", checked2)

    def test_resstack_puts_the_stack_where_the_game_file_says(self):
        page3 = self.page3()
        s = build.read_service(SERVICE)
        for at in range(s["P3_FREE"], s["P3_FREE_END"] + 1):
            if not build.CALL_AT <= at < build.CALL_AT + 64:
                page3[at & 0x3FFF] = 0x55
        _, data, _, _, checked = self.build(service=False, game=a_game(resstack=0xD400),
                                            ram={"3-x-3-0": bytes(page3)})
        self.assertIn(f"resstack {0xD400} {0xD400 + s['RESB_STACK'] + s['sub0'] - s['resbe'] - 1}\n", checked)
        code = self.core(data, 55)
        f = lambda name: self.resb(s, name)
        self.assertEqual(code[f("stack"):f("stack") + 3], bytes([0x31]) + struct.pack("<H", 0xD400 + s["RESB_STACK"]))
        page3[0x1410] = 1
        with self.assertRaisesRegex(build.BuildError,
                                    f"resstack needs {s['RESB_STACK'] + s['sub0'] - s['resbe']} bytes of zeros at D400h"):
            self.build(service=False, game=a_game(resstack=0xD400), ram={"3-x-3-0": bytes(page3)})
        with self.assertRaisesRegex(build.BuildError, "resstack goes only with an image without the tape service"):
            self.build(game=a_game(resstack=0xD400))
        # resstack no: resbg, on the game's stack, where resb has room.
        _, data, _, _, checked = self.build(service=False, game=a_game(resstack="no"))
        self.assertNotIn("resstack", checked)
        self.assertEqual(self.core(data, 55)[s["resbg.page"] - s["resbg"] + 1], 0x40)

    def test_explicit_rescode_and_resstack_accept_unused_c9_bios_hooks(self):
        page3 = self.page3()
        s = build.read_service(SERVICE)
        # Fill FF20h..FF9Fh (inside BIOS_HOOKS FD9Ah..FFC8h) with RET (0xC9).
        for at in range(0xFF20, 0xFFA0):
            page3[at & 0x3FFF] = 0xC9
        _, _, _, _, checked = self.build(service=False, game=a_game(rescode=0xFF20, resstack=0xFF60),
                                         ram={"3-x-3-0": bytes(page3)})
        self.assertIn(f"rescode {0xFF20} {0xFF20 + 55 - 1} 0\n", checked)
        stack_len = s["RESB_STACK"] + s["sub0"] - s["resbe"]
        self.assertIn(f"resstack {0xFF60} {0xFF60 + stack_len - 1}\n", checked)
        # Outside BIOS_HOOKS, C9h is still rejected.
        page3[0x1400] = 0xC9
        with self.assertRaises(build.BuildError):
            self.build(service=False, game=a_game(resstack=0xD400), ram={"3-x-3-0": bytes(page3)})

    def test_rescall_puts_a_wrapper_before_the_part_for_the_games_own_routine(self):
        header, data, _, _, checked = self.build(game=a_game(rescall=[0xB45B]))
        h, s = support.Header(header), build.read_service(SERVICE)
        at = s["P3_FREE"] & 0x3FFF
        # PUSH AF, BC, DE, HL / LD HL,resc / CALL e_run / POP HL, DE, BC, AF / JP 0B45Bh.
        self.assertEqual(data[0][at:at + 17], bytes([0xF5, 0xC5, 0xD5, 0xE5, 0x21]) + struct.pack("<H", s["resc"])
                         + b"\xCD" + struct.pack("<H", s["e_run"]) + bytes([0xE1, 0xD1, 0xC1, 0xF1, 0xC3, 0x5B, 0xB4]))
        self.assertIn(f"resvector {s['P3_FREE']} {0xB45B}\n", checked)
        # resc, in the code segment after T0, has the program's fields too.
        types = [r[0] for r in h.records]
        first = types.index(s["REC_SERVICE"])
        code = data[sum(1 for t in types[:first] if t != s["REC_ZEROS"]) + 1]
        self.assertEqual(code[s["resc.call"]:s["resc.call"] + 3], bytes([0xCD, 0x40, 0x40]))
        self.assertEqual([code[s[f"resc.{name}"] + 1] for name in ("mask", "slot", "is1", "is2")],
                         [0xF3, 0x08, 0xF5, 0xDB])
        # LD (resc_sp),SP / LD SP,resc_stack: its stack in the code segment.
        self.assertEqual(code[s["resc"] + 4:s["resc"] + 7], bytes([0x31]) + struct.pack("<H", s["resc_stack"]))
        # Without the call from T0, the wrapper still needs the program's subslot.
        header, _, _, _, checked = self.build(game=a_game(rescall=[0xB45B]), im="2")
        self.assertIn("rescall im2\n", checked)
        self.assertEqual(header[s["H_SUB"] + 2], 0xF0)

    def test_rescall_cannot_go_with_t0_without_a_part_in_page_3(self):
        with self.assertRaisesRegex(build.BuildError, "cannot go with the tape service without a part in page 3"):
            self.build(game=a_game(rescall=[0xB45B], service="t0"))

    def test_with_the_part_rescalls_wrapper_needs_its_place_at_the_default_area(self):
        page3 = self.page3()
        page3[build.read_service(SERVICE)["P3_FREE"] & 0x3FFF] = 1
        with self.assertRaisesRegex(build.BuildError, "rescall needs 17 bytes of zeros"):
            self.build(game=a_game(rescall=[0xB45B]), ram={"3-x-3-0": bytes(page3)})

    def test_without_a_ram_page_3_there_is_no_call(self):
        # Page 3 in the ROM's slot 0 at the snapshot, without the tape service.
        _, _, _, _, checked = self.build(service=False, ram={"3-x-1-0": bytes(build.PAGE)}, a8="0C", sp="7000")
        self.assertIn("rescall nopage3\n", checked)

    def test_ram_in_the_resident_programs_slot_stops_the_build(self):
        ram = {"2-0-1-x": bytes(build.PAGE), "3-x-3-0": bytes(build.PAGE)}
        with self.assertRaisesRegex(build.BuildError, "which the machine's resident program holds"):
            self.build(ram=ram, a8="C8")


class ServicePart(unittest.TestCase):
    """The place of the tape service's part of page 3, from a snapshot whose
    RAM pages the test writes."""

    def pages(self, **files):
        """The RAM pages of a snapshot with these ram/ files."""
        ram = {name.replace("_", "-"): data for name, data in files.items()}
        return Snapshot(support.snapshot(support.temp(self), ram=ram)).ram_pages

    def page3(self, sp):
        """A snapshot with the stack pointer at sp and page 3 in slot 3,
        outside a mapper, with FCC9h to FD88h in use, its page 3, and
        SERVICE.BIN."""
        data = bytearray(build.PAGE)
        data[0xFD00 & 0x3FFF] = 1
        snapshot = Snapshot(support.snapshot(support.temp(self), ram={"3-x-3-x": bytes(data)}, a8="C0", service="1",
                                             sp=f"{sp:04X}"))
        return snapshot, snapshot.selected_ram(3), build.read_service(SERVICE)

    def test_the_part_takes_the_highest_free_page_that_leaves_the_tail_alone(self):
        snapshot, p3, service = self.page3(0)
        # A part at F1E1h ends at last, and so does the tail below this stack.
        last = 0xF1E1 + len(service.parts["page3"]) - 1
        snapshot.state["sp"] = f"{last + 1:04X}"
        tail = build.tail_address(snapshot)
        self.assertEqual(tail, last - 25)
        self.assertEqual(build.find_entry_page(p3, service), 0xF1)
        self.assertEqual(build.find_entry_page(p3, service, tail=tail), 0xF0)
        # A stack in another page leaves F1E1h free.
        self.assertEqual(build.find_entry_page(p3, service, tail=0x8000), 0xF1)

    def test_the_part_stays_at_its_assemblys_page_when_the_area_is_zero(self):
        snapshot = Snapshot(support.snapshot(support.temp(self), mapper=False, service=True))
        service = build.read_service(SERVICE)
        p3 = snapshot.selected_ram(3)
        self.assertEqual(build.find_entry_page(p3, service, tail=build.tail_address(snapshot)), 0xFC)
        # A tail in the area moves the part, and so does one byte in use.
        self.assertEqual(build.find_entry_page(p3, service, tail=service["P3_FREE_END"]), 0xF1)
        p3.data[service["P3_FREE"] & 0x3FFF] = 1
        self.assertEqual(build.find_entry_page(p3, service), 0xF1)

    def test_a_page_3_without_room_has_no_entry_page(self):
        snapshot, _, service = self.page3(0xF000)
        full = Snapshot(support.snapshot(support.temp(self), ram={"3-x-3-x": b"\x01" * build.PAGE}, a8="C0",
                                         service="1"))
        self.assertIsNone(build.find_entry_page(full.selected_ram(3), service))
        # The game file's address is not looked for elsewhere.
        last = 0xF9E1 + len(service.parts["page3"]) - 1
        with self.assertRaisesRegex(build.BuildError, f"F9E1h to {last:04X}h are not zero at the snapshot"):
            build.find_entry_page(full.selected_ram(3), service, wanted=0xF9)

    def test_a_part_that_would_pass_fffeh_is_refused(self):
        _, p3, service = self.page3(0xF289)
        with self.assertRaisesRegex(build.BuildError, "a part of the tape service at FFE1h would pass FFFEh"):
            build.find_entry_page(p3, service, wanted=0xFF)
        self.assertEqual(build.find_entry_page(p3, service, wanted=0xFE), 0xFE)
        self.assertEqual(len(p3.data), build.PAGE)

    def test_without_a_part_a_page_0_in_dos_mapper_stops_the_build_when_it_knows_the_mapper(self):
        game = gamefile.Game("GAME")
        ram = bytes(build.PAGE)
        # Page 0 and page 3 in the mapper of slot 2, the snapshot's only one.
        pages = self.pages(**{"2_x_0_3": ram, "2_x_3_0": ram})
        with self.assertRaisesRegex(build.BuildError, "needs a capture variant"):
            build.check_t0_page0(pages, game)
        # A capture variant's mapper is not DOS's, and with two mappers the
        # build cannot tell which is: the restorer checks these.
        game.capture = "nms8250"
        build.check_t0_page0(pages, game)
        game.capture = None
        build.check_t0_page0(self.pages(**{"3_3_0_3": ram, "1_x_3_0": ram}), game)
        build.check_t0_page0(self.pages(**{"2_x_1_2": ram, "2_x_3_0": ram, "0_x_0_x": ram}), game)

    def test_the_mode_is_the_game_files_or_the_one_that_page_3_has_room_for(self):
        service = build.read_service(SERVICE)

        def mode(game, **options):
            snapshot = Snapshot(support.snapshot(support.temp(self), **options))
            return build.service_mode(snapshot, snapshot.selected_ram(3), service, game, build.tail_address(snapshot))
        self.assertEqual(mode(a_game()), build.Mode(False, None, 0))
        self.assertEqual(mode(a_game(), service=True), build.Mode(True, 0xFC, 0))
        self.assertEqual(mode(a_game("at", entry_page=0xF9), service=True), build.Mode(True, 0xF9, 0))
        # Without a part in page 3, TAPIN borrows page 2, or page 1 when only
        # that one is in a mapper.
        t0 = mode(a_game("t0"), service=True)
        self.assertEqual((t0, t0.t0), (build.Mode(True, None, 2), True))
        full = {"3-x-3-0": b"\x01" * build.PAGE}
        self.assertEqual(mode(a_game(), service=True, ram=full), build.Mode(True, None, 2))
        self.assertEqual(mode(a_game("t0"), service=True, mapper=False), build.Mode(True, None, 2))
        only_page_1 = {"3-x-1-2": bytes(build.PAGE), "1-x-2-x": bytes(build.PAGE), "1-x-3-x": bytes(build.PAGE)}
        self.assertEqual(mode(a_game("t0"), service=True, ram=only_page_1, a8="5C", **{"mapper3-x": "20"}),
                         build.Mode(True, None, 1))
        # rom keep rules that mode out.
        with self.assertRaisesRegex(build.BuildError, "page 3 has no room for the tape service's part, and rom keep "
                                    "needs it"):
            mode(a_game(rom_keep=True), service=True, ram=full)
        with self.assertRaisesRegex(build.BuildError, "page 3 is not a RAM page that the snapshot keeps"):
            mode(a_game(), service=True, ram={"3-x-1-2": bytes(build.PAGE)}, sp="7000")


class Tail(unittest.TestCase):
    """The tail's place and its fields (FORMATS.md, Tail)."""

    def snapshot(self, **options):
        return Snapshot(support.snapshot(support.temp(self), **options))

    def test_the_tail_is_the_26_bytes_below_the_stack_pointer(self):
        for sp, address in ((0xF000, 0xEFE6), (0xFFFF, 0xFFE5), (0x801A, 0x8000),
                            # A stack whose 26 bytes cross a page boundary: the 26 bytes below the boundary.
                            (0x8019, 0x7FE6), (0xC001, 0xBFE6), (0x4001, 0x3FE6), (0x8000, 0x7FE6)):
            with self.subTest(sp=f"{sp:04X}"):
                self.assertEqual(build.tail_address(self.snapshot(sp=f"{sp:04X}")), address)

    def test_a_stack_at_the_top_or_the_bottom_of_memory_has_no_place_for_the_tail(self):
        for sp in (0x0000, 0x0001, 0x0019):
            with self.subTest(sp=f"{sp:04X}"):
                with self.assertRaisesRegex(build.BuildError, f"the 26 bytes below SP {sp:04X}h cross a page boundary "
                                            "or include FFFFh"):
                    build.tail_address(self.snapshot(sp=f"{sp:04X}"))

    def test_the_tail_holds_the_snapshots_registers(self):
        snapshot = self.snapshot(sp="D000", pc="1234", af="56A7", iff="0")
        image = build.Image(snapshot, build.read_service(SERVICE), a_game())
        image.place_tail()
        s = image.service
        self.assertEqual(image.tail, build.Tail(0xD000 - 26, snapshot.selected_ram(3)))
        code = image.tail.ram_page.data[0xCFE6 & 0x3FFF:][:26]
        self.assertEqual(struct.unpack_from("<H", code, s["TAIL_STACK"])[0], 0xCFE6 + s["TAIL_AF"])
        self.assertEqual(struct.unpack_from("<H", code, s["TAIL_SP"])[0], 0xD000)
        self.assertEqual((code[s["TAIL_EI"]], code[s["TAIL_JP"]]), (0x00, 0xC3))
        self.assertEqual(struct.unpack_from("<HH", code, s["TAIL_PC"]), (0x1234, 0x56A7))
        # With interrupts on at the snapshot, the tail enables them.
        on = build.Image(self.snapshot(iff="1"), build.read_service(SERVICE), a_game())
        on.place_tail()
        self.assertEqual(on.tail.ram_page.data[(on.tail.address & 0x3FFF) + s["TAIL_EI"]], 0xFB)

    def test_a_stack_outside_the_kept_ram_stops_the_build(self):
        # The stack is in page 0, which selects the ROM: a load that failed.
        image = build.Image(self.snapshot(sp="3000"), build.read_service(SERVICE), a_game())
        with self.assertRaisesRegex(build.BuildError, "the 26 bytes below SP 3000h are not in a RAM page that the "
                                    "snapshot keeps. The usual cause is a load that failed on this machine: "
                                    ".*log.txt shows where it stopped"):
            image.place_tail()


class Service(unittest.TestCase):
    """Images with the tape service, of snapshots that the test writes."""

    def built(self, game=None, side1=support.BASIC_TAPE, side2=b"", patch_lines=(), **options):
        self.snapshot = Snapshot(support.snapshot(support.temp(self), **dict({"service": True}, **options)))
        return build.build(self.snapshot, SERVICE, game or a_game(), side1, side2, patch_lines)

    def test_the_records_are_the_ram_pages_then_vram_then_the_service_segments(self):
        built = self.built(tapepos="000010", fc="07", ppic="50")
        h, s = support.Header(built.header), support.service()
        self.assertEqual(h.records, [(s["REC_MAPPER"], 3, 1, 2), (s["REC_MAPPER"], 3, 2, 1), (s["REC_MAPPER"], 3, 3, 0),
                                     (s["REC_ZEROS"], 0, 0, 0), (s["REC_SERVICE"], 0, 0, 0),
                                     (s["REC_SERVICE"], 0, 0, 0)])
        self.assertEqual((h["H_FLAGS"], h["H_P3"], h["H_BORROW"], h["H_TAILREC"], h["H_P3REC"]), (0, 0xFC, 0, 2, 2))
        self.assertEqual((len(h.writes), h["H_WRITES"]), (52, 52))
        # 5 records hold data, and the mapper needs a segment for each RAM
        # page, each service segment and the worker.
        self.assertEqual([len(chunk) for chunk in built.data], [build.PAGE] * 5)
        self.assertEqual(built.report, "6 records, 52 port writes, up to 6 free mapper segments")
        # T0 is the ROM's page 0 with the stubs, and the code segment holds
        # the tape after the service's code, with its positions.
        t0, code = built.data[3], built.data[4]
        self.assertEqual(t0[s["T0_CODE"]:s["T0_END"]], s.parts["stubs"])
        start = len(s.parts["code"])
        self.assertEqual(code[start:start + len(support.BASIC_TAPE)], support.BASIC_TAPE)
        # The tape ends at a multiple of 8 bytes.
        end = start + len(support.BASIC_TAPE) + -len(support.BASIC_TAPE) % 8
        for name, value in (("D_START", start), ("D_POS", start + 0x10), ("D_TOTAL", end), ("D_S1END", end)):
            self.assertEqual(int.from_bytes(code[s[name]:s[name] + 3], "little"), value, name)

    def test_the_part_of_page_3_holds_the_games_register_and_the_motor(self):
        # The motor is off at the snapshot: bit 4 of the PPI's port C is set.
        built = self.built(fc="07", ppic="50")
        s = support.service()
        page3 = built.data[2]
        at = s["E_ENTRY"] & 0x3FFF
        part = page3[at:at + len(s.parts["page3"])]
        self.assertEqual(part[:s["E_FC"] - s["E_ENTRY"]], s.parts["page3"][:s["E_FC"] - s["E_ENTRY"]])
        self.assertEqual((part[s["E_FC"] - s["E_ENTRY"]], part[s["E_STOP"] - s["E_ENTRY"]]), (0x07, 1))
        self.assertIn(f"part {s['E_ENTRY']} {s['e_sp'] - 1} {s['E_CODE']} 0\n", built.facts)
        self.assertIn(f"cpos {0x4000 + s['D_POS']} {0x4000 + s['D_TOTAL']}\n", built.facts)
        # The code segment's two jumps at the tape's end, which follow each
        # other in the service's wrap.
        self.assertIn(f"ended {s['wrap.one']} {s['wrap.two']}\n", built.facts)
        self.assertLess(s["wrap.one"], s["wrap.two"])
        self.assertLess(s["wrap.two"], len(s.parts["code"]))
        self.assertNotIn("moved", built.facts)
        running = self.built(ppic="40")
        self.assertEqual(running.data[2][s["E_STOP"] & 0x3FFF], 0)

    def slot0_built(self, game=None, pages=(0, 1, 2, 3), page3=None, **state):
        """An image of a snapshot on a machine with the main ROM in slot 0-0
        and DOS's mapper in 0-1, as the SX-2 with its Extra-Mapper: page 0
        selects the ROM and pages 1 to 3 the mapper, whose segments the
        snapshot keeps for the pages, page 0 among them by default."""
        ram = {f"0-1-{page}-{3 - page}": bytes(build.PAGE) for page in pages}
        if page3 is not None:
            ram["0-1-3-0"] = page3
        return self.built(game, ram=ram, **dict({"a8": "00", "sub0": "54", "mapper0-1": "20"}, **state))

    def page3_of(self, built):
        return built.data[support.Header(built.header)["H_P3REC"]]

    def test_page_0_in_another_subslot_of_page_3s_slot_gets_sub0(self):
        # The snapshot keeps RAM for page 0, so T0 does not replace the ROM,
        # and the slot register alone selects the ROM in page 0.
        built, s = self.slot0_built(), support.service()
        page3, at = self.page3_of(built), s["P3_FREE"]
        code = s.parts["call"][s["sub0"]:]
        self.assertEqual(len(code), 23)
        placed = page3[at & 0x3FFF:(at & 0x3FFF) + len(code)]
        # LD (nn),A keeps the register's value in LD A,n's operand, OR n has
        # page 3's subslot, 1, and the call goes to tramp.
        back = at + s["sub0.back"] - s["sub0"]
        self.assertEqual(struct.unpack_from("<H", placed, s["sub0.save"] - s["sub0"] + 1)[0], back + 1)
        self.assertEqual(placed[s["sub0.ss"] - s["sub0"] + 1], 1)
        self.assertEqual(struct.unpack_from("<H", placed, s["sub0.tramp"] - s["sub0"] + 1)[0], s["tramp"])
        self.assertEqual(placed[:4], bytes([0x3A, 0xFF, 0xFF, 0x2F]))
        # e_run calls sub0 in place of tramp.
        self.assertEqual(page3[(s["e_run.call"] & 0x3FFF):][:3], b"\xCD" + struct.pack("<H", at))
        self.assertEqual(support.Header(built.header)["H_FLAGS"], s["FLAG_P0"])
        self.assertIn(f"sub0 {at} {at + len(code) - 1}\n", built.facts)
        self.assertIn(f"patched 0-1-3 {at & 0x3FFF} {(at & 0x3FFF) + len(code) - 1}\n", built.facts)

    def test_sub0_goes_before_a_moved_part(self):
        # A byte at FCC9h moves the part to F1E1h, and sub0 to F1C9h.
        page3 = bytearray(build.PAGE)
        page3[0xFCC9 & 0x3FFF] = 1
        built, s = self.slot0_built(page3=bytes(page3)), support.service().at(0xF1)
        self.assertEqual(support.Header(built.header)["H_P3"], 0xF1)
        self.assertIn(f"sub0 {0xF1C9} {0xF1C9 + 22}\n", built.facts)
        self.assertEqual(self.page3_of(built)[(s["e_run.call"] & 0x3FFF):][:3], bytes([0xCD, 0xC9, 0xF1]))

    def test_t0_in_place_of_the_rom_needs_no_sub0(self):
        s = support.service()
        built = self.slot0_built(pages=(1, 2, 3))
        # Without RAM for page 0, T0 replaces the ROM for good, so sub0 is not needed.
        page3 = self.page3_of(built)
        self.assertEqual(page3[(s["e_run.call"] & 0x3FFF):][:3], b"\xCD" + struct.pack("<H", s["tramp"]))
        self.assertEqual(support.Header(built.header)["H_FLAGS"], 0)
        self.assertNotIn("sub0 ", built.facts)
        self.assertFalse(any(page3[s["P3_FREE"] & 0x3FFF:s["E_ENTRY"] & 0x3FFF]))

    def test_slot0_ram_in_page_0_gets_sub0_for_later_rom_switches(self):
        # With RAM in expanded slot 0 (0-1) in page 0 at the snapshot, the game
        # may still switch page 0 back to the main ROM (0-0) when calling tape
        # entries later in play, so e_run needs sub0.
        built, s = self.slot0_built(sub0="55"), support.service()
        self.assertEqual(support.Header(built.header)["H_FLAGS"], s["FLAG_P0"])
        self.assertIn(f"sub0 {s['P3_FREE']} {s['P3_FREE'] + 22}\n", built.facts)

    def test_sub0_falls_back_when_fcc9_is_occupied(self):
        # When FCC9h..FCD9h is taken (for example by a rescall wrapper), sub0
        # falls back to unused zeros in TRPTBL (FC4Ch..FC9Dh) or C9h BIOS hooks.
        page3 = bytearray(build.PAGE)
        page3[0xFC4C & 0x3FFF:0xFC9E & 0x3FFF] = b"\x01" * (0xFC9E - 0xFC4C)
        page3[0xFF01 & 0x3FFF:0xFF40 & 0x3FFF] = b"\xC9" * (0xFF40 - 0xFF01)
        ram = {f"0-1-{page}-{3 - page}": bytes(build.PAGE) for page in (0, 1, 2, 3)}
        ram["0-1-3-0"] = bytes(page3)
        snap = Snapshot(support.snapshot(support.temp(self), service=True, ram=ram,
                                         a8="00", sub0="55", sub3="F8", mapper0_1=None, **{"mapper0-1": "20"}))
        resident = msx.Resident(0x83, 0x4040, b"\xF5\xDB\xFD\xF5\x3E")
        built = build.build(snap, SERVICE, a_game(rescall=[0x9574]), support.BASIC_TAPE, b"", (), resident=resident)
        s = support.service()
        self.assertEqual(support.Header(built.header)["H_FLAGS"], s["FLAG_P0"])
        self.assertIn(f"sub0 {0xFF01} {0xFF01 + 22}\n", built.facts)

    def test_rom_keep_keeps_the_rom_with_sub0(self):
        built, s = self.slot0_built(a_game(rom_keep=True), pages=(1, 2, 3)), support.service()
        self.assertEqual(support.Header(built.header)["H_FLAGS"], s["FLAG_ROM_KEEP"] | s["FLAG_P0"])

    def test_service_at_moves_the_part_and_names_its_place(self):
        built = self.built(a_game("at", entry_page=0xF9))
        s = support.service().at(0xF9)
        h = support.Header(built.header)
        self.assertEqual(h["H_P3"], 0xF9)
        self.assertEqual(built.data[2][0xF9E1 & 0x3FFF:][:3], s.parts["page3"][:3])
        self.assertIn(f"moved {0xF9E1} {0xF9E1 + len(s.parts['page3']) - 1}\n", built.facts)
        self.assertIn("# The tape service's part of page 3 is at F9E1h: the game uses FCC9h to FD88h.\n", built.scan)

    def test_service_at_under_the_tail_stops_the_build(self):
        last = 0xF9E1 + len(support.service().parts["page3"]) - 1
        with self.assertRaisesRegex(build.BuildError, f"the tail at F9E6h overlaps F9E1h to {last:04X}h"):
            self.built(a_game("at", entry_page=0xF9), sp="FA00")

    def test_service_at_with_a_code_address_puts_the_code_block_apart(self):
        # The entries at F9E1h and the code block at F000h, in the snapshot's
        # page 3, whose bytes are zero.
        built = self.built(a_game("at", entry_page=0xF9, code_at=0xF000))
        s = support.service().at(0xF9, 0xF000)
        page3 = built.data[2]
        (entries, at_entries), (code, at_code) = [(first, data) for first, data in s.blocks()]
        self.assertEqual((entries, code, s.split), (0xF9E1, 0xF000, True))
        self.assertEqual(page3[entries & 0x3FFF:][:3], at_entries[:3])
        self.assertEqual(page3[code & 0x3FFF:][:len(at_code)], at_code)
        # Each address in the code block keeps its offset there: the entry of
        # TAPIOF's jump to tapiof, and in T0's stubs the jumps to tramp.
        whole = support.service().at(0xF9)
        moved = 0xF000 - whole["P3_CODE"]
        jump = struct.unpack_from("<H", whole.parts["page3"], 0xF9E7 - 0xF9E1 + 1)[0]
        self.assertEqual(struct.unpack_from("<H", page3, (0xF9E7 & 0x3FFF) + 1)[0], jump + moved)
        stubs, split_stubs = whole.parts["stubs"], s.parts["stubs"]
        changed = [n for n in range(len(stubs)) if stubs[n] != split_stubs[n]]
        self.assertTrue(changed)
        for n in changed[::2]:
            self.assertEqual(struct.unpack_from("<H", split_stubs, n)[0],
                             struct.unpack_from("<H", stubs, n)[0] + moved)
        self.assertEqual(built.data[3][s["T0_CODE"]:s["T0_END"]][:len(split_stubs)], split_stubs)
        # The check guards both blocks, without the code block's scratch bytes.
        self.assertIn(f"part {0xF9E1} {s['E_STOP']} {s['E_CODE']} 0\n", built.facts)
        self.assertIn(f"partcode {0xF000} {s['e_sp'] - 1}\n", built.facts)
        self.assertIn(f"moved {0xF9E1} {s['E_STOP']} {0xF000} {0xF000 + len(at_code) - 1}\n", built.facts)

    def test_a_code_block_that_is_not_free_stops_the_build(self):
        s = support.service().at(0xF9, 0xF000)
        code = s.blocks()[1][1]
        # Bytes that are not zero, the tail, a block that passes FFFEh, and the
        # two blocks on each other.
        with self.assertRaisesRegex(build.BuildError, "F000h to .* are not zero at the snapshot"):
            self.built(a_game("at", entry_page=0xF9, code_at=0xF000),
                       ram={"3-x-3-0": bytes(0x3000) + b"\x01" + bytes(0xFFF)})
        with self.assertRaisesRegex(build.BuildError, "the tail at F0..h overlaps F000h"):
            self.built(a_game("at", entry_page=0xF9, code_at=0xF000), sp="F020")
        with self.assertRaisesRegex(build.BuildError, "is not in page 3 below FFFFh"):
            self.built(a_game("at", entry_page=0xF9, code_at=0x10000 - len(code) + 1))
        with self.assertRaisesRegex(build.BuildError, "blocks at F9E1h and F9F0h overlap"):
            self.built(a_game("at", entry_page=0xF9, code_at=0xF9F0))

    def test_service_at_puts_the_entries_over_the_bioss_copies_of_vdp_registers(self):
        # FFE7h to FFFAh, RG8SAV to RG25SAV with MINROM, hold what the BIOS
        # left, and the hooks below them hold RET.
        page3 = bytearray(0x4000)
        page3[0x3F01:0x3FC9] = b"\xC9" * 0xC8
        page3[0x3FE7], page3[0x3FF7] = 0x08, 0x80
        built = self.built(a_game("at", entry_page=0xFF, code_at=0xFF01), ram={"3-x-3-0": bytes(page3)})
        s = support.service().at(0xFF, 0xFF01)
        self.assertIn(f"part {0xFFE1} {s['E_STOP']} {s['E_CODE']} 0\n", built.facts)
        self.assertEqual(s["E_STOP"], 0xFFFA)
        # A byte that is not zero before them, at FFE6h, still stops the build,
        # and so does one of them for a part that the build places itself.
        page3[0x3FE6] = 0x01
        with self.assertRaisesRegex(build.BuildError, "FFE1h to FFFAh are not zero at the snapshot"):
            self.built(a_game("at", entry_page=0xFF, code_at=0xFF01), ram={"3-x-3-0": bytes(page3)})
        self.assertFalse(build.explicit_free(Snapshot(self.snapshot.folder).load().selected_ram(3), 0xFFE1, 0xFFFA))

    def test_without_a_part_in_page_3_t0_holds_the_service_and_the_borrowed_page(self):
        built = self.built(a_game("t0"), tapepos="000008")
        h, s = support.Header(built.header), support.service()
        self.assertEqual((h["H_FLAGS"], h["H_P3"], h["H_BORROW"]), (s["FLAG_T0"], 0, 2))
        # No code segment: T0, then the tape.
        self.assertEqual([r[0] for r in h.records].count(s["REC_SERVICE"]), 2)
        t0 = built.data[3]
        self.assertEqual(t0[s["T0_CODE"]:s["T0_END"]][len(s.parts["t0"]) - 8:], s.parts["t0"][-8:])
        self.assertEqual(int.from_bytes(t0[s["t0m.D_POS"]:s["t0m.D_POS"] + 3], "little"), 8)
        # Page 2: its mask in the slot register, its mapper register's port,
        # its first address's high byte and the game's segment there.
        self.assertEqual([t0[s[f"t0m.{name}"]] for name in ("D_PAGE_MASK", "D_PAGE_PORT", "D_PAGE_HIGH",
                                                             "D_PAGE_SEG")], [0xCF, 0xFE, 0x80, 1])
        self.assertTrue(built.scan.startswith("# The tape service has no part in page 3"))
        self.assertNotIn("part ", built.facts)
        self.assertNotIn("ended ", built.facts)

    def test_a_tape_longer_than_the_services_segments_stops_the_build(self):
        long = support.cas_file(b"\xD3" * 10 + b"GAME  ", bytes(64 * build.PAGE))
        with self.assertRaisesRegex(build.BuildError, "the tape needs 65 segments, more than 64"):
            self.built(side1=long)
        # Without a part in page 3, the tape has 16 segments.
        with self.assertRaisesRegex(build.BuildError, "the tape needs 17 segments, more than 16"):
            self.built(a_game("t0"), side1=long[:16 * build.PAGE + 100])
        self.built(a_game("t0"), side1=long[:16 * build.PAGE])

    # CALSLT's two places and the routine that the first one calls, as every
    # MSX2's BIOS has them, at their addresses there (INTERNALS.md, T0 and the
    # sub-ROM in one slot).
    CALSLT_CALL = (0x02FA, "F1 CD 78 03 F5 FD E1 E5 C5 4F 06 00 7D A4 B2 21 C5 FC 09 77")
    CALSLT_JUMP = (0x02E6, "DB A8 F5 A1 B0 D9 C3 8C F3")
    CALSLT_ROUTINE = (0x0378, "F5 7A E6 C0 4F F1 F5 57 DB A8 47 E6 3F B1 D3 A8 7A 0F 0F E6 03 57 3E AB C6 55 15 F2 90 03 "
                              "A3 57 7B 2F 67 3A FF FF 2F 6F A4 B2 32 FF FF 78 D3 A8 F1 E6 03 C9")

    def built_on(self, places, game=None):
        """An image of a snapshot whose rom.bin has the bytes of places."""
        snap = support.snapshot(support.temp(self), service=True)
        with open(os.path.join(snap, "rom.bin"), "r+b") as f:
            for address, code in places:
                f.seek(address)
                f.write(bytes.fromhex(code))
        return build.build(Snapshot(snap), SERVICE, game or a_game(), support.BASIC_TAPE)

    def test_an_msx2s_calslt_goes_to_t0s_code(self):
        t0, s = self.built_on((self.CALSLT_CALL, self.CALSLT_JUMP, self.CALSLT_ROUTINE)).data[3], support.service()
        # The call goes to t_s, whose jump goes on to the BIOS's routine, and
        # the jump goes to t_c in place of CLPRIM.
        self.assertEqual(t0[0x02FB:0x02FE], bytes([0xCD]) + struct.pack("<H", s["t_s"]))
        self.assertEqual(t0[s["t_s.jump"]:s["t_s.jump"] + 3], bytes.fromhex("C3 78 03"))
        self.assertEqual(t0[0x02EC:0x02EF], bytes([0xC3]) + struct.pack("<H", s["t_c"]))
        # The routine itself stays, for the calls that t_s sends on.
        self.assertEqual(t0[0x0378:0x0378 + 52], bytes.fromhex(self.CALSLT_ROUTINE[1]))

    def test_a_rom_without_all_of_calslts_code_keeps_it(self):
        # Without the routine that the call names, as on a BIOS with other
        # code there, and with the jump twice.
        other = (0x0378, "00" + self.CALSLT_ROUTINE[1][2:])
        twice = (0x0400, self.CALSLT_JUMP[1])
        for places in ((self.CALSLT_CALL, self.CALSLT_JUMP), (self.CALSLT_CALL, self.CALSLT_JUMP, other),
                       (self.CALSLT_CALL, self.CALSLT_JUMP, self.CALSLT_ROUTINE, twice)):
            t0, s = self.built_on(places).data[3], support.service()
            self.assertEqual(t0[0x02FB:0x02FE], bytes.fromhex("CD 78 03"))
            self.assertEqual(t0[0x02EC:0x02EF], bytes.fromhex("C3 8C F3"))
            self.assertEqual(t0[s["T0_CODE"]:s["T0_END"]], s.parts["stubs"])

    def test_without_a_part_in_page_3_calslt_stays(self):
        # That mode has no code in page 3 for the call.
        t0 = self.built_on((self.CALSLT_CALL, self.CALSLT_JUMP, self.CALSLT_ROUTINE), a_game("t0")).data[3]
        self.assertEqual(t0[0x02FB:0x02FE], bytes.fromhex("CD 78 03"))
        self.assertEqual(t0[0x02EC:0x02EF], bytes.fromhex("C3 8C F3"))

    def test_a_rom_whose_tape_entries_are_not_the_bioss_stops_the_build(self):
        snap = support.snapshot(support.temp(self), service=True)
        with open(os.path.join(snap, "rom.bin"), "r+b") as f:
            f.seek(0xE4 + 1)
            f.write(b"\x00\x00")
        with self.assertRaisesRegex(build.BuildError, r"rom.bin: the jump at 00E4h does not go to 1A[0-9A-F]{2}h"):
            build.build(Snapshot(snap), SERVICE, a_game(), support.BASIC_TAPE)

    def test_a_patch_line_changes_its_page_and_names_its_range_for_the_check(self):
        patch = gamefile.read_patch("page2:10 00 00 > 3E 14".split(), "game.txt:2")
        built = self.built(patch_lines=[patch])
        self.assertEqual(built.data[1][0x10:0x12], bytes.fromhex("3E 14"))
        self.assertIn("patched 3-x-2 16 17\n", built.facts)
        other = gamefile.read_patch("page0:10 00 > 3E".split(), "game.txt:3")
        with self.assertRaisesRegex(build.BuildError, "game.txt:3: page 0 is not a RAM page that the snapshot keeps"):
            self.built(patch_lines=[other])
        with self.assertRaisesRegex(gamefile.GameFileError, "game.txt:2: the bytes at 8010 are not the patch's old "
                                    "bytes"):
            self.built(patch_lines=[patch], ram={"3-x-2-1": b"\x01" * build.PAGE, "3-x-3-0": bytes(build.PAGE)})

    def test_without_the_service_the_image_has_no_segment_and_no_part(self):
        built = self.built(service=False)
        h, s = support.Header(built.header), support.service()
        self.assertEqual([r[0] for r in h.records], [s["REC_MAPPER"]] * 3 + [s["REC_ZEROS"]])
        self.assertEqual((h["H_P3"], h["H_P3REC"], h["H_TAILREC"]), (0, 0, 2))
        self.assertEqual(built.facts.splitlines()[1:], ["service 0", f"tail {0xF000 - 26} 25 {s['TAIL_PORT']} "
                                                        f"{s['TAIL_JP']}", f"free {s['P3_FREE']} {s['P3_FREE_END']}"])
        self.assertTrue(built.scan.startswith("# Without the tape service, the scan looks only for fixed slot values"))
        self.assertFalse(any(built.data[2][s["P3_FREE"] & 0x3FFF:(s["P3_FREE_END"] & 0x3FFF) + 1]))


class Program(unittest.TestCase):
    """build.py as a program, on a game folder with a snapshot that the test
    writes."""

    def setUp(self):
        self.folder = support.snapshot_game(os.path.join(support.temp(self), "GAME"), MACHINE, service=True)
        self.out = gamefile.out_folder(MACHINE, self.folder)

    def build(self, *extra):
        return support.tool("build.py", self.folder, MACHINE, "--tapes", self.folder, *extra)

    def test_it_writes_the_image_the_scan_and_the_facts(self):
        result = self.build()
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        image = os.path.join(self.out, "GAME.SNP")
        self.assertEqual(result.stdout, f"GAME: {image}: 6 records, 52 port writes, up to 6 free mapper segments\n")
        self.assertEqual(os.path.getsize(image), 4096 + 5 * build.PAGE)
        self.assertEqual(sorted(os.listdir(self.out)), ["GAME.SNP", "build.txt", "scan.txt", "snap"])
        with open(image, "rb") as f:
            self.assertEqual(f.read(8), support.service().mark)
        with open(os.path.join(self.out, "build.txt")) as f:
            self.assertIn("service 1\n", f.read())

    def test_a_wrong_service_version_is_refused(self):
        with open(SERVICE, "rb") as f:
            data = bytearray(f.read())
        data[0] = build.SERVICE_VERSION + 1
        wrong = os.path.join(support.temp(self), "SERVICE.BIN")
        with open(wrong, "wb") as f:
            f.write(data)
        result = self.build("--service", wrong)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn(f"version {build.SERVICE_VERSION + 1}, expected {build.SERVICE_VERSION}", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "GAME.SNP")))

    def test_an_error_in_the_input_files_stops_with_status_1_and_one_line(self):
        for change, error in ((lambda: os.remove(os.path.join(self.out, "snap", "state.txt")),
                               r"build.py: \[Errno 2\] No such file or directory: '.*state.txt'\n"),
                              (lambda: os.remove(os.path.join(self.folder, "GAME.CAS")),
                               r"build.py: \[Errno 2\] No such file or directory: '.*GAME.CAS'\n"),
                              (lambda: support.game_folder(self.folder, "cas GAME.CAS\nspeed 1\n"),
                               r"build.py: .*game.txt:2: unknown key speed\n")):
            self.setUp()
            change()
            result = self.build()
            with self.subTest(error=error):
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stderr, "^" + error + "$")

    def test_the_capture_option_replaces_the_game_files_variant(self):
        # Page 0 in the snapshot's only mapper, without a part in page 3: the
        # build stops, unless the capture ran on a variant.
        ram = {"3-x-0-3": bytes(build.PAGE), "3-x-3-0": bytes(build.PAGE)}
        support.snapshot_game(self.folder, MACHINE, "cas GAME.CAS\nservice t0\n", ram=ram, service=True, a8="C3",
                              **{"mapper3-x": "20"})
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn("The game needs a capture variant", result.stderr)
        self.assertEqual(self.build("--capture", "vg8020").returncode, 0)


if __name__ == "__main__":
    unittest.main()
