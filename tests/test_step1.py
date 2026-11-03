"""Step 1 (docs/PLAN.md): the build, the disk image, the boot keys and the
screen reading, with the first SNAPCAS.COM on phc28s-ram64k-carnivore2."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import msx  # noqa: E402

WORK = os.path.join(ROOT, "out", "test", "step1")
NEXTOR = os.environ.get("NEXTOR_DIR", os.path.join(ROOT, "out", "dl", "nextor"))


class Step1(unittest.TestCase):
    def test_usage_and_errors(self):
        os.makedirs(WORK, exist_ok=True)
        autoexec = os.path.join(WORK, "AUTOEXEC.BAT")
        with open(autoexec, "w", newline="") as f:
            f.write("SNAPCAS\r\nSNAPCAS NONE\r\nSNAPCAS SHORT\r\nSNAPCAS BAD\r\nSNAPCAS OLD\r\n")
        bad = os.path.join(WORK, "BAD.SNP")
        with open(bad, "wb") as f:
            f.write(b"SNAPDISK" + bytes(4088))
        old = os.path.join(WORK, "OLD.SNP")
        with open(old, "wb") as f:
            f.write(b"SNAPCAS2" + bytes(4088))
        short = os.path.join(WORK, "SHORT.SNP")
        with open(short, "wb") as f:
            f.write(b"SNA")
        disk = os.path.join(WORK, "disk.dsk")
        msx.make_disk(disk, [os.path.join(NEXTOR, "NEXTOR.SYS"),
                             os.path.join(NEXTOR, "COMMAND2.COM"),
                             os.path.join(ROOT, "bin", "SNAPCAS.COM"),
                             autoexec, bad, old, short])
        machine = msx.read_machine(msx.machine_path("phc28s-ram64k-carnivore2"))
        screen = msx.screen_after(machine, disk, "OLD.SNP: made",
                                  os.path.join(WORK, "screen.txt"))
        self.assertIn("Usage: SNAPCAS <game>", screen)
        self.assertIn("Restores <game>.SNP, a snapcas image.", screen)
        self.assertIn("NONE.SNP not found", screen)
        self.assertIn("SHORT.SNP is not a snapcas image", screen)
        self.assertIn("BAD.SNP is not a snapcas image", screen)
        # The message wraps at the screen's width.
        self.assertIn("OLD.SNP: made for another version of SNAPCAS.COM", " ".join(screen.split()))


if __name__ == "__main__":
    unittest.main()
