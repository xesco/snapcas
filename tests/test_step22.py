"""Step 22 (docs/PLAN.md): the snapcas command's verbs: list and machines, and
how snap finds the game and the machine (docs/CLI.md). Making an image is in
step 9's OneCommand and step 10's tests."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
import msx  # noqa: E402

COMMAND = os.path.join(ROOT, "snapcas.py")


def snapcas(*args):
    return subprocess.run([COMMAND, *args], capture_output=True, text=True)


class Command(unittest.TestCase):
    def test_the_command_is_executable(self):
        self.assertTrue(os.access(COMMAND, os.X_OK))

    def test_without_arguments_it_prints_its_help(self):
        result = snapcas()
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: snapcas.py", result.stdout)
        self.assertIn("machines", result.stdout)

    def test_an_unknown_verb_stops_with_status_1(self):
        result = snapcas("play")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid choice", result.stderr)


class List(unittest.TestCase):
    def test_a_text_finds_the_games_whose_folder_or_title_holds_it(self):
        result = snapcas("list", "wall", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        folders = [line.split()[0] for line in result.stdout.splitlines()[:-1]]
        self.assertEqual(folders, ["SUPERMSX/THEWALL", "WALL-THE", "WALLBALL"])
        self.assertEqual(result.stdout.splitlines()[-1], "3 games")

    def test_without_all_it_leaves_out_the_compilations_programs_and_counts_them(self):
        lines = snapcas("list", "wall").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in lines[:-1]], ["WALL-THE", "WALLBALL"])
        self.assertEqual(lines[-1], "2 games, and 1 in compilations, which --all lists")

    def test_a_text_matches_in_any_case(self):
        self.assertIn("GAUNTLET  Gauntlet (1986)(US Gold)", snapcas("list", "gAuNtLeT").stdout)

    def test_each_game_names_the_file_hunter_file_that_it_comes_from(self):
        self.assertIn("GAUNTLET  Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']\n", snapcas("list", "gauntlet").stdout)
        self.assertIn("001-ARIO  Turbo Pack A (1987)(Philips)(es) / 001-Aritmo.cas\n", snapcas("list", "aritmo", "--all").stdout)
        self.assertIn("PAC-MANI  Pac-Mania (Grandslam) (Zafiro) [BLOAD'CAS-',R] [_]\n",
                      snapcas("list", "pac-mani").stdout)
        self.assertIn("SUPERMSX/AFRICAFI  Super MSX n.23 (settembre 1989) - cas_23 / Africa Film\n",
                      snapcas("list", "africa", "--all").stdout)
        self.assertIn("ENGESOFT/ATHLETIC  Engesoft msxk-06 / Athletic Land (1984)(Konami)\n",
                      snapcas("list", "athletic", "--all").stdout)

    def test_a_compilations_name_finds_its_programs(self):
        self.assertEqual(snapcas("list", "super msx n.23", "--all").stdout.splitlines()[-1], "10 games")

    def test_without_a_text_it_lists_every_game_file(self):
        lines = snapcas("list", "--all").stdout.splitlines()
        self.assertEqual(len(lines) - 1, len(gamefile.game_names()))
        self.assertEqual(lines[-1], f"{len(gamefile.game_names())} games")

    def test_without_a_text_or_all_it_lists_every_game_but_the_compilations_programs(self):
        lines = snapcas("list").stdout.splitlines()
        folders = [line.split()[0] for line in lines[:-1]]
        self.assertFalse(any("/" in folder for folder in folders))
        self.assertNotIn("001-ARIO", folders)
        self.assertIn("RUR-1", folders)
        self.assertIn("RUR-2", folders)
        hidden = len(gamefile.game_names()) - len(folders)
        self.assertEqual(lines[-1], f"{len(folders)} games, and {hidden} in compilations, which --all lists")


class Machines(unittest.TestCase):
    def test_it_lists_the_user_machines_and_no_variant_or_test_machine(self):
        result = snapcas("machines")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [line.split()[0] for line in result.stdout.splitlines()]
        self.assertEqual(names, msx.user_machines())
        self.assertIn("phc28s-ram64k-carnivore2", names)
        self.assertNotIn("phc28s-ram64k", names)
        self.assertFalse(any(name.startswith("test/") for name in names))

    def test_each_machine_shows_its_first_comment_sentence(self):
        self.assertRegex(snapcas("machines").stdout,
                         r"vg8020-carnivore2 +Philips VG-8020 \(MSX1, 64 KB\) with a Carnivore2\n")


class Snap(unittest.TestCase):
    """snap's lookups, which stop before any openMSX run."""

    def test_a_text_that_is_not_a_games_name_stops(self):
        for text in ("gaunt", "no such game"):
            with self.subTest(text=text):
                result = snapcas("snap", text, "phc28s-ram64k-carnivore2")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'no game is named "{text}": snapcas.py list shows the games', result.stderr)

    def test_a_text_that_is_not_a_machines_name_stops(self):
        for text in ("phc28s", "vg8020", "msx3"):
            with self.subTest(text=text):
                result = snapcas("snap", "gauntlet", text)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'no machine is named "{text}": snapcas.py machines shows the machines', result.stderr)

    def test_dos_without_check_stops(self):
        result = snapcas("snap", "gauntlet", "phc28s-ram64k-carnivore2", "--dos", "dos")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--dos gives the DOS files for --check", result.stderr)

    def test_snap_without_arguments_prints_its_help(self):
        result = snapcas("snap")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: snapcas.py snap", result.stdout)


if __name__ == "__main__":
    unittest.main()
