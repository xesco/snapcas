"""Step 9 (docs/PLAN.md): the shipped game files, and a game's file for one
machine beside its game.txt (DESIGN.md, Game file and Shipped files)."""
import concurrent.futures
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402

GAMES = os.path.join(ROOT, "games")
WORK = os.path.join(ROOT, "out", "test", "step9")

# The shipped machines and the DOS that each boots (PLAN.md, Test setup).
SHIPPED = {machine: test_step4.MACHINES[machine][0]
           for machine in ("advanced/phc28s", "basic/vg8020", "basic/nms8250", "advanced/hbf700p")}
SHIPPED.update({"basic/msx2ide": test_step4.NEXTOR, "advanced/mfrsd": test_step4.NEXTOR})
# A single-load game that fits each of them, the NMS 8250's 128 KB included.
SINGLE = "CALDERO.CAS"


class MachineFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write("cas GAME.CAS\nsnapshot at 10\n")
        with open(os.path.join(self.folder, "advanced-phc28s.txt"), "w") as f:
            f.write("# Only for the PHC-28S.\ncapture advanced/phc28s-nodisk\nsnapshot at 20\n")

    def test_the_machine_file_adds_its_lines_for_its_machine(self):
        game = gamefile.read_game(self.folder, "advanced/phc28s")
        self.assertEqual(game.capture, "advanced/phc28s-nodisk")

    def test_the_machine_file_gives_a_value_that_both_give(self):
        self.assertEqual(gamefile.read_game(self.folder, "advanced/phc28s").snapshot_at, 20)

    def test_other_machines_read_only_game_txt(self):
        game = gamefile.read_game(self.folder, "basic/vg8020")
        self.assertIsNone(game.capture)
        self.assertEqual(game.snapshot_at, 10)


@unittest.skipUnless(os.path.isdir(GAMES), "no games/ folder")
class ShippedGameFiles(unittest.TestCase):
    def test_every_game_file_reads_on_each_machine(self):
        for name in sorted(os.listdir(GAMES)):
            for machine in ("advanced/phc28s", "basic/vg8020"):
                with self.subTest(game=name, machine=machine):
                    game = gamefile.read_game(os.path.join(GAMES, name), machine)
                    self.assertTrue(game.sha1)

    def test_machine_files_name_a_machine_file(self):
        for name in sorted(os.listdir(GAMES)):
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        machine = file[:-4].replace("-", "/", 1)
                        self.assertTrue(os.path.isfile(os.path.join(ROOT, "machines", machine + ".txt")))


def single_load(machine):
    """Captures, builds and checks SINGLE on a machine, and returns the check's
    report or the failed step's error."""
    folder = os.path.join(WORK, "games", "single-" + machine.replace("/", "-"))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {SINGLE}\n")
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--cas", test_step4.CAS_DIR)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, machine, "--dos", SHIPPED[machine]).stdout


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class Machines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.reports = dict(zip(SHIPPED, pool.map(single_load, SHIPPED)))

    def test_a_single_load_game_restores_on_each_shipped_machine(self):
        for machine, report in self.reports.items():
            with self.subTest(machine=machine):
                self.assertTrue(report.startswith("point 1: pass"), report)


if __name__ == "__main__":
    unittest.main()
