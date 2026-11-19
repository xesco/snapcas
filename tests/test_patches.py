"""The automatic patches of tools/patches/ (docs/INTERNALS.md, The tools'
code, Scan, Slot patches, The RAM search patch, The page copy patch, The
search slot patch, The interrupt slot patch, The subslot POKE patch, The hook fill patch and The
trampoline patch): each
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

    def test_the_scan_skips_a_stack_word_before_the_bioss_rdprim(self):
        # X-Racing's return address 603Eh at F37Eh, before RDPRIM at F380h.
        slots = {0: ({1, 2}, 3), 1: ({1, 2}, -1), 2: ({1, 2}, 0), 3: ({1, 2}, 0)}
        page3 = bytes.fromhex("3E 60 D3 A8 5E 18 03 D3 A8 73 7A D3 A8 C9")
        self.assertEqual(patches.find(page3, patches.Context(slots=slots, tape=False)), [])
        self.assertEqual(len(patches.find(bytes.fromhex("3E 60 D3 A8 C9"), patches.Context(slots=slots, tape=False))), 1)

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


# A RAM search as in After the War's block "slots": its start, the 130 bytes
# that test the slots, and its end with its store at FA78h.
SEARCH_SLOT = patches.searchslot.START + bytes(130) + patches.searchslot.END + bytes.fromhex("78 FA FB C9")


class SearchSlot(unittest.TestCase):
    """The search slot patch: a RAM search that stores for page 1 the slot of
    BASIC's page 2, and not the slot that it found."""

    def test_the_end_is_found_144_bytes_after_the_start(self):
        self.assertEqual(patches.searchslot.ends(SEARCH_SLOT), [144])
        self.assertEqual(patches.searchslot.ends(bytes(7) + SEARCH_SLOT + SEARCH_SLOT), [151, 151 + len(SEARCH_SLOT)])

    def test_an_end_at_another_distance_or_alone_is_left_alone(self):
        self.assertEqual(patches.searchslot.ends(patches.searchslot.START + bytes(131) + patches.searchslot.END), [])
        self.assertEqual(patches.searchslot.ends(bytes(144) + patches.searchslot.END), [])

    def test_the_patch_takes_page_1s_slot_from_c_and_keeps_the_store(self):
        # LD A,C / AND 0Ch / LD C,A / IN A,(0A8h) / AND 0F3h / OR C / NOP over
        # IN A,(0A8h) / LD C,A / SRL A / SRL A / AND 0Ch / OR C.
        self.assertEqual(patches.searchslot.OLD, bytes.fromhex("DB A8 4F CB 3F CB 3F E6 0C B1"))
        self.assertEqual(patches.searchslot.NEW, bytes.fromhex("79 E6 0C 4F DB A8 E6 F3 B1 00"))
        self.assertEqual(patches.searchslot.END[len(patches.searchslot.OLD):], b"\x32")

    def test_the_capture_gets_each_end_and_the_patch_as_settings(self):
        tcl = patches.searchslot.tcl(SEARCH_SLOT, bytes(3) + SEARCH_SLOT)
        for setting in ("set ::searchslot {{1 144} {2 147}}\n",
                        "set ::searchslot_old {219 168 79 203 63 203 63 230 12 177}\n",
                        "set ::searchslot_new {121 230 12 79 219 168 230 243 177 0}\n"):
            self.assertIn(setting, tcl)
        self.assertLess(tcl.index("set ::searchslot_new"), tcl.index("proc searchslot_start"))
        self.assertIn("hook start searchslot_start", tcl)
        self.assertIn("set ::searchslot {}\n", patches.searchslot.tcl(b"", b""))

    def test_the_scan_leaves_the_search_alone(self):
        for context in (patches.Context(), WITH_ENTRIES, patches.Context(tape=False)):
            self.assertEqual(patches.searchslot.find(SEARCH_SLOT, context), [])


# The end of the ENASLT copy in the loaders of Arkos and Satan: the write of
# the subslot register with AND B, then the slot register's old value back, and
# their selection of BASIC's ROM in page 1 by EXPTBL's entry for slot 1.
ENASLT_COPY = bytes.fromhex("7B 2F 67 3A FF FF 2F 6F A0 B2 32 FF FF 78 D3 A8 F1 E6 03 C9")
ENASLT_PAGE1 = bytes.fromhex("26 40 3A C2 FC CD 6E DB")


class Enaslt(unittest.TestCase):
    """The ENASLT copy patch: a loader's copy of ENASLT with AND B where the
    BIOS has AND H, and its selection of page 1 by EXPTBL's slot 1 entry."""

    def test_the_subslot_write_gets_and_h(self):
        self.assertEqual(patches.enaslt.places(ENASLT_COPY),
                         [(3, patches.enaslt.SUBSLOT, patches.enaslt.SUBSLOT_NEW)])
        # AND B, A0h, becomes AND H, A4h, and the rest stays.
        old, new = patches.enaslt.SUBSLOT, patches.enaslt.SUBSLOT_NEW
        self.assertEqual([(i, a, b) for i, (a, b) in enumerate(zip(old, new)) if a != b], [(5, 0xA0, 0xA4)])

    def test_the_page_1_selection_is_patched_only_with_the_copy(self):
        both = ENASLT_PAGE1 + ENASLT_COPY + ENASLT_PAGE1
        self.assertEqual([offset for offset, old, new in patches.enaslt.places(both)], [0, 11, 28])
        self.assertEqual(patches.enaslt.places(both)[0][2], bytes.fromhex("26 40 3A C1 FC"))
        self.assertEqual(patches.enaslt.places(ENASLT_PAGE1), [])

    def test_the_capture_gets_each_form_as_a_setting(self):
        tcl = patches.enaslt.tcl(ENASLT_COPY, bytes(2) + ENASLT_PAGE1 + ENASLT_COPY)
        self.assertIn("set ::enaslt {{1 3 {58 255 255 47 111 160 178 50 255 255} {58 255 255 47 111 164 178 50 255 255}}"
                      " {2 2 {38 64 58 194 252} {38 64 58 193 252}}"
                      " {2 13 {58 255 255 47 111 160 178 50 255 255} {58 255 255 47 111 164 178 50 255 255}}}\n", tcl)
        self.assertLess(tcl.index("set ::enaslt"), tcl.index("proc enaslt_start"))
        self.assertIn("hook start enaslt_start", tcl)
        self.assertIn("set ::enaslt {}\n", patches.enaslt.tcl(b"", b""))

    def test_the_scan_leaves_the_copy_alone(self):
        for context in (patches.Context(), WITH_ENTRIES, patches.Context(tape=False)):
            self.assertEqual(patches.enaslt.find(ENASLT_COPY, context), [])


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


class SubPoke(unittest.TestCase):
    """The subslot POKE patch (INTERNALS.md, The subslot POKE patch). The
    capture's decision by the machine is in tests/test_capture.py."""

    def test_a_poke_in_a_program_saved_as_text_is_found_at_its_value(self):
        # Line 2 of the loader of Super MSX's tapes.
        line = b"2 POKE&HFFFF,&HAA:SCREEN2,,0"
        self.assertEqual(patches.subpoke.places(b"1 CLEAR100\r\n" + line), [(12 + line.index(b"AA"), "H", 0xAA)])
        self.assertEqual(patches.subpoke.places(b"10 POKE-1,170:CLS"), [(10, "D", 170)])
        self.assertEqual(patches.subpoke.places(b"10 POKE -1, 170\r\n20 POKE &HFFFF , &HAA"), [(12, "D", 170), (36, "H", 0xAA)])
        # Lady Safari's and Magic Pinball's: subslot 2 in pages 1 to 3 only.
        self.assertEqual(patches.subpoke.places(b"2 POKE -1,168:' En el SONY"), [(10, "D", 168)])
        self.assertEqual(patches.subpoke.places(b"10 POKE 65535!,168:CLEAR 0"), [(15, "D", 168)])
        self.assertEqual(patches.subpoke.places(b"POKE65535,&HA8"), [(12, "H", 0xA8)])

    def test_a_poke_in_a_tokenized_program_is_found_at_its_value(self):
        # POKE-1,170 and POKE&HFFFF,&HAA as BASIC keeps them.
        self.assertEqual(patches.subpoke.places(bytes.fromhex("00 98 F2 12 2C 0F AA 3A")), [(6, "T", 0xAA)])
        self.assertEqual(patches.subpoke.places(bytes.fromhex("98 0C FF FF 2C 0C AA 00 3A")), [(6, "T", 0xAA)])
        self.assertEqual(patches.subpoke.places(bytes.fromhex("98 F2 12 2C 0F A8")), [(5, "T", 0xA8)])

    def test_another_address_or_value_is_left_alone(self):
        for data in (b"POKE&HFFFF,&HAAA", b"POKE-1,1700", b"POKE-1,169", b"POKE&HFFFE,&HAA", b"POKE-10,170",
                     b"POKE 65534,168", bytes.fromhex("98 F2 12 2C 0F A9"), bytes.fromhex("98 0C FF FF 2C 0C AA 01"),
                     bytes.fromhex("98 0C FF FF 2C 12")):
            self.assertEqual(patches.subpoke.places(data), [], data)

    def test_the_capture_gets_each_poke_as_a_setting(self):
        tcl = patches.subpoke.tcl(b"POKE-1,170", b"xPOKE&HFFFF,&HAA")
        self.assertIn("set ::subpoke {{1 7 D 170} {2 14 H 170}}\n", tcl)
        self.assertLess(tcl.index("set ::subpoke"), tcl.index("proc subpoke_start"))
        self.assertIn("hook start subpoke_start", tcl)
        self.assertIn("set ::subpoke {}\n", patches.subpoke.tcl(b"", b""))

    def test_the_scan_leaves_the_poke_alone(self):
        # The capture patches every copy on the tape before the load.
        self.assertEqual(patches.subpoke.find(b"POKE-1,170", patches.Context()), [])


class HookFill(unittest.TestCase):
    """The hook fill patch (INTERNALS.md, The hook fill patch). The capture's
    decision by the machine is in tests/test_capture.py."""

    # Digy Dung's loader: RET from FD9Ah to FFF6h, over an MSX2's RG8SAV to
    # RG23SAV.
    FILL = bytes.fromhex("F3 21 9A FD 11 9B FD 01 5C 02 36 C9 ED B0 21")

    def test_a_fill_past_the_hooks_is_found_at_its_count(self):
        self.assertEqual(patches.hookfill.places(b"\x00" * 5 + self.FILL), [(5 + 8, bytes.fromhex("5C 02"))])
        self.assertEqual(patches.hookfill.NEW, bytes.fromhex("2F 02"))

    def test_a_fill_that_ends_at_the_hooks_end_is_left_alone(self):
        # Bomb Hazard's ends at FFC9h, and another fill or another start is
        # not this code.
        for data in (self.FILL.replace(bytes.fromhex("5C 02"), bytes.fromhex("2F 02")),
                     self.FILL.replace(bytes.fromhex("36 C9"), bytes.fromhex("36 00")),
                     self.FILL.replace(bytes.fromhex("21 9A FD"), bytes.fromhex("21 9F FD"))):
            self.assertEqual(patches.hookfill.places(data), [])

    def test_the_capture_gets_each_fill_and_the_patch_as_settings(self):
        tcl = patches.hookfill.tcl(self.FILL, b"\x00" + self.FILL)
        self.assertIn("set ::hookfill {{1 8 5c02} {2 9 5c02}}\n", tcl)
        self.assertIn("set ::hookfill_new {47 2}\n", tcl)
        self.assertIn("hook start hookfill_start", tcl)
        self.assertEqual(patches.hookfill.find(self.FILL, patches.Context()), [])



# The loader of Opera Soft's and Topo Soft's tapes: the trampoline's builder
# and its first call, as in Dragon Ninja.
BUILDER = patches.tramp.BUILDER + patches.tramp.CALL


def trampoline(builder):
    """The 10 bytes that the builder's five pushes of DE leave at FC9Ah."""
    words = [builder[i + 1:i + 3] for i in (16, 12, 8, 4, 0)]
    return b"".join(words)


class Tramp(unittest.TestCase):
    """The trampoline patch (INTERNALS.md, The trampoline patch). The capture's
    decision by the machine is in tests/test_capture.py, and the build's revert
    in tests/test_build.py."""

    def test_the_tapes_trampoline_selects_page_0_by_the_slot_register(self):
        # OUT (C),L / EXX / CALL 00E1h / EXX / OUT (C),H / RET.
        self.assertEqual(trampoline(BUILDER), bytes.fromhex("ED 69 D9 CD E1 00 D9 ED 61 C9"))

    def test_the_patched_trampoline_writes_the_subslot_register(self):
        # The SX-2 with its Extra-Mapper on: the ROM in 0-0, the RAM in 0-1.
        new = patches.tramp.patched(0, 1)
        self.assertEqual(new, bytes.fromhex("11 C9 C4 D5 11 D9 71 D5 11 E1 00 D5 11 D9 CD D5 11 36 54 D5 E5 D9"
                                            "21 FF FF 7E 2F 4F"))
        # LD (HL),54h / EXX / CALL 00E1h / EXX / LD (HL),C / RET, and the free
        # byte at FCA3h.
        self.assertEqual(trampoline(new), bytes.fromhex("36 54 D9 CD E1 00 D9 71 C9 C4"))
        # The caller: LD HL,0FFFFh / LD A,(HL) / CPL / LD C,A.
        self.assertEqual(new[22:], bytes.fromhex("21 FF FF 7E 2F 4F"))

    def test_each_form_keeps_the_xor_of_the_builder(self):
        for rom in range(4):
            for ram in range(4):
                new = patches.tramp.patched(rom, ram)
                with self.subTest(rom=rom, ram=ram):
                    self.assertEqual(patches.tramp.xor(new), patches.tramp.xor(patches.tramp.BUILDER))
                    self.assertEqual(len(new), len(patches.tramp.BUILDER))
                    # Page 0 gets the ROM's subslot, the other pages the RAM's.
                    self.assertEqual(new[18], ram * 0x54 + rom)

    def test_a_builder_is_found_only_before_its_call(self):
        self.assertEqual(patches.tramp.places(bytes(3) + BUILDER + BUILDER), [3, 3 + len(BUILDER)])
        self.assertEqual(patches.tramp.places(patches.tramp.BUILDER + bytes.fromhex("CD 9A FD")), [])

    def test_the_build_makes_each_patched_builder_call_the_service(self):
        patched = patches.tramp.patched(0, 1) + patches.tramp.CALL
        data = bytearray(bytes(2) + patched + patched)
        self.assertEqual(patches.tramp.serve(data, 0xFC), [2, 33])
        served = bytes(data[2:30])
        # LD (HL),55h, RAM in every page, and the call of the entry at FCE1h.
        self.assertEqual(trampoline(served), bytes.fromhex("36 55 D9 CD E1 FC D9 71 C9") + served[2:3])
        self.assertEqual(served[22:], patches.tramp.NEW_CALLER)
        self.assertEqual(patches.tramp.xor(served), patches.tramp.xor(patches.tramp.BUILDER))
        self.assertEqual(bytes(data[33:61]), served)
        # A part at another entry page takes the call there.
        data = bytearray(patched)
        patches.tramp.serve(data, 0xEA)
        self.assertEqual(trampoline(bytes(data))[3:6], bytes.fromhex("CD E1 EA"))
        self.assertEqual(patches.tramp.xor(data[:28]), patches.tramp.xor(patches.tramp.BUILDER))
        # In the mode without a part in page 3, the call stays at 00E1h, where
        # page 0 then shows T0.
        data = bytearray(patched)
        patches.tramp.serve(data, None)
        self.assertEqual(trampoline(bytes(data)), bytes.fromhex("36 55 D9 CD E1 00 D9 71 C9") + data[2:3])
        self.assertEqual(patches.tramp.xor(data[:28]), patches.tramp.xor(patches.tramp.BUILDER))
        # The tape's builder, and a patched one without its call, stay.
        for kept in (bytearray(BUILDER), bytearray(patches.tramp.patched(0, 1) + bytes(3))):
            before = bytes(kept)
            self.assertEqual(patches.tramp.serve(kept, 0xFC), [])
            self.assertEqual(bytes(kept), before)

    def test_a_patched_trampoline_at_fc9a_calls_the_service(self):
        page3 = bytearray(0x4000)
        self.assertIsNone(patches.tramp.serve_live(page3, 0xFC))
        # The loader has changed the call's low byte for TAPIN.
        page3[0x3C9A:0x3CA4] = bytes.fromhex("36 54 D9 CD E4 00 D9 71 C9 C4")
        self.assertEqual(patches.tramp.serve_live(page3, 0xFC), 0x3C9A)
        self.assertEqual(bytes(page3[0x3C9A:0x3CA4]), bytes.fromhex("36 55 D9 CD E4 FC D9 71 C9 C4"))
        page3[0x3C9A:0x3CA4] = bytes.fromhex("36 54 D9 CD E4 00 D9 71 C9 C4")
        self.assertEqual(patches.tramp.serve_live(page3, 0xEA), 0x3C9A)
        self.assertEqual(bytes(page3[0x3C9D:0x3CA0]), bytes.fromhex("CD E4 EA"))
        page3[0x3C9A:0x3CA4] = trampoline(BUILDER)
        self.assertIsNone(patches.tramp.serve_live(page3, 0xFC))

    def test_the_capture_gets_each_builder_and_each_form_as_settings(self):
        tcl = patches.tramp.tcl(bytes(1) + BUILDER, bytes(2) + BUILDER)
        self.assertIn("set ::tramp {{1 1} {2 2}}\n", tcl)
        self.assertIn("set ::tramp_old {17 97 201 213 ", tcl)
        self.assertIn("{0,1 {17 201 196 213 17 217 113 213 17 225 0 213 17 217 205 213 17 54 84 213 229 217 33 255 255"
                      " 126 47 79} ", tcl)
        self.assertNotIn(" 1,1 ", tcl)
        self.assertLess(tcl.index("array set ::tramp_new"), tcl.index("proc tramp_start"))
        self.assertIn("hook start tramp_start", tcl)
        self.assertEqual(patches.tramp.find(BUILDER, WITH_ENTRIES), [])
