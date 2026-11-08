"""Step 10 (docs/PLAN.md): the automatic fixes, each on a game that needed a
game file line by hand, without that line (INTERNALS.md, Slot patches, The RAM
search patch, The page copy patch, Without a part in page 3, and Files and
commands)."""
import concurrent.futures
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import patches  # noqa: E402
import test_step4  # noqa: E402

COLLECTION = test_step4.CAS_DIR
WORK = os.path.join(ROOT, "out", "test", "step10")


def has(name):
    return os.path.isfile(os.path.join(COLLECTION, name))


def tape_of(name):
    """The tape file of the shipped game in games/<name>/, from its cas line."""
    with open(os.path.join(ROOT, "games", name, "game.txt")) as f:
        return next(line.split()[1] for line in f if line.startswith("cas "))


def game(key, name, machine, lines):
    """A copy of a shipped game's game.txt in a folder of its own, named after
    the run's key, with lines as its machine's game file. The folder's name
    keeps the images apart from the shipped game's."""
    folder = os.path.join(WORK, "games", f"auto-{key}")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    shutil.copy(os.path.join(ROOT, "games", name, "game.txt"), folder)
    with open(os.path.join(folder, machine.replace("/", "-") + ".txt"), "w") as f:
        f.writelines(line + "\n" for line in lines)
    return folder


def make(folder, machine):
    """snapcas.py snap on the game: capture, build and check."""
    return test_step4.command("snap", folder, machine, "--check", "--dos", test_step4.MACHINES[machine][0])


def read(folder, machine, name):
    with open(os.path.join(folder, machine, name)) as f:
        return f.read()


# The runs of snapcas.py snap, by key: the shipped game, the machine, and the lines
# of the machine's game file. setUpModule runs them at once, and the tests
# read their results.
RUNS = {
    "sootland": ("SOOTLAND", "phc28s-ram64k-carnivore2", ["capture phc28s-ram64k"]),
    "finderin": ("FINDERIN", "vg8020-carnivore2", ["capture vg8020"]),
    "chase-h": ("CHASE-H", "phc28s-ram64k-carnivore2", []),
    "digydung-variant": ("SUPERMSX/DIGYDUNG", "hbf700p-ram512k-msxdos2", []),
    "rockya": ("ROCKYA", "phc28s-ram64k-carnivore2", []),
    "uchi87": ("UCHI87", "phc28s-ram64k-carnivore2", []),
    "doki-dok": ("DOKI-DOK", "phc28s-ram64k-carnivore2", ["capture phc28s-ram64k"]),
    "emerald": ("EMERALD", "phc28s-ram64k-carnivore2", ["capture phc28s-ram64k"]),
}
RESULTS = {}


def setUpModule():
    keys = [k for k, (name, _, _) in RUNS.items() if has(tape_of(name))]
    folders = {k: game(k, *RUNS[k]) for k in keys}
    with concurrent.futures.ThreadPoolExecutor(max(len(keys), 1)) as pool:
        for k, result in zip(keys, pool.map(lambda k: make(folders[k], RUNS[k][1]), keys)):
            RESULTS[k] = (folders[k], result)


class SlotPatches(unittest.TestCase):
    def test_the_scan_skips_a_3eh_that_can_be_an_operand(self):
        # The PHC-28S's slot map: slot 3 holds nothing in any page.
        slots = {0: ({3}, 2), 1: ({3}, 1), 2: ({0, 3}, 2), 3: ({3}, 2)}
        # Knight Orc's LD A,(EF3Eh) / OUT (0A8h),A, and the same after CALL.
        for code in ("3A 3E EF D3 A8", "CD 3E EF D3 A8", "3A 00 3E EF D3 A8"):
            self.assertEqual(patches.find(bytes.fromhex(code), patches.Context(slots=slots, tape=False)), [], code)
        found = patches.find(bytes.fromhex("F5 3E EF D3 A8"), patches.Context(slots=slots, tape=False))
        self.assertEqual([(f.offset, f.new) for f in found], [(1, bytes.fromhex("3E A6 D3 A8"))])

    @unittest.skipUnless(has("SOOTLAND.CAS"), "CAS_DIR holds no SOOTLAND.CAS")
    def test_the_capture_patches_sootlands_slot_value(self):
        folder, result = RESULTS["sootland"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("patch side1:24E 3E FC D3 A8 > 3E 14 D3 A8",
                      read(folder, "phc28s-ram64k-carnivore2", "snap/patches.txt"))

    @unittest.skipUnless(has("FINDERIN.CAS"), "CAS_DIR holds no FINDERIN.CAS")
    def test_the_capture_and_the_scan_patch_finders_keepers_wslreg_calls(self):
        folder, result = RESULTS["finderin"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = read(folder, "vg8020-carnivore2", "snap/patches.txt")
        for line in ("patch side1:1B37 3E A8 CD 3B 01 > 3E FC CD 3B 01",
                     "patch side1:1B47 3E A0 CD 3B 01 > 3E F0 CD 3B 01",
                     "patch side1:402E 3E A8 CD 3B 01 > 3E FC CD 3B 01"):
            self.assertIn(line, patches)
        self.assertIn("3E A0 CD 3B 01 > 3E F0 CD 3B 01  fixed slot value",
                      read(folder, "vg8020-carnivore2", "scan.txt"))


    @unittest.skipUnless(has("ROCKYA.CAS"), "CAS_DIR holds no ROCKYA.CAS")
    def test_the_capture_patches_each_copy_of_rockys_routine(self):
        # 01 F3 3E FFh: the 3Eh can be the operand of an LD BC,nn, which the
        # watch, which knows the value, does not take it for.
        folder, result = RESULTS["rockya"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = read(folder, "phc28s-ram64k-carnivore2", "snap/patches.txt")
        for line in ("patch side1:6581 3E FF D3 A8 > 3E A6 D3 A8", "patch side1:AC49 3E FF D3 A8 > 3E A6 D3 A8"):
            self.assertIn(line, patches)

    @unittest.skipUnless(has("UCHI87.CAS"), "CAS_DIR holds no UCHI87.CAS")
    def test_the_capture_finds_uchi_matas_code_alone(self):
        # The routine writes the slot register's value into the bytes after
        # the code, so neither the bytes before nor after match the tape.
        folder, result = RESULTS["uchi87"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("patch side1:2012 3E F0 D3 A8 > 3E A0 D3 A8",
                      read(folder, "phc28s-ram64k-carnivore2", "snap/patches.txt"))

    @unittest.skipUnless(has("DOKI-DOK.CAS"), "CAS_DIR holds no DOKI-DOK.CAS")
    def test_the_capture_keeps_page_3_for_doki_doki_penguin_land(self):
        folder, result = RESULTS["doki-dok"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = read(folder, "phc28s-ram64k-carnivore2", "snap/patches.txt")
        for line in ("patch side1:46D6 3E 54 D3 A8 > 3E 14 D3 A8", "patch side1:46E5 3E 50 D3 A8 > 3E 10 D3 A8"):
            self.assertIn(line, patches)


class PageCopy(unittest.TestCase):
    def test_a_blocks_sum_byte_is_found_when_it_holds_the_sum(self):
        # Two blocks of 8 bytes, as CAS pads them: the first ends with the sum
        # of its other bytes, the second does not.
        header = patches.pagecopy.CAS_HEADER
        data = header + bytes([1, 2, 3, 0, 0, 0, 0, 6]) + header + bytes([1, 2, 3, 0, 0, 0, 0, 7])
        self.assertEqual(patches.pagecopy.sum_byte(data, 9), 15)
        self.assertEqual(patches.pagecopy.sum_byte(data, 25), -1)

    @unittest.skipUnless(has("EMERALD.CAS"), "CAS_DIR holds no EMERALD.CAS")
    def test_the_capture_patches_level_9s_copy_and_its_blocks_sum(self):
        folder, result = RESULTS["emerald"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = read(folder, "phc28s-ram64k-carnivore2", "snap/patches.txt")
        for line in ("patch side1:8B9 DB A8 CB 2F CB 2F CB 2F CB 2F E6 0F B1 > 3E 15 00 00 00 00 00 00 00 00 00 00 00",
                     "patch side1:74DA DB A8 CB 2F CB 2F CB 2F CB 2F E6 0F B1 > 3E 15 00 00 00 00 00 00 00 00 00 00 00",
                     "patch side1:BAB8 92 > D4"):
            self.assertIn(line, patches)


class WithoutPage3(unittest.TestCase):
    @unittest.skipUnless(has("CHASE-H.CAS"), "CAS_DIR holds no CHASE-H.CAS")
    def test_chase_hq_gets_the_mode_without_a_part_in_page_3(self):
        folder, result = RESULTS["chase-h"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("The tape service has no part in page 3", read(folder, "phc28s-ram64k-carnivore2", "scan.txt"))


class Variants(unittest.TestCase):
    # La Abadia del Crimen needed the variant until the RAM search patch, and
    # Sootland until the patch that keeps page 3.
    @unittest.skipUnless(has("SUPERMOB.CAS"), "CAS_DIR holds no SUPERMOB.CAS")
    def test_snapcas_py_finds_digger_dungeons_capture_variant(self):
        folder, result = RESULTS["digydung-variant"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("capture hbf700p-msxdos2", result.stdout)


if __name__ == "__main__":
    unittest.main()
