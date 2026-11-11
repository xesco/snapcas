"""Single-load games restored on the test machines (docs/PLAN.md, Test setup
and steps 4, 9, 14 and 20): each game of the corpus is captured, built and
checked on each machine where it loads, one game on every shipped machine,
Mot and Made in Spain for the RAM search patch, and two games on the HB-F700P's
capture variants whose slot 0 is not expanded. A game passes only through the
gate: check.py's exit status 0, for a report whose four points pass. Emulator
tier."""
import concurrent.futures
import os
import re
import subprocess
import sys
import unittest

import support
import msx
import patches

WORK = support.work("machines")
PHC28S, VG8020 = support.PHC28S, support.VG8020

GAMES = {
    "freddy": "cas FREDDY.CAS\n",
    "fernando": "cas FERNANDO.CAS\n",
    "moonrider": "cas 022-MOON.CAS\n",
    "caldero": "cas CALDERO.CAS\n",
    # La Abadia del Crimen leaves its last 16 KB unread during the load. Its
    # loader has the RAM search, which the capture patches on a machine where
    # it cuts off the loader's code (INTERNALS.md, The RAM search patch).
    "abadia": "cas ABADIA.CAS\nservice no\n",
    # On the PHC-28S, La Abadia's loader took the RAM cartridge in slot 1 for an
    # expanded slot and crashed, so the game loaded without it. The RAM search
    # patch fixes that now, and this one tests the capture line.
    "abadia-phc": "cas ABADIA.CAS\nservice no\ncapture phc28s-empty-carnivore2\n",
    # On the HB-F700P, whose slot 0 is expanded, Fernando Martin's loader
    # selects slot 0 in page 3, where its own code runs. So the capture runs on
    # the variant whose slot 0 is not expanded.
    "fernando-noexp0": "cas FERNANDO.CAS\ncapture hbf700p-noexp0-ram512k-msxdos2\n",
    # Bestial Warrior's loader also finds the HB-F700P's own RAM in slot 3-3 and
    # selects slot 3 in page 3, which the RAM cartridge in slot 1 holds. So the
    # capture runs on the variant without that cartridge as well.
    "bestial-noexp0": "cas BESTIAL.CAS\ncapture hbf700p-noexp0-msxdos2\n",
    # A folder whose path holds characters that Tcl's and Python's glob read:
    # the check must still find the snapshot's RAM pages.
    "caldero[1]*": "cas CALDERO.CAS\nname BRACKETS\n",
}

# machine: (games that pass, games that the restorer stops for too few free
# segments). A game left out of both fails on that machine in openMSX itself
# (docs/PLAN.md, step 4). Each machine boots the DOS that its file names.
MACHINES = {
    PHC28S: ({"freddy", "fernando", "moonrider", "caldero", "abadia", "abadia-phc"}, set()),
    VG8020: ({"freddy", "fernando", "moonrider", "caldero", "caldero[1]*"}, set()),
    "nms8250-carnivore2": ({"freddy", "fernando", "moonrider", "caldero"}, set()),
    "hbf700p-ram512k-msxdos2": ({"moonrider", "caldero", "abadia", "fernando-noexp0", "bestial-noexp0"}, set()),
    "test/nms8250-128k": ({"caldero"}, {"freddy", "fernando", "moonrider", "abadia"}),
    "test/nms8250-dos1": ({"freddy", "fernando", "moonrider", "caldero", "abadia"}, set()),
}
# The RAM search's patch of La Abadia's tape, as the capture writes it.
RAM_SEARCH_PATCH = "patch side1:84 CB FF > 00 00"


def folder_of(game):
    """The folder of a game of GAMES, which holds its work files for each
    machine."""
    return os.path.join(WORK, "games", game)


@support.needs_dos("msxdos1", "msxdos2")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for game, text in GAMES.items():
            support.tape(text.split()[1])
            support.game_folder(folder_of(game), text)
        jobs = [(g, m) for m, (passes, short) in MACHINES.items() for g in passes | short]
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.restored = dict(zip(jobs, pool.map(lambda job: support.restore(folder_of(job[0]), job[1]), jobs)))

    def test_each_game_passes_the_check_on_each_machine(self):
        for machine, (passes, _) in MACHINES.items():
            for game in sorted(passes):
                with self.subTest(machine=machine, game=game):
                    support.assert_passes(self, self.restored[game, machine])

    def test_the_restorer_names_the_segments_it_lacks(self):
        for machine, (_, short) in MACHINES.items():
            for game in sorted(short):
                with self.subTest(machine=machine, game=game):
                    restored = self.restored[game, machine]
                    # The check fails at point 1, and has no other point.
                    self.assertEqual((restored.step, restored.status, restored.points), (None, 3, {1: False}),
                                     restored)
                    # The screen wraps the message at any column, so the
                    # comparison leaves out all spaces.
                    report = re.sub(r"\s", "", restored.report)
                    self.assertRegex(report, r"needs\d+freemappersegments,andDOShas\d+")
                    # The check ends at the restorer's message, and does not
                    # wait for the tail's jump.
                    self.assertIn("the restorer stopped: ", restored.report)
                    self.assertNotIn("did not run within", restored.report)

    def test_a_path_with_glob_characters_has_its_ram_pages_compared(self):
        restored = self.restored["caldero[1]*", VG8020]
        support.assert_passes(self, restored)
        # A changed byte in a page of the snapshot must then fail point 1: a
        # check that finds no page to compare passes it.
        ram = os.path.join(restored.snap, "ram")
        name = sorted(n for n in os.listdir(ram) if n.split("-")[2] in "12")[0]
        with open(os.path.join(ram, name), "r+b") as f:
            f.seek(0x1234)
            byte = f.read(1)[0]
            f.seek(0x1234)
            f.write(bytes([byte ^ 0xFF]))
        changed = support.check_image(restored.folder, VG8020)
        support.assert_fails(self, changed, 1, "differs at")
        self.assertRegex(changed.report, r"RAM \S+ differs at [0-9A-F]{2}34")

    def test_the_capture_patches_the_ram_search_and_the_check_passes(self):
        # PLAN.md, step 14: without a capture line, on the two machines where
        # the search's slot register write cuts off the loader's code.
        for machine in (PHC28S, "hbf700p-ram512k-msxdos2"):
            with self.subTest(machine=machine):
                restored = self.restored["abadia", machine]
                support.assert_passes(self, restored)
                self.assertEqual([p.line for p in restored.snapshot.capture_patches()], [RAM_SEARCH_PATCH])
                # The capture ran again on the patched tape, and its load ends
                # without a write that cuts off its code.
                self.assertNotIn("the RAM search patched", restored.read("snap/log.txt"))
                self.assertEqual(restored.read("snap/side1.cas", binary=True)[0x84:0x86], bytes(2))

    def test_a_capture_with_slot_0_not_expanded_restores_on_the_machine_that_expands_it(self):
        # The image's header marks slot 0 as not expanded in the capture, and
        # the restorer then writes 0 to its subslot register, which selects the
        # main ROM in subslot 0 (INTERNALS.md, The capture with slot 0 not
        # expanded).
        for game in ("fernando-noexp0", "bestial-noexp0"):
            with self.subTest(game=game):
                restored = self.restored[game, "hbf700p-ram512k-msxdos2"]
                support.assert_passes(self, restored)
                self.assertEqual(restored.snapshot.state["sub0"], "-")
                self.assertEqual(restored.header["H_NOEXP"] & 1, 1)

    def test_a_machine_whose_ram_the_loader_finds_gets_no_patch(self):
        for game, machine in (("abadia", "test/nms8250-dos1"), ("abadia-phc", PHC28S)):
            with self.subTest(machine=machine):
                restored = self.restored[game, machine]
                support.assert_passes(self, restored)
                self.assertEqual(restored.snapshot.capture_patches(), [])


# The shipped games of PLAN.md's step 14, as name: the game's folder below
# games/ and the machine. Their loaders have the RAM search.
SEARCH_GAMES = {
    "mot-phc28s": ("MOT", PHC28S),
    # The shipped machine's game file captures Mot without the Carnivore2.
    "mot-vg8020": ("MOT", VG8020),
    # Made in Spain's tape holds the search twice.
    "made-in-phc28s": ("MADE-IN", PHC28S),
}


class RamSearch(unittest.TestCase):
    """The RAM search patch on the games that it was made for (INTERNALS.md,
    The RAM search patch): Mot and Made in Spain, as shipped."""

    @classmethod
    def setUpClass(cls):
        def restore(name):
            shipped, machine = SEARCH_GAMES[name]
            folder = support.shipped_copy(os.path.join(WORK, "games", "search-" + name), shipped)
            return support.restore(folder, machine)
        for tape in ("MOTB.CAS", "MADE-IN.CAS"):
            support.tape(tape)
        with concurrent.futures.ThreadPoolExecutor(len(SEARCH_GAMES)) as pool:
            cls.restored = dict(zip(SEARCH_GAMES, pool.map(restore, SEARCH_GAMES)))

    def patches(self, name, tape):
        """The capture's patches of a game, and the patch line of each copy
        of the search on its tape."""
        data, search = support.read_tape(tape), patches.ramsearch.SEARCH
        copies = [at for at in range(len(data)) if data.startswith(search, at)]
        return ([p.line for p in self.restored[name].snapshot.capture_patches()],
                [f"patch side1:{at + patches.ramsearch.AT:X} CB FF > 00 00" for at in copies])

    def test_the_capture_patches_mots_search_on_the_phc28s_and_the_image_passes(self):
        support.assert_passes(self, self.restored["mot-phc28s"])
        found, expected = self.patches("mot-phc28s", "MOTB.CAS")
        self.assertEqual((found, len(expected)), (expected, 1))

    def test_mot_gets_no_patch_where_its_loader_finds_page_3s_ram(self):
        # On the VG-8020 without the Carnivore2, the search finds the RAM in
        # slot 3, which page 3 already selects: no write cuts off its code.
        restored = self.restored["mot-vg8020"]
        support.assert_passes(self, restored)
        self.assertEqual(restored.snapshot.capture_patches(), [])
        self.assertNotIn("cuts off its code", restored.read("snap/log.txt"))

    def test_each_copy_of_made_in_spains_search_is_patched(self):
        support.assert_passes(self, self.restored["made-in-phc28s"])
        found, expected = self.patches("made-in-phc28s", "MADE-IN.CAS")
        self.assertEqual((found, len(expected)), (expected, 2))


# A single-load game that fits each shipped machine, the NMS 8250's 128 KB
# included.
SINGLE = "CALDERO.CAS"
# The shipped machines, by the DOS that each boots: every machine file of
# machines/ is one, so a new machine needs no line here.
SHIPPED = {name: [m for m in msx.user_machines() if msx.read_machine(msx.machine_path(m)).dos_files == name]
           for name in ("nextor", "msxdos1", "msxdos2")}


def single_load(machine):
    """Captures, builds and checks SINGLE on a machine."""
    support.tape(SINGLE)
    folder = support.game_folder(os.path.join(WORK, "games", "single-" + machine.replace("/", "-")),
                                 f"cas {SINGLE}\n")
    return support.restore(folder, machine)


class Shipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        machines = [m for name, group in SHIPPED.items() if os.path.isdir(support.dos(name)) for m in group]
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.restored = dict(zip(machines, pool.map(single_load, machines)))

    def restores(self, name):
        self.assertTrue(SHIPPED[name])
        for machine in SHIPPED[name]:
            with self.subTest(machine=machine):
                # The check's own boot, before the restore, is no reboot
                # (PLAN.md, step 16): point 3 passes with the others.
                support.assert_passes(self, self.restored[machine])

    def test_every_shipped_machine_is_in_a_group(self):
        self.assertEqual(sorted(m for group in SHIPPED.values() for m in group), msx.user_machines())

    def test_a_single_load_game_restores_on_each_shipped_machine_under_nextor(self):
        self.restores("nextor")

    @support.needs_dos("msxdos2")
    def test_a_single_load_game_restores_on_each_shipped_machine_under_msx_dos_2(self):
        self.restores("msxdos2")

    @support.needs_dos("msxdos1")
    def test_a_single_load_game_restores_on_each_shipped_machine_under_msx_dos_1(self):
        self.restores("msxdos1")


class Plain(unittest.TestCase):
    """tools/plain.py, the load of a tape in plain openMSX (AGENTS.md, Decide
    whether openMSX itself fails)."""

    def test_the_plain_load_types_its_command_after_basics_ok(self):
        # The HB-F700P has no boot lines, and is still booting 10 seconds after
        # power-on. A load command typed then is lost, and the screen shows
        # BASIC's banner alone. The VG-8020 with a Carnivore2 has a boot line.
        support.tape("CALDERO.CAS")
        folder = support.game_folder(os.path.join(WORK, "games", "plain"), "cas CALDERO.CAS\n")
        env = dict(os.environ, SNAPCAS_DOWNLOADS=support.TAPES)
        machines = ("hbf700p-ram512k-msxdos2", VG8020)

        def plain(machine):
            return subprocess.run([sys.executable, "-I", os.path.join(support.ROOT, "tools", "plain.py"), folder,
                                   machine], capture_output=True, text=True, env=env)
        with concurrent.futures.ThreadPoolExecutor(len(machines)) as pool:
            for machine, result in zip(machines, pool.map(plain, machines)):
                with self.subTest(machine=machine):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # El Caldero Magico's own text, in place of BASIC's banner.
                    self.assertNotIn("MSX BASIC", result.stdout)
                    self.assertIn("CONSEGUIDO", result.stdout)


if __name__ == "__main__":
    unittest.main()
