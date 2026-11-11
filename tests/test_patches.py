"""The automatic patches of tools/patches/ (docs/INTERNALS.md, The tools'
code, Scan, Slot patches, The RAM search patch, The page copy patch and The
interrupt slot patch): each
kind's patterns, on bytes made for each case, and the settings that the
capture's Tcl gets. The capture's watches run in tests/test_capture.py, and
the patches of real games in tests/test_snap.py. Pure tier."""
import unittest

import support  # noqa: F401
import cas
import patches

# A scan for an image with the tape service's entries at FCE1h to FCF3h.
WITH_ENTRIES = patches.Context(entry_page=0xFC)


def found(data):
    return [(f.what, f.offset, f.new) for f in patches.find(bytes.fromhex(data), WITH_ENTRIES)]


class Patterns(unittest.TestCase):
    def test_stubs_with_de_and_hl(self):
        self.assertEqual(found("00 11 E1 00 D5 11 D9 CD D5"),
                         [("stub of TAPION", 1, bytes.fromhex("11 E1 FC D5 11 D9 CD D5"))])
        self.assertEqual(found("21 E1 00 E5 21 D9 CD E5"),
                         [("stub of TAPION", 0, bytes.fromhex("21 E1 FC E5 21 D9 CD E5"))])

    def test_a_stub_of_tapoon_is_left_alone(self):
        self.assertEqual(found("11 EA 00 D5 11 D9 CD D5"), [])

    def test_calls(self):
        self.assertEqual(found("CD E1 00 CD E4 00 CD E7 00 CD EA 00 CD E1 01"), [
            ("call of TAPION", 0, bytes.fromhex("CD E1 FC")),
            ("call of TAPIN", 3, bytes.fromhex("CD E4 FC")),
            ("call of TAPIOF", 6, bytes.fromhex("CD E7 FC")),
        ])

    def test_entries_in_hl_before_a_call(self):
        self.assertEqual(found("21 E1 00 CD 96 FC 21 E4 00 CD 96 FC 21 E1 00 00"), [
            ("entry of TAPION in HL", 0, bytes.fromhex("21 E1 FC CD")),
            ("entry of TAPIN in HL", 6, bytes.fromhex("21 E4 FC CD")),
        ])

    def test_readers_within_4_bytes_are_listed_unpatched(self):
        self.assertEqual(found("DB A2 17"), [("reader of the cassette signal", 0, None)])
        self.assertEqual(found("DB A2 00 00 00 CB 7F"), [("reader of the cassette signal", 0, None)])
        self.assertEqual(found("DB A2 00 00 00 00 E6 80"), [])

    def test_readers_of_psg_register_14_are_listed_unpatched(self):
        self.assertEqual(found("3E 0E D3 A0 DB A2 47"),
                         [("reader of PSG register 14, the cassette signal or a joystick", 0, None)])

    def test_patch_writes_only_the_patched_findings(self):
        data = bytearray.fromhex("CD E1 00 DB A2 07")
        patches.patch(data, patches.find(bytes(data), WITH_ENTRIES))
        self.assertEqual(data, bytearray.fromhex("CD E1 FC DB A2 07"))

    def test_report_lines_are_patch_lines(self):
        text = patches.report([("page3", patches.find(bytes.fromhex("00 CD E4 00"), WITH_ENTRIES))],
                              [("side1", patches.find(bytes.fromhex("DB A2 07"), WITH_ENTRIES))])
        self.assertIn("page3:0001 CD E4 00 > CD E4 FC  call of TAPIN\n", text)
        self.assertIn("side1:0000 DB A2 07  reader of the cassette signal\n", text)


class SlotPatches(unittest.TestCase):
    def test_the_scan_skips_a_3eh_that_can_be_an_operand(self):
        # The PHC-28S's slot map: slot 3 holds nothing in any page.
        slots = {0: ({3}, 2), 1: ({3}, 1), 2: ({0, 3}, 2), 3: ({3}, 2)}
        # Knight Orc's LD A,(EF3Eh) / OUT (0A8h),A, and the same after CALL.
        for code in ("3A 3E EF D3 A8", "CD 3E EF D3 A8", "3A 00 3E EF D3 A8"):
            self.assertEqual(patches.find(bytes.fromhex(code), patches.Context(slots=slots, tape=False)), [], code)
        found = patches.find(bytes.fromhex("F5 3E EF D3 A8"), patches.Context(slots=slots, tape=False))
        self.assertEqual([(f.offset, f.new) for f in found], [(1, bytes.fromhex("3E A6 D3 A8"))])

    def test_the_watch_gets_the_scans_forms(self):
        # The forms' bytes are in slots.py only, and the capture's Tcl gets
        # them as settings before each kind's Tcl file.
        tcl = patches.tcl(b"", b"")
        for setting in ("set ::slotcode(load) {62}", "set ::slotcode(out) {211 168}",
                        "set ::slotcode(wslreg) {205 59 1}", "set ::slotcode(indirect) 58"):
            self.assertIn(setting, tcl)
        self.assertRegex(bytes([0x3E, 0xFC, 0xCD, 0x3B, 0x01]), patches.slots.SLOT_CODE)
        hooks = [tcl.index(f"hook {hook}") for hook in
                 ("start slot_start", "slot_write slot_watch", "slot_write ramsearch_watch", "start pagecopy_start")]
        self.assertEqual(hooks, sorted(hooks))


class Kinds(unittest.TestCase):
    def test_every_kind_has_the_scans_function_and_the_captures(self):
        for kind in patches.KINDS:
            with self.subTest(kind=kind.__name__):
                self.assertEqual(kind.find(b"", patches.Context()), [])
                self.assertIsInstance(kind.tcl(b"", b""), str)
        # A kind that works only in the scan has no Tcl, and one that works
        # only in the capture finds nothing.
        self.assertEqual([kind.__name__.split(".")[1] for kind in patches.KINDS if not kind.tcl(b"", b"")],
                         ["tapecode", "t0stub"])
        search = bytes.fromhex("78 3D FE 04 38 02 CB FF")
        self.assertEqual(patches.find(search, patches.Context(entry_page=0xFC)), [])


class PageCopy(unittest.TestCase):
    def test_a_blocks_sum_byte_is_found_when_it_holds_the_sum(self):
        # Two blocks of 8 bytes, as CAS pads them: the first ends with the sum
        # of its other bytes, the second does not.
        header = cas.HEADER
        data = header + bytes([1, 2, 3, 0, 0, 0, 0, 6]) + header + bytes([1, 2, 3, 0, 0, 0, 0, 7])
        blocks = cas.spans(data)
        self.assertEqual(patches.pagecopy.sum_byte(data, blocks, 9), 15)
        self.assertEqual(patches.pagecopy.sum_byte(data, blocks, 25), -1)

    def test_the_sum_byte_is_the_last_of_its_block_as_the_cas_reader_finds_it(self):
        # A block that is not padded: its sum byte comes right before the next
        # header, which is off a multiple of 8 bytes.
        data = cas.HEADER + bytes([1, 2, 3, 6]) + cas.HEADER + bytes([9])
        self.assertEqual(cas.spans(data), [(8, 12), (20, 21)])
        self.assertEqual(patches.pagecopy.sum_byte(data, cas.spans(data), 9), 11)
        # A TSX file has no CAS block, so no sum byte.
        self.assertEqual(patches.pagecopy.sum_byte(b"ZXTape!" + bytes(20), cas.spans(b"ZXTape!" + bytes(20)), 9), -1)


class T0Stub(unittest.TestCase):
    # Altered Beast's stub of TAPION, which selects the ROM in page 0 with AND H / LD L,A.
    STUB = bytes.fromhex("11 E1 00 D5 11 D9 CD D5 11 ED 69 D5 E5 D9 0E A8 ED 60 A4 6F CD 9A FC")

    def test_the_scan_patches_the_stub_only_in_the_mode_without_a_part_in_page_3(self):
        self.assertEqual(patches.find(self.STUB, patches.Context(tape=False)), [])
        with_entries = patches.find(self.STUB, patches.Context(entry_page=0xFC))
        self.assertEqual([f for f in with_entries if f.what == patches.t0stub.T0_STUB], [])
        # Without a part in page 3, the context has no entry page. The patch
        # leaves the value at 0 and names its place, for the restorer.
        found = patches.find(self.STUB, patches.Context())
        self.assertEqual([(f.offset, f.old, f.new, f.place) for f in found],
                         [(0, self.STUB[:8], None, None), (18, bytes.fromhex("A4 6F"), bytes.fromhex("2E 00"), 1)])
        self.assertEqual(found[1].line("page0"), "page0:0012 A4 6F > 2E nn  stub's selection of the ROM in page 0")
        # On the tape, the restorer fills in nothing, so the stub is only listed.
        found = patches.find(self.STUB, patches.Context(ram=False))
        self.assertEqual([(f.offset, f.new) for f in found], [(0, None), (18, None)])


class RamSearch(unittest.TestCase):
    """The RAM search patch (docs/PLAN.md, step 14). The capture's watch
    patches each copy of the search on the tape, in tests/test_capture.py."""

    def test_the_patch_writes_two_nops_over_the_set_of_bit_7(self):
        search = patches.ramsearch.SEARCH
        self.assertEqual(search[patches.ramsearch.AT:], bytes.fromhex("CB FF"))
        self.assertEqual(len(patches.ramsearch.NEW), len(search) - patches.ramsearch.AT)
        self.assertEqual(patches.ramsearch.NEW, bytes(2))

    def test_the_capture_gets_the_search_and_its_patch_as_settings(self):
        tcl = patches.ramsearch.tcl(b"", b"")
        for setting in ("set ::ramsearch [binary format H* 783dfe043802cbff]\n", "set ::ramsearch_at 6\n",
                        "set ::ramsearch_old {203 255}\n", "set ::ramsearch_new {0 0}\n"):
            self.assertIn(setting, tcl)
        self.assertLess(tcl.index("set ::ramsearch_new"), tcl.index("proc ramsearch_watch"))
        self.assertIn("hook slot_write ramsearch_watch", tcl)

    def test_the_scan_leaves_the_search_alone(self):
        # The loader has finished by the snapshot, so the kind finds nothing
        # in a RAM page, with or without the tape service.
        search = patches.ramsearch.SEARCH
        for context in (patches.Context(), patches.Context(entry_page=0xFC), patches.Context(tape=False)):
            self.assertEqual(patches.ramsearch.find(search, context), [])
            self.assertEqual(patches.find(search, context), [])


# The interrupt handler of Aventuras AD's interpreter, with the game's copy of
# the slot register at D053h, as in La Aventura Espacial: its start, the call
# of the game's routine and its end.
HANDLER = bytes.fromhex("F3 F5 E5 DD E5 3A 53 D0 F5 3A 09 B0 D3 A8 32 53 D0 2A 11 B0 DD 21 67 D1 CD 10 B0"
                        "3A 08 B0 D3 A8 32 53 D0 00 00 FF F3 F1 D3 A8 32 53 D0 DD E1 E1 F1 FB C9")


class IrqSlot(unittest.TestCase):
    """The interrupt slot patch (INTERNALS.md, The interrupt slot patch). The
    capture's decision by the machine is in tests/test_capture.py."""

    def test_a_handler_is_found_at_its_read_of_the_copy(self):
        self.assertEqual(patches.irqslot.places(b"\x00" * 7 + HANDLER), [(7 + 5, bytes.fromhex("3A 53 D0"))])
        # The Elves's interpreter keeps the copy at CFBEh.
        other = HANDLER.replace(bytes.fromhex("53 D0"), bytes.fromhex("BE CF"))
        self.assertEqual(patches.irqslot.places(HANDLER + other),
                         [(5, bytes.fromhex("3A 53 D0")), (len(HANDLER) + 5, bytes.fromhex("3A BE CF"))])

    def test_code_that_does_not_write_the_copys_value_back_is_left_alone(self):
        # Without the handler's end, with an end that stores to another
        # address, and with a start that stores to another address.
        end = HANDLER.index(bytes.fromhex("F1 D3 A8 32 53 D0"))
        for data in (HANDLER[:end], HANDLER[:end] + bytes.fromhex("F1 D3 A8 32 54 D0"),
                     HANDLER[:14] + bytes.fromhex("32 54 D0") + HANDLER[17:]):
            self.assertEqual(patches.irqslot.places(data), [])

    def test_the_capture_gets_each_handler_and_the_patch_as_settings(self):
        tcl = patches.irqslot.tcl(b"\x00" + HANDLER, b"\x00" * 3 + HANDLER)
        self.assertIn("set ::irqslot {{1 6 3a53d0} {2 8 3a53d0}}\n", tcl)
        self.assertIn("set ::irqslot_new {219 168 0}\n", tcl)
        self.assertLess(tcl.index("set ::irqslot_new"), tcl.index("proc irqslot_start"))
        self.assertIn("hook start irqslot_start", tcl)
        self.assertIn("set ::irqslot {}\n", patches.irqslot.tcl(b"", b""))

    def test_the_scan_leaves_the_handler_alone(self):
        # The capture patches every copy on the tape before the load.
        self.assertEqual(patches.irqslot.find(HANDLER, patches.Context()), [])


if __name__ == "__main__":
    unittest.main()
