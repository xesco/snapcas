"""snapcas.py sync, which copies a machine's images and SNAPCAS.COM to a card
(docs/CLI.md, Sync a card, and docs/PLAN.md, step 26). The tests make the
images and the card in folders of their own. Pure tier."""
import os
import unittest
from unittest import mock

import support
import card


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Sync(unittest.TestCase):
    def setUp(self):
        self.top = support.temp(self)
        self.images = os.path.join(self.top, "images")
        self.com = os.path.join(self.top, "SNAPCAS.COM")
        self.card = os.path.join(self.top, "card")
        os.makedirs(self.card)
        write(self.com, b"restorer")
        for key, name in (("GAUNTLET", "GAUNTLET.SNP"), ("SUPERMSX/GOLF", "GOLF.SNP"),
                          ("custom/MYGAME", "MYGAME.SNP"), ("1942", "1942.SNP")):
            write(os.path.join(self.images, key, name), key.encode())

    def test_each_file_goes_to_its_letters_folder(self):
        self.assertEqual(sorted(card.card_files(self.images, self.com)), sorted([
            os.path.join("BIN", "SNAPCAS.COM"),
            os.path.join("SNAPCAS", "G", "GAUNTLET.SNP"),
            os.path.join("SNAPCAS", "S", "SUPERMSX", "GOLF.SNP"),
            os.path.join("SNAPCAS", "CUSTOM", "MYGAME.SNP"),
            os.path.join("SNAPCAS", "0-9", "1942.SNP")]))

    def test_a_second_sync_copies_only_what_changed_and_deletes_nothing(self):
        files = card.card_files(self.images, self.com)
        self.assertEqual(card.sync(files, self.card, log=lambda text: None), (5, 0))
        write(os.path.join(self.images, "GAUNTLET", "GAUNTLET.SNP"), b"a new build")
        write(os.path.join(self.card, "SNAPCAS", "Z", "ZANAC.SNP"), b"the user's own")
        self.assertEqual(card.sync(card.card_files(self.images, self.com), self.card, log=lambda text: None), (1, 4))
        with open(os.path.join(self.card, "SNAPCAS", "G", "GAUNTLET.SNP"), "rb") as f:
            self.assertEqual(f.read(), b"a new build")
        self.assertTrue(os.path.isfile(os.path.join(self.card, "SNAPCAS", "Z", "ZANAC.SNP")))

    def test_the_sidecar_that_macos_writes_beside_a_copy_goes(self):
        # macOS keeps a file's extended attributes on a FAT card in ._<name>,
        # an AppleDouble file, which DOS lists as one more file.
        sidecar = os.path.join(self.card, "SNAPCAS", "G", "._GAUNTLET.SNP")
        other = os.path.join(self.card, "SNAPCAS", "Z", "._ZANAC.SNP")
        own = os.path.join(self.card, "SNAPCAS", "0-9", "._1942.SNP")
        write(sidecar, card.APPLEDOUBLE + bytes(4092))
        write(other, card.APPLEDOUBLE + bytes(4092))
        write(own, b"the user's own file of that name")
        card.sync(card.card_files(self.images, self.com), self.card, log=lambda text: None)
        self.assertFalse(os.path.exists(sidecar))
        # A sidecar of a file that sync did not copy stays, and so does a file
        # of that name that is no AppleDouble file.
        self.assertTrue(os.path.isfile(other))
        self.assertTrue(os.path.isfile(own))

    def test_a_copy_that_fails_leaves_no_file_under_its_name(self):
        files = card.card_files(self.images, self.com)
        with mock.patch.object(card.os, "fsync", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                card.sync(files, self.card, log=lambda text: None)
        self.assertEqual([name for _, _, names in os.walk(self.card) for name in names], [])
        # The next sync copies every file, and leaves no temporary file.
        self.assertEqual(card.sync(files, self.card, log=lambda text: None), (5, 0))
        self.assertFalse(any(name.endswith(".$$$") for _, _, names in os.walk(self.card) for name in names))

    def test_the_cards_snapcas_or_bin_folder_is_refused(self):
        for name in ("SNAPCAS", "bin"):
            with self.subTest(name=name):
                os.makedirs(os.path.join(self.card, name), exist_ok=True)
                with self.assertRaisesRegex(card.CardError, "give the card's top folder"):
                    card.check_destination(os.path.join(self.card, name))

    def test_two_images_for_one_place_stop_the_sync(self):
        write(os.path.join(self.images, "GAUNTLE2", "GAUNTLET.SNP"), b"another")
        with self.assertRaisesRegex(card.CardError, "both go to"):
            card.card_files(self.images, self.com)


if __name__ == "__main__":
    unittest.main()
