"""tools/msx.py without openMSX (docs/INTERNALS.md, The tools' code): machine
files, the DOS files' folders, the Tcl that it writes, a run's savestates, and
what it makes of openMSX's end, which the test gives. Runs in openMSX are in
tests/test_harness.py. Pure tier."""
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import support
import msx


class Msx(unittest.TestCase):
    def test_a_folder_with_glob_characters_gives_its_dos_files(self):
        with tempfile.TemporaryDirectory() as top:
            folder = os.path.join(top, "dos [2.11]")
            os.mkdir(folder)
            with self.assertRaisesRegex(OSError, "no DOS system files"):
                msx.dos_files(folder)
            open(os.path.join(folder, "NEXTOR.SYS"), "w").close()
            self.assertEqual(msx.dos_files(folder), [os.path.join(folder, "NEXTOR.SYS")])

    def test_a_machine_file_names_the_dos_that_it_boots(self):
        self.assertEqual(msx.read_machine(msx.machine_path("vg8235")).dos_files, "msxdos1")
        self.assertEqual(msx.read_machine(msx.machine_path("hbf700p-ram512k-msxdos2")).dos_files, "msxdos2")
        self.assertEqual(msx.read_machine(msx.machine_path("vg8020-carnivore2")).dos_files, "nextor")

    def test_a_press_line_presses_its_key_at_its_time_after_power_on(self):
        machine = msx.read_machine(msx.variant_path("hb75p"))
        self.assertIn("after time 10 {keymatrixdown 7 128; after time 0.1 [list keymatrixup 7 128]}", machine.args)
        self.assertIn("after time 8.5 {keymatrixdown 8 64; after time 0.1 [list keymatrixup 8 64]}", machine.args)

    def test_a_typed_text_reaches_tcl_as_hex(self):
        tcl = msx.tcl_type('BLOAD"$[x]",R\r')
        self.assertEqual(tcl, "type [binary format H* 424c4f414422245b785d222c520d]")

    def test_only_a_runs_own_savestates_are_removed(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, OPENMSX_HOME=home):
            os.makedirs(os.path.join(home, "savestates"))
            names = ["snapcas-check-12-10s.oms", "snapcas-check-12-60s.oms", "snapcas-check-123-10s.oms",
                     "snapcas-capture-12-wait.oms"]
            for name in names:
                open(os.path.join(home, "savestates", name), "w").close()
            msx.remove_savestates("snapcas-check-12")
            self.assertEqual(sorted(os.listdir(os.path.join(home, "savestates"))), sorted(names[2:]))

    def test_an_openmsx_that_does_not_start_stops_the_disk_with_one_error(self):
        # OPENMSX names the program, and check.py and try.py print this error.
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, OPENMSX="/no/such/openmsx"):
            with self.assertRaisesRegex(msx.DiskError, "openMSX did not write the disk image: .*/no/such/openmsx") as e:
                msx.make_disk(os.path.join(folder, "disk.dsk"), [])
            # The error says nothing of the game, so its result is not kept.
            self.assertTrue(e.exception.broke)

    def test_a_tcl_word_holds_any_text(self):
        self.assertEqual(msx.tcl_word("/Users/me/out dir/snap"), "{/Users/me/out dir/snap}")
        self.assertEqual(msx.tcl_word('RUN"CAS:"'), '{RUN"CAS:"}')
        # Braces cannot hold a last backslash or an unbalanced brace, so these
        # go in double quotes, with a backslash before what Tcl reads there.
        self.assertEqual(msx.tcl_word("C:\\snapcas\\out\\"), '"C:\\\\snapcas\\\\out\\\\"')
        self.assertEqual(msx.tcl_word("a{b"), '"a\\{b"')
        self.assertEqual(msx.tcl_word('a}"$[b]\n'), '"a\\}\\"\\$\\[b\\]\\n"')

    def test_a_test_machines_file_names_its_dos_files(self):
        for machine, folder in (("test/nms8250-128k", "msxdos2"), ("test/nms8250-512k", "msxdos2"),
                                ("test/hc90a-msxdos2", "msxdos2"), ("test/nms8250-dos1", "msxdos1"),
                                ("test/nms8250-4m-dos1", "msxdos1"), ("test/nms8250-4m-ram4mb-dos1", "msxdos1")):
            self.assertEqual(msx.read_machine(msx.machine_path(machine)).dos_files, folder, machine)
            self.assertEqual(support.dos_of(machine), os.path.join(support.DOS_DIR, folder))
        self.assertEqual(support.dos_of(support.PHC28S), support.NEXTOR)

    def test_a_machine_file_gives_its_arguments_its_disk_and_its_keys(self):
        folder = support.temp(self)

        def machine(text):
            path = os.path.join(folder, "machine.txt")
            with open(path, "w") as f:
                f.write(text)
            return msx.read_machine(path)
        read = machine("# A machine (MSX1, 64 KB) with a cartridge. More.\nopenmsx -machine A -ext B\ndisk diska 360\n"
                       'boot "DefConfig" space\ndos "A:\\>" B\nfirmware extensions/x.xml\nhold del 6\n'
                       "variant vg8020\n")
        self.assertEqual((read.disk, read.disk_size, read.boot, read.dos, read.dos_files, read.firmware, read.variants),
                         ("diska", 360, [("DefConfig", "space")], ("A:\\>", "B"), "nextor", ["extensions/x.xml"],
                          ["vg8020"]))
        self.assertEqual(read.args, ["-machine", "A", "-ext", "B", "-command",
                                     "keymatrixdown 8 8; after time 6 [list keymatrixup 8 8]"])
        self.assertEqual(msx.description(read.path), "A machine (MSX1, 64 KB) with a cartridge")
        self.assertEqual(msx.boot_steps(read),
                         "{{DefConfig} {keymatrixdown 8 1; after time 0.1 [list keymatrixup 8 1]}}")
        for text, error in (("disk hda\n", "machine.txt: needs one openmsx line and one disk line"),
                            ("openmsx -machine A\n", "needs one openmsx line and one disk line"),
                            ("openmsx -machine A\ndisk hda 1440\n", "machine.txt:2: a disk is 360 or 720 KB"),
                            ("openmsx -machine A\ndisk hda\nboot text nokey\n", "machine.txt:3: cannot read this line"),
                            ("openmsx -machine A\ndisk hda\ndosfiles nextor\n", "machine.txt:3: cannot read this line"),
                            ("openmsx -machine A\ndisk hda\nvariant none\n", r"machine.txt:3: .*none.txt does not exist")):
            with self.subTest(text=text), self.assertRaisesRegex(msx.MachineError, error):
                machine(text)

    def test_every_machine_file_reads(self):
        for folder in (msx.MACHINES, msx.VARIANTS, os.path.join(msx.MACHINES, "test")):
            for name in sorted(os.listdir(folder)):
                if name.endswith(".txt"):
                    with self.subTest(file=name):
                        msx.read_machine(os.path.join(folder, name))

    def ended(self, status, stderr=""):
        """msx.run with an openMSX that ends with the status, after it printed
        stderr."""
        def run(command, **options):
            return subprocess.CompletedProcess(command, status, stderr=stderr)
        with mock.patch.object(msx.subprocess, "run", side_effect=run) as started:
            try:
                return msx.run(["-machine", "A"], "stop\n", timeout=60)
            finally:
                self.command = started.call_args.args[0]

    def test_a_run_gives_what_openmsx_printed_and_is_muted_without_a_window(self):
        self.assertEqual(self.ended(0, "a warning\n"), "a warning\n")
        self.assertEqual(self.command[:3], [msx.openmsx(), "-machine", "A"])
        self.assertEqual(self.command[-2:], ["-command", "set renderer none; set throttle off; set mute on"])
        self.assertIn("-script", self.command)

    def test_an_openmsx_that_ends_with_another_status_than_0_is_an_error(self):
        for status, stderr, error in (
                (1, "script error: boom\n", "openMSX ended with exit status 1; openMSX's last output: script error: boom"),
                (3, "", "openMSX ended with exit status 3$"),
                (-15, "", "openMSX was stopped by signal 15"),
                (0, "Fatal error: Couldn't find ROM file for \"MSX BIOS\"\n", "^Fatal error: Couldn't find ROM file")):
            with self.subTest(status=status), self.assertRaisesRegex(msx.MachineError, error):
                self.ended(status, stderr)

    def test_the_last_output_is_openmsxs_last_three_lines_on_one(self):
        self.assertEqual(msx.last_output(""), "")
        self.assertEqual(msx.last_output("one\n\n two \nthree\nfour\n"), "; openMSX's last output: two | three | four")

    def test_the_script_goes_after_the_prelude_under_a_catch(self):
        folder = support.temp(self)
        main = msx.script_files(folder, "nosuchcommand\n")
        with open(main) as f:
            text = f.read()
        self.assertTrue(text.startswith(msx.tcl("tcl/prelude.tcl")))
        self.assertIn("if {[catch {source {" + os.path.join(folder, "script.tcl") + "}} e]", text)
        self.assertTrue(text.rstrip().endswith("exit 1\n}"))
        # With its window, openMSX prints the error and stays.
        self.assertNotIn("exit 1", msx.script_files(folder, "nosuchcommand\n", window=True).replace(
            msx.tcl("tcl/prelude.tcl"), ""))

    def test_a_failure_prints_its_output_and_its_error(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = msx.Failure(2, "check.py: openMSX failed", True, "point 1: pass\n").show()
        self.assertEqual((status, out.getvalue(), err.getvalue()), (2, "point 1: pass\n", "check.py: openMSX failed\n"))


if __name__ == "__main__":
    unittest.main()
