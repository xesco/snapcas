"""The scan over the corpus (docs/INTERNALS.md, Scan, and docs/PLAN.md, Test
setup and step 6): each tape of the corpus is captured and built on the
PHC-28S, and the findings that were confirmed by hand must be in its scan.txt.
Emulator tier."""
import concurrent.futures
import os
import re
import unittest

import support

MACHINE = support.PHC28S
WORK = support.work("corpus")

# Side 2 files, by the side 1 file of their game.
SIDE2 = {"GAUNTLET.CAS": "GAUNTLEB.CAS", "TOUR-91.CAS": "TOUR-91B.CAS", "SOOTLAND.CAS": "SOOTLANB.CAS"}

# The corpus that Corpus scans: side 1 of each of its games, whose files are
# in CAS_DIR with the tapes of the other tests.
CORPUS = ("022-MOON.CAS", "ABADIA.CAS", "ABU-SIMB.CAS", "AMOTO-S.CAS", "BATMAN.CAS", "BESTIAL.CAS", "CALDERO.CAS",
          "CAMELOT.CAS", "CHICAGO.CAS", "COBRA-S.CAS", "COMPUTAD.CAS", "DESPERAD.CAS", "DUSTIN.CAS", "FERNANDO.CAS",
          "FREDDY.CAS", "GAUNTLET.CAS", "GHOSTB85.CAS", "ITALIA.CAS", "JET-BOMB.CAS", "KNIGHTMA.CAS", "LIVINGST.CAS",
          "MAD-MIDE.CAS", "MAD-MIX.CAS", "MOONWALK.CAS", "MORTADEL.CAS", "MOTORIST.CAS", "NONAMED.CAS",
          "SIR-FRED.CAS", "SOOTLAND.CAS", "TETRIS.CAS", "THING-BO.CAS", "TOUR-91.CAS", "TUAREG.CAS", "TURBO-GI.CAS",
          "WORLD-CU.CAS", "YIE-AR.CAS", "YIE-ARII.CAS", "ZANAC.CAS")

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


def scan_file(cas):
    """Captures and builds a tape of the corpus, with its side 2, and returns
    its scan.txt, or None when it needs no tape service, or the failed step."""
    name = "scan-" + re.sub(r"[^a-z0-9]", "", os.path.splitext(cas)[0].lower())
    for file in (cas, SIDE2.get(cas)):
        if file:
            support.tape(file)
    made = support.make_image(support.game_folder(os.path.join(WORK, "games", name), f"cas {cas}\n"
                                                  + (f"side2 {SIDE2[cas]}\n" if cas in SIDE2 else "")), MACHINE)
    if made.step:
        return repr(made)
    text = made.read("scan.txt")
    return None if text.startswith("# Without the tape service") else text


class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.scans = dict(zip(CORPUS, pool.map(scan_file, CORPUS)))
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

    def test_every_tape_of_the_corpus_is_captured_and_built(self):
        for cas, text in self.scans.items():
            with self.subTest(cas=cas):
                self.assertFalse(text is not None and (text.startswith("capture.py") or text.startswith("build.py")),
                                 text)


if __name__ == "__main__":
    unittest.main()
