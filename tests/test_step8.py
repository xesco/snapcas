"""Step 8 (docs/PLAN.md): the tape speed and its sound, /T1200 and /T2400
(INTERNALS.md, Tape speed and sound), on Gauntlet's main game's load."""
import concurrent.futures
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import msx  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step5  # noqa: E402

MACHINE = test_step5.MACHINE
WORK = os.path.join(ROOT, "out", "test", "step8")

# option: the restorer's option, and the seconds that the play takes. At 1200
# baud the main game's 34,341 bytes take 315 seconds.
RUNS = {"fast": ("", 120), "t1200": ("/T1200", 480), "t2400": ("/T2400", 300)}
# The intro, the players and the character, which start the main game's load.
INPUTS = ["space"] * 4 + ["fire"] * 15
# A byte's 11 bits at each speed, in seconds.
BYTE = {"t1200": 11 / 1200, "t2400": 11 / 2400}


def run(name):
    """Captures, builds and checks Gauntlet with the run's option, then plays it
    to its main game's load, and returns the check's report and the play's
    values."""
    option, seconds = RUNS[name]
    folder = os.path.join(WORK, "games", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(test_step5.GAMES["gauntlet"])
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--tapes", test_step4.CAS_DIR)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}", {}
    report = test_step4.tool("check.py", folder, MACHINE, "--dos", test_step4.NEXTOR, "--options", option).stdout
    if not report.startswith("point 1: pass"):
        return report, {}
    out = os.path.join(WORK, f"{name}-play.txt")
    if os.path.exists(out):
        os.remove(out)
    machine = msx.read_machine(msx.machine_path(MACHINE))
    disk = os.path.join(folder, MACHINE, "check", "disk.dsk")
    msx.run([*machine.args, f"-{machine.disk}", disk], script(folder, seconds, out, left_out(name) if option else 0),
            timeout=1200)
    values = {}
    if os.path.exists(out):
        with open(out) as f:
            values = dict(line.split(" ", 1) for line in f.read().splitlines())
    return report, {k: float(v) for k, v in values.items()}


def left_out(name):
    """The stop bits' edges that the gap between two bytes takes, at the run's
    speed."""
    return 8 - test_step5.service_symbol({"t1200": "STOP1200", "t2400": "STOP2400"}[name])


def script(folder, seconds, out, left):
    """The play's Tcl: the presses, and the watch of TAPION, TAPIN, the code
    segment's play routine and the writes to PPI port C."""
    presses = []
    for n, key in enumerate(INPUTS):
        action = "set ::fire 1; after time 0.3 {set ::fire 0}" if key == "fire" else msx.press(key, 0.5)
        presses.append(f"after time {2 + 4 * n} {{{action}}}")
    in_code = f"[debug read {{MSX Memory Mapper I/O}} 0] == [debug read memory {test_step5.service_symbol('E_CODE')}]"
    joy = "\n".join(f"debug set_bp {a} {{}} fire" for a in test_step5.JOYSTICK_READS)
    return f"""
loadstate {msx.tcl_word(os.path.join(folder, MACHINE, "check", "10s"))}
after time {seconds + 60} exit
set ::fire 0
proc fire {{}} {{
    if {{$::fire && ([debug read {{PSG regs}} 15] & 0x40) == 0}} {{ reg AF [expr {{[reg AF] & ~0x1000}}] }}
}}
{joy}
# The time between two TAPINs of one block: no TAPION between them.
set ::last -1
set ::gaps {{}}
set ::tapins 0
# The leader: from TAPION's call to the block's first TAPIN.
set ::tapion -1
set ::leaders {{}}
debug set_bp 0x1A63 {{}} {{ set ::last -1; set ::prev -1; set ::tapion [machine_info time] }}
debug set_bp 0x1ABC {{}} {{
    incr ::tapins
    set now [machine_info time]
    if {{$::tapion >= 0}} {{ lappend ::leaders [expr {{$now - $::tapion}}]; set ::tapion -1 }}
    if {{$::last >= 0}} {{ lappend ::gaps [expr {{$now - $::last}}] }}
    set ::last $now
}}
# The keyclick bit's edges for each byte that play plays, against 2 for each 0
# bit and 4 for each 1 bit of its 11.
set ::click -1
set ::edges 0
set ::prev -1
set ::bytes 0
set ::wrong 0
set ::motor_off 0
debug set_watchpoint write_io 0xAA {{}} {{
    set bit [expr {{($::wp_last_value >> 7) & 1}}]
    if {{$::click >= 0 && $bit != $::click}} {{ incr ::edges }}
    set ::click $bit
}}
proc expected {{byte}} {{
    set ones 2
    for {{set i 0}} {{$i < 8}} {{incr i}} {{ incr ones [expr {{($byte >> $i) & 1}}] }}
    expr {{4 * $ones + 2 * (11 - $ones) - {left}}}
}}
debug set_bp {test_step5.service_symbol("play")} {{{in_code}}} {{
    if {{$::bytes == 0}} {{ set ::click0 [expr {{([debug read ioports 0xAA] >> 7) & 1}}] }}
    if {{$::prev >= 0 && $::edges != [expected $::prev]}} {{ incr ::wrong }}
    if {{[debug read ioports 0xAA] & 0x10}} {{ incr ::motor_off }}
    set ::prev [expr {{[reg AF] >> 8}}]
    set ::edges 0
    incr ::bytes
}}
{chr(10).join(presses)}
after time {seconds} {{
    set f [open {msx.tcl_word(out)} w]
    set g [lsort -real $::gaps]
    set n [llength $g]
    puts $f "tapins $::tapins"
    puts $f "leaders [llength $::leaders]"
    set i 0
    foreach t $::leaders {{ puts $f "leader$i $t"; incr i }}
    if {{$n}} {{ puts $f "median [lindex $g [expr {{$n / 2}}]]" }}
    puts $f "bytes $::bytes"
    puts $f "wrong $::wrong"
    puts $f "motor_off $::motor_off"
    puts $f "motor_end [expr {{([debug read ioports 0xAA] >> 4) & 1}}]"
    puts $f "click_end [expr {{([debug read ioports 0xAA] >> 7) & 1}}]"
    if {{[info exists ::click0]}} {{ puts $f "click0 $::click0" }}
    close $f
    exit
}}
"""


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, "GAUNTLET.CAS")), "CAS_DIR holds no GAUNTLET.CAS")
class TapeSpeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "cache", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(len(RUNS)) as pool:
            cls.results = dict(zip(RUNS, pool.map(run, RUNS)))

    def test_the_checks_pass_with_each_option(self):
        for name, (report, values) in self.results.items():
            with self.subTest(name=name):
                self.assertTrue(report.startswith("point 1: pass"), report)
                self.assertGreater(values.get("tapins", 0), 34000, values)

    def test_a_byte_takes_its_11_bits_at_the_speed(self):
        for name, byte in BYTE.items():
            with self.subTest(name=name):
                median = self.results[name][1]["median"]
                self.assertAlmostEqual(median / byte, 1, delta=0.01, msg=f"{median:.6f} s for {byte:.6f}")

    def test_the_short_leader_tone_plays_before_the_main_games_block(self):
        # The main game is one block without a file type's 10 bytes, so its
        # tone is the short one: 1.6 seconds at either speed.
        for name in BYTE:
            with self.subTest(name=name):
                values = self.results[name][1]
                self.assertEqual(values["leaders"], 1, values)
                self.assertAlmostEqual(values["leader0"] / 1.6, 1, delta=0.1, msg=values)
        self.assertLess(self.results["fast"][1]["leader0"], 0.1)

    def test_the_fast_load_stays_fast(self):
        self.assertLess(self.results["fast"][1]["median"], 0.001, self.results["fast"][1])
        self.assertEqual(self.results["fast"][1]["bytes"], 0)

    def test_each_bit_toggles_the_keyclick_bit_2_or_4_times_but_the_gaps_edges(self):
        for name in BYTE:
            with self.subTest(name=name):
                values = self.results[name][1]
                self.assertGreater(values["bytes"], 34000, values)
                self.assertEqual(values["wrong"], 0, values)
                self.assertEqual(values["click_end"], values["click0"], values)

    def test_the_motor_runs_during_the_load_and_stops_after_it(self):
        for name in BYTE:
            with self.subTest(name=name):
                values = self.results[name][1]
                self.assertEqual(values["motor_off"], 0, values)
                self.assertEqual(values["motor_end"], 1, values)


if __name__ == "__main__":
    unittest.main()
