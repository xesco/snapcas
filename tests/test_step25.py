"""Step 25 (docs/PLAN.md): custom games, the user's own game files in custom/,
each with its tape files beside it (custom/README.md). The tests point
gamefile.CUSTOM at a folder of their own, so that they leave custom/ alone."""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
import snapcas  # noqa: E402

MACHINE = "phc28s-ram64k-carnivore2"


class Custom(unittest.TestCase):
    def setUp(self):
        self.real_custom = gamefile.CUSTOM
        gamefile.CUSTOM = os.path.join(tempfile.mkdtemp(), "custom")
        self.folder = os.path.join(gamefile.CUSTOM, "MyGame")
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write("# My game, my own dump\ncas MYGAME.CAS\n")
        # A folder without a game.txt is no game.
        os.makedirs(os.path.join(gamefile.CUSTOM, "notes"))

    def tearDown(self):
        shutil.rmtree(os.path.dirname(gamefile.CUSTOM))
        gamefile.CUSTOM = self.real_custom

    def test_the_custom_games_are_the_folders_with_a_game_file(self):
        self.assertEqual(gamefile.custom_names(), ["custom/MyGame"])

    def test_a_custom_games_name_finds_its_folder_in_any_case(self):
        self.assertEqual(snapcas.find_game("CUSTOM/mygame"), self.folder)

    def test_list_shows_a_custom_game_with_its_title(self):
        self.assertIn(("custom/MyGame", "My game, my own dump"), snapcas.games_with("custom"))

    def test_a_custom_games_tapes_are_in_its_folder(self):
        self.assertTrue(gamefile.is_custom(self.folder))
        self.assertEqual(snapcas.tapes_folder(self.folder), self.folder)

    def test_a_custom_games_work_folder_and_image_are_below_custom(self):
        self.assertEqual(gamefile.out_folder(MACHINE, self.folder),
                         os.path.join(ROOT, "out", "work", MACHINE, "custom", "MyGame"))
        self.assertEqual(gamefile.published_path(MACHINE, self.folder, "MYGAME"),
                         os.path.join(gamefile.IMAGES, MACHINE, "custom", "MyGame", "MYGAME.SNP"))

    def test_a_shipped_game_is_no_custom_game(self):
        folder = gamefile.game_folder("GAUNTLET")
        self.assertFalse(gamefile.is_custom(folder))
        self.assertEqual(snapcas.tapes_folder(folder), gamefile.DOWNLOADS)
        self.assertEqual(gamefile.game_key(folder), "GAUNTLET")


if __name__ == "__main__":
    unittest.main()
