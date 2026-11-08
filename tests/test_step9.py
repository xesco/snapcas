"""Step 9 (docs/PLAN.md): the shipped game files, and a game's file for one
machine beside its game.txt (FILES.md, Game file and Shipped files)."""
import concurrent.futures
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
import msx  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402

GAMES = os.path.join(ROOT, "games")


WORK = os.path.join(ROOT, "out", "test", "step9")

# The shipped machines and the DOS that each boots (PLAN.md, Test setup).
SHIPPED = {machine: test_step4.MACHINES[machine][0]
           for machine in ("phc28s-ram64k-carnivore2", "vg8020-carnivore2", "nms8250-carnivore2", "hbf700p-ram512k-msxdos2")}
SHIPPED.update({"nms8245-ram512k-sunriseide": test_step4.NEXTOR, "hb75p-mfrsd": test_step4.NEXTOR,
                "vg8020-picoverse": test_step4.NEXTOR, "vg8020-sdmapper": test_step4.NEXTOR,
                "xp800-sdmapper": test_step4.NEXTOR, "fsa1-mfrsd": test_step4.NEXTOR,
                "hbf1xd-mfrsd": test_step4.NEXTOR, "hb75p-carnivore2": test_step4.NEXTOR, "vg8235": os.path.join(test_step4.DOS_DIR, "msxdos1")})
# A single-load game that fits each of them, the NMS 8250's 128 KB included.
SINGLE = "CALDERO.CAS"


class MachineFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write("cas GAME.CAS\nsnapshot at 10\n")
        with open(os.path.join(self.folder, "phc28s-ram64k-carnivore2.txt"), "w") as f:
            f.write("# Only for the PHC-28S.\ncapture phc28s-ram64k\nsnapshot at 20\n")

    def test_the_machine_file_adds_its_lines_for_its_machine(self):
        game = gamefile.read_game(self.folder, "phc28s-ram64k-carnivore2")
        self.assertEqual(game.capture, "phc28s-ram64k")

    def test_the_machine_file_gives_a_value_that_both_give(self):
        self.assertEqual(gamefile.read_game(self.folder, "phc28s-ram64k-carnivore2").snapshot_at, 20)

    def test_other_machines_read_only_game_txt(self):
        game = gamefile.read_game(self.folder, "vg8020-carnivore2")
        self.assertIsNone(game.capture)
        self.assertEqual(game.snapshot_at, 10)


class UrlLine(unittest.TestCase):
    def read(self, text):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(text)
        return gamefile.read_game(folder)

    def test_a_link_for_each_side(self):
        game = self.read("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip https://example.org/b.ZIP\n")
        self.assertEqual(game.urls, ["https://example.org/a.zip", "https://example.org/b.ZIP"])

    def test_a_link_missing_for_side_2_is_refused(self):
        with self.assertRaisesRegex(gamefile.GameFileError, "a link for each side"):
            self.read("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip\n")

    def test_a_link_that_is_not_https_to_a_zip_is_refused(self):
        with self.assertRaisesRegex(gamefile.GameFileError, "https links to zip files"):
            self.read("cas A.CAS\nurl http://example.org/a.zip\n")


@unittest.skipUnless(os.path.isdir(GAMES), "no games/ folder")
class ShippedGameFiles(unittest.TestCase):
    def test_each_game_file_links_its_zips_on_file_hunter(self):
        for name in gamefile.game_names():
            with self.subTest(game=name):
                game = gamefile.read_game(os.path.join(GAMES, name))
                self.assertTrue(game.urls)
                for url in game.urls:
                    self.assertTrue(url.startswith("https://download.file-hunter.com/Games/MSX1/CAS/"), url)

    def test_every_game_file_reads_on_each_machine(self):
        for name in gamefile.game_names():
            for machine in ("phc28s-ram64k-carnivore2", "vg8020-carnivore2"):
                with self.subTest(game=name, machine=machine):
                    game = gamefile.read_game(os.path.join(GAMES, name), machine)
                    self.assertTrue(game.sha1)

    def test_machine_files_name_a_machine_file(self):
        for name in gamefile.game_names():
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        self.assertTrue(os.path.isfile(msx.machine_path(file[:-4])))

    def test_capture_lines_name_a_variant_of_their_machine(self):
        for name in gamefile.game_names():
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        machine = file[:-4]
                        game = gamefile.read_game(os.path.join(GAMES, name), machine)
                        if game.capture:
                            variants = msx.read_machine(msx.machine_path(machine)).variants
                            self.assertIn(game.capture, variants)


def single_load(machine):
    """Captures, builds and checks SINGLE on a machine, and returns the check's
    report or the failed step's error."""
    folder = os.path.join(WORK, "games", "single-" + machine.replace("/", "-"))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {SINGLE}\n")
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--tapes", test_step4.CAS_DIR)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, machine, "--dos", SHIPPED[machine]).stdout


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class Machines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "cache", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.reports = dict(zip(SHIPPED, pool.map(single_load, SHIPPED)))

    def test_a_single_load_game_restores_on_each_shipped_machine(self):
        for machine, report in self.reports.items():
            with self.subTest(machine=machine):
                self.assertTrue(report.startswith("point 1: pass"), report)
                # The check's own boot, before the restore, is no reboot
                # (PLAN.md, step 16).
                self.assertIn("point 3: pass", report)
                self.assertIn("point 4: pass", report)


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class OneCommand(unittest.TestCase):
    def test_snapcas_py_makes_and_checks_the_image(self):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "cache", "openmsx-home"))
        folder = os.path.join(WORK, "games", "one-command")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(f"cas {SINGLE}\n")
        result = test_step4.command("snap", folder, "phc28s-ram64k-carnivore2", "--check", "--dos",
                                    test_step4.NEXTOR)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("check     pass  the restored machine equals the snapshot", result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(folder, "phc28s-ram64k-carnivore2", "ONECOMMA.SNP")))


if __name__ == "__main__":
    unittest.main()
