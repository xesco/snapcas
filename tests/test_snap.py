"""snapcas.py snap on games: the command makes and checks an image, and the
automatic fixes work on games that needed a game file's line by hand, without
that line (docs/INTERNALS.md, Slot patches, The page copy patch and Without a
part in page 3, and docs/PLAN.md, steps 9, 10 and 19). The patterns of the
patches are in tests/test_patches.py. Emulator tier."""
import concurrent.futures
import os
import shutil
import unittest

import support
import gamefile

WORK = support.work("snap")
PHC28S, VG8020 = support.PHC28S, support.VG8020

# The runs of snapcas.py snap, by key: the shipped game, the machine, and the
# lines of the machine's game file. setUpModule runs them at once, and the
# tests read their results.
RUNS = {
    "sootland": ("SOOTLAND", PHC28S, ["capture phc28s-ram64k"]),
    "finderin": ("FINDERIN", VG8020, ["capture vg8020"]),
    "chase-h": ("CHASE-H", PHC28S, []),
    "digydung-variant": ("SUPERMSX/DIGYDUNG", "hbf700p-ram512k-msxdos2", []),
    "rockya": ("ROCKYA", PHC28S, []),
    "uchi87": ("UCHI87", PHC28S, []),
    "doki-dok": ("DOKI-DOK", PHC28S, ["capture phc28s-ram64k"]),
    "emerald": ("EMERALD", PHC28S, ["capture phc28s-ram64k"]),
}
# A game folder of the test's own, for the command alone.
ONE_COMMAND = "one-command"
RESULTS = {}


def game(key, name, machine, lines):
    """A copy of a shipped game's game.txt in a folder of its own, named after
    the run's key, with lines as its machine's game file. The folder's name
    keeps the images apart from the shipped game's."""
    folder = os.path.join(WORK, "games", f"auto-{key}")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    shutil.copy(os.path.join(support.ROOT, "games", name, "game.txt"), folder)
    with open(gamefile.machine_file(folder, machine), "w") as f:
        f.writelines(line + "\n" for line in lines)
    read = gamefile.read_game(folder, machine)
    for tape in (read.tape, read.side2):
        if tape:
            support.tape(tape)
    return folder


def snap(folder, machine):
    """snapcas.py snap on the game, with the check: the command's result, and
    the Restored of what it left."""
    result = support.command("snap", folder, machine, "--check", "--dos", support.dos_of(machine))
    report = os.path.join(gamefile.out_folder(machine, folder), "check", "report.txt")
    text = ""
    if os.path.exists(report):
        with open(report) as f:
            text = f.read()
    return result, support.Restored(folder, machine, None, result.returncode, result.stderr, text)


@support.needs_dos("msxdos2")
def setUpModule():
    folders = {k: (game(k, *run), run[1]) for k, run in RUNS.items()}
    support.tape("CALDERO.CAS")
    folders[ONE_COMMAND] = (support.game_folder(os.path.join(WORK, "games", ONE_COMMAND), "cas CALDERO.CAS\n"), PHC28S)
    with concurrent.futures.ThreadPoolExecutor(len(folders)) as pool:
        RESULTS.update(zip(folders, pool.map(lambda k: snap(*folders[k]), folders)))


class Snap(unittest.TestCase):
    """A run of RUNS, whose result must pass the gate: the command's exit
    status 0, and a report whose four points pass."""

    def passed(self, key):
        """The run's Restored, once it has passed."""
        result, restored = RESULTS[key]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        support.assert_passes(self, restored)
        # The command prints the four points of its last check as passed.
        checks = [line for line in result.stdout.splitlines() if line.startswith("check     ")]
        self.assertEqual([line.split()[1] for line in checks[-4:]], ["pass"] * 4, result.stdout)
        return restored

    def patches(self, key):
        return self.passed(key).read("snap/patches.txt")


class OneCommand(Snap):
    def test_snapcas_py_makes_and_checks_the_image(self):
        restored = self.passed(ONE_COMMAND)
        result, _ = RESULTS[ONE_COMMAND]
        self.assertEqual(result.stdout.splitlines()[1:], [
            "capture   done",
            "build     done: 3 records, 52 port writes, up to 3 free mapper segments",
            "check     pass  the restored machine equals the snapshot",
            "check     pass  the game does not write to the tape service in page 3",
            "check     pass  the machine does not reboot",
            "check     pass  the game does not stop at a BASIC error"])
        # A game folder outside games/ keeps its image in its work folder.
        self.assertTrue(os.path.isfile(os.path.join(restored.out, "ONECOMMA.SNP")))


class SlotPatches(Snap):
    def test_the_capture_patches_sootlands_slot_value(self):
        self.assertIn("patch side1:24E 3E FC D3 A8 > 3E 14 D3 A8", self.patches("sootland"))

    def test_the_capture_and_the_scan_patch_finders_keepers_wslreg_calls(self):
        patches = self.patches("finderin")
        for line in ("patch side1:1B37 3E A8 CD 3B 01 > 3E FC CD 3B 01",
                     "patch side1:1B47 3E A0 CD 3B 01 > 3E F0 CD 3B 01",
                     "patch side1:402E 3E A8 CD 3B 01 > 3E FC CD 3B 01"):
            self.assertIn(line, patches)
        self.assertIn("3E A0 CD 3B 01 > 3E F0 CD 3B 01  fixed slot value", self.passed("finderin").read("scan.txt"))

    def test_the_capture_patches_each_copy_of_rockys_routine(self):
        # 01 F3 3E FFh: the 3Eh can be the operand of an LD BC,nn, which the
        # watch, which knows the value, does not take it for.
        patches = self.patches("rockya")
        for line in ("patch side1:6581 3E FF D3 A8 > 3E A6 D3 A8", "patch side1:AC49 3E FF D3 A8 > 3E A6 D3 A8"):
            self.assertIn(line, patches)

    def test_the_capture_finds_uchi_matas_code_alone(self):
        # The routine writes the slot register's value into the bytes after
        # the code, so neither the bytes before nor after match the tape.
        self.assertIn("patch side1:2012 3E F0 D3 A8 > 3E A0 D3 A8", self.patches("uchi87"))

    def test_the_capture_keeps_page_3_for_doki_doki_penguin_land(self):
        patches = self.patches("doki-dok")
        for line in ("patch side1:46D6 3E 54 D3 A8 > 3E 14 D3 A8", "patch side1:46E5 3E 50 D3 A8 > 3E 10 D3 A8"):
            self.assertIn(line, patches)


class PageCopy(Snap):
    def test_the_capture_patches_level_9s_copy_and_its_blocks_sum(self):
        patches = self.patches("emerald")
        for line in ("patch side1:8B9 DB A8 CB 2F CB 2F CB 2F CB 2F E6 0F B1 > 3E 15 00 00 00 00 00 00 00 00 00 00 00",
                     "patch side1:74DA DB A8 CB 2F CB 2F CB 2F CB 2F E6 0F B1 > 3E 15 00 00 00 00 00 00 00 00 00 00 00",
                     "patch side1:BAB8 92 > D4"):
            self.assertIn(line, patches)


class WithoutPage3(Snap):
    def test_chase_hq_gets_the_mode_without_a_part_in_page_3(self):
        restored = self.passed("chase-h")
        self.assertIn("The tape service has no part in page 3", restored.read("scan.txt"))
        header = restored.header
        self.assertEqual(header["H_FLAGS"] & header.service["FLAG_T0"], header.service["FLAG_T0"])


class Variants(Snap):
    # La Abadia del Crimen needed the variant until the RAM search patch, and
    # Sootland until the patch that keeps page 3.
    def test_snapcas_py_finds_digger_dungeons_capture_variant(self):
        self.passed("digydung-variant")
        result, _ = RESULTS["digydung-variant"]
        self.assertIn("snapcas.py: trying the capture variant hbf700p-msxdos2\n", result.stderr)
        self.assertIn("snapcas.py: it passes, so the machine's game file needs: capture hbf700p-msxdos2\n",
                      result.stdout)


if __name__ == "__main__":
    unittest.main()
