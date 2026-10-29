"""Step 4 (docs/PLAN.md): the restorer and the check, for each single-load file
of the corpus on each test machine.

Check point 1 must pass, except where the restorer stops because DOS leaves
too few free mapper segments. Then the report holds the restorer's message.
"""
import concurrent.futures
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step2  # noqa: E402

CAS_DIR = test_step2.CAS_DIR
NEXTOR = os.environ.get("NEXTOR_DIR", os.path.join(ROOT, "out", "dl", "nextor"))
DOS_DIR = os.environ.get("DOS_DIR", os.path.join(ROOT, "dos"))
WORK = os.path.join(ROOT, "out", "test", "step4")

GAMES = {
    "freddy": "cas FREDDY.CAS\n",
    "fernando": "cas FERNANDO.CAS\n",
    "moonrider": "cas 022-MOON.CAS\n",
    "caldero": "cas CALDERO.CAS\n",
    "abadia": "cas ABADIA.CAS\nservice no\n",
    # On the PHC-28S, La Abadia's loader takes the RAM cartridge in slot 1 for
    # an expanded slot and crashes, so the game loads without it.
    "abadia-phc": "cas ABADIA.CAS\nservice no\ncapture advanced/phc28s-noslot1\n",
}

# machine: (DOS folder, games that pass, games that the restorer stops for
# too few free segments). A game left out of both fails on that machine in
# openMSX itself (docs/PLAN.md, the corpus).
MACHINES = {
    "advanced/phc28s": (NEXTOR, {"freddy", "fernando", "moonrider", "caldero", "abadia-phc"}, set()),
    "basic/vg8020": (NEXTOR, {"freddy", "fernando", "moonrider", "caldero"}, set()),
    "basic/nms8250": (os.path.join(DOS_DIR, "msxdos2"), {"caldero"},
                      {"freddy", "fernando", "moonrider", "abadia"}),
    "advanced/hbf700p": (os.path.join(DOS_DIR, "msxdos2"), {"moonrider", "caldero", "abadia"}, set()),
    "test/nms8250-dos1": (os.path.join(DOS_DIR, "msxdos1"),
                          {"freddy", "fernando", "moonrider", "caldero", "abadia"}, set()),
}


def tool(name, *args):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", name), *args],
                          capture_output=True, text=True)


def restore(game, machine):
    """Captures, builds and checks a game on a machine, and returns the
    check's report, or the error of the step that failed."""
    folder = os.path.join(WORK, "games", game)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(GAMES[game])
    for step, args in (("capture.py", ["--cas", CAS_DIR]), ("build.py", ["--cas", CAS_DIR])):
        result = tool(step, folder, machine, *args)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return tool("check.py", folder, machine, "--dos", MACHINES[machine][0]).stdout


@unittest.skipUnless(os.path.isdir(CAS_DIR), "CAS_DIR names no folder of CAS files")
@unittest.skipUnless(os.path.isdir(os.path.join(DOS_DIR, "msxdos2")), "DOS_DIR holds no msxdos2 folder")
class Step4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jobs = [(g, m) for m, (_, passes, short) in MACHINES.items() for g in passes | short]
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.reports = dict(zip(jobs, pool.map(lambda job: restore(*job), jobs)))

    def test_check_point_1_passes(self):
        for machine, (_, passes, _) in MACHINES.items():
            for game in sorted(passes):
                with self.subTest(machine=machine, game=game):
                    self.assertTrue(self.reports[game, machine].startswith("point 1: pass"),
                                    self.reports[game, machine])

    def test_the_restorer_names_the_segments_it_lacks(self):
        for machine, (_, _, short) in MACHINES.items():
            for game in sorted(short):
                with self.subTest(machine=machine, game=game):
                    # The screen wraps the message at any column, so the
                    # comparison leaves out all spaces.
                    report = re.sub(r"\s", "", self.reports[game, machine])
                    self.assertRegex(report, r"needs\d+freemappersegments,andDOShas\d+")


if __name__ == "__main__":
    unittest.main()
