"""The capture (docs/INTERNALS.md, Capture, Slot patches and The RAM search
patch): the snapshots of single-load games, the capture's Tcl procedures in
openMSX's C-BIOS machine, the images that build.py makes of captured
snapshots, and a capture of a patched tape with two sides. Emulator tier."""
import concurrent.futures
import filecmp
import os
import re
import shutil
import struct
import unittest

import support
import build
import msx
import patches
from snapshot import Snapshot
import tape

WORK = support.work("capture")
PHC28S = support.PHC28S

# game: (CAS file, machine)
GAMES = {
    "freddy": ("FREDDY.CAS", PHC28S),
    "fernando": ("FERNANDO.CAS", PHC28S),
    "moonrider": ("022-MOON.CAS", PHC28S),
    "caldero": ("CALDERO.CAS", PHC28S),
    "abadia": ("ABADIA.CAS", "test/nms8250-128k"),
}

# The names of state.txt (FORMATS.md, Snapshot files).
NAMES = ([r for r in "af bc de hl af2 bc2 de2 hl2 ix iy sp pc i im iff a8 ppic".split()]
         + [f"sub{n}" for n in range(4)] + ["fc", "fd", "fe", "ff"]
         + [f"psg{n}" for n in range(16)] + ["psgsel", "vramptr", "vramwrite",
                                             "tapepos", "service", "tapetime", "tapeside"])
MSX1_VDP = [f"vdp{n}" for n in range(8)]
V9938 = ([f"vdp{n}" for n in range(24)] + [f"vdp{n}" for n in range(32, 46)]
         + [f"pal{n}" for n in range(16)])

# The PHC-28S's RAM: its own page 3 in slot 0, the RAM cartridge in slot 1,
# and the Carnivore2's mapper in subslot 2-2.
PHC_RAM = {"0-x-3"} | {f"1-x-{p}" for p in range(4)} | {f"2-2-{p}" for p in range(4)}


def capture(game, copy=None):
    """Captures a game of GAMES, and returns capture.py's result and the
    snapshot's folder. With copy, a capture that passes is copied there."""
    cas, machine = GAMES[game]
    # La Abadia del Crimen leaves its last 16 KB unread during the load.
    folder = support.game_folder(os.path.join(WORK, "games", "single-" + game),
                                 f"cas {cas}\n" + ("service no\n" if game == "abadia" else ""))
    support.tape(cas)
    result = support.tool("capture.py", folder, machine, "--tapes", support.TAPES)
    snap = os.path.join(folder, machine, "snap")
    if copy and result.returncode == 0:
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(snap, copy)
    return result, snap


def read_state(snap):
    return Snapshot(snap).state


def read_log(snap):
    with open(os.path.join(snap, "log.txt")) as f:
        return f.read()


class SingleLoads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(WORK, exist_ok=True)
        cls.first = os.path.join(WORK, "freddy-first")
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            jobs = {g: pool.submit(capture, g, cls.first if g == "freddy" else None)
                    for g in GAMES}
            cls.results = {g: job.result() for g, job in jobs.items()}

    def snap(self, game):
        result, snap = self.results[game]
        self.assertEqual(result.returncode, 0, f"{game}: {result.stderr}")
        return snap

    def test_state_names(self):
        for game in GAMES:
            with self.subTest(game=game):
                state = read_state(self.snap(game))
                v9938 = os.path.getsize(os.path.join(self.snap(game), "vram.bin")) > 16384
                expected = set(NAMES) | set(V9938 if v9938 else MSX1_VDP)
                # Each mapper that holds a kept page adds its size.
                sizes = {name for name in state if re.fullmatch(r"mapper\d-[x\d]", name)}
                self.assertEqual(set(state) - sizes, expected)

    def test_slot_and_mapper_values_keep_their_two_digits(self):
        for game in GAMES:
            with self.subTest(game=game):
                state = read_state(self.snap(game))
                for name in ("sub0", "sub1", "sub2", "sub3", "fc", "fd", "fe", "ff"):
                    self.assertRegex(state[name], r"^(-|[0-9A-F]{2})$", name)
        # The PHC-28S's mapper is the Carnivore2's, whose registers BASIC
        # leaves at 3, 2, 1 and 0, and whose 1 MB is 64 segments.
        state = read_state(self.snap("caldero"))
        self.assertEqual([state[name] for name in ("fc", "fd", "fe", "ff")], ["03", "02", "01", "00"])
        self.assertEqual(state["mapper2-2"], "40")

    def test_single_loads_need_no_tape_service(self):
        for game in ("freddy", "fernando", "moonrider", "caldero"):
            with self.subTest(game=game):
                self.assertEqual(read_state(self.snap(game))["service"], "0")

    def test_kept_pages_are_ram_of_the_phc28s(self):
        for game in ("freddy", "fernando", "moonrider", "caldero"):
            with self.subTest(game=game):
                ram = os.listdir(os.path.join(self.snap(game), "ram"))
                self.assertTrue(ram)
                for name in ram:
                    m = re.fullmatch(r"(\d-[x\d]-\d)-([x\d]+)\.bin", name)
                    self.assertTrue(m, name)
                    self.assertIn(m.group(1), PHC_RAM)
                    self.assertEqual(os.path.getsize(os.path.join(self.snap(game), "ram", name)), 16384)
                    if m.group(1).startswith("2-2"):
                        self.assertLess(int(m.group(2)), 64)
                self.assertIn("the mapper in slot 2-2 has 64 segments", read_log(self.snap(game)))

    def test_a_load_that_waits_for_a_key_continues(self):
        log = read_log(self.snap("abadia"))
        self.assertIn("continue space", log)

    def test_service_no_leaves_out_the_tape_service(self):
        self.assertEqual(read_state(self.snap("abadia"))["service"], "0")

    def test_a_second_capture_gives_the_same_snapshot(self):
        result, snap = capture("freddy")
        self.assertEqual(result.returncode, 0, result.stderr)
        compare = filecmp.dircmp(self.first, snap)
        self.assertEqual(compare.diff_files, [])
        self.assertEqual(compare.left_only + compare.right_only, [])
        ram = filecmp.dircmp(os.path.join(self.first, "ram"), os.path.join(snap, "ram"))
        self.assertEqual(ram.diff_files + ram.left_only + ram.right_only, [])

    def test_a_machine_whose_ram_the_loader_finds_gets_no_ram_search_patch(self):
        # La Abadia del Crimen's loader has the RAM search (PLAN.md, step 14).
        # On the NMS 8250 the slot that it finds holds page 3's RAM, so no
        # write cuts off its code, and the tape stays as it is.
        self.assertEqual(support.read_tape("ABADIA.CAS").count(patches.ramsearch.SEARCH), 1)
        snap = self.snap("abadia")
        self.assertEqual(Snapshot(snap).capture_patches(), [])
        self.assertNotIn("cuts off its code", read_log(snap))
        self.assertFalse(os.path.exists(os.path.join(snap, "side1.cas")))


# Tcl that calls the capture's procedures and writes each result as a line.
PROCEDURES = r"""
set f [open [file join $::S(snap) results.txt] w]
proc result {name value} { puts $::f "$name $value" }

# The procedures run at 1 emulated second, when the BIOS has set the slot
# register: at time 0 it reads back as 0 whatever a script writes to it.
later 1 {
# read_with wraps at FFFFh, and puts the slot register back after an error.
# The BIOS has selected the RAM, in slot 3, in page 3 by now, and slot 0 holds
# nothing there: a read with slot 0 in page 3 gives other bytes than the RAM's.
set a8 [debug read ioports 0xA8]
result a8_page_3 [expr {$a8 >> 6}]
debug write_block memory 0xC102 [binary format H* 01020304]
result reads_ram [expr {[read_with $a8 0xC102 4] eq [binary format H* 01020304]}]
result reads_the_other_slot [expr {[read_with [expr {$a8 & 0x3F}] 0xC102 4] ne [binary format H* 01020304]}]
result a8_back_after_a_read [expr {[debug read ioports 0xA8] == $a8}]
result wrapped [expr {[read_with $a8 0xFFFE 4] eq "[debug read_block memory 0xFFFE 2][debug read_block memory 0 2]"}]
result below_zero [string length [read_with $a8 -3 5]]
result read_error [catch {read_with [expr {$a8 & 0x3F}] 0 -1}]
result a8_back [expr {[debug read ioports 0xA8] == $a8}]

# The tape position after side 2 goes in, without and with a standard block.
set ::S(headers) {0 100}
set ::S(s1len) 208
set ::st(pos) 208; next_header
result pos_without_block $::st(pos)
set ::S(headers2) {208 400}
set ::st(pos) 208; next_header
result pos_with_block $::st(pos)

# TAPIN at a header reads the byte after it, on either side, and elsewhere the
# byte at the position.
set ::st(tapin) 0
set ::st(pos) 50; on_tapin
result tapin_in_a_block $::st(pos)
set ::st(pos) 100; on_tapin
result tapin_at_a_header $::st(pos)
set ::st(pos) 400; on_tapin
result tapin_at_a_header_of_side_2 "$::st(pos) $::st(tapin)"

# The slot watches leave out the capture's own writes of the snap phase.
set ::hooks(slot_write) {}
foreach ps {0 1 2 3} { set ::st(sub$ps) 0 }
set ::st(sel) {}
set ::st(a8) 0
set ::run(phase) snap; on_a8 255; on_ffff 85
result snap_phase "$::st(a8) $::st(sub0) [dict size $::st(sel)]"
set ::run(phase) load; on_a8 255
result load_phase $::st(a8)

# loadstate removes the watchpoints, and a rewind sets those of the slot
# register again: a write after it still reaches on_a8 and on_ffff.
set ::st(a8) 0
watch_slots
moment_save rewind
moment_load rewind
set before [debug read ioports 0xA8]
debug write ioports 0xA8 [expr {$before ^ 0x04}]
result rewind_a8 [expr {$::st(a8) == ($before ^ 0x04)}]
debug write ioports 0xA8 $before
result rewind_watchpoints [llength $::run(slotwp)]
catch { file delete [moment_file rewind] }

# A reset during a key try follows the machine, and another is kept.
set ::run(phase) try; on_reset
result try_reset "[llength $::st(log)] [llength $::run(decisions)]"
set ::run(phase) load; on_reset
result load_reset "[llength $::st(log)] [llength $::run(decisions)]"

result patch_line [patch_line 2 0x1F {0x3E 0xFC 0xD3 0xA8} {62 21 211 168}]

# The log of the writes that name a slot that holds nothing: each pair of an
# address and a value once, and none from the main ROM.
array set ::slots {0 {{} -1} 1 {{} -1} 2 {{} -1} 3 {3 -1}}
set ::exptbl {0 0 0 0}
set ::run(tape1) ""; set ::run(tape2) ""
set ::run(decisions) {}
set pc [reg pc]
reg pc 0x9000
slot_watch 0xC0 0; slot_watch 0xC0 0; slot_watch 0xC1 0
result ram_writes [llength $::run(decisions)]
reg pc 0x0100
slot_watch 0xC2 0
result rom_writes [llength $::run(decisions)]
# A write that keeps page 3's slot cuts off no code: the watch of the RAM
# search does nothing.
reg pc 0xC100
set decisions [llength $::run(decisions)]
ramsearch_watch [expr {$a8 ^ 0x03}] $a8
result ramsearch_same_page_3 "[expr {[llength $::run(decisions)] - $decisions}] [file exists [file join $::S(snap) newpatch.txt]]"
# An MSX1 has no sub-ROM, so a tape's interrupt handler keeps its bytes there.
set ::irqslot {{1 21 3a53d0}}
set ::run(msx2) 0
irqslot_start
result irqslot_msx1 [file exists [file join $::S(snap) newpatch.txt]]
set ::irqslot {}
reg pc $pc
close $f

# fail leaves its callback, and what comes after it does not run.
later 0.1 {
    safe { fail "first"; write_lines after.txt went_on }
    safe { fail "second" }
    safe { write_lines later.txt ran }
}
}
"""

# Tcl for the watch of the RAM search (INTERNALS.md, The RAM search patch): a
# write to the slot register, from code in page 3, that selects another slot
# there, where the bytes after the code differ. The search occurs twice on side
# 1 and once on side 2.
RAMSEARCH = r"""
set search [binary format H* %s]
set ::run(tape1) "[string repeat x 16]${search}[string repeat x 100]${search}xx"
set ::run(tape2) "[string repeat x 8]${search}"
set ::run(decisions) {}
# The C-BIOS machine's RAM is in slot 3, which page 3 selects once the BIOS has
# started, and its slot 0 holds nothing in page 3: the write selects slot 0
# there, from code in slot 3.
later 1 {
    set ram [expr {[debug read ioports 0xA8] | 0xC0}]
    debug write ioports 0xA8 $ram
    debug write_block memory 0xC102 [binary format H* 01020304]
    reg pc 0xC100
    ramsearch_watch [expr {$ram & 0x3F}] $ram
    # stop_with_patch has stopped the capture, and nothing runs after it.
    write_lines went_on.txt 1
    stop
}
""" % patches.ramsearch.SEARCH.hex()


# Tcl for the interrupt slot patch (INTERNALS.md, The interrupt slot patch), on
# an MSX2: a handler on each side of the tape.
IRQSLOT = r"""
set ::irqslot {{1 21 3a53d0} {2 5 3abecf}}
set ::run(msx2) 1
later 1 {
    irqslot_start
    # stop_with_patch has stopped the capture, and nothing runs after it.
    write_lines went_on.txt 1
    stop
}
"""


class Procedures(unittest.TestCase):
    """The capture's Tcl procedures, run in openMSX's C-BIOS machine, which
    needs no system ROMs."""

    @classmethod
    def setUpClass(cls):
        cls.snaps = {}
        for name, start in (("procedures", PROCEDURES), ("boot", "safe step1\n"), ("ramsearch", RAMSEARCH),
                            ("irqslot", IRQSLOT)):
            snap = cls.snaps[name] = os.path.join(WORK, name)
            shutil.rmtree(snap, ignore_errors=True)
            os.makedirs(snap)
            settings = {"snap": msx.tcl_word(snap), "home": msx.tcl_word(msx.home()), "state": "snapcas-test",
                        "boot": "{}", "afterboot": "wait_ok", "tape": "{}", "cmd": "{}", "cload": "0",
                        "headers": "{}", "needed": "0", "side2tape": "{}", "s1len": "0", "headers2": "{}",
                        "nosvc": "0", "keys": "{}", "lastkey": "0", "tries": "{}", "snapat": "{}"}
            script = ("".join(f"set ::S({k}) {v}\n" for k, v in settings.items())
                      + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/capture.tcl") + patches.tcl(b"", b"") + start)
            support.cbios(script)
        with open(os.path.join(cls.snaps["procedures"], "results.txt")) as f:
            cls.results = dict(line.rstrip("\n").split(" ", 1) for line in f)

    def read(self, name, file):
        with open(os.path.join(self.snaps[name], file)) as f:
            return f.read()

    def test_a_read_wraps_at_ffffh_and_puts_the_slot_register_back(self):
        self.assertEqual(self.results["wrapped"], "1")
        self.assertEqual(self.results["below_zero"], "5")
        self.assertEqual(self.results["read_error"], "1")
        self.assertEqual(self.results["a8_back"], "1")
        # The read selects the slots that it is given: page 3's RAM is in slot
        # 3, and with slot 0 there the same address reads other bytes. So the
        # slot register changes for a read, and is back after it.
        self.assertEqual(self.results["a8_page_3"], "3")
        self.assertEqual((self.results["reads_ram"], self.results["reads_the_other_slot"]), ("1", "1"))
        self.assertEqual(self.results["a8_back_after_a_read"], "1")

    def test_side_2_without_a_standard_block_starts_at_its_start(self):
        self.assertEqual(self.results["pos_without_block"], "208")
        self.assertEqual(self.results["pos_with_block"], "216")

    def test_a_tapin_at_a_header_goes_past_it_as_the_tape_services_does(self):
        # A game that reads on into the next block calls no TAPION there, and
        # the tape service's TAPIN skips the header's 8 bytes (src/tape.inc).
        self.assertEqual(self.results["tapin_in_a_block"], "51")
        self.assertEqual(self.results["tapin_at_a_header"], "109")
        self.assertEqual(self.results["tapin_at_a_header_of_side_2"], "409 3")

    def test_the_slot_watches_leave_out_the_snapshots_own_writes(self):
        self.assertEqual(self.results["snap_phase"], "0 0 0")
        self.assertEqual(self.results["load_phase"], "255")

    def test_a_reset_during_a_key_try_goes_with_its_rewind(self):
        self.assertEqual(self.results["try_reset"], "1 0")
        self.assertEqual(self.results["load_reset"], "1 1")

    def test_a_patch_line_has_one_form(self):
        self.assertEqual(self.results["patch_line"], "patch side2:1F 3E FC D3 A8 > 3E 15 D3 A8")

    def test_the_log_holds_each_write_once_and_none_from_the_main_rom(self):
        self.assertEqual(self.results["ram_writes"], "2")
        self.assertEqual(self.results["rom_writes"], "2")

    def test_fail_stops_the_capture_at_its_first_error(self):
        self.assertEqual(self.read("procedures", "error.txt"), "capture: first\n")
        for file in ("after.txt", "later.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.snaps["procedures"], file)), file)

    def test_a_boot_that_fails_leaves_its_error_and_the_screen_in_the_log(self):
        self.assertEqual(self.read("boot", "error.txt"), "capture: BASIC's Ok did not appear within 120 seconds\n")
        log = self.read("boot", "log.txt")
        self.assertRegex(log, r"^120\.00 the capture stops: BASIC's Ok did not appear within 120 seconds, screen: ")
        self.assertIn("C-BIOS", log)

    def test_the_ram_search_is_patched_at_each_copy_on_the_tape(self):
        # Made in Spain's tape holds the search in each of its loaders
        # (PLAN.md, step 14): the capture stops with a patch of every copy.
        at = patches.ramsearch.AT
        self.assertEqual(self.read("ramsearch", "newpatch.txt").splitlines(),
                         [f"patch side1:{16 + at:X} CB FF > 00 00", f"patch side1:{16 + 8 + 100 + at:X} CB FF > 00 00",
                          f"patch side2:{8 + at:X} CB FF > 00 00"])
        self.assertRegex(self.read("ramsearch", "log.txt"),
                         r"the slot register write of [0-9A-F]{2} at PC C100 cuts off its code: the RAM search patched")
        for file in ("went_on.txt", "error.txt", "state.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.snaps["ramsearch"], file)), file)

    def test_an_msx2_gets_the_interrupt_slot_patch_at_each_handler(self):
        self.assertEqual(self.read("irqslot", "newpatch.txt").splitlines(),
                         ["patch side1:15 3A 53 D0 > DB A8 00", "patch side2:5 3A BE CF > DB A8 00"])
        self.assertIn("the tape's interrupt handler writes the slot register from the game's copy of it",
                      self.read("irqslot", "log.txt"))
        self.assertFalse(os.path.exists(os.path.join(self.snaps["irqslot"], "went_on.txt")))

    def test_a_rewind_sets_the_slot_registers_watchpoints_again(self):
        # Before, a RAM page that a game first selected after a rewind was not
        # kept: A-TEAM's pages 0 and 1, after the rewind of its key try.
        self.assertEqual((self.results["rewind_a8"], self.results["rewind_watchpoints"]), ("1", "2"))

    def test_an_msx1_keeps_the_handlers_bytes(self):
        self.assertEqual(self.results["irqslot_msx1"], "0")

    def test_a_write_that_keeps_page_3s_slot_is_left_alone(self):
        self.assertEqual(self.results["ramsearch_same_page_3"], "0 0")


# game: (CAS file, machine), all single loads, for Images.
IMAGES = {
    "freddy": ("FREDDY.CAS", PHC28S),
    "fernando": ("FERNANDO.CAS", PHC28S),
    "caldero": ("CALDERO.CAS", PHC28S),
    "freddy8250": ("FREDDY.CAS", "nms8250-carnivore2"),
}


class Images(unittest.TestCase):
    """The images of captured snapshots, checked against the format's tables
    (FORMATS.md), one of them of an MSX2, for the V9938's port writes."""

    @classmethod
    def setUpClass(cls):
        def make(game):
            cas, machine = IMAGES[game]
            support.tape(cas)
            return support.make_image(support.game_folder(os.path.join(WORK, "games", "image-" + game),
                                                          f"cas {cas}\n"), machine)
        with concurrent.futures.ThreadPoolExecutor(len(IMAGES)) as pool:
            made = dict(zip(IMAGES, pool.map(make, IMAGES)))
        cls.images = {}
        for game, result in made.items():
            if result.step:
                raise AssertionError(f"{game}: {result}")
            name = build.gamefile.default_name("image-" + game)
            cls.images[game] = (result.read(f"{name}.SNP", binary=True), result.snapshot.state, result.snap)

    service = support.service()

    def header(self, image):
        h = image[:4096]
        rom, subrom, records, writes = struct.unpack_from("<HHBB", h, 8)
        table = [h[64 + 4 * n:68 + 4 * n] for n in range(records)]
        start = 64 + 4 * records
        ports = [tuple(h[start + 2 * n:start + 2 * n + 2]) for n in range(writes)]
        return h, rom, subrom, table, ports

    def test_mark_crcs_and_size(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h, rom, subrom, table, _ = self.header(image)
                self.assertEqual(h[:8], self.service.mark)
                with open(os.path.join(snap, "rom.bin"), "rb") as f:
                    self.assertEqual(rom, build.crc16(f.read()))
                if os.path.exists(os.path.join(snap, "subrom.bin")):
                    with open(os.path.join(snap, "subrom.bin"), "rb") as f:
                        self.assertEqual(subrom, build.crc16(f.read()))
                else:
                    self.assertEqual(subrom, 0)
                full = sum(1 for r in table if r[0] != self.service["REC_ZEROS"])
                self.assertEqual(len(image), 4096 + 16384 * full)

    def test_registers(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h = image[:4096]
                names = "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()
                self.assertEqual(list(struct.unpack_from("<12H", h, 16)),
                                 [int(state[n], 16) for n in names])
                self.assertEqual(h[40], int(state["i"], 16))
                self.assertEqual(h[41], int(state["im"], 16))
                self.assertEqual(h[42], int(state["iff"], 16) & 1)
                self.assertEqual(h[43], int(state["a8"], 16))

    def test_records(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                _, _, _, table, _ = self.header(image)
                types = {name: self.service[name] for name in ("REC_MAPPER", "REC_RAM", "REC_VRAM", "REC_ZEROS")}
                ram = [r for r in table if r[0] in (types["REC_MAPPER"], types["REC_RAM"])]
                vram = [r for r in table if r[0] in (types["REC_VRAM"], types["REC_ZEROS"])]
                files = os.listdir(os.path.join(snap, "ram"))
                self.assertTrue(ram)
                self.assertLessEqual(len(ram), len(files))
                self.assertEqual(sorted(r[1] for r in vram),
                                 list(range(os.path.getsize(os.path.join(snap, "vram.bin")) // 16384)))

    def test_port_writes_start_with_the_psg_and_end_with_the_pointer(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                _, _, _, _, ports = self.header(image)
                self.assertEqual([p for p, _ in ports[:32]], [0xA0, 0xA1] * 16)
                self.assertEqual(ports[33], (0xAA, int(state["ppic"], 16)))
                if state["vramwrite"] == "1":
                    self.assertTrue(ports[-1][1] & 0x40)

    def test_tail(self):
        for game, (image, state, snap) in self.images.items():
            with self.subTest(game=game):
                h, _, _, table, _ = self.header(image)
                tail = struct.unpack_from("<H", h, 52)[0]
                sp, pc, af = (int(state[n], 16) for n in ("sp", "pc", "af"))
                self.assertEqual(tail, sp - 26)
                page = tail >> 14
                ps, ss = Snapshot(snap).selected_slot(page)
                slot = ps if ss is None else 0x80 | (ss << 2) | ps
                # The header names the tail's record, which is the page's.
                n = h[self.service["H_TAILREC"]]
                self.assertEqual(table[n][1:3], bytes([slot, page]))
                data = image[4096 + 16384 * n:4096 + 16384 * (n + 1)]
                code = data[tail & 0x3FFF:(tail & 0x3FFF) + 26]
                ei = 0xFB if int(state["iff"], 16) & 1 else 0x00
                expected = (bytes([0x3E, 0, 0xD3, 0, 0x3E, 0, 0xD3, 0xA8, 0x3E, 0, 0, 0, 0, 0x31])
                            + struct.pack("<H", tail + 24) + bytes([0xF1, 0x31])
                            + struct.pack("<H", sp) + bytes([ei, 0xC3])
                            + struct.pack("<H", pc) + struct.pack("<H", af))
                self.assertEqual(code, expected)


# Sootland selects RAM in slot 3, so its side1 patch makes its loader keep page
# 3 in the PHC-28S's internal RAM and select the RAM cartridge for pages 1 and
# 2. The capture must load the patched tape, or the game crashes.
SOOTLAND = """cas SOOTLAND.CAS
side2 SOOTLANB.CAS
sha1 5ccf9a2463aa3144f3c03c2a23b798ba68d184e4 c2d10d8d5694de81b1192ec7d85aa80a10f89045
capture phc28s-ram64k
patch side1:024E 3E FC D3 A8 > 3E 14 D3 A8
"""


class PatchedTape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("SOOTLAND.CAS", "SOOTLANB.CAS"):
            support.tape(name)
        cls.restored = support.restore(support.game_folder(os.path.join(WORK, "games", "patched-sootland"), SOOTLAND),
                                       PHC28S)

    def test_the_capture_loads_the_patched_tape(self):
        self.assertEqual(self.restored.read("snap/side1.cas", binary=True)[0x24E:0x252], bytes.fromhex("3E 14 D3 A8"))

    def test_the_capture_turns_the_tape_over(self):
        # The game reads on past side 1's end, so side 2 goes in, and the
        # tape position goes on in side 2 (INTERNALS.md, Capture, step 4).
        support.assert_passes(self, self.restored)
        self.assertIn("side 2 inserted", self.restored.read("snap/log.txt"))
        side2_start = tape.side2_start(len(support.read_tape("SOOTLAND.CAS")))
        self.assertGreater(self.restored.snapshot.num("tapepos"), side2_start)


if __name__ == "__main__":
    unittest.main()
