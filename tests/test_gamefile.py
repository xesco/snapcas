"""Game files as tools/gamefile.py reads them (docs/FILES.md, Game file and
Shipped files): each kind of line, each error, a machine's game file beside
game.txt, and the shipped game files. Pure tier."""
import os
import unittest

import support
import gamefile
import msx

GAMES = os.path.join(support.ROOT, "games")


class Folder(unittest.TestCase):
    """A game folder that each test writes."""

    def read(self, text, machine=None, machines=None):
        return gamefile.read_game(support.game_folder(os.path.join(support.temp(self), "GAME"), text, machines),
                                  machine)

    def refused(self, text, error, machines=None, machine=None):
        with self.subTest(text=text), self.assertRaisesRegex(gamefile.GameFileError, error):
            self.read(text, machine, machines)


class Lines(Folder):
    def test_each_kind_of_line_reads_to_its_value(self):
        game = self.read("# A game.\n\n"
                         "cas GAME.CAS\n"
                         "side2 GAMEB.CAS\n"
                         "sha1 " + "a" * 40 + " " + "b" * 40 + "\n"
                         "url https://example.org/a.zip https://example.org/b.zip\n"
                         "name MYGAME\n"
                         "load 'BLOAD\"CAS:\",R'\n"
                         "start SKY\n"
                         "keys 5 space\n"
                         'keys 7.5 "1"\n'
                         "continue return\n"
                         "snapshot at 130\n"
                         "service at f9e1\n"
                         "capture vg8020\n"
                         "rom keep\n"
                         "  # A comment after spaces.\n"
                         "patch page3:1F 3E FC > 3e 14\n"
                         "patch side2:AE88 CD > C9\n")
        self.assertEqual((game.tape, game.side2, game.sha1, game.name), ("GAME.CAS", "GAMEB.CAS",
                                                                           ["a" * 40, "b" * 40], "MYGAME"))
        self.assertEqual(game.urls, ["https://example.org/a.zip", "https://example.org/b.zip"])
        self.assertEqual((game.load, game.start, game.continue_key, game.snapshot_at),
                         ('BLOAD"CAS:",R', "SKY", "return", 130))
        self.assertEqual(game.keys, [(5, "key", "space"), (7.5, "text", "1")])
        self.assertEqual((game.service, game.entry_page, game.capture, game.rom_keep), ("at", 0xF9, "vg8020", True))
        self.assertEqual([(p.side, p.page, p.offset, p.old, p.new, p.place) for p in game.patches],
                         [(None, 3, 0x1F, bytes.fromhex("3EFC"), bytes.fromhex("3E14"), "C01F"),
                          (2, None, 0xAE88, b"\xCD", b"\xC9", "side2:AE88")])
        self.assertTrue(game.patches[0].where.endswith("game.txt:18"))

    def test_a_game_file_with_only_its_tape_has_the_defaults(self):
        game = self.read("cas GAME.CAS\n")
        self.assertEqual((game.name, game.side2, game.sha1, game.urls, game.load, game.start), ("GAME", None, [], [],
                                                                                               None, None))
        self.assertEqual((game.keys, game.continue_key, game.snapshot_at, game.service, game.entry_page),
                         ([], None, None, None, None))
        self.assertEqual((game.capture, game.rom_keep, game.patches), (None, False, []))

    def test_the_images_name_is_the_folders_in_8_capital_letters_and_digits(self):
        self.assertEqual(gamefile.default_name("caldero[1]*"), "CALDERO1")
        self.assertEqual(gamefile.default_name("s16-konami-vg"), "S16KONAM")
        self.assertEqual(gamefile.default_name("---"), "")

    def test_tsx_and_load_lines(self):
        game = self.read("tsx GAME.TSX\nload 'RUN\"CAS:\"'\n")
        self.assertEqual((game.tape, game.load), ("GAME.TSX", 'RUN"CAS:"'))

    def test_a_line_that_cannot_be_read_is_refused_with_its_place(self):
        for line, error in (
                ("load 'RUN", "game.txt:2: No closing quotation"),
                ("side2", "game.txt:2: side2 takes one value"),
                ("name A B", "game.txt:2: name takes one value"),
                ("continue", "game.txt:2: continue takes one value"),
                ("capture a b", "game.txt:2: capture takes one value"),
                ("rom", "game.txt:2: rom takes one value"),
                ("sha1 abc", "game.txt:2: sha1 takes one or two 40-digit SHA-1s"),
                ("sha1 " + "A" * 40, "sha1 takes one or two 40-digit SHA-1s"),
                ("sha1 " + " ".join(["a" * 40] * 3), "sha1 takes one or two 40-digit SHA-1s"),
                ("name game", "game.txt:2: name takes up to 8 capital letters and digits"),
                ("name ", "game.txt:2: name takes one value"),
                ('name ""', "game.txt:2: name takes up to 8 capital letters and digits"),
                ("name TOOLONGNAME", "name takes up to 8 capital letters and digits"),
                ("keys 5", "game.txt:2: keys takes a time and a key name or a text"),
                ("keys 5 nokey", "game.txt:2: nokey is not a key name"),
                ("keys soon space", "game.txt:2: soon is not a time in seconds"),
                ("keys -1 space", "game.txt:2: the time -1 is negative"),
                ("continue nokey", "game.txt:2: nokey is not a key name"),
                ("snapshot 130", "game.txt:2: snapshot takes at and a time"),
                ("snapshot at", "game.txt:2: snapshot takes at and a time"),
                ("snapshot at -5", "game.txt:2: the time -5 is negative"),
                ("service", "game.txt:2: service takes no, at and an address xxE1 in page 3, or t0"),
                ("service at FCE0", "service takes no, at and an address xxE1 in page 3, or t0"),
                ("service at BFE1", "service takes no, at and an address xxE1 in page 3, or t0"),
                ("service yes", "service takes no, at and an address xxE1 in page 3, or t0"),
                ("rom drop", "game.txt:2: rom takes keep"),
                ("patch page3:1F 3E FC", "game.txt:2: patch takes a place, the old bytes, > and as many new bytes"),
                ("patch page3:1F 3E FC > 3E", "patch takes a place, the old bytes, > and as many new bytes"),
                ("patch page3:1F > ", "patch takes a place, the old bytes, > and as many new bytes"),
                ("patch page3:1F 3E G0 > 3E 14", "patch takes a place, the old bytes, > and as many new bytes"),
                ("patch page3:3FFF 3E FC > 3E 14", "game.txt:2: the patch goes past the page's end"),
                ("patch page4:0 3E > 3F", r"game.txt:2: page4:0 is not a place: page<n>:<offset>, side1:<offset> "
                                          "or side2:<offset>"),
                ("patch side3:0 3E > 3F", "side3:0 is not a place"),
                ("speed 2400", "game.txt:2: unknown key speed")):
            self.refused("cas GAME.CAS\n" + line + "\n", error)

    def test_wrong_tape_lines_are_refused(self):
        for text, error in (("cas GAME.TSX\n", "game.txt:1: cas takes a .CAS file"),
                            ("tsx GAME.CAS\n", "game.txt:1: tsx takes a .TSX file"),
                            ("cas GAME.CAS\ntsx GAME.TSX\n", "game.txt:2: a game file has one cas or tsx line"),
                            ("tsx GAME.TSX\nside2 GAMEB.CAS\n", "game.txt: side2 takes a file of side 1's format"),
                            ("load RUN\n", "game.txt: needs a cas or tsx line"),
                            ("# Only a comment.\n", "needs a cas or tsx line")):
            self.refused(text, error)

    def test_values_that_would_stop_a_later_step_are_refused(self):
        for line, error in (("snapshot at nan", "game.txt:2: nan is not a time in seconds"),
                            ("snapshot at inf", "game.txt:2: inf is not a time in seconds"),
                            ("snapshot at -inf", "-inf is not a time in seconds"),
                            ("keys nan space", "nan is not a time in seconds"),
                            ("keys 5 nan", "game.txt:2: nan is not a key name"),
                            ('keys 5 "Ł"', "game.txt:2: the text holds a character that is not in Latin-1"),
                            ("service at FFE1", "game.txt:2: a part of the tape service at FFE1h would pass FFFEh, "
                                                "the last byte that it can take")):
            self.refused("cas GAME.CAS\n" + line + "\n", error)
        game = self.read("cas GAME.CAS\nservice at FEE1\n")
        self.assertEqual((game.service, game.entry_page), ("at", 0xFE))
        # A text in Latin-1 is typed as its bytes.
        self.assertEqual(self.read('cas GAME.CAS\nkeys 5 "Ñ"\n').keys, [(5, "text", "Ñ")])

    def test_a_folder_whose_name_gives_no_image_name_needs_a_name_line(self):
        folder = support.game_folder(os.path.join(support.temp(self), "---"))
        with self.assertRaisesRegex(gamefile.GameFileError, "the folder's name has no letter or digit for the "
                                    "image's name, so the game file needs a name line"):
            gamefile.read_game(folder)
        with open(os.path.join(folder, "game.txt"), "a") as f:
            f.write("name MYGAME\n")
        self.assertEqual(gamefile.read_game(folder).name, "MYGAME")

    def test_a_patch_stops_at_other_bytes_than_its_old_ones(self):
        patch = self.read("cas GAME.CAS\npatch side1:2 3E FC > 3E 14\n").patches[0]
        data = bytearray.fromhex("00 00 3E FC 00")
        patch.apply(data)
        self.assertEqual(data, bytearray.fromhex("00 00 3E 14 00"))
        with self.assertRaisesRegex(gamefile.GameFileError, "game.txt:2: the bytes at side1:2 are not the patch's "
                                    "old bytes"):
            patch.apply(data)


class UrlLine(Folder):
    def test_a_link_for_each_side(self):
        game = self.read("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip https://example.org/b.ZIP\n")
        self.assertEqual(game.urls, ["https://example.org/a.zip", "https://example.org/b.ZIP"])

    def test_a_link_missing_for_side_2_is_refused(self):
        self.refused("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip\n", "url takes a link for each side")
        self.refused("cas A.CAS\nurl https://example.org/a.zip https://example.org/b.zip\n",
                     "url takes a link for each side")

    def test_a_link_that_is_not_https_to_a_zip_is_refused(self):
        for url in ("http://example.org/a.zip", "https://example.org/a.cas", "https://example.org/a b.zip"):
            self.refused(f"cas A.CAS\nurl {url}\n", "game.txt:2: url takes one or two https links to zip files")


class ServiceLine(Folder):
    def test_a_file_holds_one_service_line(self):
        self.refused("cas GAME.CAS\nservice no\nservice t0\n", r"game.txt:3: a file holds one service line")

    def test_rom_keep_cannot_go_with_service_t0(self):
        self.refused("cas GAME.CAS\nrom keep\nservice t0\n", "rom keep needs the tape service's part of page 3, so "
                     "it cannot go with service t0")

    def test_the_machines_service_line_replaces_game_txts(self):
        machines = {support.PHC28S: "service t0\n"}
        text = "cas GAME.CAS\nservice no\n"
        self.assertEqual(self.read(text, support.PHC28S, machines).service, "t0")
        self.assertEqual(self.read(text, support.VG8020, machines).service, "no")
        # The machine's line also replaces an entry page.
        game = self.read("cas GAME.CAS\nservice at F9E1\n", support.PHC28S, machines)
        self.assertEqual((game.service, game.entry_page), ("t0", None))


class MachineFile(Folder):
    TEXT = "cas GAME.CAS\nsnapshot at 10\n"
    MACHINES = {support.PHC28S: "# Only for the PHC-28S.\ncapture phc28s-ram64k\nsnapshot at 20\n"}

    def test_the_machine_file_adds_its_lines_for_its_machine(self):
        self.assertEqual(self.read(self.TEXT, support.PHC28S, self.MACHINES).capture, "phc28s-ram64k")

    def test_the_machine_file_gives_a_value_that_both_give(self):
        self.assertEqual(self.read(self.TEXT, support.PHC28S, self.MACHINES).snapshot_at, 20)

    def test_other_machines_read_only_game_txt(self):
        game = self.read(self.TEXT, support.VG8020, self.MACHINES)
        self.assertIsNone(game.capture)
        self.assertEqual(game.snapshot_at, 10)
        self.assertEqual(self.read(self.TEXT, None, self.MACHINES).snapshot_at, 10)

    def test_a_test_machines_file_has_a_hyphen_for_the_slash(self):
        folder = os.path.join("games", "GAME")
        self.assertEqual(gamefile.machine_file(folder, "test/nms8250-128k"),
                         os.path.join(folder, "test-nms8250-128k.txt"))
        game = self.read(self.TEXT, "test/nms8250-128k", {"test/nms8250-128k": "snapshot at 30\n"})
        self.assertEqual(game.snapshot_at, 30)

    def test_an_error_in_the_machines_file_names_that_file(self):
        self.refused(self.TEXT, r"vg8020-carnivore2.txt:1: unknown key speed", {support.VG8020: "speed 1\n"},
                     support.VG8020)


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
            for machine in (support.PHC28S, support.VG8020):
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


if __name__ == "__main__":
    unittest.main()
