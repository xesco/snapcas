"""TSX tape files of the collection (docs/INTERNALS.md, Tape files and A game
later on the tape, and docs/PLAN.md, step 15): the reader's times against
openMSX's, and games captured from TSX files, with turbo blocks, at another
speed, patched, and from a later file of a CAS tape. The readers on bytes that
a test writes are in tests/test_tape.py. Emulator tier."""
import concurrent.futures
import os
import unittest

import support
import msx
import tape

WORK = support.work("tsx")
MACHINE = support.PHC28S


class Files(unittest.TestCase):
    def read(self, name):
        return tape.read(name, support.read_tape(name))

    def test_a_tsx_file_of_standard_blocks_gives_its_cas_files_tape(self):
        cas_data = support.read_tape("035-EDGY.CAS")
        blocks = self.read("LAZERBYK.TSX")
        self.assertTrue(all(b.standard for b in blocks))
        self.assertEqual(tape.service(blocks).rstrip(b"\0"), cas_data.rstrip(b"\0"))

    def test_the_times_end_where_openmsx_ends_the_tape(self):
        names = ("LAZERBYK.TSX", "LICENCE.TSX", "4X4OFFRO.TSX")
        out = os.path.join(WORK, "lengths.txt")
        os.makedirs(WORK, exist_ok=True)
        script = f"set f [open {msx.tcl_word(out)} w]\n"
        for n in names:
            script += f"cassetteplayer insert {msx.tcl_word(support.tape(n))}\nputs $f [cassetteplayer getlength]\n"
        # An error of a command here ends openMSX, by the prelude's catch.
        msx.run(["-machine", "Sanyo_PHC-28S"], script + "close $f\nstop\n", timeout=120)
        with open(out) as f:
            lengths = [float(v) for v in f.read().split()]
        self.assertEqual(len(lengths), len(names))
        for n, length in zip(names, lengths):
            with self.subTest(name=n):
                self.assertAlmostEqual(self.read(n)[-1].end, length, delta=0.05)


# The games that Games captures, as name: game file's lines: two turbo
# loaders, and Lazer Bykes from its TSX and its CAS file.
GAMES = {
    "s15-licence": ["tsx LICENCE.TSX"],
    "s15-4x4offro": ["tsx 4X4OFFRO.TSX"],
    "s15-lazerbyk": ["tsx LAZERBYK.TSX"],
    "s15-edgy": ["cas 035-EDGY.CAS"],
    # Standard blocks recorded at about 1660 baud, between the two speeds.
    "s15-picopico": ["tsx PICOPICO.TSX"],
    # The "I" of "Instructions", at offset 3EAh of the file, which the game
    # loads to 82E0h.
    "s15-patched": ["tsx LAZERBYK.TSX", "sha1 d6f9fd9dd69bdbd2cb9c426240fb6053d6f6af53",
                    "patch side1:3EA 49 6E 73 > 69 6E 73"],
    # Sky Jaguar, the second game on a side whose block headers are off the
    # grid of 8 bytes.
    "s15-sky": ["cas ENGESO07.CAS", "start SKY"],
}


def restore(name):
    """Captures, builds and checks a game of GAMES."""
    support.tape(GAMES[name][0].split()[1])
    folder = support.game_folder(os.path.join(WORK, "games", name), "".join(line + "\n" for line in GAMES[name]))
    return support.restore(folder, MACHINE)


class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.restored = dict(zip(GAMES, pool.map(restore, GAMES)))

    def passed(self, name):
        support.assert_passes(self, self.restored[name])
        return self.restored[name]

    def test_turbo_loaders_load_their_whole_tape_and_the_images_pass(self):
        for name in ("s15-licence", "s15-4x4offro"):
            with self.subTest(game=name):
                state = self.passed(name).snapshot.state
                blocks = tape.read("GAME.TSX", support.read_tape(GAMES[name][0].split()[1]))
                self.assertEqual(tape.unread(blocks, float(state["tapetime"])), [])

    def test_tapion_reads_standard_blocks_recorded_between_the_speeds(self):
        restored = self.passed("s15-picopico")
        service = tape.service(tape.read("PICOPICO.TSX", support.read_tape("PICOPICO.TSX")))
        self.assertGreaterEqual(restored.snapshot.num("tapepos"), tape.needed_end(service) - 7)

    def test_a_start_line_loads_a_game_later_on_the_tape(self):
        restored = self.passed("s15-sky")
        self.assertEqual(tape.read("SIDE1.CAS", restored.read("snap/side1.cas", binary=True))[0].data,
                         b"\xEA" * 10 + b"SKY   ")

    def test_a_patch_line_patches_the_tsx_file_that_the_capture_loads(self):
        restored = self.passed("s15-patched")
        self.assertEqual(restored.read("snap/side1.tsx", binary=True)[0x3EA:0x3ED], b"ins")
        self.assertEqual(restored.read("snap/ram/2-2-2-1.bin", binary=True)[0x2E0:0x2EC], b"instructions")

    def test_a_tsx_file_and_its_cas_file_load_the_same_game(self):
        # The game's page, 8000h to BFFFh; page 3 holds timers that differ.
        page = "snap/ram/2-2-2-1.bin"
        self.assertEqual(self.passed("s15-lazerbyk").read(page, binary=True),
                         self.passed("s15-edgy").read(page, binary=True))


if __name__ == "__main__":
    unittest.main()
