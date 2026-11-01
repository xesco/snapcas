#!/usr/bin/env python3
"""Make a game's snapcas image in one command: capture, build and, with --dos,
check (docs/DESIGN.md, Files and commands).

Usage: snapcas.py <game> <machine> --tapes <dir> [--dos <dir>]

<game>, <machine> and --tapes are as for capture.py, and --dos as for check.py.
The image goes to out/<machine>/<game>/<GAME>.SNP. When a step fails and the
game file names no capture machine, the steps run again on each capture
variant of the machine, and the first that passes gives the capture line for
the machine's game file.

Exit status: that of the first step that fails, or 0.
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402


def step(name, *args):
    """Runs one of the tools with its output shown, and returns its exit status."""
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, name), *args]).returncode


def steps(args, variant=None):
    """Captures, builds and, with --dos, checks the image, and returns the exit
    status of the first step that fails, or 0."""
    extra = ["--capture", variant] if variant else []
    for name, options in (("capture.py", ["--tapes", args.tapes, *extra]), ("build.py", ["--tapes", args.tapes])):
        status = step(name, args.game, args.machine, *options)
        if status != 0:
            return status
    if args.dos:
        return step("check.py", args.game, args.machine, "--dos", args.dos)
    return 0


def variants(machine):
    """The capture variants of a machine: the machine files beside it whose
    names start with its name and -, in the order of their names."""
    files = glob.glob(msx.machine_path(machine + "-*"))
    return sorted(os.path.relpath(f, msx.MACHINES)[:-4] for f in files)


def main():
    parser = argparse.ArgumentParser(description="Make a game's snapcas image: capture, build and check.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--tapes", required=True, help="the folder that holds the tape files, CAS or TSX")
    parser.add_argument("--dos", help="the folder that holds the DOS system files, to check the image in openMSX")
    args = parser.parse_args()

    status = steps(args)
    if status == 0:
        return 0
    try:
        game = gamefile.read_game(gamefile.game_folder(args.game), args.machine)
    except (OSError, gamefile.GameFileError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    if game.capture:
        return status
    for variant in variants(args.machine):
        print(f"snapcas.py: trying the capture variant {variant}", file=sys.stderr)
        if steps(args, variant) == 0:
            print(f"snapcas.py: it passes, so the machine's game file needs: capture {variant}")
            return 0
    if variants(args.machine):
        # Leaves the image of the game file's own lines.
        steps(args)
    return status


if __name__ == "__main__":
    sys.exit(main())
