"""Step 18 (docs/PLAN.md): the check's point 4, which fails a game that stops at
a BASIC error after the restore (INTERNALS.md, Check, point 4)."""
import concurrent.futures
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step9  # noqa: E402

COLLECTION = test_step4.CAS_DIR
MACHINE = "phc28s-ram64k-carnivore2"
WORK = os.path.join(ROOT, "out", "test", "step18")

# The game files that BasicErrors checks: Field Master without its patch line,
# which stops at "Overflow in 130", and Aritmo, from Turbo Pack A, which runs its
# BASIC program without an error.
GAMES = ("FIELD-MA", "001-ARIO")


def check(game):
    """Captures, builds and checks a copy of a shipped game file in WORK, without
    its patch lines, and returns the check's report or the failed step's error."""
    folder = os.path.join(WORK, "games", game)
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "games", game), folder)
    path = os.path.join(folder, "game.txt")
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if not line.startswith("patch ")]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--tapes", COLLECTION)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, MACHINE, "--dos", test_step9.SHIPPED[MACHINE]).stdout


@unittest.skipUnless(all(os.path.isfile(os.path.join(COLLECTION, g + ".CAS")) for g in GAMES),
                     "CAS_DIR lacks the tapes of BasicErrors")
class BasicErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "cache", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.reports = dict(zip(GAMES, pool.map(check, GAMES)))

    def test_a_stop_at_a_basic_error_fails_point_4(self):
        report = self.reports["FIELD-MA"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 4: fail", report)
        self.assertIn("the screen shows Overflow in 130", report)

    def test_a_basic_program_without_an_error_passes_point_4(self):
        report = self.reports["001-ARIO"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 4: pass", report)


if __name__ == "__main__":
    unittest.main()
