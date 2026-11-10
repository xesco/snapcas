"""tools/pipeline.py: the steps of one game's image on one machine, the trials
of the capture variants, and their result (docs/INTERNALS.md, The tools'
code). The tests give the steps' ends, or openMSX's, and start no openMSX.
Pure tier."""
import json
import os
import subprocess
import unittest
from unittest import mock

import support
import capture
import gamefile
import msx
import pipeline

GAMES = os.path.join(support.ROOT, "games")


PASSES = "point 1: pass\npoint 2: pass\npoint 3: pass\npoint 4: pass\n"


class Pipeline(unittest.TestCase):
    """pipeline.py's result, from steps that the test gives, without a run
    (INTERNALS.md, The tools' code)."""

    def result(self, name, status, error="", broke=False, output=""):
        return pipeline.result(pipeline.Step(name, status, error, broke, output))

    def test_a_failed_step_gives_its_name_its_status_and_its_error(self):
        error = "capture: the CPU is halted with no interrupt, at 1234"
        result = self.result("capture", 2, error)
        self.assertEqual(result, pipeline.Result("capture", 2, error, False, None, None))
        self.assertFalse(result.passed)
        result = self.result("build", 1, "build.py: the tape needs 20 segments, more than 16")
        self.assertEqual((result.step, result.status, result.transient), ("build", 1, False))
        # An error of several lines gives its last one.
        error = "capture: the load ran for more than 3600 seconds"
        self.assertEqual(self.result("capture", 2, "a warning\n" + error).message, error)

    def test_a_check_that_passes_gives_the_pass_and_no_failed_step(self):
        result = self.result("check", 0, output=PASSES)
        self.assertEqual((result.step, result.status, result.message, result.transient),
                         (None, 0, pipeline.PASS, False))
        self.assertTrue(result.passed)
        # Without the check, the steps pass with no message.
        self.assertEqual(self.result("build", 0, output="3 records").message, "")

    def test_a_check_that_fails_gives_its_failed_point_with_its_first_line(self):
        report = ("point 1: pass\npoint 2: fail\n  the game writes FCE1h, in the tape service's part of page 3\n"
                  "  the game writes FCE2h\npoint 3: pass\npoint 4: fail\n  the screen shows Overflow in 130\n")
        result = self.result("check", 3, output=report)
        self.assertEqual((result.step, result.status, result.transient), ("check", 3, False))
        self.assertEqual(result.message, "point 2: fail:  the game writes FCE1h, in the tape service's part of page 3")
        # Point 1 fails alone, and gives the report's first line.
        self.assertEqual(self.result("check", 3, output="point 1: fail\n  RAM 3-x-2 differs at 8000\n").message,
                         "point 1: fail")

    def test_a_run_that_broke_is_transient(self):
        result = self.result("check", 2, "check.py: openMSX stopped before the report's end; see out", True,
                             "point 1: pass\n")
        self.assertEqual((result.step, result.status, result.transient), ("check", 2, True))
        self.assertEqual(result.message, "check.py: openMSX stopped before the report's end; see out")

    def test_the_tools_say_when_a_run_broke(self):
        # An openMSX that fails or times out, and one that the capture's
        # script ends with its own error.
        # The game's tape is beside its game.txt, and holds a BASIC program.
        folder = support.snapshot_game(os.path.join(support.temp(self), "GAME"))
        args = (folder, "vg8020-carnivore2", folder)
        with mock.patch.object(msx, "run", side_effect=subprocess.TimeoutExpired("openmsx", 1800)):
            with self.assertRaises(msx.Failure) as failed:
                capture.capture(*args)
        self.assertEqual((failed.exception.status, failed.exception.broke), (2, True))
        self.assertIn("capture.py: openMSX failed: Command 'openmsx' timed out", failed.exception.error)
        with mock.patch.object(msx, "run", return_value=""):
            with self.assertRaises(msx.Failure) as failed:
                capture.capture(*args)
        self.assertEqual((failed.exception.status, failed.exception.broke), (2, True))
        self.assertIn("openMSX stopped before the snapshot", failed.exception.error)

        def halted(machine_args, script, timeout):
            with open(os.path.join(folder, "vg8020-carnivore2", "snap", "error.txt"), "w") as f:
                f.write("capture: the CPU is halted with no interrupt, at 1234\n")
            return ""
        with mock.patch.object(msx, "run", side_effect=halted):
            with mock.patch.object(pipeline, "tapes_folder", return_value=folder):
                step = pipeline.run_step("capture", pipeline.capture_step, folder, "vg8020-carnivore2", None)
        self.assertEqual(step, pipeline.Step("capture", 2, "capture: the CPU is halted with no interrupt, at 1234",
                                             False, ""))
        # An error in the input files is status 1, and the game's own.
        step = pipeline.run_step("capture", pipeline.capture_step, folder, "no-such-machine", None)
        self.assertEqual((step.status, step.broke), (1, False))

    def test_the_program_prints_the_result_that_the_games_run_reads(self):
        result = pipeline.Result("check", 3, "point 3: fail:  the machine rebooted", False, None, None)
        self.assertEqual(pipeline.read_result(0, json.dumps(result._asdict()) + "\n", ""), result)
        passed = pipeline.Result(None, 0, pipeline.PASS, False, "vg8020", "/images/GAME.SNP")
        self.assertEqual(pipeline.read_result(0, json.dumps(passed._asdict()), ""), passed)

    def test_a_program_that_ends_without_a_result_is_transient(self):
        # A Python error, a signal, and output that is no result.
        for status, output, error, message in (
                (1, "", "Traceback (most recent call last):\n  File \"x.py\"\nValueError: bad\n", "ValueError: bad"),
                (-9, "", "", "pipeline.py failed"),
                (0, "not a result\n", "", "pipeline.py failed")):
            with self.subTest(status=status, output=output):
                result = pipeline.read_result(status, output, error)
                self.assertEqual((result.message, result.transient, result.passed), (message, True, False))

    def test_the_variants_are_tried_unless_the_capture_stops_at_its_input(self):
        game, machine = os.path.join(GAMES, "CALDERO"), "vg8020-carnivore2"
        failed_check = pipeline.Step("check", 3, "", False, "point 1: fail\n")
        passed = pipeline.Step("check", 0, "", False, PASSES)
        tried = []
        with mock.patch.object(pipeline, "steps") as steps, \
                mock.patch.object(gamefile, "publish", return_value="/images/CALDERO.SNP") as publish:
            # An error in the input files, which a variant has too.
            steps.side_effect = [pipeline.Step("capture", 1, "capture.py: no tape", False, "")]
            result = pipeline.run(game, machine, "dos", try_variants=True, trying=tried.append)
            self.assertEqual((result.step, result.status, result.image, steps.call_count), ("capture", 1, None, 1))
            # A failed check: the variant, then the game file's own image
            # again, without the check. The result is the first failure.
            steps.reset_mock()
            steps.side_effect = [failed_check, failed_check, pipeline.Step("build", 0, "", False, "3 records")]
            result = pipeline.run(game, machine, "dos", try_variants=True, trying=tried.append)
            self.assertEqual((result.step, result.status, result.variant, result.image), ("check", 3, None, None))
            self.assertEqual(steps.call_args_list, [mock.call(game, machine, "dos", show=None),
                                                    mock.call(game, machine, "dos", "vg8020", None),
                                                    mock.call(game, machine, show=None)])
            self.assertEqual(tried, ["vg8020"])
            publish.assert_not_called()
            # A failed build has a snapshot that another capture can change,
            # and the variant that passes is in the result.
            steps.reset_mock()
            steps.side_effect = [pipeline.Step("build", 1, "build.py: no room", False, ""), passed]
            result = pipeline.run(game, machine, "dos", try_variants=True)
            self.assertEqual(result, pipeline.Result(None, 0, pipeline.PASS, False, "vg8020", "/images/CALDERO.SNP"))
            # The games run tries no variant.
            steps.reset_mock()
            steps.side_effect = [failed_check]
            self.assertEqual(pipeline.run(game, machine, "dos").status, 3)
            self.assertEqual(steps.call_count, 1)

    def test_the_steps_stop_at_the_first_that_fails(self):
        shown = []
        with mock.patch.object(pipeline.capture, "capture"), \
                mock.patch.object(pipeline.build, "write_image",
                                  side_effect=msx.Failure(1, "build.py: no room")) as write_image, \
                mock.patch.object(pipeline.check, "check") as check:
            step = pipeline.steps("GAME", "machine", "dos", "variant", shown.append)
        self.assertEqual(step, pipeline.Step("build", 1, "build.py: no room", False, ""))
        self.assertEqual(shown, [pipeline.Step("capture", 0, "", False, ""), step])
        write_image.assert_called_once_with("GAME", "machine", gamefile.DOWNLOADS, variant="variant")
        check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
