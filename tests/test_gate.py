"""The gate: what makes an image pass (docs/INTERNALS.md, Check). check.py
passes an image only when its report holds all four points as passed, and it
tells a check that fails from a run that broke. The tests give check.py the
reports and the ends of openMSX, on a game whose snapshot they write, and
start no openMSX. The check's Tcl runs in tests/test_check.py. Pure tier."""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

import support
import build
import check
import gamefile
import msx
from snapshot import Snapshot

MACHINE = support.VG8020
PASSES = "point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: pass\n"


class Report(unittest.TestCase):
    """check.py's reading of a report's text."""

    def test_a_report_gives_the_exit_status(self):
        self.assertEqual(check.verdict("point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: pass\n"), 0)
        self.assertEqual(check.verdict("point 1: fail\n  RAM 1-x-2 differs at 8000\n"), 3)
        self.assertEqual(check.verdict("point 1: pass\npoint 2: pass\npoint 3: fail\npoint 4: pass\n"), 3)
        # openMSX left the report after point 1.
        self.assertEqual(check.verdict("point 1: pass\n"), 2)
        # An error of check.tcl ended it at point 3.
        self.assertEqual(check.verdict("point 1: pass\npoint 3: fail\n  check: no such variable\n"), 3)

    def test_only_a_report_with_all_four_points_passes(self):
        for report in ("", "point 1: pass\n", "point 1: pass\npoint 2: pass\n",
                       "point 1: pass\npoint 2: pass\npoint 3: pass\n",
                       "point 2: pass\npoint 3: pass\npoint 4: pass\n",
                       "point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: fail\n",
                       # A passed point in a failed point's lines is no point.
                       "point 1: fail\n  point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: pass\n",
                       "point 1: pass point 2: pass point 3: pass point 4: pass\n"):
            with self.subTest(report=report):
                self.assertNotEqual(check.verdict(report), 0)
        for point in (1, 2, 3, 4):
            failed = PASSES.replace(f"point {point}: pass", f"point {point}: fail\n  why")
            self.assertEqual(check.verdict(failed), 3, failed)
        # A point that passes can hold notes, as point 3 does for a reset.
        self.assertEqual(check.verdict(PASSES.replace("point 3: pass\n", "point 3: pass\n  the machine resets\n")), 0)

    def test_a_report_gives_its_points_with_what_failed_them(self):
        report = ("point 1: pass\npoint 2: fail\n  the game writes FCE1h\n  the game writes FCE2h\n"
                  "point 3: pass\npoint 4: pass\n")
        self.assertEqual(check.points(report), [(1, True, []), (2, False, ["  the game writes FCE1h",
                                                                           "  the game writes FCE2h"]),
                                                (3, True, []), (4, True, [])])
        # A line before the first point belongs to no point.
        self.assertEqual(check.points("a note\npoint 1: fail\n"), [(None, False, ["a note"]), (1, False, [])])
        self.assertEqual(check.points(""), [])

    def test_the_stop_address_needs_the_symbols_of_this_snapcas_com(self):
        com = bytes(16) + bytes([0xCD, 0x00, 0x02]) + bytes(8)
        folder = support.temp(self)
        symbols = os.path.join(folder, "snapcas.sym")
        with open(symbols, "w") as f:
            f.write("print: EQU 0x00000200\nstart: EQU 0x00000100\nstop_message: EQU 0x00000110\n")
        self.assertEqual(check.stop_address(com, symbols), "272 205 0 2")
        # Another assembly's symbols, and no symbols.
        self.assertEqual(check.stop_address(bytes(32), symbols), "")
        self.assertEqual(check.stop_address(com, os.path.join(folder, "none.sym")), "")

    def test_the_stop_address_of_this_build_is_found(self):
        with open(support.COM, "rb") as f:
            com = f.read()
        restorer = support.symbols("snapcas")
        address, *code = check.stop_address(com, check.SYMBOLS).split()
        self.assertEqual(int(address), restorer["stop_message"])
        self.assertEqual([int(b) for b in code], [0xCD, restorer["print"] & 0xFF, restorer["print"] >> 8])

    def test_the_captures_reset_after_the_snapshot_is_read_from_its_log(self):
        folder = support.snapshot(support.temp(self))

        def reset(log):
            with open(os.path.join(folder, "log.txt"), "w") as f:
                f.write(log)
            return check.capture_reset(Snapshot(folder))
        self.assertEqual(reset("0.00 typed RUN\n45.92 snapshot at an interrupt's entry\n"), "")
        self.assertEqual(reset("3.10 the game reset the machine\n45.92 snapshot at an interrupt's entry\n"), "")
        self.assertEqual(reset("45.92 snapshot at an interrupt's entry\n54.62 the game reset the machine\n"
                               "60.00 the game reset the machine\n"), "8.7")
        # A reset after the check's 60 seconds does not count.
        self.assertEqual(reset("10.00 snapshot at TAPION's entry\n70.00 the game reset the machine\n"), "")

    def test_the_builds_facts_are_read_under_their_names(self):
        folder = support.temp(self)
        with open(os.path.join(folder, "build.txt"), "w") as f:
            f.write("# What the check takes from the build.\nservice 1\ntail 61414 25 3 21\nfree 64713 64904\n"
                    "patched 3-x-2 16 17\npatched 3-x-3 0 1\npart 64737 64769 64760 0\ncpos 16384 16390\nended 456 464\n")
        self.assertEqual(check.read_facts(folder), {
            "service": "1", "tail": "61414 25 3 21", "free": "64713 64904", "patched": "3-x-2 16 17 3-x-3 0 1",
            "part": "64737 64769 64760 0", "moved": "", "cpos": "16384 16390", "ended": "456 464"})
        # A build.txt without the tape service, or of an older build.
        with open(os.path.join(folder, "build.txt"), "w") as f:
            f.write("service 0\ntail 61414 25 3 21\n")
        self.assertEqual(check.read_facts(folder)["ended"], "")


class Gate(unittest.TestCase):
    """check.py on a built image, with openMSX's run replaced by its end: the
    report that it leaves, its exit status, or its error."""

    def setUp(self):
        self.folder = support.snapshot_game(os.path.join(support.temp(self), "GAME"), MACHINE)
        build.write_image(self.folder, MACHINE, self.folder)
        self.out = gamefile.out_folder(MACHINE, self.folder)
        self.report = os.path.join(self.out, "check", "report.txt")
        self.dos = support.temp(self)
        open(os.path.join(self.dos, "NEXTOR.SYS"), "w").close()
        # A home of the test's own, for the check's savestates.
        self.home = support.temp(self)
        os.makedirs(os.path.join(self.home, "savestates"))
        for patch in (mock.patch.dict(os.environ, OPENMSX_HOME=self.home), mock.patch.object(msx, "make_disk")):
            patch.start()
            self.addCleanup(patch.stop)

    def left(self, report, stderr="", savestates=()):
        """A run of openMSX that leaves a report, or none, and savestates,
        and ends with status 0."""
        def run(args, script, timeout):
            if report is not None:
                with open(self.report, "w") as f:
                    f.write(report)
            for name in savestates:
                open(os.path.join(self.home, "savestates", f"snapcas-check-{os.getpid()}-{name}.oms"), "w").close()
            return stderr
        return mock.patch.object(msx, "run", side_effect=run)

    def check(self):
        return check.check(self.folder, MACHINE, self.dos)

    def main(self):
        """check.py as a program: its exit status, and what it prints."""
        out, err = io.StringIO(), io.StringIO()
        argv = ["check.py", self.folder, MACHINE, "--dos", self.dos]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = check.main()
        return status, out.getvalue(), err.getvalue()

    def test_a_report_whose_four_points_pass_passes(self):
        with self.left(PASSES):
            self.assertEqual(self.check(), (0, PASSES))
            self.assertEqual(self.main(), (0, PASSES, ""))

    def test_a_point_that_fails_gives_exit_status_3(self):
        for point in (1, 2, 3, 4):
            report = PASSES.replace(f"point {point}: pass\n", f"point {point}: fail\n  what failed it\n")
            with self.subTest(point=point), self.left(report):
                self.assertEqual(self.check(), (3, report))
                self.assertEqual(self.main(), (3, report, ""))
        # The restorer refused the image: point 1 fails, and no point follows.
        refused = "point 1: fail\n  the restorer stopped: GAME.SNP: made for another machine\n"
        with self.left(refused):
            self.assertEqual(self.main(), (3, refused, ""))

    def test_a_report_with_only_point_1_does_not_pass(self):
        # openMSX ended after the restore, before the 60 seconds of points 2
        # to 4: the run broke, and the image is not checked.
        for report in ("point 1: pass\n", "point 1: pass\npoint 2: pass\n", "point 1: pass\npoint 2: pass\npoint 3: pass\n"):
            with self.subTest(report=report), self.left(report, "script error: boom\n"):
                with self.assertRaises(msx.Failure) as failed:
                    self.check()
                e = failed.exception
                self.assertEqual((e.status, e.broke, e.output), (2, True, report))
                self.assertEqual(e.error, "check.py: openMSX stopped before the report's end; see "
                                 f"{os.path.dirname(self.report)}; openMSX's last output: script error: boom")
                status, out, err = self.main()
                self.assertEqual((status, out), (2, report))
                self.assertIn("openMSX stopped before the report's end", err)

    def test_a_run_without_a_report_broke(self):
        with self.left(None, "Fatal\n"), self.assertRaises(msx.Failure) as failed:
            self.check()
        e = failed.exception
        self.assertEqual((e.status, e.broke, e.output), (2, True, ""))
        self.assertIn("check.py: openMSX stopped before the report; see ", e.error)
        self.assertTrue(e.error.endswith("; openMSX's last output: Fatal"))
        # An earlier check's report does not stand in for this run's.
        with self.left(PASSES):
            self.check()
        with self.left(None), self.assertRaises(msx.Failure):
            self.check()

    def test_an_openmsx_that_ends_with_another_status_than_0_is_a_failure(self):
        # Whatever the report holds: an error of the script can come after
        # the last point.
        def ended(status, stderr=""):
            def run(command, **options):
                with open(self.report, "w") as f:
                    f.write(PASSES)
                return subprocess.CompletedProcess(command, status, stderr=stderr)
            return mock.patch.object(msx.subprocess, "run", side_effect=run)
        for patch, error in (
                (ended(1, "script error: boom\n"), "check.py: openMSX failed: openMSX ended with exit status 1; "
                                                   "openMSX's last output: script error: boom"),
                (ended(3), "check.py: openMSX failed: openMSX ended with exit status 3"),
                (ended(-9), "check.py: openMSX failed: openMSX was stopped by signal 9"),
                (ended(0, "Fatal error: Couldn't find ROM file\n"),
                 "check.py: openMSX failed: Fatal error: Couldn't find ROM file"),
                (mock.patch.object(msx.subprocess, "run", side_effect=subprocess.TimeoutExpired("openmsx", 600)),
                 "check.py: openMSX failed: Command 'openmsx' timed out after 600 seconds")):
            with self.subTest(error=error), patch:
                with self.assertRaises(msx.Failure) as failed:
                    self.check()
                self.assertEqual((failed.exception.status, failed.exception.broke, failed.exception.error),
                                 (2, True, error))
                status, out, err = self.main()
                self.assertEqual((status, out, err), (2, "", error + "\n"))

    def test_an_error_in_the_input_files_stops_with_status_1_before_openmsx(self):
        def no_image():
            os.remove(os.path.join(self.out, "GAME.SNP"))

        def no_dos():
            os.remove(os.path.join(self.dos, "NEXTOR.SYS"))

        def no_snapshot():
            os.remove(os.path.join(self.out, "snap", "state.txt"))

        def no_tail():
            with open(os.path.join(self.out, "build.txt"), "w") as f:
                f.write("service 0\n")
        for change, error in ((no_image, "GAME.SNP: no image; run build.py first"),
                              (no_dos, "no DOS system files"), (no_snapshot, "state.txt"),
                              (no_tail, "build.txt: no tail line; run build.py again")):
            self.setUp()
            change()
            with self.subTest(error=error), mock.patch.object(msx, "run") as run:
                with self.assertRaises(msx.Failure) as failed:
                    self.check()
                self.assertEqual((failed.exception.status, failed.exception.broke), (1, False))
                self.assertRegex(failed.exception.error, "^check.py: .*" + error)
                run.assert_not_called()
        with mock.patch.object(msx, "run") as run:
            with self.assertRaises(msx.Failure) as failed:
                check.check(self.folder, "no-such-machine", self.dos)
            self.assertEqual(failed.exception.status, 1)
            run.assert_not_called()

    def test_a_disk_that_openmsx_does_not_write_is_a_failure(self):
        for broke in (True, False):
            with self.subTest(broke=broke), self.left(PASSES), \
                    mock.patch.object(msx, "make_disk", side_effect=msx.DiskError("disk.dsk: no room", broke)):
                with self.assertRaises(msx.Failure) as failed:
                    self.check()
                self.assertEqual((failed.exception.status, failed.exception.broke, failed.exception.error),
                                 (2, broke, "check.py: disk.dsk: no room"))

    def test_the_savestates_go_to_the_check_folder_and_none_stays_in_openmsxs_home(self):
        with self.left(PASSES, savestates=("10s", "60s")):
            self.check()
        self.assertEqual(os.listdir(os.path.join(self.home, "savestates")), [])
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.report))),
                         ["10s.oms", "60s.oms", "AUTOEXEC.BAT", "report.txt"])
        # A run that broke leaves none either, and another check's stay.
        other = os.path.join(self.home, "savestates", f"snapcas-check-{os.getpid()}0-10s.oms")
        open(other, "w").close()
        with self.left(None, savestates=("10s",)), self.assertRaises(msx.Failure):
            self.check()
        self.assertEqual(os.listdir(os.path.join(self.home, "savestates")), [os.path.basename(other)])

    def test_the_script_holds_the_images_name_and_the_snapshots_state(self):
        with self.left(PASSES) as run:
            self.check()
        (args, script), timeout = run.call_args.args, run.call_args.kwargs["timeout"]
        machine = msx.read_machine(msx.machine_path(MACHINE))
        self.assertEqual(args, [*machine.args, f"-{machine.disk}", os.path.join(self.out, "check", "disk.dsk")])
        self.assertEqual(timeout, check.TIMEOUT)
        for line in ("set ::C(name) {GAME}\n", f"set ::C(state) snapcas-check-{os.getpid()}\n", "set ::C(pages) 3\n",
                     "set ::C(service) {0}\n", "set ::C(capreset) {}\n", f"set ::C(tail) {{{0xF000 - 26} 25 3 21}}\n"):
            self.assertIn(line, script)
        self.assertIn(" sp F000 ", script)
        self.assertTrue(script.rstrip().endswith("{start_check}}"))
        with open(os.path.join(self.out, "check", "AUTOEXEC.BAT"), newline="") as f:
            self.assertEqual(f.read(), "SNAPCAS GAME\r\n")


if __name__ == "__main__":
    unittest.main()
