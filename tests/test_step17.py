"""Step 17 (docs/PLAN.md): one service setting for a game, and rom keep
without the mode without a part in page 3 (DESIGN.md, Game file, Without a
part in page 3)."""
import concurrent.futures
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step9  # noqa: E402

COLLECTION = os.path.join(test_step4.CAS_DIR, "collection")
WORK = os.path.join(ROOT, "out", "test", "step17")
MACHINE = "advanced/phc28s"


class ServiceLine(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def write(self, name, *lines):
        with open(os.path.join(self.folder, name), "w") as f:
            f.writelines(line + "\n" for line in lines)

    def test_a_file_holds_one_service_line(self):
        self.write("game.txt", "cas GAME.CAS", "service no", "service t0")
        with self.assertRaisesRegex(gamefile.GameFileError, r"game.txt:3: a file holds one service line"):
            gamefile.read_game(self.folder)

    def test_rom_keep_cannot_go_with_service_t0(self):
        self.write("game.txt", "cas GAME.CAS", "rom keep", "service t0")
        with self.assertRaisesRegex(gamefile.GameFileError, "rom keep needs the tape service's part"):
            gamefile.read_game(self.folder)

    def test_the_machines_service_line_replaces_game_txts(self):
        self.write("game.txt", "cas GAME.CAS", "service no")
        self.write("advanced-phc28s.txt", "service t0")
        self.assertEqual(gamefile.read_game(self.folder, "advanced/phc28s").service, "t0")
        self.assertEqual(gamefile.read_game(self.folder, "basic/vg8020").service, "no")


def build_game(name, shipped, extra):
    """Captures, builds and checks a copy of a shipped game file with extra
    lines in its game.txt, and returns its output folder and the check's
    report, or the failed step's error."""
    folder = os.path.join(WORK, "games", name)
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "games", shipped), folder)
    with open(os.path.join(folder, "game.txt"), "a") as f:
        f.writelines(line + "\n" for line in extra)
    out = gamefile.out_folder(MACHINE, folder)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--tapes", COLLECTION)
        if result.returncode != 0:
            return out, f"{step}: {result.stderr.strip()}"
    return out, test_step4.tool("check.py", folder, MACHINE, "--dos", test_step9.SHIPPED[MACHINE]).stdout


# The game files that Builds captures, as name: the shipped game file's folder
# below games/ and the lines added to its game.txt.
GAMES = {
    # Athletic Land's page 3 also has room for the part at F9E1h.
    "s17-at": ("ENGESOFT/ATHLETIC", ["service at F9E1"]),
    # Bronx's page 3 has no room for the part, so build.py takes the mode
    # without a part in page 3 itself.
    "s17-romkeep": ("BRONX", ["rom keep"]),
}


@unittest.skipUnless(all(os.path.isfile(os.path.join(COLLECTION, n)) for n in ("ENGESO06.CAS", "BRONX.CAS")),
                     "CAS_DIR lacks the tapes of Builds")
class Builds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.results = dict(zip(GAMES, pool.map(lambda n: build_game(n, *GAMES[n]), GAMES)))

    def test_service_at_places_the_part_there(self):
        out, report = self.results["s17-at"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        with open(os.path.join(out, "build.txt")) as f:
            self.assertIn(f"moved {0xF9E1} ", f.read())

    def test_rom_keep_stops_the_build_without_room_in_page_3(self):
        out, report = self.results["s17-romkeep"]
        self.assertTrue(report.startswith("build.py:"), report)
        self.assertIn("rom keep needs it", report)


if __name__ == "__main__":
    unittest.main()
