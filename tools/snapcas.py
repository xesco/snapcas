#!/usr/bin/env python3
"""Make a game's snapcas image in one command: capture, build and, with --dos,
check (docs/DESIGN.md, Files and commands).

Usage: snapcas.py <game> <machine> --cas <dir> [--dos <dir>]

<game>, <machine> and --cas are as for capture.py, and --dos as for check.py.
The image goes to out/<machine>/<game>/<GAME>.SNP.

Exit status: that of the first step that fails, or 0.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(name, *args):
    """Runs one of the tools with its output shown, and returns its exit status."""
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, name), *args]).returncode


def main():
    parser = argparse.ArgumentParser(description="Make a game's snapcas image: capture, build and check.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--cas", required=True, help="the folder that holds the CAS files")
    parser.add_argument("--dos", help="the folder that holds the DOS system files, to check the image in openMSX")
    args = parser.parse_args()

    for name, extra in (("capture.py", ["--cas", args.cas]), ("build.py", ["--cas", args.cas])):
        status = step(name, args.game, args.machine, *extra)
        if status != 0:
            return status
    if args.dos:
        return step("check.py", args.game, args.machine, "--dos", args.dos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
