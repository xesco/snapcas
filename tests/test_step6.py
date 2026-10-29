"""Step 6 (docs/PLAN.md): the scan's patterns, on bytes made for each case,
and the scan of each file of CAS_DIR that needs the tape service (DESIGN.md,
Scan)."""
import concurrent.futures
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scan  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step5  # noqa: E402

CAS_DIR = test_step4.CAS_DIR
MACHINE = "advanced/phc28s"
WORK = os.path.join(ROOT, "out", "test", "step6")

# Side 2 files, by the side 1 file of their game.
SIDE2 = {"GAUNTLET.CAS": "GAUNTLEB.CAS", "TOUR-91.CAS": "TOUR-91B.CAS"}

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
    return [(f.what, f.offset, f.new) for f in scan.find(bytes.fromhex(data))]


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
        scan.patch(data, scan.find(bytes(data)))
        self.assertEqual(data, bytearray.fromhex("CD E1 FC DB A2 07"))

    def test_report_lines_are_patch_lines(self):
        text = scan.report([("page3", scan.find(bytes.fromhex("00 CD E4 00")))],
                           [("side1", scan.find(bytes.fromhex("DB A2 07")))])
        self.assertIn("page3:0001 CD E4 00 > CD E4 FC  call of TAPIN\n", text)
        self.assertIn("side1:0000 DB A2 07  reader of the cassette signal\n", text)


def folder_name(cas):
    return "scan-" + re.sub(r"[^a-z0-9]", "", os.path.splitext(cas)[0].lower())


def scan_file(cas):
    """Captures and builds a file of CAS_DIR, and returns its scan.txt, or
    None when it needs no tape service, or the failed step's error."""
    name = folder_name(cas)
    folder = os.path.join(WORK, "games", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {cas}\n" + (f"side2 {SIDE2[cas]}\n" if cas in SIDE2 else ""))
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, MACHINE, "--cas", CAS_DIR)
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
    error = scan_file(cas)
    if error is not None and not error.startswith("#"):
        return error, {}
    name = folder_name(cas)
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
            result = test_step4.tool(step, folder, MACHINE, "--cas", CAS_DIR)
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


if __name__ == "__main__":
    unittest.main()
