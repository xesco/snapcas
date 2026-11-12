"""The snapcas command, snapcas.py (docs/CLI.md): its verbs list and machines,
how snap finds the game and the machine, what snap prints for the steps' ends
that the test gives, and the tools as programs without their arguments. No
test here starts openMSX: snap makes images in tests/test_snap.py. Pure
tier."""
import argparse
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import support
import capture
import gamefile
import msx
import pipeline
import snapcas as snapcas_py

ROOT = support.ROOT
COMMAND = os.path.join(ROOT, "snapcas.py")
snapcas = support.command


class Command(unittest.TestCase):
    def test_the_command_is_executable(self):
        self.assertTrue(os.access(COMMAND, os.X_OK))

    def test_without_arguments_it_prints_its_help(self):
        result = snapcas()
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: snapcas.py", result.stdout)
        self.assertIn("machines", result.stdout)

    def test_an_unknown_verb_stops_with_status_1(self):
        result = snapcas("play")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid choice", result.stderr)

    def test_a_tools_command_line_error_stops_with_status_1(self):
        for tool in ("build.py", "capture.py", "check.py", "games.py", "plain.py", "try.py"):
            with self.subTest(tool=tool):
                result = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", tool)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("usage:", result.stderr)

    def test_an_error_in_the_captures_input_stops_with_status_1_and_one_line(self):
        # An error that the capture meets only when it runs, as a patch of
        # its own that does not fit the tape.
        folder = support.snapshot_game(os.path.join(support.temp(self), "GAME"))
        argv = ["capture.py", folder, "vg8020-carnivore2", "--tapes", folder]
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
                capture, "capture_once", side_effect=gamefile.GameFileError("the bytes are not the patch's")), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(capture.main(), 1)
        self.assertEqual(stderr.getvalue(), "capture.py: the bytes are not the patch's\n")


class List(unittest.TestCase):
    def test_a_text_finds_the_games_whose_folder_or_title_holds_it(self):
        result = snapcas("list", "wall", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        folders = [line.split()[0] for line in result.stdout.splitlines()[:-1]]
        self.assertEqual(folders, ["SUPERMSX/THEWALL", "WALL-THE", "WALLBALL"])
        self.assertEqual(result.stdout.splitlines()[-1], "3 games")

    def test_without_all_it_leaves_out_the_compilations_programs_and_counts_them(self):
        lines = snapcas("list", "wall").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in lines[:-1]], ["WALL-THE", "WALLBALL"])
        self.assertEqual(lines[-1], "2 games, and 1 in compilations, which --all lists")

    def test_a_folder_of_a_games_name_below_the_current_folder_is_not_the_game(self):
        # As in images/<machine>/, where each game has a folder of its name.
        with tempfile.TemporaryDirectory() as folder:
            os.mkdir(os.path.join(folder, "GAUNTLET"))
            result = snapcas("list", "gauntlet", cwd=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GAUNTLET  Gauntlet (1986)(US Gold)", result.stdout)
            cwd = os.getcwd()
            os.chdir(folder)
            try:
                self.assertEqual(gamefile.game_folder("GAUNTLET"), os.path.join(ROOT, "games", "GAUNTLET"))
            finally:
                os.chdir(cwd)

    def test_a_text_matches_in_any_case(self):
        self.assertIn("GAUNTLET  Gauntlet (1986)(US Gold)", snapcas("list", "gAuNtLeT").stdout)

    def test_each_game_names_the_file_hunter_file_that_it_comes_from(self):
        self.assertIn("GAUNTLET  Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']\n", snapcas("list", "gauntlet").stdout)
        self.assertIn("001-ARIO  Turbo Pack A (1987)(Philips)(es) / 001-Aritmo.cas\n", snapcas("list", "aritmo", "--all").stdout)
        self.assertIn("PAC-MANI  Pac-Mania (Grandslam) (Zafiro) [BLOAD'CAS-',R] [_]\n",
                      snapcas("list", "pac-mani").stdout)
        self.assertIn("SUPERMSX/AFRICAFI  Super MSX n.23 (settembre 1989) - cas_23 / Africa Film\n",
                      snapcas("list", "africa", "--all").stdout)
        self.assertIn("ENGESOFT/ATHLETIC  Engesoft msxk-06 / Athletic Land (1984)(Konami)\n",
                      snapcas("list", "athletic", "--all").stdout)

    def test_a_compilations_name_finds_its_programs(self):
        self.assertEqual(snapcas("list", "super msx n.23", "--all").stdout.splitlines()[-1], "10 games")

    def test_without_a_text_it_lists_every_game_file(self):
        lines = snapcas("list", "--all").stdout.splitlines()
        total = len(gamefile.game_names()) + len(gamefile.custom_names())
        self.assertEqual(len(lines) - 1, total)
        self.assertEqual(lines[-1], f"{total} games")

    def test_without_a_text_or_all_it_lists_every_game_but_the_compilations_programs(self):
        lines = snapcas("list").stdout.splitlines()
        folders = [line.split()[0] for line in lines[:-1]]
        shipped = [folder for folder in folders if not folder.startswith("custom/")]
        self.assertFalse(any("/" in folder for folder in shipped))
        self.assertNotIn("001-ARIO", folders)
        self.assertIn("RUR-1", folders)
        self.assertIn("RUR-2", folders)
        hidden = len(gamefile.game_names()) - len(shipped)
        self.assertEqual(lines[-1], f"{len(folders)} games, and {hidden} in compilations, which --all lists")


class Machines(unittest.TestCase):
    def test_it_lists_the_user_machines_and_no_variant_or_test_machine(self):
        result = snapcas("machines")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [line.split()[0] for line in result.stdout.splitlines()]
        self.assertEqual(names, msx.user_machines())
        self.assertIn("phc28s-ram64k-carnivore2", names)
        self.assertNotIn("phc28s-ram64k", names)
        self.assertFalse(any(name.startswith("test/") for name in names))

    def test_each_machine_shows_its_first_comment_sentence(self):
        self.assertRegex(snapcas("machines").stdout,
                         r"vg8020-carnivore2 +Philips VG-8020 \(MSX1, 64 KB\) with a Carnivore2\n")


class Snap(unittest.TestCase):
    """snap's lookups, which stop before any openMSX run."""

    def test_a_text_that_is_not_a_games_name_stops(self):
        for text in ("gaunt", "no such game"):
            with self.subTest(text=text):
                result = snapcas("snap", text, "phc28s-ram64k-carnivore2")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'no game is named "{text}": snapcas.py list shows the games', result.stderr)

    def test_a_text_that_is_not_a_machines_name_stops(self):
        for text in ("phc28s", "vg8020", "msx3"):
            with self.subTest(text=text):
                result = snapcas("snap", "gauntlet", text)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'no machine is named "{text}": snapcas.py machines shows the machines', result.stderr)

    def test_dos_without_check_stops(self):
        result = snapcas("snap", "gauntlet", "phc28s-ram64k-carnivore2", "--dos", "dos")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--dos gives the DOS files for --check", result.stderr)

    def snap(self, steps):
        """Runs snap --check on Caldero with the steps' ends that the test
        gives, and returns its exit status and what it printed on standard
        output and on standard error."""
        args = argparse.Namespace(game="CALDERO", machine="vg8020-carnivore2", check=True, dos="dos")
        image = os.path.join(ROOT, "images", "vg8020-carnivore2", "CALDERO", "CALDERO.SNP")

        def run_step(name, tool, *args):
            return steps.pop(0)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(pipeline, "run_step", side_effect=run_step), \
                mock.patch.object(gamefile, "publish", return_value=image), \
                mock.patch.object(snapcas_py.download, "tapes"), mock.patch.object(msx, "check_firmware"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = snapcas_py.snap(args)
        self.assertEqual(steps, [])
        return status, out.getvalue().splitlines()[1:], err.getvalue().splitlines()

    CAPTURED = pipeline.Step("capture", 0, "", False, "")
    BUILT = pipeline.Step("build", 0, "", False, "3 records, 52 port writes, up to 3 free mapper segments")
    PASSED = pipeline.Step("check", 0, "", False, "point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: pass\n")
    REBOOTED = pipeline.Step("check", 3, "", False, "point 1: pass\npoint 2: pass\npoint 3: fail\n"
                             "  the machine rebooted\npoint 4: pass\n")

    def test_snap_prints_each_step_and_the_image(self):
        status, out, err = self.snap([self.CAPTURED, self.BUILT, self.PASSED])
        self.assertEqual((status, err), (0, []))
        self.assertEqual(out, ["capture   done",
                               "build     done: 3 records, 52 port writes, up to 3 free mapper segments",
                               "check     pass  the restored machine equals the snapshot",
                               "check     pass  the game does not write to the tape service in page 3",
                               "check     pass  the machine does not reboot",
                               "check     pass  the game does not stop at a BASIC error",
                               "image     images/vg8020-carnivore2/CALDERO/CALDERO.SNP"])

    def test_snap_stops_at_an_error_in_the_captures_input(self):
        # A variant reads the same files, so none is tried.
        status, out, err = self.snap([pipeline.Step("capture", 1, "capture.py: no tape", False, "")])
        self.assertEqual((status, out, err), (1, [], ["capture.py: no tape"]))

    def test_snap_tries_the_variants_and_names_the_one_that_passes(self):
        status, out, err = self.snap([self.CAPTURED, self.BUILT, self.REBOOTED,
                                      self.CAPTURED, self.BUILT, self.PASSED])
        self.assertEqual(status, 0)
        self.assertEqual(err, ["snapcas.py: trying the capture variant vg8020"])
        self.assertEqual(out[2:6], ["check     pass  the restored machine equals the snapshot",
                                    "check     pass  the game does not write to the tape service in page 3",
                                    "check     fail  the machine does not reboot",
                                    "                the machine rebooted"])
        self.assertEqual(out[-2:], ["image     images/vg8020-carnivore2/CALDERO/CALDERO.SNP",
                                    "snapcas.py: it passes, so the machine's game file needs: capture vg8020"])

    def test_snap_exits_with_the_first_failure_when_no_variant_passes(self):
        # A failed build has a snapshot that another capture can change, so
        # the variant is tried. Then the game file's own image is made again.
        failed = pipeline.Step("build", 1, "build.py: no room", False, "")
        status, out, err = self.snap([self.CAPTURED, failed, self.CAPTURED, self.BUILT, self.REBOOTED,
                                      self.CAPTURED, failed])
        self.assertEqual(status, 1)
        self.assertEqual(err, ["build.py: no room", "snapcas.py: trying the capture variant vg8020",
                               "build.py: no room"])
        self.assertNotIn("image", " ".join(out))

    def test_try_types_the_command_at_doss_prompt_with_the_preludes_deadline(self):
        # The module only: its openMSX has a window, so the tests do not run
        # it.
        spec = importlib.util.spec_from_file_location("try_py", os.path.join(ROOT, "tools", "try.py"))
        try_py = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(try_py)
        typed = b"SNAPCAS GAUNTLET\r".hex()
        for machine, dos, prompt, typed in (
                ("test/nms8250-dos1", ["MSXDOS.SYS", "COMMAND.COM"], "A>", typed),
                ("vg8020-carnivore2", ["NEXTOR.SYS", "COMMAND2.COM"], "A:\\>", typed),
                ("hb75p-mfrsd", ["NEXTOR.SYS", "COMMAND2.COM"], "A:\\>", b"B:\r".hex() + typed)):
            with self.subTest(machine=machine):
                read = msx.read_machine(msx.machine_path(machine))
                script = try_py.script(read, "GAUNTLET", [os.path.join("dos", name) for name in dos])
                self.assertEqual(script, f"safe {{boot {{{msx.boot_steps(read)}}} "
                                         f"{{at_prompt {prompt.encode().hex()} {typed} {{}}}}}}\n")

    def test_a_machines_missing_dos_files_stop_with_where_they_go(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(msx, "DOS", folder):
            with self.assertRaisesRegex(msx.MachineError, "test/nms8250-dos1 boots msxdos1: put its files in"):
                snapcas_py.dos_folder("test/nms8250-dos1")
            os.mkdir(os.path.join(folder, "msxdos1"))
            open(os.path.join(folder, "msxdos1", "MSXDOS.SYS"), "w").close()
            self.assertEqual(snapcas_py.dos_folder("test/nms8250-dos1"), os.path.join(folder, "msxdos1"))

    def test_a_machine_without_its_firmware_stops_and_names_make_firmware(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, OPENMSX_HOME=home)
            for verb in (("snap", "CALDERO", "fsa1-mfrsd"), ("try", "CALDERO", "vg8020-sdmapper")):
                with self.subTest(verb=verb):
                    result = snapcas(*verb, env=env)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("make firmware makes it", result.stderr)

    def test_snap_without_arguments_prints_its_help(self):
        result = snapcas("snap")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: snapcas.py snap", result.stdout)


if __name__ == "__main__":
    unittest.main()
