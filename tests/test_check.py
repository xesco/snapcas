"""The check on games (docs/INTERNALS.md, Check): point 3, which fails a reboot
of the machine after the restore, point 4, which fails a game that stops at a
BASIC error, and what check.tcl leaves in the report when one of its own
callbacks fails. check.py's reading of a report is in tests/test_gate.py, and
point 2's guard in tests/test_service.py. Emulator tier."""
import concurrent.futures
import os
import unittest

import support
import check
import gamefile
import msx

WORK = support.work("check")
PHC28S = support.PHC28S

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


def check_copy(name, shipped, machine, without_machine=False, without_patches=False):
    """Captures, builds and checks a copy of a shipped game file in WORK,
    without its machine's game file or without its patch lines."""
    folder = support.shipped_copy(os.path.join(WORK, "games", name), shipped)
    if without_machine:
        os.remove(gamefile.machine_file(folder, machine))
    if without_patches:
        path = os.path.join(folder, "game.txt")
        with open(path, encoding="utf-8") as f:
            lines = [line for line in f if not line.startswith("patch ")]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    game = gamefile.read_game(folder, machine)
    for tape in (game.tape, game.side2):
        if tape:
            support.tape(tape)
    return support.restore(folder, machine)


class Reboots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with concurrent.futures.ThreadPoolExecutor(len(GAMES)) as pool:
            cls.restored = dict(zip(GAMES, pool.map(lambda name: check_copy(name, *GAMES[name]), GAMES)))

    def passes_with_note(self, name, note):
        """The game passes the check, and point 3 holds a line with the note."""
        restored = self.restored[name]
        support.assert_passes(self, restored)
        self.assertTrue(any(note in line for line in restored.lines(3)), restored)

    def test_a_reboot_to_the_boot_screen_fails_point_3(self):
        support.assert_fails(self, self.restored["s16-aliens"], 3, "the screen shows the BIOS's boot screen")

    def test_a_reboot_into_dos_fails_point_3(self):
        support.assert_fails(self, self.restored["s16-konami-vg"], 3, "SNAPCAS.COM starts again")

    def test_a_reset_that_starts_the_game_passes_point_3(self):
        self.passes_with_note("s16-japan", "the machine resets")

    def test_a_game_that_passes_the_tails_jump_again_passes_point_3(self):
        support.assert_passes(self, self.restored["s16-enchante"])

    def test_a_restored_screen_with_basics_banner_passes_point_3(self):
        support.assert_passes(self, self.restored["s16-robe"])

    def test_a_reset_whose_boot_screen_one_savestate_catches_passes_point_3(self):
        self.passes_with_note("s16-raider", "the screen shows the BIOS's boot screen")

    def test_a_restore_that_skips_the_captures_reset_fails_point_3(self):
        support.assert_fails(self, self.restored["s16-konami"], 3, "the restored game does not")

    def test_a_reset_on_the_phc28s_is_noted(self):
        self.passes_with_note("s16-bumper", "the machine resets")


# The game files that BasicErrors checks: Field Master without its patch line,
# which stops at "Overflow in 130", and Aritmo, from Turbo Pack A, which runs its
# BASIC program without an error.
BASIC_GAMES = ("FIELD-MA", "001-ARIO")


class BasicErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with concurrent.futures.ThreadPoolExecutor(len(BASIC_GAMES)) as pool:
            cls.restored = dict(zip(BASIC_GAMES, pool.map(
                lambda name: check_copy(name, name, PHC28S, without_patches=True), BASIC_GAMES)))

    def test_a_stop_at_a_basic_error_fails_point_4(self):
        support.assert_fails(self, self.restored["FIELD-MA"], 4, "the screen shows Overflow in 130")

    def test_a_basic_program_without_an_error_passes_point_4(self):
        support.assert_passes(self, self.restored["001-ARIO"])


class Script(unittest.TestCase):
    """check.tcl's procedures in openMSX's C-BIOS machine, which needs no
    system ROMs: what it leaves in the report when it cannot go on."""

    def report(self, start):
        """The report of check.tcl with the Tcl start after it, in the C-BIOS
        machine."""
        folder = support.temp(self)
        report = os.path.join(folder, "report.txt")
        settings = {"report": msx.tcl_word(report), "snap": msx.tcl_word(folder), "pages": "0",
                    "kv": "{pc 0000 a8 00}", "capreset": "{}", "state": "snapcas-test", "name": "TEST",
                    "com": "{0 0 0}", "stop": "{}", "tail": "{0 25 3 21}", "free": "{}", "service": "0",
                    "patched": "{}", "part": "{}", "moved": "{}", "cpos": "{}", "ended": "{}"}
        script = ("".join(f"set ::C({k}) {v}\n" for k, v in settings.items())
                  + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/check.tcl") + start)
        support.cbios(script)
        with open(report) as f:
            return f.read()

    def test_an_error_of_a_callback_fails_its_point_in_the_report(self):
        first = self.report("later 1 {error boom}\n")
        self.assertEqual(first, "point 1: fail\n  check: boom\n")
        after_point_1 = "write_report\nset ::point 2\nlater 1 {for_point 3 {error boom}}\n"
        later = self.report(after_point_1)
        self.assertEqual(later, "point 1: pass\npoint 3: fail\n  check: boom\n")
        # check.py takes both for a check that fails, and not for a run that
        # broke.
        self.assertEqual((check.verdict(first), check.verdict(later)), (3, 3))

    def test_a_check_that_never_ends_stops_at_its_deadline(self):
        report = self.report("")
        self.assertEqual(report, "point 1: fail\n  check: the check did not end within 600 seconds\n")
        self.assertEqual(check.verdict(report), 3)


if __name__ == "__main__":
    unittest.main()
