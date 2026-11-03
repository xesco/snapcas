"""Step 6 (docs/PLAN.md): the scan's patterns, on bytes made for each case,
and the scan of each file of CAS_DIR that needs the tape service (DESIGN.md,
Scan)."""
import concurrent.futures
import hashlib
import os
import re
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import tape  # noqa: E402
import patches  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step5  # noqa: E402

CAS_DIR = test_step4.CAS_DIR
MACHINE = "phc28s-ram64k-carnivore2"
WORK = os.path.join(ROOT, "out", "test", "step6")

# Side 2 files, by the side 1 file of their game.
SIDE2 = {"GAUNTLET.CAS": "GAUNTLEB.CAS", "TOUR-91.CAS": "TOUR-91B.CAS", "SOOTLAND.CAS": "SOOTLANB.CAS"}

# The findings confirmed by hand, by file.
CONFIRMED = {
    "GAUNTLET.CAS": [
        "page3:215F CD E1 00 > CD E1 FC  call of TAPION",
        "page3:21AB CD E4 00 > CD E4 FC  call of TAPIN",
        "side1:AE88 CD E1 00 > CD E1 FC  call of TAPION",
        "side1:AED4 CD E4 00 > CD E4 FC  call of TAPIN",
    ],
    "TOUR-91.CAS": ["page0:0725 11 E1 00 D5 11 D9 CD D5 > 11 E1 FC D5 11 D9 CD D5  stub of TAPION"],
    "MAD-MIDE.CAS": ["page0:017D 11 E1 00 D5 11 D9 CD D5 > 11 E1 FC D5 11 D9 CD D5  stub of TAPION"],
    "DESPERAD.CAS": [
        "page3:0504 21 E1 00 CD > 21 E1 FC CD  entry of TAPION in HL",
        "page3:050C 21 E4 00 CD > 21 E4 FC CD  entry of TAPIN in HL",
    ],
}

# file: the inputs that reach the next load from the check's savestate at 10
# seconds, 4 seconds apart, and the seconds of play (test_step5.PLAYS).
PLAYS = {
    "TOUR-91.CAS": (["0"], 60),               # the menu's 0, COMENZAR
    "MAD-MIDE.CAS": (["space", "space", "0"], 60),  # the title, then the menu's 0, START
    "DESPERAD.CAS": (["1"], 60),              # the menu's 1, Fase 1
}


def found(data):
    return [(f.what, f.offset, f.new) for f in patches.find(bytes.fromhex(data))]


class Patterns(unittest.TestCase):
    def test_stubs_with_de_and_hl(self):
        self.assertEqual(found("00 11 E1 00 D5 11 D9 CD D5"),
                         [("stub of TAPION", 1, bytes.fromhex("11 E1 FC D5 11 D9 CD D5"))])
        self.assertEqual(found("21 E1 00 E5 21 D9 CD E5"),
                         [("stub of TAPION", 0, bytes.fromhex("21 E1 FC E5 21 D9 CD E5"))])

    def test_a_stub_of_tapoon_is_left_alone(self):
        self.assertEqual(found("11 EA 00 D5 11 D9 CD D5"), [])

    def test_calls(self):
        self.assertEqual(found("CD E1 00 CD E4 00 CD E7 00 CD EA 00 CD E1 01"), [
            ("call of TAPION", 0, bytes.fromhex("CD E1 FC")),
            ("call of TAPIN", 3, bytes.fromhex("CD E4 FC")),
            ("call of TAPIOF", 6, bytes.fromhex("CD E7 FC")),
        ])

    def test_entries_in_hl_before_a_call(self):
        self.assertEqual(found("21 E1 00 CD 96 FC 21 E4 00 CD 96 FC 21 E1 00 00"), [
            ("entry of TAPION in HL", 0, bytes.fromhex("21 E1 FC CD")),
            ("entry of TAPIN in HL", 6, bytes.fromhex("21 E4 FC CD")),
        ])

    def test_readers_within_4_bytes_are_listed_unpatched(self):
        self.assertEqual(found("DB A2 17"), [("reader of the cassette signal", 0, None)])
        self.assertEqual(found("DB A2 00 00 00 CB 7F"), [("reader of the cassette signal", 0, None)])
        self.assertEqual(found("DB A2 00 00 00 00 E6 80"), [])

    def test_readers_of_psg_register_14_are_listed_unpatched(self):
        self.assertEqual(found("3E 0E D3 A0 DB A2 47"),
                         [("reader of PSG register 14, the cassette signal or a joystick", 0, None)])

    def test_patch_writes_only_the_patched_findings(self):
        data = bytearray.fromhex("CD E1 00 DB A2 07")
        patches.patch(data, patches.find(bytes(data)))
        self.assertEqual(data, bytearray.fromhex("CD E1 FC DB A2 07"))

    def test_report_lines_are_patch_lines(self):
        text = patches.report([("page3", patches.find(bytes.fromhex("00 CD E4 00")))],
                           [("side1", patches.find(bytes.fromhex("DB A2 07")))])
        self.assertIn("page3:0001 CD E4 00 > CD E4 FC  call of TAPIN\n", text)
        self.assertIn("side1:0000 DB A2 07  reader of the cassette signal\n", text)


def folder_name(cas, prefix="scan-"):
    """The file's folder name, with a prefix of the class's own, because make
    test runs the classes at once."""
    return prefix + re.sub(r"[^a-z0-9]", "", os.path.splitext(cas)[0].lower())


def scan_file(cas, prefix="scan-"):
    """Captures and builds a file of CAS_DIR, and returns its scan.txt, or
    None when it needs no tape service, or the failed step's error."""
    name = folder_name(cas, prefix)
    folder = os.path.join(WORK, "games", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {cas}\n" + (f"side2 {SIDE2[cas]}\n" if cas in SIDE2 else ""))
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--tapes", CAS_DIR)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    with open(os.path.join(ROOT, "out", MACHINE, name, "scan.txt")) as f:
        text = f.read()
    return None if text.startswith("No tape service") else text


@unittest.skipUnless(os.path.isdir(CAS_DIR), "CAS_DIR names no folder of CAS files")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        files = sorted(f for f in os.listdir(CAS_DIR)
                       if f.upper().endswith(".CAS") and f not in SIDE2.values())
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.scans = dict(zip(files, pool.map(scan_file, files)))
        with open(os.path.join(WORK, "report.txt"), "w") as f:
            for cas, text in cls.scans.items():
                if text is not None:
                    f.write(f"== {cas}\n{text}\n")

    def test_confirmed_findings(self):
        for cas, lines in CONFIRMED.items():
            with self.subTest(cas=cas):
                text = self.scans.get(cas) or ""
                for line in lines:
                    self.assertIn(line + "\n", text)


# Moonwalker, with the tape service in T0 (DESIGN.md, Without a part in page
# 3): its game file, and the inputs from the intro to the main game's load.
MOONWALKER = """cas MOONWALK.CAS
sha1 1787776aeef9420ebb35c3ecb879a7c9a556a512
snapshot at 135
service t0
patch page0:38CD A4 6F > 2E A6
"""


def play(cas):
    """Captures, builds and checks a file, then plays it to its next load, and
    returns the check's report and the play's values."""
    error = scan_file(cas, "play-")
    if error is not None and not error.startswith("#"):
        return error, {}
    name = folder_name(cas, "play-")
    report = test_step4.tool("check.py", os.path.join(WORK, "games", name), MACHINE,
                             "--dos", test_step4.NEXTOR).stdout
    if not report.startswith("point 1: pass"):
        return report, {}
    inputs, seconds = PLAYS[cas]
    test_step5.PLAYS[name] = (name, inputs, seconds, {})
    return report, test_step5.play(name)


@unittest.skipUnless(os.path.isdir(CAS_DIR), "CAS_DIR names no folder of CAS files")
class Stubs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            cls.plays = dict(zip(PLAYS, pool.map(play, PLAYS)))

    def test_a_patched_stub_reaches_the_tape_service(self):
        for cas, (report, values) in self.plays.items():
            with self.subTest(cas=cas):
                self.assertTrue(report.startswith("point 1: pass"), report)
                # The patched stub calls the entry in page 3, which calls T0's
                # TAPION, and the position moves past its value at the snapshot.
                self.assertGreater(values["tapion"], 0, values)
                self.assertGreater(values["pos"], values["pos0"], values)


@unittest.skipUnless(os.path.isfile(os.path.join(CAS_DIR, "MOONWALK.CAS")), "CAS_DIR holds no MOONWALK.CAS")
class WithoutAPartInPage3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        folder = os.path.join(WORK, "games", "t0-moonwalk")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(MOONWALKER)
        cls.error = None
        for step in ("capture.py", "build.py"):
            result = test_step4.tool(step, folder, MACHINE, "--tapes", CAS_DIR)
            if result.returncode != 0:
                cls.error = f"{step}: {result.stderr.strip()}"
                return
        cls.report = test_step4.tool("check.py", folder, MACHINE, "--dos", test_step4.NEXTOR).stdout
        test_step5.PLAYS["t0-moonwalk"] = ("t0-moonwalk", ["space"] * 3, 120, {}, True)
        cls.values = test_step5.play("t0-moonwalk") if cls.report.startswith("point 1: pass") else {}

    def test_moonwalker_loads_its_main_game_through_t0(self):
        self.assertIsNone(self.error)
        self.assertTrue(self.report.startswith("point 1: pass"), self.report)
        # From the intro to the end of the main game's 22 KB block, as in a
        # load from the tape.
        self.assertGreater(self.values["tapion"], 0, self.values)
        self.assertEqual(self.values["pos"], 60418, self.values)


def capture_build_check(name, text, cas_dir):
    """Writes a game file, then captures, builds and checks the game, and
    returns the failed step's error or the check's report."""
    folder = os.path.join(WORK, "games", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(text)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--tapes", cas_dir)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, MACHINE, "--dos", test_step4.NEXTOR).stdout


# Sootland selects RAM in slot 3, so its side1 patch makes its loader keep page
# 3 in the PHC-28S's internal RAM and select the RAM cartridge for pages 1 and
# 2. The capture must load the patched tape, or the game crashes.
SOOTLAND = """cas SOOTLAND.CAS
side2 SOOTLANB.CAS
sha1 5ccf9a2463aa3144f3c03c2a23b798ba68d184e4 c2d10d8d5694de81b1192ec7d85aa80a10f89045
capture phc28s-ram64k
patch side1:024E 3E FC D3 A8 > 3E 14 D3 A8
"""


@unittest.skipUnless(all(os.path.isfile(os.path.join(CAS_DIR, f)) for f in ("SOOTLAND.CAS", "SOOTLANB.CAS")),
                     "CAS_DIR holds no SOOTLAND.CAS and SOOTLANB.CAS")
class PatchedTape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        cls.report = capture_build_check("patched-sootland", SOOTLAND, CAS_DIR)
        snap = os.path.join(ROOT, "out", MACHINE, "patched-sootland", "snap")
        with open(os.path.join(snap, "log.txt")) as f:
            cls.log = f.read()
        with open(os.path.join(snap, "state.txt")) as f:
            cls.state = dict(line.split(" ", 1) for line in f.read().splitlines())

    def test_the_capture_loads_the_patched_tape(self):
        with open(os.path.join(ROOT, "out", MACHINE, "patched-sootland", "snap", "side1.cas"), "rb") as f:
            self.assertEqual(f.read()[0x24E:0x252], bytes.fromhex("3E 14 D3 A8"))

    def test_the_capture_turns_the_tape_over(self):
        # The game reads on past side 1's end, so side 2 goes in, and the
        # tape position goes on in side 2 (DESIGN.md, Capture, step 4).
        self.assertTrue(self.report.startswith("point 1: pass"), self.report)
        self.assertIn("side 2 inserted", self.log)
        with open(os.path.join(CAS_DIR, "SOOTLAND.CAS"), "rb") as f:
            side2_start = tape.side2_start(len(f.read()))
        self.assertGreater(int(self.state["tapepos"], 16), side2_start)


def borrow_symbols():
    with open(os.path.join(ROOT, "out", "borrow.sym")) as f:
        return {name.rstrip(":"): int(value, 16) for name, _, value in (line.split() for line in f)}


def borrow_tape():
    """tests/borrow.asm as a binary file on tape, then a block of the bytes 0
    to 255 (DESIGN.md, CAS data)."""
    with open(os.path.join(ROOT, "out", "borrow.bin"), "rb") as f:
        code = f.read()
    start = borrow_symbols()["start"]

    def padded(data):
        return data + bytes(-len(data) % 8)
    data = padded(tape.HEADER + b"\xD0" * 10 + b"BORROW")
    data = padded(data + tape.HEADER + struct.pack("<3H", start, start + len(code) - 1, start) + code)
    return data + tape.HEADER + bytes(range(256))


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "out", "borrow.bin")), "make builds out/borrow.bin")
class BorrowedBySlot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        tapes = os.path.join(WORK, "tapes")
        os.makedirs(tapes, exist_ok=True)
        with open(os.path.join(tapes, "BORROW.CAS"), "wb") as f:
            f.write(borrow_tape())
        # The patch selects slot 2 in page 0, DOS's mapper on the PHC-28S
        # with the Carnivore2, in place of the ROM.
        rom = borrow_symbols()["rom"] - 0xC000
        text = (f"cas BORROW.CAS\nsha1 {hashlib.sha1(borrow_tape()).hexdigest()}\nservice t0\n"
                f"patch page3:{rom:04X} F6 00 > F6 02\n")
        cls.report = capture_build_check("t0-borrow", text, tapes)
        cls.header = b""
        cls.values = {}
        if cls.report.startswith("point 1: pass"):
            with open(os.path.join(ROOT, "out", MACHINE, "t0-borrow", "T0BORROW.SNP"), "rb") as f:
                cls.header = f.read(64)
            symbols = borrow_symbols()
            test_step5.PLAYS["t0-borrow"] = ("t0-borrow", [], 90,
                                             {"passed": symbols["passed"], "failed": symbols["failed"]}, True)
            cls.values = test_step5.play("t0-borrow")

    def test_tapin_borrows_page_2_outside_the_mapper(self):
        self.assertTrue(self.report.startswith("point 1: pass"), self.report)
        self.assertEqual(self.header[55], 2)  # the borrowed page
        self.assertGreaterEqual(self.values["tapin"], 256, self.values)
        self.assertGreater(self.values["passed"], 0, self.values)
        self.assertEqual(self.values["failed"], 0, self.values)


if __name__ == "__main__":
    unittest.main()
