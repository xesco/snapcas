"""Step 10 (docs/PLAN.md): the automatic fixes, each on a game that needed a
game file line by hand, without that line (DESIGN.md, Slot patches, Without a
part in page 3, and Files and commands)."""
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scan  # noqa: E402
import test_step4  # noqa: E402

COLLECTION = os.environ.get("COLLECTION_DIR", os.path.join(test_step4.CAS_DIR, "collection"))
WORK = os.path.join(ROOT, "out", "test", "step10")


def has(name):
    return os.path.isfile(os.path.join(COLLECTION, name))


def game(name, machine, lines):
    """A copy of a shipped game's game.txt in a folder of its own, named after
    the test, with lines as its machine's game file. The folder's name keeps
    the images apart from the shipped game's."""
    folder = os.path.join(WORK, "games", f"auto-{name.lower()}")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    shutil.copy(os.path.join(ROOT, "games", name, "game.txt"), folder)
    with open(os.path.join(folder, machine.replace("/", "-") + ".txt"), "w") as f:
        f.writelines(line + "\n" for line in lines)
    return folder


def make(folder, machine):
    """snapcas.py on the game: capture, build and check."""
    return test_step4.tool("snapcas.py", folder, machine, "--cas", COLLECTION,
                           "--dos", test_step4.MACHINES[machine][0])


def read(folder, machine, name):
    with open(os.path.join(ROOT, "out", machine, os.path.basename(folder), name)) as f:
        return f.read()


class SlotPatches(unittest.TestCase):
    def test_the_scan_skips_a_3eh_that_can_be_an_operand(self):
        # The PHC-28S's slot map: slot 3 holds nothing in any page.
        slots = {0: ({3}, 2), 1: ({3}, 1), 2: ({0, 3}, 2), 3: ({3}, 2)}
        # Knight Orc's LD A,(EF3Eh) / OUT (0A8h),A, and the same after CALL.
        for code in ("3A 3E EF D3 A8", "CD 3E EF D3 A8", "3A 00 3E EF D3 A8"):
            self.assertEqual(scan.find(bytes.fromhex(code), slots=slots, tape=False), [], code)
        found = scan.find(bytes.fromhex("F5 3E EF D3 A8"), slots=slots, tape=False)
        self.assertEqual([(f.offset, f.new) for f in found], [(1, bytes.fromhex("3E A6 D3 A8"))])

    @unittest.skipUnless(has("SOOTLAND.CAS"), "COLLECTION_DIR holds no SOOTLAND.CAS")
    def test_the_capture_patches_sootlands_slot_value(self):
        folder = game("SOOTLAND", "advanced/phc28s", ["capture advanced/phc28s-nodisk"])
        result = make(folder, "advanced/phc28s")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("patch side1:24E 3E FC D3 A8 > 3E 14 D3 A8",
                      read(folder, "advanced/phc28s", "snap/patches.txt"))

    @unittest.skipUnless(has("FINDERIN.CAS"), "COLLECTION_DIR holds no FINDERIN.CAS")
    def test_the_capture_and_the_scan_patch_finders_keepers_wslreg_calls(self):
        folder = game("FINDERIN", "basic/vg8020", ["capture basic/vg8020-nodisk"])
        result = make(folder, "basic/vg8020")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = read(folder, "basic/vg8020", "snap/patches.txt")
        for line in ("patch side1:1B37 3E A8 CD 3B 01 > 3E FC CD 3B 01",
                     "patch side1:1B47 3E A0 CD 3B 01 > 3E F0 CD 3B 01",
                     "patch side1:402E 3E A8 CD 3B 01 > 3E FC CD 3B 01"):
            self.assertIn(line, patches)
        self.assertIn("3E A0 CD 3B 01 > 3E F0 CD 3B 01  fixed slot value",
                      read(folder, "basic/vg8020", "scan.txt"))


class WithoutPage3(unittest.TestCase):
    @unittest.skipUnless(has("CHASE-H.CAS"), "COLLECTION_DIR holds no CHASE-H.CAS")
    def test_chase_hq_gets_the_mode_without_a_part_in_page_3(self):
        folder = game("CHASE-H", "advanced/phc28s", [])
        result = make(folder, "advanced/phc28s")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("The tape service has no part in page 3", read(folder, "advanced/phc28s", "scan.txt"))


class Variants(unittest.TestCase):
    @unittest.skipUnless(has("ABADIA.CAS"), "COLLECTION_DIR holds no ABADIA.CAS")
    def test_snapcas_py_finds_la_abadias_capture_variant(self):
        folder = game("ABADIA", "advanced/hbf700p", [])
        result = make(folder, "advanced/hbf700p")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("capture advanced/hbf700p-noram", result.stdout)


if __name__ == "__main__":
    unittest.main()
