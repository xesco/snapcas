"""Step 16 (docs/PLAN.md): the check's point 3, which fails a reboot of the
machine after the restore (DESIGN.md, Check, point 3)."""
import concurrent.futures
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402
import test_step9  # noqa: E402

COLLECTION = os.path.join(test_step4.CAS_DIR, "collection")
WORK = os.path.join(ROOT, "out", "test", "step16")

# The game files that Reboots checks, as name: the shipped game file's folder
# below games/, the machine, and whether the copy leaves out the machine's game
# file.
GAMES = {
    # Reboots to the boot screen on the PHC-28S without its machine's game file,
    # whose capture without the Carnivore2 fixes it.
    "s16-aliens": ("SUPERMSX/ALIENS", "phc28s-ram64k-carnivore2", True),
    # Reboots into DOS on the VG-8020, whose AUTOEXEC.BAT runs SNAPCAS.COM again,
    # without its machine's game file, whose capture without the Carnivore2 fixes it.
    "s16-konami-vg": ("KONAMI", "vg8020-carnivore2", True),
    # Resets the VG-8020 on purpose after the restore, and starts its ROM copy.
    "s16-japan": ("SUPERMSX/JAPAN", "vg8020-carnivore2", False),
    # Passes the tail's jump address again with its own code.
    "s16-enchante": ("ENCHANTE", "phc28s-ram64k-carnivore2", False),
    # Keeps BASIC's banner on its restored screen.
    "s16-robe": ("016-ROBE", "phc28s-ram64k-carnivore2", False),
    # Never reaches the reset that its capture shows 8.7 seconds after the
    # snapshot, without its machine's game file.
    "s16-konami": ("KONAMI", "phc28s-ram64k-carnivore2", True),
    # Resets the PHC-28S on purpose after the restore, and starts its game.
    "s16-bumper": ("BUMPER", "phc28s-ram64k-carnivore2", False),
    # Resets the VG-8020 on purpose after the restore, and one savestate catches
    # the boot screen before the game starts.
    "s16-raider": ("SUPERMSX/RAIDER18", "vg8020-carnivore2", False),
}


def check(name):
    """Captures, builds and checks a copy of a shipped game file in WORK, and
    returns the check's report or the failed step's error."""
    shipped, machine, without_machine = GAMES[name]
    folder = os.path.join(WORK, "games", name)
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "games", shipped), folder)
    if without_machine:
        os.remove(os.path.join(folder, machine.replace("/", "-") + ".txt"))
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--tapes", COLLECTION)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, machine, "--dos", test_step9.SHIPPED[machine]).stdout


TAPES = ("SUPER-09.CAS", "SUPERMOB.CAS", "ENCHANTE.CAS", "016-ROBE.CAS", "SUPERM18.CAS",
         "KONAMI.CAS", "BUMPER.CAS")


@unittest.skipUnless(all(os.path.isfile(os.path.join(COLLECTION, n)) for n in TAPES),
                     "CAS_DIR lacks the tapes of Reboots")
class Reboots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.reports = dict(zip(GAMES, pool.map(check, GAMES)))

    def test_a_reboot_to_the_boot_screen_fails_point_3(self):
        report = self.reports["s16-aliens"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 2: pass", report)
        self.assertIn("point 3: fail", report)
        self.assertIn("the screen shows the BIOS's boot screen", report)

    def test_a_reboot_into_dos_fails_point_3(self):
        report = self.reports["s16-konami-vg"]
        self.assertIn("point 3: fail", report)
        self.assertIn("SNAPCAS.COM starts again", report)

    def test_a_reset_that_starts_the_game_passes_point_3(self):
        report = self.reports["s16-japan"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 3: pass", report)
        self.assertIn("the machine resets", report)

    def test_a_game_that_passes_the_tails_jump_again_passes_point_3(self):
        report = self.reports["s16-enchante"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 3: pass", report)

    def test_a_restored_screen_with_basics_banner_passes_point_3(self):
        report = self.reports["s16-robe"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 3: pass", report)


    def test_a_reset_whose_boot_screen_one_savestate_catches_passes_point_3(self):
        report = self.reports["s16-raider"]
        self.assertTrue(report.startswith("point 1: pass"), report)
        self.assertIn("point 3: pass", report)
        self.assertIn("the screen shows the BIOS's boot screen", report)


    def test_a_restore_that_skips_the_captures_reset_fails_point_3(self):
        report = self.reports["s16-konami"]
        self.assertIn("point 3: fail", report)
        self.assertIn("the restored game does not", report)

    def test_a_reset_on_the_phc28s_is_noted(self):
        report = self.reports["s16-bumper"]
        self.assertIn("point 3: pass", report)
        self.assertIn("the machine resets", report)


if __name__ == "__main__":
    unittest.main()
