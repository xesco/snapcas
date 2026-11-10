"""The tape service in restored games (docs/INTERNALS.md, Tape service, The
manual tape and Without a part in page 3): games that load during play, each
captured, built and checked on the PHC-28S and then played to its next load,
the contracts of the service's entries, the manual tape of /M, the place of
the service's part of page 3, and the check's guard of that part. Emulator
tier.

A play starts from the check's savestate at 10 seconds, with the inputs that
reach the game's next load. It reads the tape position in the code segment,
which it finds in DOS's mapper by its CAS header. The addresses in the service
come from out/service.sym, and those of the test games from their own symbols.
"""
import collections
import concurrent.futures
import hashlib
import os
import struct
import unittest

import support
from cas import HEADER as CAS_HEADER
import msx

MACHINE = support.PHC28S
MAPPER_RAM = "Carnivore2 ram"  # the openMSX debuggable of DOS's mapper on it
WORK = support.work("service")
GAMES_DIR = os.path.join(WORK, "games")
T0_TABLE, PART = 0x00E1, 0xFCE1  # TAPION's entry in T0's jump table and in page 3


def sym(name):
    """A label's address in SERVICE.BIN, from out/service.sym."""
    return support.symbols("service")[name]


def game(name, text):
    """Writes a game folder of this module, and returns it."""
    return support.game_folder(os.path.join(GAMES_DIR, name), text)


# A play of a restored game: the game's folder, the inputs, 4 seconds apart,
# the seconds of play, the breakpoints to count, as {name: address}, and
# whether the image has the tape service without a part in page 3, where T0
# holds the data and the routines. An input is a key name, a digit, keys
# joined by +, which are held for 3 seconds with space in them for 0.5, or
# fire, the joystick's button, which the play gives by clearing bit 4 of A
# after the game reads PSG register 14 for port 1. The game reads it in the
# BIOS's RDPSG, at 1112h, or in its own code.
Play = collections.namedtuple("Play", "folder inputs seconds counts t0", defaults=({}, False))
JOYSTICK_READS = (0x1112, 0xB3FD)


def play_script(play, out):
    names = ("pos", "s1end", "total", "start", "header")
    if play.t0:
        fields = {k: sym(f"t0m.D_{k.upper()}") & 0x3FFF for k in names}
        here = f"[debug read_block memory {sym('t0m.D_HEADER')} 8] eq [binary format H* {CAS_HEADER.hex()}]"
        entries = {"tapion": sym("t0m.tapion"), "tapin": sym("t0m.tapin")}
    else:
        # The code segment's routines, which T0's stubs and the entries in
        # page 3 both call, while mapper register FCh selects that segment.
        fields = {k: sym(f"D_{k.upper()}") for k in names}
        here = f"[debug read {{MSX Memory Mapper I/O}} 0] == [debug read memory {sym('E_CODE')}]"
        entries = {"tapion": sym("tapion"), "tapin": sym("tapin")}
    entries = {name: (address, here) for name, address in entries.items()}
    presses = []
    for n, name in enumerate(play.inputs):
        if name == "fire":
            action = "set ::fire 1; later 0.3 {set ::fire 0}"
        elif "+" in name:
            action = "; ".join(msx.press(key, 0.5 if key == "space" else 3) for key in name.split("+"))
        elif name.isdigit():
            # The digits are not key names, because their place depends on the
            # layout. 1 is row 0, bit 1, on this machine.
            action = f"keymatrixdown 0 {1 << int(name)}; later 0.5 {{keymatrixup 0 {1 << int(name)}}}"
        else:
            action = msx.press(name, 0.5)
        presses.append(f"later {2 + 4 * n} {{{action}}}")
    state = os.path.join(play.folder, MACHINE, "check", "10s")
    bps = "\n".join(f'set ::n({name}) 0\ndebug set_bp {address} {{{condition}}} {{safe {{incr ::n({name})}}}}'
                    for name, (address, condition) in {**entries,
                                                       **{k: (a, "") for k, a in play.counts.items()}}.items())
    joy = "\n".join(f"debug set_bp {a} {{}} {{safe fire}}" for a in JOYSTICK_READS)
    return f"""
loadstate {msx.tcl_word(state)}
later {play.seconds + 60} {{ error "the play did not write its values within {play.seconds + 60} seconds" }}
proc base {{}} {{
    for {{set a 0}} {{$a < [debug size "{MAPPER_RAM}"]}} {{incr a 16384}} {{
        if {{[debug read_block "{MAPPER_RAM}" [expr {{$a + {fields["header"]}}}] 8] eq [binary format H* {CAS_HEADER.hex()}]}} {{ return $a }}
    }}
    error "no code segment or T0"
}}
proc word3 {{offset}} {{
    binary scan [debug read_block "{MAPPER_RAM}" [expr {{$::base + $offset}}] 3] cu3 b
    expr {{[lindex $b 0] | ([lindex $b 1] << 8) | ([lindex $b 2] << 16)}}
}}
set ::base [base]
set ::pos0 [word3 {fields["pos"]}]
set ::fire 0
proc fire {{}} {{
    if {{$::fire && ([debug read {{PSG regs}} 15] & 0x40) == 0}} {{ reg AF [expr {{[reg AF] & ~0x1000}}] }}
}}
{bps}
{joy}
# The flash's colours, from E at the start of mark in the code segment.
set ::colours {{}}
if {{!{int(bool(play.t0))}}} {{
    debug set_bp {sym("mark")} {{[debug read {{MSX Memory Mapper I/O}} 0] == [debug read memory {sym("E_CODE")}]}} {{safe {{ lappend ::colours [expr {{[reg DE] & 255}}] }}}}
}}
{chr(10).join(presses)}
later {play.seconds} {{
    set f [open {msx.tcl_word(out)} w]
    puts $f "pos0 $::pos0"
    foreach {{name offset}} {{pos {fields["pos"]} s1end {fields["s1end"]} total {fields["total"]} start {fields["start"]}}} {{ puts $f "$name [word3 $offset]" }}
    foreach name [array names ::n] {{ puts $f "$name $::n($name)" }}
    foreach c {{3 9}} {{ puts $f "colour$c [llength [lsearch -all $::colours $c]]" }}
    close $f
    stop
}}
"""


def run_play(name, play):
    """Plays a restored game, and returns its tape values and counts. An
    error of the play's Tcl ends openMSX, which fails the test."""
    out = os.path.join(WORK, f"{name}-play.txt")
    if os.path.exists(out):
        os.remove(out)
    machine = msx.read_machine(msx.machine_path(MACHINE))
    disk = os.path.join(play.folder, MACHINE, "check", "disk.dsk")
    stderr = msx.run([*machine.args, f"-{machine.disk}", disk], play_script(play, out), timeout=600)
    if not os.path.exists(out):
        raise AssertionError(f"{name}: openMSX stopped before the play's report{msx.last_output(stderr)}")
    with open(out) as f:
        return {k: int(v) for k, v in (line.split() for line in f)}


def restore_and_play(name, text, inputs, seconds, counts=None, t0=False, tapes=support.TAPES):
    """Captures, builds and checks a game, and plays it when the check
    passes. Returns the Restored and the play's values, or none."""
    restored = support.restore(game(name, text), MACHINE, tapes)
    if restored.step or restored.status:
        return restored, {}
    return restored, run_play(name, Play(restored.folder, inputs, seconds, counts or {}, t0))


GAMES = {
    "computad": "cas COMPUTAD.CAS\n",
    "gauntlet": """cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
# The loaders select the ROM in page 0 from a copy of the slot register. The
# scan patches the one in RAM. The main game's, loaded at 4400h, is in an
# unread block, which ends with a 16-bit sum of its bytes, so the 1F8h that
# the two patches add goes into the sum.
patch side1:AE88 CD E1 00 > CD E1 FC
patch side1:AED4 CD E4 00 > CD E4 FC
patch side1:E2F3 45 F0 > 3D F2
# Its RAM search adds page 0's RAM slot to the slot register's page 0 bits.
rom keep
""",
}

# play: (game, inputs, seconds of play, breakpoints to count).
PLAYS = {
    # The instructions, the menu's theme 1 and RETURN, then the data tape.
    "computad": ("computad", ["space", "space", "1", "return", "space"], 50, {}),
    # The intro, the players and the character, then the side 2 prompt.
    # 958Bh jumps to the level that the level loader read.
    "gauntlet": ("gauntlet", ["space"] * 4 + ["fire"] * 15 + ["space"] * 8, 180,
                 {"level": 0x958B, "joy": 0xB3FD}),
    # The same, with GRAPH and CODE held at the side 2 prompt.
    "gauntlet-keys": ("gauntlet", ["space"] * 4 + ["fire"] * 15 + ["graph+code+space"] * 2, 180,
                      {"level": 0x958B}),
}


class Loads(unittest.TestCase):
    """Computad and Gauntlet, which load during play (PLAN.md, step 5)."""

    @classmethod
    def setUpClass(cls):
        for name in ("COMPUTAD.CAS", "GAUNTLET.CAS", "GAUNTLEB.CAS"):
            support.tape(name)
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.restored = dict(zip(GAMES, pool.map(lambda name: support.restore(game(name, GAMES[name]), MACHINE),
                                                    GAMES)))
        names = [name for name in PLAYS if cls.restored[PLAYS[name][0]].status == 0]
        with concurrent.futures.ThreadPoolExecutor(max(len(names), 1)) as pool:
            played = dict(zip(names, pool.map(
                lambda name: run_play(name, Play(cls.restored[PLAYS[name][0]].folder, *PLAYS[name][1:])), names)))
        cls.plays = {name: played.get(name, {}) for name in PLAYS}

    def test_the_games_pass_the_check_with_the_service(self):
        for name, restored in self.restored.items():
            with self.subTest(game=name):
                support.assert_passes(self, restored)
                self.assertEqual(restored.snapshot.state["service"], "1")

    def test_computad_loads_theme_1(self):
        values = self.plays["computad"]
        # Theme 1's two blocks: a 16-byte name and 256 bytes, which end at
        # offset 7,560 of the CAS file.
        self.assertEqual(values.get("tapion"), 2, values)
        self.assertEqual(values.get("tapin"), 272, values)
        self.assertEqual(values["pos"], values["start"] + 7560)
        self.assertEqual((values.get("colour3"), values.get("colour9")), (0, 0), values)

    def test_gauntlet_loads_its_main_game_then_a_level_from_side_2(self):
        values = self.plays["gauntlet"]
        self.assertGreater(values.get("joy", 0), 0, values)
        # Side 1 ends at 58,101 bytes, padded to 58,104, and side 2 adds
        # 95,157.
        self.assertEqual(values["s1end"], values["start"] + 58104)
        self.assertEqual(values["total"], values["s1end"] + 95157)
        self.assertGreater(values["pos"], values["s1end"], values)
        self.assertLess(values["pos"], values["total"], values)
        self.assertEqual(values.get("level"), 1, values)
        # The turn-over to side 2 shows light red.
        self.assertEqual((values.get("colour3"), values.get("colour9")), (0, 1), values)

    def test_graph_and_code_show_their_border_colours(self):
        values = self.plays["gauntlet-keys"]
        # One TAPION reads both keys: GRAPH, light green, side 1's start, then
        # CODE, light red, side 2's start, where the level loads from.
        self.assertEqual(values.get("colour3"), 1, values)
        self.assertEqual(values.get("colour9"), 1, values)
        self.assertEqual(values.get("level"), 1, values)
        self.assertGreater(values["pos"], values["s1end"], values)


# The games whose loader's stub the scan patches, as folder: the game file,
# the inputs that reach the next load from the check's savestate at 10
# seconds, and the seconds of play.
STUBS = {
    "play-tour91": ("cas TOUR-91.CAS\nside2 TOUR-91B.CAS\n", ["0"], 60),         # the menu's 0, COMENZAR
    "play-madmide": ("cas MAD-MIDE.CAS\n", ["space", "space", "0"], 60),          # the title, then the menu's 0, START
    # Its loader selects the ROM in page 0 itself, with IN A,(0A8h) / AND 0FCh /
    # OR 00h / OUT (0A8h),A.
    "play-desperad": ("cas DESPERAD.CAS\n", ["1"], 60),                           # the menu's 1, Fase 1
}


class Stubs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for text, _, _ in STUBS.values():
            for line in text.splitlines():
                support.tape(line.split()[1])
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            cls.plays = dict(zip(STUBS, pool.map(lambda name: restore_and_play(name, *STUBS[name]), STUBS)))

    def test_a_patched_stub_reaches_the_tape_service(self):
        for name, (restored, values) in self.plays.items():
            with self.subTest(game=name):
                support.assert_passes(self, restored)
                # The patched stub calls the entry in page 3, which calls T0's
                # TAPION, and the position moves past its value at the snapshot.
                self.assertGreater(values["tapion"], 0, values)
                self.assertGreater(values["pos"], values["pos0"], values)


# Moonwalker, with the tape service in T0 (INTERNALS.md, Without a part in page
# 3): its game file, and the inputs from the intro to the main game's load. Its
# loader's stub selects the ROM in page 0, so the scan patches it, and the
# restorer writes the value that selects DOS's mapper there.
MOONWALKER = """cas MOONWALK.CAS
sha1 1787776aeef9420ebb35c3ecb879a7c9a556a512
snapshot at 135
service t0
"""


class WithoutAPartInPage3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.tape("MOONWALK.CAS")
        cls.restored, cls.values = restore_and_play("t0-moonwalk", MOONWALKER, ["space"] * 3, 120, t0=True)

    def test_moonwalker_loads_its_main_game_through_t0(self):
        support.assert_passes(self, self.restored)
        # From the intro to the end of the main game's 22 KB block, as in a
        # load from the tape.
        self.assertGreater(self.values["tapion"], 0, self.values)
        self.assertEqual(self.values["pos"], 60418, self.values)

    def test_the_restorer_writes_the_value_of_the_stubs_selection(self):
        # The header lists the value's place, in the record of the game's
        # page 0, and the scan shows no patch that the build did not apply.
        support.assert_passes(self, self.restored)
        scan, header = self.restored.read("scan.txt"), self.restored.header
        self.assertIn("page0:38CD A4 6F > 2E nn  stub's selection of the ROM in page 0\n", scan)
        self.assertEqual(scan.count(" > "), 1)
        (record, offset), = header.places
        self.assertEqual(offset, 0x38CE)
        self.assertEqual(header.records[record][2], 0)
        # With the value, the stub reaches T0 at the main game's load: the
        # tape position moves, as the test above checks.
        self.assertGreater(self.values["tapion"], 0, self.values)


def test_game(name):
    """A test game of tests/<name>.asm, as make test assembles it: its code
    and its symbols."""
    path = os.path.join(support.ROOT, "out", name + ".bin")
    if not os.path.isfile(path):
        raise support.SetupError(f"out/{name}.bin is missing: make test assembles it")
    with open(path, "rb") as f:
        return bytearray(f.read()), support.symbols(name)


def write_tape(name, data):
    """Writes a tape of the test's own in the module's tapes folder, and
    returns the folder."""
    tapes = os.path.join(WORK, "tapes")
    os.makedirs(tapes, exist_ok=True)
    with open(os.path.join(tapes, name), "wb") as f:
        f.write(data)
    return tapes


class BorrowedBySlot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # tests/borrow.asm as a binary file on tape, then a block of the
        # bytes 0 to 255 (FORMATS.md, CAS data).
        code, symbols = test_game("borrow")
        data = support.binary_tape("BORROW", bytes(code), symbols["start"], bytes(range(256)))
        tapes = write_tape("BORROW.CAS", data)
        # The patch selects slot 2 in page 0, DOS's mapper on the PHC-28S
        # with the Carnivore2, in place of the ROM.
        rom = symbols["rom"] - 0xC000
        text = (f"cas BORROW.CAS\nsha1 {hashlib.sha1(data).hexdigest()}\nservice t0\n"
                f"patch page3:{rom:04X} F6 00 > F6 02\n")
        cls.restored, cls.values = restore_and_play(
            "t0-borrow", text, [], 90, {"passed": symbols["passed"], "failed": symbols["failed"]}, True, tapes)

    def test_tapin_borrows_page_2_outside_the_mapper(self):
        support.assert_passes(self, self.restored)
        self.assertEqual(self.restored.header["H_BORROW"], 2)
        self.assertGreaterEqual(self.values["tapin"], 256, self.values)
        self.assertGreater(self.values["passed"], 0, self.values)
        self.assertEqual(self.values["failed"], 0, self.values)


# The contracts of the tape service's entries (INTERNALS.md, Tape service), from
# the BIOS's code: what each routine returns, and what it keeps. Each case is
# the routine, the opcode that sets the interrupts at the call, AF at the call,
# and what must hold after it: the carry flag, the interrupts, on, off or as
# at the call, the registers that must be as at the call, and for TAPIN the
# tape's block and byte in A, and B. tests/contract.asm calls the entries with BC =
# 1122h, DE = 3344h and HL = 5566h.
DI, EI = 0xF3, 0xFB
ENTRIES = ("tapion", "tapin", "tapiof", "tapoon", "tapout", "tapoof", "stmotr")
CONTRACT = [
    # TAPION disables interrupts, and carry is clear without CTRL+STOP.
    ("tapion", EI, 0x5A01, {"carry": 0, "iff": 0}),
    # TAPIN leaves B = 0, as the BIOS's does: Gauntlet's level loader adds BC to
    # its sum after LD C,A.
    *[("tapin", DI, 0x5A01, {"carry": 0, "iff": 0, "byte": (0, n), "b": 0}) for n in range(4)],
    # TAPIOF and TAPOOF keep every register and flag, and enable interrupts.
    ("tapiof", DI, 0x5AC5, {"iff": 1, "keeps": "af bc de hl"}),
    ("tapiof", EI, 0xA500, {"iff": 1, "keeps": "af bc de hl"}),
    # STMOTR changes only AF, whatever A asks: stop, start or the other state.
    ("stmotr", EI, 0x0001, {"iff": 1, "keeps": "bc de hl"}),
    ("stmotr", DI, 0x0100, {"iff": 0, "keeps": "bc de hl"}),
    ("stmotr", EI, 0xFF00, {"iff": 1, "keeps": "bc de hl"}),
    ("stmotr", DI, 0x0000, {"iff": 0, "keeps": "bc de hl"}),
    # The tape cannot be written: TAPOON and TAPOUT return carry, as the
    # BIOS's do for CTRL+STOP. TAPOON has disabled interrupts by then, and
    # TAPOUT leaves them as they are. Neither changes DE.
    ("tapoon", EI, 0x5A00, {"carry": 1, "iff": 0, "keeps": "de"}),
    ("tapout", EI, 0x5A00, {"carry": 1, "iff": 1, "keeps": "de"}),
    ("tapout", DI, 0x5A00, {"carry": 1, "iff": 0, "keeps": "de"}),
    ("tapoof", DI, 0x5AC5, {"iff": 1, "keeps": "af bc de hl"}),
    ("tapoof", EI, 0xA500, {"iff": 1, "keeps": "af bc de hl"}),
    # The next block, after the stops above.
    ("tapion", DI, 0x0000, {"carry": 0, "iff": 0}),
    *[("tapin", DI, 0x0000, {"carry": 0, "iff": 0, "byte": (1, n), "b": 0}) for n in range(2)],
]
CONTRACT_BLOCKS = [bytes((32 * block + n) & 0xFF for n in range(32)) for block in range(4)]

# The manual tape (INTERNALS.md, The manual tape): the cases, and the key that
# the test gives each read that waits, by its case: RETURN plays on, and
# CTRL+STOP ends the read with carry and leaves the tape stopped, where it was.
# The tape is stopped at the snapshot, and TAPIOF stops it again: after 3 bytes
# of the block, where TAPION reads on to a multiple of 8 before it looks for a
# header, and after 8 bytes, where TAPION and TAPIN look for a header at once.
MANUAL = [
    ("tapion", DI, 0x0000, {"carry": 0, "iff": 0}),
    *[("tapin", DI, 0x0000, {"carry": 0, "iff": 0, "byte": (0, n), "b": 0}) for n in range(3)],
    ("tapiof", DI, 0x0000, {"iff": 1, "keeps": "af bc de hl"}),
    ("tapion", DI, 0x0000, {"carry": 1, "iff": 0}),
    *[("tapin", DI, 0x0000, {"carry": 0, "iff": 0, "byte": (0, n), "b": 0}) for n in range(3, 8)],
    ("tapiof", DI, 0x0000, {"iff": 1, "keeps": "af bc de hl"}),
    ("tapion", DI, 0x0000, {"carry": 1, "iff": 0}),
    ("tapin", DI, 0x0000, {"carry": 1, "iff": 0}),
    ("tapin", DI, 0x0000, {"carry": 0, "iff": 0, "byte": (0, 8), "b": 0}),
]
MANUAL_KEYS = {0: "return", 5: "ctrl+stop", 6: "return", 12: "ctrl+stop", 13: "ctrl+stop", 14: "return"}

# The deepest path of the entry code's stack (src/service.asm, e_sp): a flash
# under the header's compare of TAPION. The tape ends with a header and no
# byte after it, so the fifth TAPION reads the tape's last byte as the
# header's last, and the tape goes back to its start with a flash. The TAPIN
# after it reads the first byte of the tape's first block, the type of a
# binary file.
DEEP = [
    *[("tapion", DI, 0x0000, {"carry": 0, "iff": 0}) for _ in range(5)],
    ("tapin", DI, 0x0000, {"carry": 0, "iff": 0, "a": 0xD0, "b": 0}),
]
STACK_USED = 20  # of the stack's 22 bytes
RESULT = 9  # a result's bytes: IFF, F, A, C, B, E, D, L, H


def contract_tape(contract, first, second=0, bare_header=False):
    """tests/contract.asm as a binary file on tape, with the contract's cases
    and TAPION's entry of its first and second run, then CONTRACT_BLOCKS, and
    with bare_header a header that ends the tape."""
    code, symbols = test_game("contract")
    start = symbols["start"]
    cases = b"".join(bytes([3 * ENTRIES.index(name), iff]) + struct.pack("<H", af) for name, iff, af, _ in contract)
    assert len(contract) <= symbols["CASES"]
    code[symbols["cases"] - start:symbols["cases"] - start + len(cases)] = cases
    for name, entry in (("first", first), ("second", second)):
        struct.pack_into("<H", code, symbols[name] - start, entry)
    data = support.binary_tape("CONTRA", bytes(code), start, *CONTRACT_BLOCKS)
    return data + bytes(-len(data) % 8) + (CAS_HEADER if bare_header else b"")


def contract_script(name, armed=""):
    """The Tcl that follows a contract game until it has called every case,
    and the files of its results: the game's results, the cases whose read
    waited, and the entry code's stack, which the Tcl fills with A5h first.
    The Tcl procedure start begins the watch, and armed is Tcl that it runs
    first. Each read that waits gets its case's key of MANUAL_KEYS, once, and
    the keys go up when the next case starts."""
    symbols = support.symbols("contract")
    files = {kind: os.path.join(WORK, f"{name}-{kind}") for kind in ("results.bin", "waits.txt", "stack.bin")}
    for path in files.values():
        if os.path.exists(path):
            os.remove(path)
    # The stack, from after the scratch bytes to E_STACK, at the page of the
    # part's assembly.
    stack_at = sym("e_a8") + 1
    stack_size = sym("E_STACK") - stack_at
    code = f"[debug read {{MSX Memory Mapper I/O}} 0] == [debug read memory {sym('E_CODE')}]"
    # CTRL is row 6's bit 1, STOP row 7's bit 4 and RETURN row 7's bit 7.
    keys = {"return": "keymatrixdown 7 0x80; later 0.3 {keymatrixup 7 0x80}",
            "ctrl+stop": "keymatrixdown 6 0x02; keymatrixdown 7 0x10"}
    script = f"""
proc poll {{}} {{
    if {{[debug read memory {symbols["done"]}] == 1}} {{
        set f [open {msx.tcl_word(files["results.bin"])} wb]
        puts -nonewline $f [debug read_block memory {symbols["results"]} {2 * RESULT * symbols["CASES"]}]
        close $f
        set f [open {msx.tcl_word(files["waits.txt"])} w]
        puts $f $::waited
        close $f
        set f [open {msx.tcl_word(files["stack.bin"])} wb]
        puts -nonewline $f [debug read_block memory {stack_at} {stack_size}]
        close $f
        stop
    }}
    later 2 poll
}}
set ::waited {{}}
set ::case -1
array set ::keys {{{" ".join(f"{case} {{{keys[key]}}}" for case, key in MANUAL_KEYS.items())}}}
proc start {{}} {{
    {armed}
    for {{set a 0}} {{$a < {stack_size}}} {{incr a}} {{ debug write memory [expr {{{stack_at} + $a}}] 0xA5 }}
    debug set_bp {symbols["run.iff"]} {{}} {{safe {{
        incr ::case
        keymatrixup 6 0x02
        keymatrixup 7 0x10
    }}}}
    debug set_bp {sym("wait")} {{{code}}} {{safe {{
        if {{$::case ni $::waited}} {{
            lappend ::waited $::case
            if {{[info exists ::keys($::case)]}} {{ later 0.2 $::keys($::case) }}
        }}
    }}}}
    later 2 poll
    later 150 {{ error "the game did not call every case within 150 seconds" }}
}}
"""
    return script, files, stack_size


def contract_read(files, stack_size):
    """The results that contract_script's Tcl wrote: the game's results, the
    cases whose read waited, and the bytes that the calls used of the entry
    code's stack."""
    with open(files["results.bin"], "rb") as f, open(files["waits.txt"]) as g, open(files["stack.bin"], "rb") as h:
        untouched = h.read()
        return (f.read(), [int(case) for case in g.read().split()],
                stack_size - (len(untouched) - len(untouched.lstrip(b"\xA5"))))


def contract_results(restored, name):
    """Runs a restored contract game from the check's savestate at 10 seconds
    until it has called every case, and returns contract_read's values."""
    script, files, stack_size = contract_script(name)
    check = os.path.join(restored.out, "check")
    machine = msx.read_machine(msx.machine_path(MACHINE))
    msx.run([*machine.args, f"-{machine.disk}", os.path.join(check, "disk.dsk")],
            f"loadstate {msx.tcl_word(os.path.join(check, '10s'))}\n" + script + "start\n", timeout=600)
    return contract_read(files, stack_size)


def manual_results(restored, name):
    """Restores a contract game's image with /M in the restorer's command
    line, and follows the game from the restorer's switch to it. Returns
    contract_read's values, and the code segment's mode byte, C_MODE, when the
    game has called every case."""
    restorer = support.symbols("snapcas")
    mode = os.path.join(WORK, f"{name}-mode.txt")
    # The game's code is in memory once the restorer switches to its worker:
    # until then, DOS's own code runs at the game's addresses.
    armed = f"""
    set header [binary format H* {CAS_HEADER.hex()}]
    for {{set a 0}} {{$a < [debug size "{MAPPER_RAM}"]}} {{incr a 16384}} {{
        if {{[debug read_block "{MAPPER_RAM}" [expr {{$a + {sym("D_HEADER")}}}] 8] eq $header}} {{
            set f [open {msx.tcl_word(mode)} w]
            puts $f [debug read "{MAPPER_RAM}" [expr {{$a + {sym("D_MODE")}}}]]
            close $f
        }}
    }}
"""
    script, files, stack_size = contract_script(name, armed)
    script += f"debug set_bp {restorer['switch']} $::snapcas {{safe start}}\n"
    with open(os.path.join(restored.out, "CONTRACT.SNP"), "rb") as f:
        image = f.read()
    support.restorer_run(MACHINE, support.NEXTOR, os.path.join(WORK, name + "-run"), {"CONTRACT.SNP": image},
                         ["SNAPCAS CONTRACT /M"], script)
    with open(mode) as f:
        return (*contract_read(files, stack_size), int(f.read()))


def contract_failures(results, path, contract=CONTRACT):
    """What the results of the path's cases, 0 for the first set that the game
    ran and 1 for the second, break of the contract, as a list of texts."""
    failures = []
    for n, (name, iff, af, expect) in enumerate(contract):
        r = results[(path * len(contract) + n) * RESULT:][:RESULT]
        if len(r) < RESULT:
            return failures + [f"case {n} {name}: no result"]
        got = {"iff": r[0], "af": r[2] << 8 | r[1], "bc": r[4] << 8 | r[3], "de": r[6] << 8 | r[5],
               "hl": r[8] << 8 | r[7]}
        before = {"af": af, "bc": 0x1122, "de": 0x3344, "hl": 0x5566}
        said = f"case {n} {name} with AF {af:04X} and interrupts {'on' if iff == EI else 'off'}"
        if "carry" in expect and got["af"] & 1 != expect["carry"]:
            failures.append(f"{said}: carry {got['af'] & 1}")
        if got["iff"] != expect["iff"]:
            failures.append(f"{said}: interrupts {'on' if got['iff'] else 'off'} after it")
        for reg in expect.get("keeps", "").split():
            if got[reg] != before[reg]:
                failures.append(f"{said}: {reg.upper()} {got[reg]:04X}")
        if "b" in expect and got["bc"] >> 8 != expect["b"]:
            failures.append(f"{said}: B {got['bc'] >> 8:02X}")
        byte = expect.get("a")
        if "byte" in expect:
            block, at = expect["byte"]
            byte = CONTRACT_BLOCKS[2 * path + block][at]
        if byte is not None and got["af"] >> 8 != byte:
            failures.append(f"{said}: A {got['af'] >> 8:02X}, the tape has {byte:02X}")
    return failures


class Contracts(unittest.TestCase):
    """Each entry of the tape service returns what the BIOS's routine does and
    keeps what it keeps: through T0's jump table and through the entries in
    page 3, and in the mode without a part in page 3."""

    @classmethod
    def setUpClass(cls):
        games = {}
        for name, cas, text, data in (
                ("contract", "CONTRACT.CAS", "", contract_tape(CONTRACT, T0_TABLE, PART)),
                ("contract-t0", "CONTRAT0.CAS", "service t0\n", contract_tape(CONTRACT, T0_TABLE)),
                ("contract-manual", "CONTRAMA.CAS", "", contract_tape(MANUAL, T0_TABLE)),
                ("contract-deep", "CONTRADE.CAS", "", contract_tape(DEEP, PART, bare_header=True))):
            tapes = write_tape(cas, data)
            games[name] = f"cas {cas}\n" + text

        def run(name):
            restored = support.restore(game(name, games[name]), MACHINE, tapes)
            if restored.step or restored.status:
                return restored, b"", [], 0
            if name == "contract-manual":
                return (restored, *manual_results(restored, name))
            return (restored, *contract_results(restored, name))
        with concurrent.futures.ThreadPoolExecutor(len(games)) as pool:
            cls.runs = dict(zip(games, pool.map(run, games)))

    def test_the_game_calls_the_entries_that_the_scan_did_not_patch(self):
        for name, (restored, *_) in self.runs.items():
            with self.subTest(name=name):
                self.assertNotIn(" > ", restored.read("scan.txt"))

    def test_through_t0s_jump_table(self):
        restored, results, _, _ = self.runs["contract"]
        support.assert_passes(self, restored)
        self.assertEqual(contract_failures(results, 0), [])

    def test_through_the_entries_in_page_3(self):
        restored, results, _, _ = self.runs["contract"]
        # The part is at FCE1h, where the game calls it, and T0 is not the
        # only place of the service.
        header = restored.header
        self.assertEqual((header["H_FLAGS"] & header.service["FLAG_T0"], header["H_P3"]), (0, PART >> 8))
        self.assertEqual(contract_failures(results, 1), [])

    def test_without_a_part_in_page_3(self):
        restored, results, _, _ = self.runs["contract-t0"]
        support.assert_passes(self, restored)
        header = restored.header
        self.assertEqual(header["H_FLAGS"] & header.service["FLAG_T0"], header.service["FLAG_T0"])
        self.assertEqual(contract_failures(results, 0), [])

    def test_ctrl_stop_ends_a_read_that_waits_on_the_stopped_manual_tape(self):
        restored, results, waited, _, mode = self.runs["contract-manual"]
        support.assert_passes(self, restored)
        # The restorer's /M made the tape the manual tape.
        self.assertEqual(mode, 1)
        self.assertEqual(contract_failures(results, 0, MANUAL), [])
        # The reads that waited: after CTRL+STOP the tape is still stopped, so
        # the next read waits too.
        self.assertEqual(waited, sorted(MANUAL_KEYS))

    def test_the_deepest_path_fits_the_entry_codes_stack(self):
        restored, results, _, used = self.runs["contract-deep"]
        support.assert_passes(self, restored)
        self.assertEqual(restored.header["H_P3"], PART >> 8)
        self.assertEqual(contract_failures(results, 0, DEEP), [])
        self.assertEqual(used, STACK_USED)


def guard_tape(loads, reads, writes):
    """tests/guard.asm as a binary file on tape, for a game that reads so many
    bytes of the tape before its wait and after it, and then writes the
    service's part of page 3 or not."""
    code, symbols = test_game("guard")
    start = symbols["start"]
    for name, value in (("loads", loads), ("reads", reads), ("writes", int(writes))):
        code[symbols[name] - start] = value
    return support.binary_tape("GUARD ", bytes(code), start)


GUARD_BLOCK = bytes(range(1, 33))
# The games of Guard, as name: the bytes that the game reads from the tape
# before its wait, those that it reads after it, whether it then writes the
# part, and the tape's side 2. The tape's next block, of 32 bytes, follows the
# game on side 1. With "block", it is side 2 instead. A game that reads it
# before its wait makes the capture turn the tape over, and the snapshot's tape
# is at its end. With "more", side 2 holds another block, which the game never
# reads.
GUARDS = {
    "guard-writes": (0, 8, True, None),
    "guard-reads": (0, 8, False, None),
    "guard-end": (32, 0, True, "block"),
    "guard-last": (0, 32, True, None),
    "guard-side1": (0, 32, True, "more"),
    "guard-side2": (0, 32, True, "block"),
    "guard-on-side2": (0, 8, True, "block"),
}


class Guard(unittest.TestCase):
    """The check's guard of the tape service's part of page 3 (INTERNALS.md,
    Check, point 2, and PLAN.md, step 13), on a game that reads the tape and
    writes the part within the check's 60 seconds."""

    @classmethod
    def setUpClass(cls):
        games = {}
        for number, (name, (loads, reads, writes, side2)) in enumerate(GUARDS.items(), 1):
            cas = f"GUARD{number}"
            side1, block = guard_tape(loads, reads, writes), support.cas_file(GUARD_BLOCK)
            if side2 != "block":
                side1 += bytes(-len(side1) % 8) + block
            if side2:
                write_tape(cas + "B.CAS", block if side2 == "block" else support.cas_file(bytes(range(33, 65))))
            games[name] = f"cas {cas}.CAS\n" + (f"side2 {cas}B.CAS\n" if side2 else "")
            tapes = write_tape(cas + ".CAS", side1)
        with concurrent.futures.ThreadPoolExecutor(len(games)) as pool:
            cls.restored = dict(zip(games, pool.map(
                lambda name: support.restore(game(name, games[name]), MACHINE, tapes), games)))

    def test_the_images_have_the_part_where_the_game_writes(self):
        for name, restored in self.restored.items():
            with self.subTest(game=name):
                self.assertIsNone(restored.step, restored)
                header = restored.header
                self.assertEqual((header["H_FLAGS"] & header.service["FLAG_T0"], header["H_P3"]), (0, PART >> 8))
                # The game calls the entries in page 3: the scan sent its calls there.
                self.assertIn("CD E1 00 > CD E1 FC  call of TAPION\n", restored.read("scan.txt"))
                self.assertEqual(restored.snapshot.state["service"], "1")

    def test_a_game_that_writes_the_part_fails_point_2(self):
        restored = self.restored["guard-writes"]
        support.assert_fails(self, restored, 2, "the game writes FCE1h, in the tape service's part of page 3, from C0")
        self.assertEqual(len(restored.lines(2)), 1)

    def test_a_write_after_the_service_has_read_the_tape_to_its_end_does_not_count(self):
        # The game writes the part as guard-writes does, and its tape is at
        # side 2's end at the snapshot: 7 Card Stud's case.
        restored = self.restored["guard-end"]
        support.assert_passes(self, restored)
        self.assertIn("side 2 inserted", restored.read("snap/log.txt"))
        side1 = len(guard_tape(*GUARDS["guard-end"][:3]))
        self.assertEqual(restored.snapshot.num("tapepos"), side1 + -side1 % 8 + 8 + len(GUARD_BLOCK))

    def test_a_write_after_the_game_has_read_the_tapes_last_byte_does_not_count(self):
        # The game reads the tape's last block after the restore, and then
        # writes the part. The automatic tape is back at its start by then, so
        # the check notes the end where the service leaves it.
        restored = self.restored["guard-last"]
        support.assert_passes(self, restored)
        self.assertLess(restored.snapshot.num("tapepos"), len(guard_tape(0, 32, True)) + 8)

    def test_a_write_after_the_last_byte_of_side_2_does_not_count(self):
        # The game's tape is at side 1's end at the snapshot. After the
        # restore the game reads side 2, which is one block, and then writes
        # the part.
        restored = self.restored["guard-side2"]
        support.assert_passes(self, restored)
        self.assertNotIn("side 2 inserted", restored.read("snap/log.txt"))

    def test_side_1s_end_of_a_tape_with_two_sides_is_not_the_tapes_end(self):
        # The same game, whose tape has a side 2 that it has not read.
        support.assert_fails(self, self.restored["guard-side1"], 2,
                             "the game writes FCE1h, in the tape service's part of page 3, from C0")

    def test_a_write_before_the_last_byte_of_side_2_fails_point_2(self):
        # The game reads 8 bytes of side 2's block of 32, and then writes.
        support.assert_fails(self, self.restored["guard-on-side2"], 2,
                             "the game writes FCE1h, in the tape service's part of page 3, from C0")

    def test_the_services_own_writes_during_the_games_tape_calls_do_not_count(self):
        support.assert_passes(self, self.restored["guard-reads"])


class TapeEnd(unittest.TestCase):
    """7 Card Stud, as shipped (PLAN.md, step 13). Its snapshot is in the
    middle of its load. The restored game loads the rest of its tape through
    the tape service, and then keeps its own values in the service's part of
    page 3. Those writes do not count for point 2, because the service has
    read the tape to its end."""

    @classmethod
    def setUpClass(cls):
        support.tape("7-CARD.CAS")
        cls.restored = support.restore(support.shipped_copy(os.path.join(GAMES_DIR, "tape-end-7card"), "7-CARD"),
                                       MACHINE)
        cls.values, cls.part = {}, b""
        if cls.restored.step or cls.restored.status:
            return
        # At the check's last savestate, 60 seconds after the restore: the
        # service's tape position, the tape's end and its start, from the code
        # segment, and the part's bytes in the game's memory.
        check = os.path.join(cls.restored.out, "check")
        out = os.path.join(WORK, "tape-end.txt")
        if os.path.exists(out):
            os.remove(out)
        fields = " ".join(f"{name} {sym('D_' + name.upper())}" for name in ("pos", "total", "start"))
        machine = msx.read_machine(msx.machine_path(MACHINE))
        msx.run([*machine.args, f"-{machine.disk}", os.path.join(check, "disk.dsk")], f"""
loadstate {msx.tcl_word(os.path.join(check, "60s"))}
set f [open {msx.tcl_word(out)} w]
for {{set a 0}} {{$a < [debug size "{MAPPER_RAM}"]}} {{incr a 16384}} {{
    if {{[debug read_block "{MAPPER_RAM}" [expr {{$a + {sym("D_HEADER")}}}] 8] eq [binary format H* {CAS_HEADER.hex()}]}} {{
        foreach {{name offset}} {{{fields}}} {{
            binary scan [debug read_block "{MAPPER_RAM}" [expr {{$a + $offset}}] 3] cu3 b
            puts $f "$name [expr {{[lindex $b 0] | ([lindex $b 1] << 8) | ([lindex $b 2] << 16)}}]"
        }}
    }}
}}
binary scan [debug read_block memory {PART} {sym("e_sp") - PART}] H* part
puts $f "part $part"
close $f
stop
""", timeout=120)
        with open(out) as f:
            cls.values = dict(line.split() for line in f)
        cls.part = bytes.fromhex(cls.values.pop("part"))

    def test_the_image_passes_the_check_with_the_part_in_page_3(self):
        support.assert_passes(self, self.restored)
        header = self.restored.header
        self.assertEqual((header["H_FLAGS"] & header.service["FLAG_T0"], header["H_P3"]), (0, PART >> 8))

    def test_the_restored_game_reads_its_tape_to_its_end(self):
        tape = len(support.read_tape("7-CARD.CAS"))
        total = tape + -tape % 8
        # The snapshot is at a TAPION call in the middle of the tape.
        self.assertEqual(self.restored.snapshot.state["service"], "1")
        self.assertLess(self.restored.snapshot.num("tapepos"), total // 2)
        # After 60 seconds the position is at the tape's last byte, with only
        # the file's padding left, and the tape has not gone back to its start.
        start, pos, end = (int(self.values[name]) for name in ("start", "pos", "total"))
        self.assertEqual((end - start, end - pos), (total, total - tape))
        self.assertLessEqual(end - pos, 7)

    def test_the_game_writes_the_part(self):
        support.assert_passes(self, self.restored)
        # The part's code after E_STOP is the service's until the game writes
        # over it.
        code = sym("E_STOP") + 1 - PART
        built = support.service().parts["page3"][:len(self.part)]
        self.assertEqual(self.part[:7 * 3], built[:7 * 3])
        self.assertNotEqual(self.part[code:], built[code:])


# The game files that Parts builds, as name: the shipped game file's folder
# below games/ and the lines added to its game.txt.
PARTS = {
    # Athletic Land's page 3 also has room for the part at F9E1h.
    "s17-at": ("ENGESOFT/ATHLETIC", ["service at F9E1"]),
    # Chase H.Q.'s page 3 has no room for the part, so build.py takes the mode
    # without a part in page 3 itself.
    "s17-romkeep": ("CHASE-H", ["rom keep"]),
}


def build_part(name):
    """Captures, builds and checks a copy of a shipped game file with lines
    added to its game.txt."""
    shipped, extra = PARTS[name]
    folder = support.shipped_copy(os.path.join(GAMES_DIR, name), shipped)
    with open(os.path.join(folder, "game.txt"), "a") as f:
        f.writelines(line + "\n" for line in extra)
    return support.restore(folder, MACHINE)


class Parts(unittest.TestCase):
    """The place of the service's part of page 3 by the game file's lines
    (PLAN.md, step 17)."""

    @classmethod
    def setUpClass(cls):
        for name in ("ENGESO06.CAS", "CHASE-H.CAS", "CHASEB.CAS"):
            support.tape(name)
        with concurrent.futures.ThreadPoolExecutor(len(PARTS)) as pool:
            cls.restored = dict(zip(PARTS, pool.map(build_part, PARTS)))

    def test_service_at_places_the_part_there(self):
        restored = self.restored["s17-at"]
        support.assert_passes(self, restored)
        self.assertIn(f"moved {0xF9E1} ", restored.read("build.txt"))
        self.assertEqual(restored.header["H_P3"], 0xF9)

    def test_rom_keep_stops_the_build_without_room_in_page_3(self):
        restored = self.restored["s17-romkeep"]
        self.assertEqual((restored.step, restored.status), ("build.py", 1), restored)
        self.assertIn("rom keep needs it", restored.error)


if __name__ == "__main__":
    unittest.main()
