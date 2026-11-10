"""The restorer, SNAPCAS.COM, on images that the tests write (docs/INTERNALS.md,
Restorer and The restorer's stops): its usage and its messages, its stops for
an image that the machine cannot restore, its plan: the segment that each
record is read into, the holding segments and T0's segment, and what it fills
in, read from the restored machine at the tail's jump. The restores of games
are in tests/test_machines.py. Emulator tier."""
import concurrent.futures
import os
import struct
import unittest

import support
import build
import msx
from snapshot import Snapshot

WORK = support.work("restore")
FCB_FILESIZE = 16  # the file's size in an FCB, 4 bytes (src/snapcas.asm)


class Usage(unittest.TestCase):
    """The first SNAPCAS.COM of PLAN.md's step 1: the assembler, the disk
    image, the boot keys and the screen reading."""

    def test_usage_and_errors(self):
        folder = os.path.join(WORK, "usage")
        os.makedirs(folder, exist_ok=True)
        files = {"AUTOEXEC.BAT": b"SNAPCAS\r\nSNAPCAS NONE\r\nSNAPCAS SHORT\r\nSNAPCAS BAD\r\nSNAPCAS OLD\r\n",
                 "BAD.SNP": b"SNAPDISK" + bytes(4088), "OLD.SNP": b"SNAPCAS2" + bytes(4088), "SHORT.SNP": b"SNA"}
        for name, data in files.items():
            with open(os.path.join(folder, name), "wb") as f:
                f.write(data)
        disk = os.path.join(folder, "disk.dsk")
        msx.make_disk(disk, [os.path.join(support.NEXTOR, "NEXTOR.SYS"), os.path.join(support.NEXTOR, "COMMAND2.COM"),
                             support.COM] + [os.path.join(folder, name) for name in files])
        machine = msx.read_machine(msx.machine_path(support.PHC28S))
        screen = support.screen_after(machine, disk, "OLD.SNP: made", os.path.join(folder, "screen.txt"))
        self.assertIn("Usage: SNAPCAS <game> [/M]", screen)
        self.assertIn("Restores <game>.SNP, a snapcas image.", screen)
        self.assertIn("NONE.SNP not found", screen)
        self.assertIn("SHORT.SNP is not a snapcas image", screen)
        self.assertIn("BAD.SNP is not a snapcas image", screen)
        # The message wraps at the screen's width.
        self.assertIn("OLD.SNP: made for another version of SNAPCAS.COM", " ".join(screen.split()))


class Stops(unittest.TestCase):
    """The restorer's stops for an image that the machine cannot restore, on
    the PHC-28S with the RAM cartridge in slot 1 and the Carnivore2, DOS's
    mapper, in slot 2-2, and its stop after a VRAM block there and on an
    MSX2."""

    MSX1, MSX2 = "phc28s-ram64k-carnivore2", "nms8250-carnivore2"

    @classmethod
    def setUpClass(cls):
        service = support.service()
        symbols = support.symbols("snapcas")
        ram, vram = service["REC_RAM"], service["REC_VRAM"]
        # The second read of a record fails, as at a disk error: the file's
        # size in the restorer's FCB is 0 by then, so DOS reads nothing. The
        # first VRAM block is written by then.
        fail = f"""
set ::reads 0
debug set_bp {symbols["read_this"]} $::snapcas {{safe {{
    incr ::reads
    if {{$::reads == 2}} {{ debug write_block memory {symbols["fcb"] + FCB_FILESIZE} [binary format H* 00000000] }}
}}}}
"""

        def run(machine):
            work = os.path.join(WORK, "stops", machine)
            facts = support.restorer_facts(machine, support.NEXTOR, work)
            files = {"VRAM.SNP": support.synthetic_image(facts["crcs"], [(vram, 0, 0, 0, 0x41), (vram, 1, 0, 0, 0x42)])}
            if machine == cls.MSX1:
                page = (ram, 1, 1, 0, 0x55)
                files.update({
                    # One byte short of its two records' data.
                    "CUT.SNP": support.synthetic_image(facts["crcs"], [page, (vram, 0, 0, 0, 0x41)], cut=1),
                    # A page outside a mapper in DOS's mapper's slot.
                    "PLAIN.SNP": support.synthetic_image(facts["crcs"], [(ram, facts["dos_slot"], 1, 0, 0x55)]),
                    # Slot 1 as an expanded slot, which it is not.
                    "EXPANDED.SNP": support.synthetic_image(facts["crcs"], [(ram, 0x81, 1, 0, 0x55)]),
                })
            return facts, support.restorer_screen(machine, support.NEXTOR, work, files, fail)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            cls.runs = dict(zip((cls.MSX1, cls.MSX2), pool.map(run, (cls.MSX1, cls.MSX2))))

    def test_a_stop_after_a_vram_block_shows_its_message_on_a_text_screen(self):
        for machine, (_, screen) in self.runs.items():
            with self.subTest(machine=machine):
                self.assertIn(support.said("VRAM.SNP: cannot be read"), screen)

    def test_a_cut_file_stops_before_its_first_record_is_placed(self):
        facts, screen = self.runs[self.MSX1]
        self.assertEqual(facts["dos_slot"], 0x8A)
        self.assertIn(support.said("CUT.SNP: the file is cut short: it lacks data of its records"), screen)
        # Neither a read nor a VRAM block came before the message: the forced
        # failure, at the second read of the run, is still VRAM.SNP's.
        self.assertNotIn(support.said("CUT.SNP: cannot be read"), screen)

    def test_a_page_outside_a_mapper_in_dos_mappers_slot_stops(self):
        _, screen = self.runs[self.MSX1]
        self.assertIn(support.said("PLAIN.SNP: slot 2 is DOS's mapper, and the image has RAM without a mapper there"),
                      screen)

    def test_a_slot_that_is_not_expanded_as_at_the_capture_stops(self):
        _, screen = self.runs[self.MSX1]
        self.assertIn(support.said("EXPANDED.SNP: slot 1 is not expanded as at the capture: "
                           "the machine file does not describe this machine"), screen)


@support.needs_dos("msxdos2")
class RomKeep(unittest.TestCase):
    """The Victor HC-90A has its main ROM in slot 0-0 and its mapper, DOS's,
    in slot 0-2. The tape service needs the mapper's subslot in page 0's bits
    of slot 0's subslot register, so the snapshot's page 0 cannot stay in
    another subslot of slot 0."""

    @classmethod
    def setUpClass(cls):
        dos = support.dos("msxdos2")
        work = os.path.join(WORK, "stops", "hc90a")
        service = support.service()
        cls.facts = support.restorer_facts("test/hc90a-msxdos2", dos, work)
        segment = (service["REC_SERVICE"], 0, 0, 0, 0)
        # Slot 0 in every page, with subslot 2 in pages 1 to 3, and in page 0
        # subslot 0, the main ROM, or subslot 1, the sub-ROM.
        rom, subrom = {"H_A8": 0x00, "H_SUB": (0xA8, 0, 0, 0)}, {"H_A8": 0x00, "H_SUB": (0xA9, 0, 0, 0)}
        files = {
            "KEEP.SNP": support.synthetic_image(cls.facts["crcs"], [segment], H_FLAGS=service["FLAG_ROM_KEEP"], **rom),
            # Without rom keep, T0 replaces the ROM, and the restorer goes on
            # to count the segments: 20 service segments and the worker.
            "REPLACE.SNP": support.synthetic_image(cls.facts["crcs"], [segment] * 20, **rom),
            "SUBROM.SNP": support.synthetic_image(cls.facts["crcs"], [segment], **subrom),
        }
        cls.screen = support.restorer_screen("test/hc90a-msxdos2", dos, work, files)

    def test_rom_keep_with_the_rom_in_dos_mappers_slot_stops(self):
        self.assertEqual(self.facts["dos_slot"], 0x88)
        self.assertIn(support.said("KEEP.SNP: rom keep needs the main ROM outside DOS's mapper's slot"), self.screen)

    def test_without_rom_keep_t0_replaces_that_rom(self):
        self.assertRegex(self.screen, support.said(r"REPLACE.SNP: needs 21 free mapper segments, and DOS has \d+"))

    def test_another_page_0_in_dos_mappers_slot_stops(self):
        self.assertIn(support.said("SUBROM.SNP: a page 0 is in another subslot of DOS's mapper's slot"), self.screen)


@support.needs_dos("msxdos1")
class Dos1(unittest.TestCase):
    """Under MSX-DOS 1 the restorer takes DOS's segments for 3, 2, 1 and 0,
    and checks them."""

    @classmethod
    def setUpClass(cls):
        dos = support.dos("msxdos1")
        blank = support.synthetic_image((0, 0), [])
        # The Tcl changes a mapper register before the restorer's second and
        # third start, and puts DOS's segments back before the fourth.
        tcl = """
set ::starts 0
debug set_bp 0x0100 $::snapcas {
    incr ::starts
    if {$::starts == 2} { debug write ioports 0xFD 5 }
    if {$::starts == 3} { debug write ioports 0xFD 2; debug write ioports 0xFE 5 }
    if {$::starts == 4} { debug write ioports 0xFE 1 }
}
"""
        cls.screen = support.restorer_screen("test/nms8250-dos1", dos, os.path.join(WORK, "stops", "dos1"),
                                     {name: blank for name in ("DOS.SNP", "PAGE1.SNP", "PAGE2.SNP", "AGAIN.SNP")},
                                     tcl)

    def test_dos_in_segments_3_to_0_passes_the_check(self):
        # The restorer goes on to the ROMs, whose CRC-16s these images lack.
        for name in ("DOS.SNP", "AGAIN.SNP"):
            self.assertIn(support.said(f"{name}: made for another machine"), self.screen)

    def test_a_page_in_another_segment_stops(self):
        for name in ("PAGE1.SNP", "PAGE2.SNP"):
            self.assertIn(support.said(f"{name}: MSX-DOS 1 needs a memory mapper with DOS in segments 3, 2, 1 and 0"),
                          self.screen)


@support.needs_dos("msxdos1")
class Plan(unittest.TestCase):
    """The plan under MSX-DOS 1 in a mapper of 4 MB, which has a segment 255
    and 252 free segments, so no segment number stands for a record without a
    segment, and the worker's list of holding segments can fill."""

    @classmethod
    def setUpClass(cls):
        machine, dos = "test/nms8250-4m-dos1", support.dos("msxdos1")
        work = os.path.join(WORK, "stops", "plan")
        service = support.service()
        cls.facts = support.restorer_facts(machine, dos, work)
        slot = cls.facts["dos_slot"]
        # A page in segment 3 is DOS's own in page 0: it needs a holding
        # segment, which the worker copies into segment 3 at the end.
        held = (service["REC_MAPPER"], slot, 1, 3, None)
        files = {
            # A page in segment 255, which is free, and one in segment 3.
            "PLAN.SNP": support.synthetic_image((0, 0), [(service["REC_MAPPER"], slot, 1, 255, None),
                                                         (service["REC_MAPPER"], slot, 2, 3, None)]),
            "HOLD64.SNP": support.synthetic_image((0, 0), [held] * 64),
            "HOLD65.SNP": support.synthetic_image((0, 0), [held] * 65),
        }
        cls.plans, cls.screen = support.restorer_plans(machine, dos, work, files)

    def test_a_page_goes_straight_into_segment_255(self):
        plan = self.plans["PLAN"]
        self.assertEqual(self.facts["map_size"], 0)  # 256 segments
        self.assertEqual((plan["map_size"][0], plan["free_count"][0], tuple(plan["dos_seg0"])), (0, 252, (3, 2, 1, 0)))
        self.assertEqual(plan["dest"][0], 255)
        # Only the page in DOS's segment has a holding segment, the first
        # free one, which the worker copies into segment 3.
        self.assertEqual((plan["hold_count"][0], tuple(plan["holds"][:2])), (1, (4, 3)))
        self.assertEqual(plan["dest"][1], 4)
        self.assertEqual(plan["worker_seg"][0], 5)

    def test_the_list_of_holding_segments_holds_64(self):
        plan = self.plans["HOLD64"]
        self.assertEqual(plan["hold_count"][0], 64)
        # Each page has a holding segment of its own, from the first free one
        # on, and the worker takes the next.
        self.assertEqual(list(plan["holds"]), [b for n in range(64) for b in (4 + n, 3)])
        self.assertEqual(list(plan["dest"][:64]), list(range(4, 68)))
        self.assertEqual(plan["worker_seg"][0], 68)

    def test_a_65th_holding_segment_stops_the_restorer(self):
        self.assertNotIn("HOLD65", self.plans)
        self.assertIn(support.said("HOLD65.SNP: more than 64 pages need a segment that DOS uses"), self.screen)


@support.needs_dos("msxdos1")
class OtherMapper(unittest.TestCase):
    """A RAM page in segment 255 of a mapper that is not DOS's is copied into
    that segment: no segment number stands for a page outside a mapper. The
    machine is an NMS 8250 with two mappers of 4 MB, its own in slot 3-2 and a
    cartridge in slot 1, under MSX-DOS 1. Each has a segment 255, so whichever
    is DOS's, the other has one too. The restore runs until the restorer has
    placed the page."""

    MACHINE = "test/nms8250-4m-ram4mb-dos1"
    MAPPERS = {0x01, 0x8B}  # the slot IDs of the two mappers
    FILL = 0x55

    @classmethod
    def setUpClass(cls):
        dos = support.dos("msxdos1")
        work = os.path.join(WORK, "stops", "othermapper")
        service, restorer = support.service(), support.symbols("snapcas")
        cls.facts = support.restorer_facts(cls.MACHINE, dos, work)
        cls.other = min(cls.MAPPERS - {cls.facts["dos_slot"]})
        # The header names record 1 for the tail, which the image does not
        # have, so the restorer fills in no byte of the page.
        image = support.synthetic_image(cls.facts["crcs"], [(service["REC_MAPPER"], cls.other, 1, 255, cls.FILL)],
                                        H_TAILREC=1)
        out = os.path.join(work, "segments.txt")
        if os.path.exists(out):
            os.remove(out)
        # When the restorer has placed the RAM pages outside DOS's mapper, the
        # first pass of its records: the bytes of the fill in three segments,
        # each read in page 1 of its mapper's slot. Both mappers follow mapper
        # register FDh, which holds DOS's segment of page 1 again by then.
        tcl = f"""
proc filled {{id segment}} {{
    lassign [slot_parts $id] ps ss
    set fd [debug read {{MSX Memory Mapper I/O}} 1]
    debug write ioports 0xFD $segment
    set data [with_slot $ps $ss 1 {{ read_page 1 }}]
    debug write ioports 0xFD $fd
    regexp -all [binary format c {cls.FILL}] $data
}}
debug set_bp {restorer["read_records.passed"]} $::snapcas {{safe {{
    read_exptbl
    set fd [debug read {{MSX Memory Mapper I/O}} 1]
    set f [open {msx.tcl_word(out)} w]
    puts $f "other [filled {cls.other} 255]"
    puts $f "dos [filled {cls.facts["dos_slot"]} 255]"
    puts $f "selected [filled {cls.other} $fd]"
    puts $f "register $fd"
    close $f
    stop
}}}}
"""
        support.restorer_run(cls.MACHINE, dos, work, {"PAGE.SNP": image}, ["SNAPCAS PAGE"], tcl)
        with open(out) as f:
            cls.filled = {name: int(value) for name, value in (line.split() for line in f)}

    def test_each_mapper_has_256_segments(self):
        self.assertIn(self.facts["dos_slot"], self.MAPPERS)
        self.assertEqual(self.facts["map_size"], 0)  # 256 segments

    def test_the_page_is_in_segment_255_of_its_own_mapper(self):
        self.assertEqual(self.filled["other"], 16384)

    def test_the_page_is_not_in_dos_mapper_or_in_the_segment_that_page_1_selected(self):
        # A page outside a mapper is copied into whatever segment its page
        # selects: DOS's segment of page 1, 2, as mapper register FDh has it.
        self.assertEqual(self.filled["register"], 2)
        self.assertLess(self.filled["selected"], 16384)
        self.assertLess(self.filled["dos"], 16384)


@support.needs_dos("msxdos2")
class T0Segment(unittest.TestCase):
    """T0's segment when it shares mapper register FCh with a page 0 of the
    game in another mapper (src/snapcas.asm, t0_segment), on the Sony HB-F700P
    with a RAM cartridge of 512 KB: DOS's mapper is the cartridge, in slot 1,
    and the machine's own mapper is in slot 3-3. Afterburner on this machine
    has its page 0 there."""

    MACHINE = "hbf700p-ram512k-msxdos2"
    OTHER = 0x8F  # the slot ID of the machine's own mapper

    @classmethod
    def setUpClass(cls):
        dos = support.dos("msxdos2")
        work = os.path.join(WORK, "stops", "t0segment")
        service = support.service()
        cls.facts = support.restorer_facts(cls.MACHINE, dos, work)
        mapper, segment = service["REC_MAPPER"], (service["REC_SERVICE"], 0, 0, 0, None)

        def page0(seg):
            """A RAM page for page 0 in a segment of the machine's own mapper."""
            return (mapper, cls.OTHER, 0, seg, None)
        # Without a part in page 3, with page 0 in slot 3-3 at the snapshot.
        t0 = {"H_FLAGS": service["FLAG_T0"], "H_A8": 0x03, "H_SUB": (0, 0, 0, 0x03), "H_BORROW": 2}
        files = {
            # Segment 5 is free in DOS's mapper: T0 is read straight into it.
            "DIRECT.SNP": support.synthetic_image((0, 0), [page0(5), segment, segment], **t0),
            # Segment 3 is DOS's own in page 0: T0 goes to a holding segment.
            "HOLDING.SNP": support.synthetic_image((0, 0), [page0(3), segment, segment], **t0),
            # Two pages for page 0 in different segments.
            "DIFFER.SNP": support.synthetic_image((0, 0), [page0(5), page0(6), segment], **t0),
            # A segment beyond DOS's mapper's 32.
            "BEYOND.SNP": support.synthetic_image((0, 0), [page0(32), segment], **t0),
            # A RAM page of DOS's mapper has the segment.
            "TAKEN.SNP": support.synthetic_image((0, 0), [page0(5), (mapper, cls.facts["dos_slot"], 1, 5, None),
                                                          segment], **t0),
            # With a part in page 3 and rom keep, T0 takes register FCh only
            # in its own calls: any free segment will do.
            "KEEP.SNP": support.synthetic_image((0, 0), [page0(5), segment, segment],
                                                H_FLAGS=service["FLAG_ROM_KEEP"], H_A8=0x00),
            # With a part in page 3 and without rom keep, T0 replaces the ROM
            # in page 0 for good, as without a part.
            "REPLACE.SNP": support.synthetic_image((0, 0), [(mapper, cls.OTHER, 0, 6, None), segment, segment],
                                                   H_A8=0x00),
        }
        cls.plans, cls.screen = support.restorer_plans(cls.MACHINE, dos, work, files)

    def test_dos_mapper_is_the_cartridge_of_32_segments(self):
        self.assertEqual((self.facts["dos_slot"], self.facts["map_size"]), (0x01, 32))
        self.assertEqual(self.plans["DIRECT"]["dos_seg0"][0], 3)

    def test_t0_is_read_straight_into_a_free_segment(self):
        plan = self.plans["DIRECT"]
        self.assertEqual((plan["t0_fixed"], plan["t0_fix"], plan["t0_direct"]), (b"\1", b"\5", b"\1"))
        # T0, the image's record 1, is read into segment 5, which mapper
        # register FCh selects in the restored game, and no holding segment
        # is needed.
        self.assertEqual((plan["dest"][1], plan["svc_segs"][0], plan["map"][0], plan["hold_count"][0]), (5, 5, 5, 0))
        # The tape's segment and the worker take other segments.
        self.assertEqual(len({5, plan["dest"][2], plan["worker_seg"][0]}), 3)

    def test_t0_goes_through_a_holding_segment_into_one_that_dos_uses(self):
        plan = self.plans["HOLDING"]
        self.assertEqual((plan["t0_fixed"], plan["t0_fix"], plan["t0_direct"]), (b"\1", b"\3", b"\0"))
        holding = plan["dest"][1]
        self.assertNotIn(holding, tuple(plan["dos_seg0"]))
        # The worker copies the holding segment into segment 3 at the end.
        self.assertEqual((plan["hold_count"][0], tuple(plan["holds"][:2])), (1, (holding, 3)))
        self.assertEqual((plan["svc_segs"][0], plan["map"][0]), (3, 3))

    def test_pages_for_page_0_in_different_segments_stop(self):
        self.assertNotIn("DIFFER", self.plans)
        self.assertIn(support.said("DIFFER.SNP: T0 cannot take the segment of page 0's RAM, which shares mapper "
                                   "register FCh with it"), self.screen)

    def test_a_segment_beyond_dos_mapper_stops(self):
        self.assertNotIn("BEYOND", self.plans)
        self.assertIn(support.said("BEYOND.SNP: T0 cannot take the segment of page 0's RAM,"), self.screen)

    def test_a_segment_that_a_page_of_dos_mapper_has_stops(self):
        self.assertNotIn("TAKEN", self.plans)
        self.assertIn(support.said("TAKEN.SNP: T0 cannot take the segment of page 0's RAM,"), self.screen)

    def test_with_rom_keep_t0_takes_any_free_segment(self):
        plan = self.plans["KEEP"]
        self.assertEqual((plan["t0_fixed"], plan["t0_direct"], plan["hold_count"][0]), (b"\0", b"\0", 0))
        self.assertEqual(plan["dest"][1], plan["svc_segs"][0])

    def test_t0_in_place_of_the_rom_takes_the_segment_too(self):
        plan = self.plans["REPLACE"]
        self.assertEqual((plan["t0_fixed"], plan["t0_fix"], plan["t0_direct"]), (b"\1", b"\6", b"\1"))
        self.assertEqual((plan["dest"][1], plan["map"][0]), (6, 6))


@support.needs_dos("msxdos2")
class Fill(unittest.TestCase):
    """The values that the restorer fills in go into the record that the
    header names (src/snapcas.asm, fill), and not into a record of the tail's
    page or of page 3. The image is of a snapshot whose pages 2 and 3 select
    one mapper segment: its one record has page 2, and holds the tail and the
    game's page 3. The restore runs to the tail's jump, on an NMS 8250 whose
    mapper of 512 KB, DOS's, is in slot 3-2. The check cannot see the tail's
    bytes, which it leaves out of its comparison."""

    MACHINE = "test/nms8250-512k"
    TAIL, PC = 0xF000 - build.TAIL_SIZE, 0xD000

    @classmethod
    def setUpClass(cls):
        work = os.path.join(WORK, "fill")
        ram = {"3-2-1-2": bytes(build.PAGE), "3-2-2-5": bytes(build.PAGE), "3-2-3-5": bytes(build.PAGE)}
        # Slot 3 in pages 1 to 3, with subslot 2 there, and the ROM in page 0.
        snap = support.snapshot(os.path.join(work, "snap"), ram=ram, service=True, v9938=True, a8="FC", sub3="A8",
                                fd="02", fe="05", ff="05", sp="F000", pc=f"{cls.PC:04X}", af="1234",
                                **{"mapper3-2": "20"})
        game = build.gamefile.Game("GAME")
        game.tape = "GAME.CAS"
        cls.built = build.build(Snapshot(snap), support.SERVICE, game, support.BASIC_TAPE)
        cls.header, cls.service = support.Header(cls.built.header), support.service()
        s = cls.service
        jump = cls.TAIL + s["TAIL_JP"]
        # The restorer writes DOS's mapper's slot ID, T0's segment, the code
        # segment and mapper register FCh's value one after the other, after
        # the 7 entries (src/service.inc, E_SLOT), and E_STOP follows them.
        cls.filled_at = s["E_CODE"] - 2
        reads = {"tail": (cls.TAIL, build.TAIL_SIZE), "tail_in_page_2": (cls.TAIL - 0x4000, build.TAIL_SIZE),
                 "entries": (s["E_ENTRY"], cls.filled_at - s["E_ENTRY"]), "filled": (cls.filled_at, 5),
                 "slttbl": (0xFCC5, 4)}
        cls.memory = support.restorer_memory(
            cls.MACHINE, support.dos("msxdos2"), work, cls.built.header + b"".join(cls.built.data), jump,
            bytes([0xC3, cls.PC & 0xFF, cls.PC >> 8]), reads)

    def test_one_record_of_page_2_holds_the_tail_and_page_3(self):
        s, h = self.service, self.header
        self.assertEqual(h.records[:2], [(s["REC_MAPPER"], 0x8B, 1, 2), (s["REC_MAPPER"], 0x8B, 2, 5)])
        self.assertEqual((h["H_TAILREC"], h["H_P3REC"], h.word("H_TAIL") >> 14), (1, 1, 3))

    def test_the_tail_holds_the_builds_bytes_and_the_restorers_values(self):
        # The tail's fields have the restorer's names (src/service.inc).
        s, tail = support.symbols("snapcas"), self.memory["tail"]
        planned = self.built.data[1][self.TAIL & 0x3FFF:][:build.TAIL_SIZE]
        filled = {s["TAIL_MAP"], s["TAIL_PORT"], s["TAIL_A8"]}
        for offset in range(build.TAIL_SIZE):
            if offset not in filled:
                self.assertEqual(tail[offset], planned[offset], offset)
        self.assertEqual(struct.unpack_from("<H", tail, s["TAIL_PC"])[0], self.PC)
        # The worker's page is page 1, whose mapper register is FDh and held
        # segment 2 at the snapshot. Page 0 selects DOS's mapper's slot, 3,
        # where T0 replaces the ROM.
        self.assertEqual((planned[s["TAIL_MAP"]], planned[s["TAIL_PORT"]], planned[s["TAIL_A8"]]), (0, 0, 0))
        self.assertEqual((tail[s["TAIL_MAP"]], tail[s["TAIL_PORT"]], tail[s["TAIL_A8"]]), (0x02, 0xFD, 0xFF))
        # The segment is in page 2 as well, as at the snapshot.
        self.assertEqual(self.memory["tail_in_page_2"], tail)

    def test_page_3_holds_the_services_part_with_the_restorers_values(self):
        s = self.service
        self.assertEqual((self.filled_at - s["E_ENTRY"], s["E_FC"], s["E_STOP"]),
                         (7 * 3, self.filled_at + 3, self.filled_at + 4))
        self.assertEqual(self.memory["entries"], s.parts["page3"][:7 * 3])
        slot, t0, code, fc, stop = self.memory["filled"]
        # DOS's mapper's slot ID, T0's segment and the code segment, two free
        # segments of the mapper's 32, and T0's segment for mapper register
        # FCh. The motor is off at the snapshot.
        self.assertEqual((slot, fc, stop), (0x8B, t0, 1))
        self.assertEqual(len({t0, code, 2, 5}), 4)
        self.assertLess(max(t0, code), 32)
        # SLTTBL's value for slot 3 has DOS's mapper's subslot, 2, in page 0.
        self.assertEqual(self.memory["slttbl"][3] & 3, 2)


class Manual(unittest.TestCase):
    """/M in the restorer's command line, for the manual tape (INTERNALS.md,
    The manual tape), which needs the tape service with its part in page 3.
    The manual tape's reads are in tests/test_service.py."""

    @classmethod
    def setUpClass(cls):
        service = support.service()
        segment = (service["REC_SERVICE"], 0, 0, 0, None)
        files = {"PART.SNP": support.synthetic_image((0, 0), [segment] * 3),
                 # The capture's slot 2 was not expanded, so the restorer selects
                 # DOS's mapper's subslot in the borrowed page itself.
                 "T0.SNP": support.synthetic_image((0, 0), [segment] * 2, H_FLAGS=service["FLAG_T0"], H_BORROW=2,
                                                   H_NOEXP=0x04),
                 "PLAIN.SNP": support.synthetic_image((0, 0), [])}
        runs = {"upper": " /M", "lower": " /m", "none": "", "other": " /T /"}
        with concurrent.futures.ThreadPoolExecutor(len(runs)) as pool:
            cls.runs = dict(zip(runs, pool.map(lambda name: support.restorer_plans(
                support.PHC28S, support.NEXTOR, os.path.join(WORK, "manual", name), files, runs[name]), runs)))

    def test_the_option_is_read_in_either_case(self):
        for name, manual in (("upper", 1), ("lower", 1), ("none", 0), ("other", 0)):
            plans, _ = self.runs[name]
            self.assertEqual({image: plan["manual"][0] for image, plan in plans.items()},
                             {"PART": manual, "T0": manual, "PLAIN": manual}, name)

    def test_an_image_without_the_part_in_page_3_says_that_the_tape_stays_automatic(self):
        note = ": /M does not work with this image,"
        for name in ("upper", "lower"):
            _, screen = self.runs[name]
            self.assertIn(support.said("T0.SNP" + note), screen)
            self.assertIn(support.said("PLAIN.SNP" + note), screen)
            self.assertNotIn(support.said("PART.SNP" + note), screen)
        self.assertNotIn(support.said(note), self.runs["none"][1])
        self.assertNotIn(support.said(note), self.runs["other"][1])


if __name__ == "__main__":
    unittest.main()
