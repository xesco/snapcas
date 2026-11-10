"""Custom games, the user's own game files in custom/, each with its tape
files beside it (custom/README.md, and docs/PLAN.md, step 25). The tests give
gamefile.CUSTOM a folder of their own for the time of a test, so that they
leave custom/ alone. Pure tier."""
import os
import unittest
from unittest import mock

import support
import gamefile
import pipeline
import snapcas

ROOT = support.ROOT
MACHINE = support.PHC28S


class Custom(unittest.TestCase):
    def setUp(self):
        custom = os.path.join(support.temp(self), "custom")
        patch = mock.patch.object(gamefile, "CUSTOM", custom)
        patch.start()
        self.addCleanup(patch.stop)
        self.folder = support.game_folder(os.path.join(custom, "MyGame"), "# My game, my own dump\ncas MYGAME.CAS\n")
        # A folder without a game.txt is no game.
        os.makedirs(os.path.join(custom, "notes"))

    def test_the_custom_games_are_the_folders_with_a_game_file(self):
        self.assertEqual(gamefile.custom_names(), ["custom/MyGame"])

    def test_a_custom_games_name_finds_its_folder_in_any_case(self):
        self.assertEqual(snapcas.find_game("CUSTOM/mygame"), self.folder)

    def test_list_shows_a_custom_game_with_its_title(self):
        self.assertIn(("custom/MyGame", "My game, my own dump"), snapcas.games_with("custom"))

    def test_a_custom_games_tapes_are_in_its_folder(self):
        self.assertTrue(gamefile.is_custom(self.folder))
        self.assertEqual(pipeline.tapes_folder(self.folder), self.folder)

    def test_a_custom_games_work_folder_and_image_are_below_custom(self):
        self.assertEqual(gamefile.out_folder(MACHINE, self.folder),
                         os.path.join(ROOT, "out", "work", MACHINE, "custom", "MyGame"))
        self.assertEqual(gamefile.published_path(MACHINE, self.folder, "MYGAME"),
                         os.path.join(gamefile.IMAGES, MACHINE, "custom", "MyGame", "MYGAME.SNP"))

    def test_a_shipped_game_is_no_custom_game(self):
        folder = gamefile.game_folder("GAUNTLET")
        self.assertFalse(gamefile.is_custom(folder))
        self.assertEqual(pipeline.tapes_folder(folder), gamefile.DOWNLOADS)
        self.assertEqual(gamefile.game_key(folder), "GAUNTLET")

    def test_a_games_name_has_slashes_on_windows(self):
        folder = os.path.join(ROOT, "games", "SUPERMSX", "GOLF")
        with mock.patch.object(gamefile.os, "sep", "\\"), \
                mock.patch.object(gamefile.os.path, "relpath", return_value="SUPERMSX\\GOLF"):
            self.assertEqual(gamefile.game_key(folder), "SUPERMSX/GOLF")

    def test_a_folder_on_another_drive_is_no_shipped_or_custom_game(self):
        # On Windows, commonpath raises ValueError for paths on two drives.
        with mock.patch.object(gamefile.os.path, "commonpath", side_effect=ValueError("mixed drives")):
            self.assertIsNone(gamefile.game_key(self.folder))
            self.assertFalse(gamefile.is_custom(self.folder))


if __name__ == "__main__":
    unittest.main()
