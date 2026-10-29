"""Step 5 (docs/PLAN.md): the tape service, for Computad and Gauntlet on the
PHC-28S.

Each game is captured, built and checked, then played from the check's
savestate at 10 seconds with the inputs that reach its next load. The play
reads the tape position in the code segment, which it finds in DOS's mapper by
the CAS header at offset 12h.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msx  # noqa: E402
import test_step4  # noqa: E402

CAS_DIR = test_step4.CAS_DIR
MACHINE = "advanced/phc28s"
MAPPER_RAM = "Carnivore2 ram"  # the openMSX debuggable of DOS's mapper on it
WORK = os.path.join(ROOT, "out", "test", "step5")

GAMES = {
    "computad": "cas COMPUTAD.CAS\n",
    "gauntlet": """cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
# The loader selects the ROM in page 0 from a copy of the slot register.
patch page3:215F CD E1 00 > CD E1 FC
patch page3:21AB CD E4 00 > CD E4 FC
# The main game, loaded at 4400h, selects the ROM in page 0 for its level
# loads too. Its block ends with a 16-bit sum of its bytes, so the 1F8h that
# the two patches add goes into the sum.
patch side1:AE88 CD E1 00 > CD E1 FC
patch side1:AED4 CD E4 00 > CD E4 FC
patch side1:E2F3 45 F0 > 3D F2
# Its RAM search adds page 0's RAM slot to the slot register's page 0 bits.
rom keep
""",
}

# game: (inputs, 4 seconds apart, seconds of play, breakpoints to count). An
# input is a key name, a digit, or fire, the joystick's button, which the play gives by
# clearing bit 4 of A after the game reads PSG register 14 for port 1. The
# game reads it in the BIOS's RDPSG, at 1112h, or in its own code.
PLAYS = {
    # The instructions, the menu's theme 1 and RETURN, then the data tape.
    "computad": (["space", "space", "1", "return", "space"], 50, {}),
    # The intro, the players and the character, then the side 2 prompt.
    # 958Bh jumps to the level that the level loader read.
    "gauntlet": (["space"] * 4 + ["fire"] * 15 + ["space"] * 8, 180,
                 {"level": 0x958B, "joy": 0xB3FD}),
}
JOYSTICK_READS = (0x1112, 0xB3FD)


def play_script(game, out):
    inputs, seconds, counts = PLAYS[game]
    presses = []
    for n, name in enumerate(inputs):
        if name == "fire":
            action = "set ::fire 1; after time 0.3 {set ::fire 0}"
        elif name.isdigit():
            # The digits are not key names, because their place depends on the
            # layout. 1 is row 0, bit 1, on this machine.
            action = f"keymatrixdown 0 {1 << int(name)}; after time 0.5 [list keymatrixup 0 {1 << int(name)}]"
        else:
            action = msx.press(name, 0.5)
        presses.append(f"after time {2 + 4 * n} {{{action}}}")
    state = os.path.join(ROOT, "out", MACHINE, game, "check", "10s")
    bps = "\n".join(f'set ::n({name}) 0\ndebug set_bp {address} {{}} {{incr ::n({name})}}'
                    for name, address in {"tapion": 0x1A63, "tapin": 0x1ABC, **counts}.items())
    joy = "\n".join(f"debug set_bp {a} {{}} fire" for a in JOYSTICK_READS)
    return f"""
loadstate {msx.tcl_word(state)}
after time {seconds + 60} exit
proc base {{}} {{
    for {{set a 0}} {{$a < [debug size "{MAPPER_RAM}"]}} {{incr a 16384}} {{
        if {{[debug read_block "{MAPPER_RAM}" [expr {{$a + 0x12}}] 8] eq [binary format H* 1FA6DEBACC137D74]}} {{ return $a }}
    }}
    error "no code segment"
}}
proc word3 {{offset}} {{
    binary scan [debug read_block "{MAPPER_RAM}" [expr {{$::base + $offset}}] 3] cu3 b
    expr {{[lindex $b 0] | ([lindex $b 1] << 8) | ([lindex $b 2] << 16)}}
}}
set ::base [base]
set ::pos0 [word3 6]
set ::fire 0
proc fire {{}} {{
    if {{$::fire && ([debug read {{PSG regs}} 15] & 0x40) == 0}} {{ reg AF [expr {{[reg AF] & ~0x1000}}] }}
}}
{bps}
{joy}
{chr(10).join(presses)}
after time {seconds} {{
    set f [open {msx.tcl_word(out)} w]
    puts $f "pos0 $::pos0"
    foreach {{name offset}} {{pos 6 s1end 9 total 12 start 15}} {{ puts $f "$name [word3 $offset]" }}
    foreach name [array names ::n] {{ puts $f "$name $::n($name)" }}
    close $f
    exit
}}
"""


def play(game):
    """Plays a restored game and returns its tape values and counts."""
    out = os.path.join(WORK, f"{game}-play.txt")
    if os.path.exists(out):
        os.remove(out)
    machine = msx.read_machine(os.path.join(ROOT, "machines", MACHINE + ".txt"))
    disk = os.path.join(ROOT, "out", MACHINE, game, "check", "disk.dsk")
    msx.run([*machine.args, f"-{machine.disk}", disk], play_script(game, out), timeout=600)
    if not os.path.exists(out):
        return {}
    with open(out) as f:
        return {k: int(v) for k, v in (line.split() for line in f)}


def run(game):
    """Captures, builds, checks and plays a game, and returns (the check's
    report or the failed step's error, state.txt, the play's values)."""
    folder = os.path.join(WORK, "games", game)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(GAMES[game])
    for step, args in (("capture.py", ["--cas", CAS_DIR]), ("build.py", ["--cas", CAS_DIR])):
        result = test_step4.tool(step, folder, MACHINE, *args)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}", {}, {}
    report = test_step4.tool("check.py", folder, MACHINE, "--dos", test_step4.NEXTOR).stdout
    with open(os.path.join(ROOT, "out", MACHINE, game, "snap", "state.txt")) as f:
        state = dict(line.split(" ", 1) for line in f.read().splitlines())
    return report, state, play(game) if report.startswith("point 1: pass") else {}


@unittest.skipUnless(os.path.isdir(CAS_DIR), "CAS_DIR names no folder of CAS files")
class Step5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        cls.results = {game: run(game) for game in GAMES}

    def test_check_point_1_passes_with_the_service(self):
        for game, (report, state, _) in self.results.items():
            with self.subTest(game=game):
                self.assertTrue(report.startswith("point 1: pass"), report)
                self.assertEqual(state["service"], "1")

    def test_computad_loads_theme_1(self):
        values = self.results["computad"][2]
        # Theme 1's two blocks: a 16-byte name and 256 bytes, which end at
        # offset 7,560 of the CAS file.
        self.assertEqual(values.get("tapion"), 2, values)
        self.assertEqual(values.get("tapin"), 272, values)
        self.assertEqual(values["pos"], values["start"] + 7560)

    def test_gauntlet_loads_its_main_game_then_a_level_from_side_2(self):
        values = self.results["gauntlet"][2]
        self.assertGreater(values.get("joy", 0), 0, values)
        # Side 1 ends at 58,101 bytes, padded to 58,104, and side 2 adds
        # 95,157.
        self.assertEqual(values["s1end"], values["start"] + 58104)
        self.assertEqual(values["total"], values["s1end"] + 95157)
        self.assertGreater(values["pos"], values["s1end"], values)
        self.assertLess(values["pos"], values["total"], values)
        self.assertEqual(values.get("level"), 1, values)


if __name__ == "__main__":
    unittest.main()
