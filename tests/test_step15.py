"""Step 15 (docs/PLAN.md): TSX tape files, read into the tape model
(DESIGN.md, Tape files and TSX data)."""
import concurrent.futures
import os
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build  # noqa: E402
import capture  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import tape  # noqa: E402
import tsx  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402

TSX_DIR = os.path.join(test_step4.CAS_DIR, "tsx")
COLLECTION = os.path.join(test_step4.CAS_DIR, "collection")
WORK = os.path.join(ROOT, "out", "test", "step15")
MACHINE = "advanced/phc28s"


def kcs(data, byte_cfg=0x54, zero=1458, one=729, pilots=100, pause=1000):
    """A block 4Bh: the BIOS's bits, with byte_cfg's start and stop bits."""
    body = struct.pack("<HHHHHBB", pause, one, pilots, zero, one, 0x24, byte_cfg) + data
    return b"\x4B" + struct.pack("<I", len(body)) + body


def turbo(data, pilot=600, sync1=200, sync2=250, zero=300, one=600, pilots=1000, pause=500):
    """A block 11h, with all bits of the last byte."""
    return (b"\x11" + struct.pack("<HHHHHHBH", pilot, sync1, sync2, zero, one, pilots, 8, pause)
            + len(data).to_bytes(3, "little") + data)


def tsx_file(*blocks):
    return tsx.SIGNATURE + b"\x01\x15" + b"".join(blocks)


class Reader(unittest.TestCase):
    def test_blocks_kinds_offsets_and_times(self):
        header = b"\xD0" * 10 + b"GAME  "
        data = tsx_file(kcs(header), b"\x20" + struct.pack("<H", 2000), turbo(b"\x00\xFF"),
                        b"\x30\x04text", kcs(b"\x00", byte_cfg=0x5C), kcs(b"\x00", byte_cfg=0x44))
        blocks = tape.read("GAME.TSX", data)
        self.assertEqual([b.standard for b in blocks], [True, False, True, False])
        self.assertEqual(blocks[0].data, header)
        for b in blocks:
            self.assertEqual(data[b.offset:b.offset + len(b.data)], b.data)
        # The header block: 100 pilot pulses, then each byte's start bit 0, 8
        # bits and 2 stop bits 1, a 0 bit as 2 pulses and a 1 bit as 4.
        ones = sum(bin(b).count("1") for b in header)
        t = 100 * 729 + 16 * (2 * 1458 + 2 * 4 * 729) + ones * 4 * 729 + (128 - ones) * 2 * 1458
        self.assertAlmostEqual(blocks[0].end, t / 3500000)
        # Its pause of 1 second and block 20h's of 2 come before the turbo
        # block: 1000 pilot pulses, the syncs, then 8 bits 0 and 8 bits 1.
        self.assertAlmostEqual(blocks[1].start, blocks[0].end + 3)
        t = 1000 * 600 + 200 + 250 + 8 * 2 * 300 + 8 * 2 * 600
        self.assertAlmostEqual(blocks[1].end - blocks[1].start, t / 3500000)

    def test_the_service_tape_holds_only_the_standard_blocks(self):
        data = tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02"), kcs(b"\x03" * 5))
        service = tape.service(tape.read("GAME.TSX", data))
        self.assertEqual(service, tape.HEADER + b"\xD0" * 10 + b"GAME  " + tape.HEADER + b"\x03" * 5)
        self.assertEqual(tape.load_command(service), 'BLOAD"CAS:",R')

    def test_an_unknown_block_or_file_is_refused(self):
        with self.assertRaisesRegex(tape.TapeError, "block 19h"):
            tape.read("GAME.TSX", tsx_file(b"\x19\x00\x00\x00\x00"))
        with self.assertRaisesRegex(tape.TapeError, "no ZXTape! signature"):
            tape.read("GAME.TSX", b"not a tape")
        with self.assertRaisesRegex(tape.TapeError, "not a CAS or TSX file"):
            tape.read("GAME.WAV", b"")


@unittest.skipUnless(os.path.isfile(os.path.join(TSX_DIR, "LAZERBYK.TSX")), "CAS_DIR holds no tsx/LAZERBYK.TSX")
class Files(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(TSX_DIR, name), "rb") as f:
            return tape.read(name, f.read())

    @unittest.skipUnless(os.path.isfile(os.path.join(COLLECTION, "035-EDGY.CAS")), "no collection/035-EDGY.CAS")
    def test_a_tsx_file_of_standard_blocks_gives_its_cas_files_tape(self):
        with open(os.path.join(COLLECTION, "035-EDGY.CAS"), "rb") as f:
            cas_data = f.read()
        blocks = self.read("LAZERBYK.TSX")
        self.assertTrue(all(b.standard for b in blocks))
        self.assertEqual(tape.service(blocks).rstrip(b"\0"), cas_data.rstrip(b"\0"))

    def test_the_times_end_where_openmsx_ends_the_tape(self):
        names = [n for n in ("LAZERBYK.TSX", "LICENCE.TSX", "4X4OFFRO.TSX") if os.path.isfile(os.path.join(TSX_DIR, n))]
        out = os.path.join(ROOT, "out", "test", "step15", "lengths.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        script = f"set f [open {msx.tcl_word(out)} w]\n"
        for n in names:
            script += f"cassetteplayer insert {msx.tcl_word(os.path.join(TSX_DIR, n))}\nputs $f [cassetteplayer getlength]\n"
        msx.run(["-machine", "Sanyo_PHC-28S"], script + "close $f\nexit\n", timeout=120)
        with open(out) as f:
            lengths = [float(v) for v in f.read().split()]
        for n, length in zip(names, lengths):
            with self.subTest(name=n):
                self.assertAlmostEqual(self.read(n)[-1].end, length, delta=0.05)


def game_file(lines):
    """A game folder of its own in a temporary folder, with game.txt's lines."""
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.writelines(line + "\n" for line in lines)
    return folder


class GameFile(unittest.TestCase):
    def test_tsx_and_load_lines(self):
        game = gamefile.read_game(game_file(["tsx GAME.TSX", "load 'RUN\"CAS:\"'"]))
        self.assertEqual((game.tape, game.load), ("GAME.TSX", 'RUN"CAS:"'))

    def test_wrong_tape_lines_are_refused(self):
        for lines, error in ((["cas GAME.TSX"], "cas takes a .CAS file"),
                             (["cas GAME.CAS", "tsx GAME.TSX"], "one cas or tsx line"),
                             (["tsx GAME.TSX", "side2 GAMEB.CAS"], "side 1's format"),
                             (["load RUN"], "needs a cas or tsx line")):
            with self.subTest(lines=lines), self.assertRaisesRegex(gamefile.GameFileError, error):
                gamefile.read_game(game_file(lines))


class Model(unittest.TestCase):
    def test_a_tape_that_starts_with_a_turbo_block_needs_a_load_line(self):
        data = tsx_file(turbo(b"\x01\x02"), kcs(b"\xEA" * 10 + b"GAME  "))
        game = gamefile.read_game(game_file(["tsx GAME.TSX"]))
        self.assertIsNone(capture.load_command(game, data))
        game.load = 'RUN"CAS:"'
        self.assertEqual(capture.load_command(game, data), 'RUN"CAS:"')

    def test_a_turbo_block_after_the_snapshot_stops_the_build(self):
        blocks = tape.read("GAME.TSX", tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02")))
        names = ("GAME.TSX", "")
        state = {"tapetime": f"{blocks[1].start - 1:.2f}", "tapeside": "1"}
        with self.assertRaisesRegex(build.BuildError, f"GAME.TSX: the non-standard block at {blocks[1].offset:X}h"):
            build.check_unread(state, (blocks, []), names, False)
        build.check_unread(state, (blocks, []), names, True)
        state["tapetime"] = f"{blocks[1].end:.2f}"
        build.check_unread(state, (blocks, []), names, False)

    def test_an_offset_in_the_service_tape_is_an_offset_in_the_file(self):
        data = tsx_file(kcs(b"\xD0" * 10 + b"GAME  "), turbo(b"\x01\x02"), kcs(b"\x11\x22\x33"))
        blocks = tape.read("GAME.TSX", data)
        service = tape.service(blocks)
        at = service.index(b"\x11\x22\x33")
        self.assertEqual(data[tape.file_offset(blocks, at):][:3], b"\x11\x22\x33")
        self.assertIsNone(tape.file_offset(blocks, 0))


def restore(name, lines, tapes):
    """Captures, builds and checks a game file in WORK, and returns its folder
    and the check's report or the failed step's error."""
    folder = os.path.join(WORK, "games", name)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.writelines(line + "\n" for line in lines)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--cas", tapes)
        if result.returncode != 0:
            return folder, f"{step}: {result.stderr.strip()}"
    return folder, test_step4.tool("check.py", folder, MACHINE, "--dos", test_step4.NEXTOR).stdout


# The games of TSX files that Games captures, as name: game file's lines and
# tape folder: two turbo loaders, and Lazer Bykes from its TSX and its CAS file.
GAMES = {
    "s15-licence": (["tsx LICENCE.TSX"], TSX_DIR),
    "s15-4x4offro": (["tsx 4X4OFFRO.TSX"], TSX_DIR),
    "s15-lazerbyk": (["tsx LAZERBYK.TSX"], TSX_DIR),
    "s15-edgy": (["cas 035-EDGY.CAS"], COLLECTION),
}


@unittest.skipUnless(all(os.path.isfile(os.path.join(TSX_DIR, n)) for n in ("LICENCE.TSX", "4X4OFFRO.TSX", "LAZERBYK.TSX"))
                     and os.path.isfile(os.path.join(COLLECTION, "035-EDGY.CAS")), "CAS_DIR lacks the TSX games' files")
class Games(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.results = dict(zip(GAMES, pool.map(lambda n: restore(n, *GAMES[n]), GAMES)))

    def snap(self, name):
        return os.path.join(ROOT, "out", MACHINE, name, "snap")

    def test_turbo_loaders_load_their_whole_tape_and_the_images_pass(self):
        for name in ("s15-licence", "s15-4x4offro"):
            with self.subTest(game=name):
                folder, report = self.results[name]
                self.assertTrue(report.startswith("point 1: pass"), report)
                self.assertIn("point 2: pass", report)
                state = build.read_state(self.snap(name))
                with open(os.path.join(TSX_DIR, GAMES[name][0][0].split()[1]), "rb") as f:
                    blocks = tape.read("GAME.TSX", f.read())
                self.assertEqual(tape.unread(blocks, float(state["tapetime"])), [])

    def test_a_tsx_file_and_its_cas_file_load_the_same_game(self):
        for name in ("s15-lazerbyk", "s15-edgy"):
            self.assertTrue(self.results[name][1].startswith("point 1: pass"), self.results[name][1])
        # The game's page, 8000h to BFFFh; page 3 holds timers that differ.
        page = "2-2-2-1.bin"
        with open(os.path.join(self.snap("s15-lazerbyk"), "ram", page), "rb") as a, \
                open(os.path.join(self.snap("s15-edgy"), "ram", page), "rb") as b:
            self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
