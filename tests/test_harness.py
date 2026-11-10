"""The harness: openMSX as tools/msx.py runs it, with the prelude's procedures
(docs/INTERNALS.md, The tools' code, and docs/PLAN.md, step 1). The runs are
in openMSX's C-BIOS machine, which needs no system ROMs: an error of a script
must end openMSX and reach the caller, and never leave it waiting. Emulator
tier."""
import os
import unittest
import unittest.mock

import support
import msx


class Run(unittest.TestCase):
    def test_openmsxs_fatal_error_reaches_the_caller(self):
        with self.assertRaisesRegex(msx.MachineError, "Fatal error:.*NoSuchMachine"):
            msx.run(["-machine", "NoSuchMachine"], "exit\n", timeout=60)

    def test_an_openmsx_that_ends_with_another_status_than_0_reaches_the_caller(self):
        with self.assertRaisesRegex(msx.MachineError, "openMSX ended with exit status 3"):
            msx.run(["-machine", msx.DISK_MACHINE], "exit 3\n", timeout=60)

    def test_an_error_of_a_script_ends_openmsx_and_reaches_the_caller(self):
        # While openMSX reads the script, and in a callback later.
        for script in ("nosuchcommand\nexit\n", "later 1 {nosuchcommand}\n"):
            with self.subTest(script=script):
                with self.assertRaisesRegex(msx.MachineError, 'exit status 1; openMSX\'s last output: script error: '
                                            'invalid command name "nosuchcommand"'):
                    msx.run(["-machine", msx.DISK_MACHINE], script, timeout=60)

    def test_a_wait_for_the_screen_ends_at_its_deadline(self):
        for script, error in (("safe {wait_screen {no such text} 2 {error found} {error {not found}}}\n", "not found"),
                              ("safe {boot {{{no such text} {}}} {error booted} 3}\n",
                               "the boot text 'no such text' did not appear within 3 seconds"),
                              ("safe {at_prompt 5a3e 00 {error typed} 2}\n",
                               "DOS's prompt 'Z>' did not appear within 2 seconds")):
            with self.subTest(script=script):
                with self.assertRaisesRegex(msx.MachineError, "script error: " + error):
                    msx.run(["-machine", msx.DISK_MACHINE], script, timeout=60)

    def test_stop_ends_the_run_and_no_callback_runs_after_it(self):
        folder = support.temp(self)

        def touch(name):
            return "close [open " + msx.tcl_word(os.path.join(folder, name)) + " w]"
        support.cbios(f"later 1 {{ {touch('before')}; stop; {touch('after')} }}\n"
                      f"later 1 {{ {touch('same')} }}\nlater 2 {{ {touch('later')} }}\n", timeout=60)
        # stop leaves its callback, and safe runs none once the run is stopping.
        self.assertEqual(os.listdir(folder), ["before"])

    def test_a_script_that_stops_while_openmsx_reads_it_ends_with_status_0(self):
        out = os.path.join(support.temp(self), "out.txt")
        support.cbios(f"set f [open {msx.tcl_word(out)} w]; puts $f [expr {{6 * 7}}]; close $f\nstop\n", timeout=60)
        with open(out) as f:
            self.assertEqual(f.read(), "42\n")

    def test_an_error_after_a_callback_that_failed_is_printed_once(self):
        # The first error ends the run, and the callback after it does not
        # replace it.
        with self.assertRaisesRegex(msx.MachineError, "script error: first$"):
            support.cbios("later 1 {error first}\nlater 1 {error second}\nlater 2 {error third}\n", timeout=60)


class Setup(unittest.TestCase):
    """The tests' own setup (docs/PLAN.md, Test setup)."""

    def test_the_makefile_lists_each_tape_of_the_tests(self):
        with open(os.path.join(support.ROOT, "Makefile")) as f:
            text = f.read().split("TEST_TAPES := $(addprefix tests/tapes/,", 1)[1].split(")", 1)[0]
        self.assertEqual(sorted(text.replace("\\", " ").split()), sorted(os.listdir(support.TAPES)))

    def test_each_module_of_the_pure_tier_is_a_test_module(self):
        modules = {name[:-3] for name in os.listdir(support.HERE) if name.startswith("test_") and name.endswith(".py")}
        self.assertEqual(set(support.PURE) - modules, set())
        self.assertNotIn(__name__, support.PURE)

    def test_a_test_of_the_pure_tier_cannot_ask_for_a_tape_or_for_openmsx(self):
        with unittest.mock.patch.object(support, "PURE_RUN", True):
            for ask in (lambda: support.tape("CALDERO.CAS"), lambda: support.cbios("stop\n"),
                        lambda: support.work("harness"), lambda: support.make_image("GAME", support.PHC28S)):
                with self.assertRaisesRegex(AssertionError, "a test of the pure tier"):
                    ask()

    def test_a_missing_tape_is_an_error_of_the_setup(self):
        with self.assertRaisesRegex(support.SetupError, "tests/tapes/NOTAPE.CAS is missing"):
            support.tape("NOTAPE.CAS")
        self.assertFalse(issubclass(support.SetupError, unittest.SkipTest))


if __name__ == "__main__":
    unittest.main()
