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
    def state(self, v9938=True, **values):
        """A snapshot with the state that the test gives."""
        values = dict(dict(psgsel="0E", ppic="50", vramptr="00000", vramwrite="1"), **values)
        return Snapshot(support.snapshot(support.temp(self), v9938=v9938, **values))

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
        with self.assertRaisesRegex(build.BuildError, "8 parts, expected 7"):
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
