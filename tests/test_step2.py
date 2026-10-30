"""Step 2 (docs/PLAN.md): the capture of single-load games.

The CAS files come from the folder that CAS_DIR names; without it, the tests
are skipped.
"""
import concurrent.futures
import filecmp
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAS_DIR = os.environ.get("CAS_DIR", "")
WORK = os.path.join(ROOT, "out", "test", "step2")

# game: (CAS file, machine)
GAMES = {
    "freddy": ("FREDDY.CAS", "advanced/phc28s"),
    "fernando": ("FERNANDO.CAS", "advanced/phc28s"),
    "moonrider": ("022-MOON.CAS", "advanced/phc28s"),
    "caldero": ("CALDERO.CAS", "advanced/phc28s"),
    "abadia": ("ABADIA.CAS", "test/nms8250-128k"),
}

# The names of state.txt (DESIGN.md, Snapshot files).
NAMES = ([r for r in "af bc de hl af2 bc2 de2 hl2 ix iy sp pc i im iff a8 ppic".split()]
         + [f"sub{n}" for n in range(4)] + ["fc", "fd", "fe", "ff"]
         + [f"psg{n}" for n in range(16)] + ["psgsel", "vramptr", "vramwrite",
                                             "tapepos", "service"])
MSX1_VDP = [f"vdp{n}" for n in range(8)]
V9938 = ([f"vdp{n}" for n in range(24)] + [f"vdp{n}" for n in range(32, 46)]
         + [f"pal{n}" for n in range(16)])

# The PHC-28S's RAM: its own page 3 in slot 0, the RAM cartridge in slot 1,
# and the Carnivore2's mapper in subslot 2-2.
PHC_RAM = {"0-x-3"} | {f"1-x-{p}" for p in range(4)} | {f"2-2-{p}" for p in range(4)}


def capture(game, folder=None):
    cas, machine = GAMES[game]
    games = os.path.join(WORK, "games", game)
    os.makedirs(games, exist_ok=True)
    with open(os.path.join(games, "game.txt"), "w") as f:
        f.write(f"cas {cas}\n")
        if game == "abadia":
            # La Abadia del Crimen leaves its last 16 KB unread during the load.
            f.write("service no\n")
    result = subprocess.run(
        [sys.executable, "-I", os.path.join(ROOT, "tools", "capture.py"), games, machine,
         "--cas", CAS_DIR], capture_output=True, text=True)
    snap = os.path.join(ROOT, "out", machine, game, "snap")
    if folder and result.returncode == 0:
        shutil.rmtree(folder, ignore_errors=True)
        shutil.copytree(snap, folder)
    return result, snap


def read_state(snap):
    with open(os.path.join(snap, "state.txt")) as f:
        return dict(line.split(" ", 1) for line in f.read().splitlines())


def read_log(snap):
    with open(os.path.join(snap, "log.txt")) as f:
        return f.read()


@unittest.skipUnless(os.path.isdir(CAS_DIR), "CAS_DIR names no folder of CAS files")
class Step2(unittest.TestCase):
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
                self.assertEqual(set(state), expected)

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


if __name__ == "__main__":
    unittest.main()
