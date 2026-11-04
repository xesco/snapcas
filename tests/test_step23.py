"""Step 23 (docs/PLAN.md): the download of a game's tape files from its url
line (docs/CLI.md, Download). The tests replace the network with zips that
they make, so they run offline."""
import hashlib
import io
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import download  # noqa: E402
import gamefile  # noqa: E402

SIDE1 = b"side 1's tape"
SIDE2 = b"side 2's tape"


def zipped(**members):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, content in members.items():
            z.writestr(name, content)
    return data.getvalue()


class Download(unittest.TestCase):
    def setUp(self):
        self.zips = {"https://example.org/a.zip": zipped(**{"Game (Side A).cas": SIDE1, "Other.cas": b"other"}),
                     "https://example.org/b.zip": zipped(**{"Game (Side B).cas": SIDE2})}
        self.fetched = []
        self.real_fetch = download.fetch
        download.fetch = lambda url: self.fetched.append(url) or self.zips[url]
        self.folder = tempfile.mkdtemp()
        self.tapes = tempfile.mkdtemp()

    def tearDown(self):
        download.fetch = self.real_fetch

    def game(self, lines):
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write(lines)
        return gamefile.read_game(self.folder)

    def two_sides(self):
        return self.game(f"cas GAME.CAS\nside2 GAMEB.CAS\nsha1 {hashlib.sha1(SIDE1).hexdigest()} "
                         f"{hashlib.sha1(SIDE2).hexdigest()}\n"
                         "url https://example.org/a.zip https://example.org/b.zip\n")

    def read(self, name):
        with open(os.path.join(self.tapes, name), "rb") as f:
            return f.read()

    def test_each_side_is_found_by_its_sha1_and_saved_under_the_game_files_name(self):
        download.tapes(self.two_sides(), self.tapes, log=lambda text: None)
        self.assertEqual(self.read("GAME.CAS"), SIDE1)
        self.assertEqual(self.read("GAMEB.CAS"), SIDE2)

    def test_each_side_prints_the_zip_it_downloads_and_the_file_it_copies(self):
        lines = []
        download.tapes(self.two_sides(), self.tapes, log=lines.append)
        self.assertEqual(lines, ["download  a.zip from example.org",
                                 f"copy      Game (Side A).cas to {os.path.join(self.tapes, 'GAME.CAS')}, sha1 ok",
                                 "download  b.zip from example.org",
                                 f"copy      Game (Side B).cas to {os.path.join(self.tapes, 'GAMEB.CAS')}, sha1 ok"])

    def test_a_tape_already_in_the_folder_is_not_downloaded_again(self):
        game = self.two_sides()
        download.tapes(game, self.tapes, log=lambda text: None)
        self.fetched.clear()
        download.tapes(game, self.tapes, log=lambda text: None)
        self.assertEqual(self.fetched, [])

    def test_a_tape_in_the_folder_with_another_sha1_stops_and_is_kept(self):
        with open(os.path.join(self.tapes, "GAME.CAS"), "wb") as f:
            f.write(b"the user's own dump")
        with self.assertRaisesRegex(download.DownloadError, "Move it away"):
            download.tapes(self.two_sides(), self.tapes, log=lambda text: None)
        self.assertEqual(self.read("GAME.CAS"), b"the user's own dump")

    def test_a_zip_without_the_sha1_stops_and_writes_nothing(self):
        game = self.game(f"cas GAME.CAS\nsha1 {hashlib.sha1(b'missing').hexdigest()}\n"
                         "url https://example.org/a.zip\n")
        with self.assertRaisesRegex(download.DownloadError, "the zip holds no file whose SHA-1 is"):
            download.tapes(game, self.tapes, log=lambda text: None)
        self.assertEqual(os.listdir(self.tapes), [])

    def test_a_game_file_without_a_url_line_names_the_file_to_put_in_the_folder(self):
        game = self.game(f"cas GAME.CAS\nsha1 {hashlib.sha1(SIDE1).hexdigest()}\n")
        with self.assertRaisesRegex(download.DownloadError, "has no url line. Put the file whose SHA-1 is"):
            download.tapes(game, self.tapes, log=lambda text: None)


if __name__ == "__main__":
    unittest.main()
