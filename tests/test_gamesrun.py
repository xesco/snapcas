"""The games run of tools/games.py (docs/INTERNALS.md, The games run): its two
lists of failures, the three groups that it prints, its exit status and its
cache. The tests give the game files and each game's result, so no game runs
and no openMSX starts. Pure tier."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

import support
import gamefile
import games
import msx
import pipeline

MACHINE = support.VG8020


class Lists(unittest.TestCase):
    """The lists of failures, as the run reads them before it starts."""

    def failures(self, text):
        path = os.path.join(support.temp(self), "failures.txt")
        with open(path, "w") as f:
            f.write("# A list.\n\n" + text)
        return games.read_failures(path, MACHINE, ["CALDERO", "FREDDY"])

    def test_a_list_gives_the_machines_folders(self):
        self.assertEqual(self.failures("vg8020-carnivore2 CALDERO The load stops\n"
                                       "nms8250-carnivore2 FREDDY The load stops\n"), {"CALDERO"})
        self.assertEqual(self.failures(""), set())

    def test_a_line_that_cannot_be_read_stops_the_run_before_it_starts(self):
        for line, error in (("vg8020-carnivore2 CALDERO", "failures.txt:3: a line holds a machine"),
                            ("vg8020 CALDERO The load stops", "failures.txt:3: no machine is named vg8020"),
                            ("vg8020-carnivore2 CALDERA The load stops",
                             "failures.txt:3: no game file is in games/CALDERA/"),
                            # Also a line of another machine.
                            ("nms8250-carnivore2 CALDERA The load stops", "no game file is in games/CALDERA/")):
            with self.subTest(line=line), self.assertRaisesRegex(games.ListError, error):
                self.failures(line + "\n")

    def test_the_shipped_lists_read_on_each_machine(self):
        names = gamefile.game_names()
        for machine in msx.user_machines():
            for path in (games.OPENMSX_FAILURES, games.SNAPCAS_FAILURES):
                games.read_failures(path, machine, names)

    def test_the_hash_of_a_result_holds_the_dos_files_and_openmsxs_version(self):
        folder = support.temp(self)
        with open(os.path.join(folder, "NEXTOR.SYS"), "wb") as f:
            f.write(b"2.11")
        first = games.tools_hash(folder, "openMSX 22.0")
        self.assertEqual(games.tools_hash(folder, "openMSX 22.0"), first)
        self.assertNotEqual(games.tools_hash(folder, "openMSX 22.1"), first)
        with open(os.path.join(folder, "NEXTOR.SYS"), "wb") as f:
            f.write(b"2.12")
        self.assertNotEqual(games.tools_hash(folder, "openMSX 22.0"), first)


def passed():
    return pipeline.Result(None, 0, pipeline.PASS, False, None, "/images/GAME.SNP")


def failed(message, transient=False):
    return pipeline.Result("check", 2 if transient else 3, message, transient, None, None)


REBOOT = "point 3: fail:  the machine rebooted"


class Run(unittest.TestCase):
    """games.py's run over four game files that the test writes, one of them
    a compilation's program, with the result that the test gives each."""

    NAMES = ["ALPHA", "BETA", "GAMMA", "PACK/DELTA"]

    def setUp(self):
        top = support.temp(self)
        self.games = os.path.join(top, "games")
        self.downloads = os.path.join(top, "downloads")
        self.reports = os.path.join(top, "out")
        self.dos = os.path.join(top, "dos")
        self.lists = {name: os.path.join(top, name + "-failures.txt") for name in ("openmsx", "snapcas")}
        for folder in (self.downloads, self.dos):
            os.makedirs(folder)
        open(os.path.join(self.dos, "NEXTOR.SYS"), "w").close()
        for name in self.NAMES:
            tape = name.split("/")[-1] + ".CAS"
            support.game_folder(os.path.join(self.games, name), f"cas {tape}\n")
            with open(os.path.join(self.downloads, tape), "wb") as f:
                f.write(support.BASIC_TAPE)
        self.listed()
        # Each game's result, which the tests change, the games that ran, and
        # the passes whose image images/ lacks.
        self.results = {name: passed() for name in self.NAMES}
        self.ran, self.no_image, self.tools = [], set(), "tools"

        def run_game(machine, name, dos):
            self.assertEqual((machine, dos), (MACHINE, self.dos))
            self.ran.append(name)
            return self.results[name]
        for patch in (mock.patch.object(games, "GAMES", self.games), mock.patch.object(games, "REPORTS", self.reports),
                      mock.patch.object(games, "OPENMSX_FAILURES", self.lists["openmsx"]),
                      mock.patch.object(games, "SNAPCAS_FAILURES", self.lists["snapcas"]),
                      mock.patch.object(gamefile, "DOWNLOADS", self.downloads),
                      mock.patch.object(gamefile, "game_names", return_value=list(self.NAMES)),
                      mock.patch.object(msx, "check_firmware"), mock.patch.object(msx, "version", return_value="22.0"),
                      mock.patch.object(games, "tools_hash", side_effect=lambda dos, version: self.tools),
                      mock.patch.object(games, "image_missing", side_effect=lambda m, name, game: name in self.no_image),
                      mock.patch.object(games, "run_game", side_effect=run_game)):
            patch.start()
            self.addCleanup(patch.stop)

    def listed(self, openmsx=(), snapcas=()):
        """Writes the two lists: the folders that each holds for the machine."""
        for name, folders in (("openmsx", openmsx), ("snapcas", snapcas)):
            with open(self.lists[name], "w") as f:
                f.write("# A list.\n" + "".join(f"{MACHINE} {folder} What fails\n" for folder in folders))

    def run_games(self, *args):
        """Runs games.py: its exit status, what it printed, and the games
        that ran, in order."""
        self.ran.clear()
        out, err = io.StringIO(), io.StringIO()
        argv = ["games.py", MACHINE, "--dos", self.dos, "--workers", "1", *args]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = games.main()
        return status, out.getvalue(), err.getvalue(), sorted(self.ran)

    def report(self):
        with open(os.path.join(self.reports, MACHINE + ".txt")) as f:
            return f.read()

    def test_the_failures_are_printed_in_three_groups_and_only_a_new_one_fails_the_run(self):
        self.results.update({"BETA": failed("capture: the load ran for more than 3600 seconds"),
                             "GAMMA": failed(REBOOT), "PACK/DELTA": failed("point 1: fail")})
        self.listed(openmsx=["BETA"], snapcas=["GAMMA"])
        status, out, err, ran = self.run_games()
        self.assertEqual((status, err, ran), (3, "", self.NAMES))
        lines = out.splitlines()
        self.assertEqual(lines[0], f"{MACHINE}: 0 unchanged, 4 to run, 0 without their tapes in downloads/")
        self.assertEqual(lines[5:], [
            f"1 of 4 game files pass; the results are in {os.path.join(self.reports, MACHINE + '.txt')}",
            "These game files fail in openMSX itself, as tests/openmsx-failures.txt lists:",
            "  BETA: capture: the load ran for more than 3600 seconds",
            "These game files fail because of snapcas, as tests/snapcas-failures.txt lists:",
            "  GAMMA: " + REBOOT,
            "These game files fail, and neither list holds them:",
            "  PACK/DELTA: point 1: fail"])
        self.assertEqual(self.report(), "ALPHA\tpoint 1: pass\nBETA\tcapture: the load ran for more than 3600 seconds\n"
                         f"GAMMA\t{REBOOT}\nPACK/DELTA\tpoint 1: fail\n")

    def test_the_run_passes_when_every_failure_is_in_a_list(self):
        self.results.update({"BETA": failed("point 1: fail"), "GAMMA": failed(REBOOT)})
        self.listed(openmsx=["BETA"], snapcas=["GAMMA"])
        status, out, _, _ = self.run_games()
        self.assertEqual(status, 0)
        self.assertIn("2 of 4 game files pass", out)
        self.assertNotIn("neither list", out)
        # With no failure, no group is printed.
        self.results.update({"BETA": passed(), "GAMMA": passed()})
        self.listed()
        status, out, _, _ = self.run_games("--full")
        self.assertEqual((status, out.splitlines()[5:]), (0, [
            f"4 of 4 game files pass; the results are in {os.path.join(self.reports, MACHINE + '.txt')}"]))

    def test_a_listed_game_file_that_passes_now_is_named_for_its_line_to_go(self):
        self.listed(openmsx=["BETA"], snapcas=["GAMMA", "PACK/DELTA"])
        self.results["PACK/DELTA"] = failed(REBOOT)
        status, out, _, _ = self.run_games()
        self.assertEqual(status, 0)
        self.assertRegex(out, r"In \S*openmsx-failures.txt, but passing now: BETA\n")
        self.assertRegex(out, r"In \S*snapcas-failures.txt, but passing now: GAMMA\n")

    def test_a_list_that_cannot_be_read_stops_the_run_before_any_game(self):
        with open(self.lists["snapcas"], "a") as f:
            f.write(f"{MACHINE} OMEGA What fails\n")
        status, out, err, ran = self.run_games()
        self.assertEqual((status, out, ran), (1, "", []))
        self.assertRegex(err, r"^games.py: \S*snapcas-failures.txt:2: no game file is in games/OMEGA/\n$")
        self.listed(openmsx=["BETA", "GAMMA"], snapcas=["GAMMA"])
        status, out, err, ran = self.run_games()
        self.assertEqual((status, out, err, ran),
                         (1, "", f"games.py: GAMMA is in both lists of failures for {MACHINE}\n", []))

    def test_what_stops_every_game_stops_the_run_before_it_starts(self):
        with mock.patch.object(msx, "check_firmware", side_effect=msx.MachineError("needs SDMAPPER.ROM")):
            self.assertEqual(self.run_games()[::2], (1, "games.py: needs SDMAPPER.ROM\n"))
        os.remove(os.path.join(self.dos, "NEXTOR.SYS"))
        status, _, err, ran = self.run_games()
        self.assertEqual((status, ran), (1, []))
        self.assertIn("no DOS system files", err)
        with mock.patch.object(sys, "argv", ["games.py", "no-such-machine"]), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(games.main(), 1)
        self.assertIn("no-such-machine.txt: no such machine file", err.getvalue())

    def test_a_game_file_whose_inputs_are_unchanged_is_not_run_again(self):
        self.results["BETA"] = failed(REBOOT)
        self.assertEqual(self.run_games()[3], self.NAMES)
        first = self.report()
        status, out, _, ran = self.run_games()
        self.assertEqual((status, ran), (3, []))
        self.assertEqual(out.splitlines()[0], f"{MACHINE}: 4 unchanged, 0 to run, 0 without their tapes in downloads/")
        # The kept results are the report's, and the failure still fails the run.
        self.assertEqual(self.report(), first)
        self.assertIn("  BETA: " + REBOOT, out)

    def test_a_changed_input_runs_its_game_file_again(self):
        self.run_games()
        with open(os.path.join(self.games, "BETA", "game.txt"), "a") as f:
            f.write("snapshot at 100\n")
        self.assertEqual(self.run_games()[3], ["BETA"])
        with open(os.path.join(self.downloads, "GAMMA.CAS"), "ab") as f:
            f.write(b"\0")
        self.assertEqual(self.run_games()[3], ["GAMMA"])
        # A machine's game file is an input of its machine only.
        with open(os.path.join(self.games, "ALPHA", MACHINE + ".txt"), "w") as f:
            f.write("capture vg8020\n")
        self.assertEqual(self.run_games()[3], ["ALPHA"])
        self.assertEqual(self.run_games()[3], [])
        # The code, the DOS files and openMSX's version are inputs of every
        # game file, and --full runs them all whatever their inputs.
        self.tools = "other tools"
        self.assertEqual(self.run_games()[3], self.NAMES)
        self.assertEqual(self.run_games()[3], [])
        self.assertEqual(self.run_games("--full")[3], self.NAMES)

    def test_a_result_of_a_run_that_broke_is_not_kept(self):
        broke = "check.py: openMSX stopped before the report's end; see out"
        self.results["BETA"] = failed(broke, transient=True)
        status, out, _, ran = self.run_games()
        self.assertEqual((status, ran), (3, self.NAMES))
        self.assertRegex(out, rf"\d/4  BETA  {broke}  \(not kept\)\n")
        self.assertNotIn("(not kept)", out.replace("BETA  " + broke + "  (not kept)", ""))
        # The report holds it, and the cache does not, so it runs again.
        self.assertIn("BETA\t" + broke + "\n", self.report())
        with open(os.path.join(self.reports, MACHINE + ".txt.cache")) as f:
            self.assertEqual([line.split("\t")[0] for line in f], ["ALPHA", "GAMMA", "PACK/DELTA"])
        self.results["BETA"] = passed()
        status, out, _, ran = self.run_games()
        self.assertEqual((status, ran), (0, ["BETA"]))
        self.assertEqual(self.run_games()[3], [])

    def test_a_pass_whose_image_is_gone_runs_again(self):
        self.results["BETA"] = failed(REBOOT)
        self.run_games()
        self.no_image = {"ALPHA", "BETA"}
        # A failure has no image in images/ to look for.
        self.assertEqual(self.run_games()[3], ["ALPHA"])

    def test_a_game_file_without_its_tape_is_not_run_and_fails(self):
        os.remove(os.path.join(self.downloads, "DELTA.CAS"))
        status, out, _, ran = self.run_games()
        self.assertEqual((status, ran), (3, ["ALPHA", "BETA", "GAMMA"]))
        self.assertEqual(out.splitlines()[0], f"{MACHINE}: 0 unchanged, 3 to run, 1 without their tapes in downloads/")
        self.assertIn("  PACK/DELTA: no DELTA.CAS in downloads/\n", out)
        self.assertIn("PACK/DELTA\tno DELTA.CAS in downloads/\n", self.report())

    def test_a_game_file_that_cannot_be_read_is_not_run_and_fails(self):
        with open(os.path.join(self.games, "GAMMA", "game.txt"), "a") as f:
            f.write("speed 1\n")
        status, out, _, ran = self.run_games()
        self.assertEqual((status, ran), (3, ["ALPHA", "BETA", "PACK/DELTA"]))
        self.assertRegex(out, r"  GAMMA: \S*game.txt:2: unknown key speed\n")

    def test_a_program_that_prints_no_result_is_a_run_that_broke(self):
        # run_game gives what pipeline.py printed to pipeline.read_result.
        result = pipeline.read_result(1, "", "Traceback (most recent call last):\nValueError: bad\n")
        self.results["ALPHA"] = result
        status, out, _, _ = self.run_games()
        self.assertEqual(status, 3)
        self.assertIn("ALPHA  ValueError: bad  (not kept)\n", out)


if __name__ == "__main__":
    unittest.main()
