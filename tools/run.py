#!/usr/bin/env python3
"""Start openMSX, with its window, as a machine file describes, with a disk of
the DOS files and the given files, to try them by hand.

Usage: run.py <machine> --dos <dir> <file>...

<machine> is a path below machines/ without .txt. <dir> holds the DOS system
files. The disk image goes to out/run/<machine>/disk.dsk. Pass the boot menu
by hand, as on the real machine.
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msx  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Start openMSX with a machine file and a disk of files.")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    parser.add_argument("files", nargs="+", help="the files to put on the disk")
    args = parser.parse_args()
    try:
        machine = msx.read_machine(os.path.join(ROOT, "machines", args.machine + ".txt"))
    except (OSError, msx.MachineError) as e:
        print(f"run.py: {e}", file=sys.stderr)
        return 1
    folder = os.path.join(ROOT, "out", "run", args.machine)
    os.makedirs(folder, exist_ok=True)
    disk = os.path.join(folder, "disk.dsk")
    msx.make_disk(disk, sorted(glob.glob(os.path.join(args.dos, "*"))) + args.files)
    print(f"{disk}: {', '.join(os.path.basename(f) for f in args.files)}")
    return subprocess.run(["openmsx", *machine.args, f"-{machine.disk}", disk]).returncode


if __name__ == "__main__":
    sys.exit(main())
