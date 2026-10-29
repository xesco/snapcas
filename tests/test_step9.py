"""Step 9 (docs/PLAN.md): the shipped game files, and a game's file for one
machine beside its game.txt (DESIGN.md, Game file and Shipped files)."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402

GAMES = os.path.join(ROOT, "games")


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


if __name__ == "__main__":
    unittest.main()
