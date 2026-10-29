#!/usr/bin/env python3
"""Load a cassette game in openMSX and save its snapshot (docs/DESIGN.md,
Capture).

Usage: capture.py <game> <machine> --cas <dir>

<game> is a folder below games/, or the path of a folder, that holds
game.txt. <machine> is a path below machines/ without .txt. <dir> holds the
CAS files. The snapshot goes to out/<machine>/<game>/snap/. A game file's
capture line names another machine file to load the game on: the user's
machine without a cartridge that the game's loader trips over.

Exit status: 0 on success, 1 for an error in the input files, 2 when openMSX
fails or a wait times out.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build  # noqa: E402
import cas  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402

# Real seconds that one capture may take: the load's 3600 emulated seconds
# run much faster with the throttle off.
TIMEOUT = 1800


def tcl_list(items):
    return "{" + " ".join(items) + "}"


def key_tcl(kind, value):
    if kind == "key":
        return msx.press(value)
    # The text as hex, so that the command needs no quoting inside the keys
    # list's braces.
    return f"type [binary format H* {value.encode('latin-1').hex()}]"


def game_folder(game):
    if os.sep in game or os.path.isdir(game):
        return os.path.abspath(game)
    return os.path.join(ROOT, "games", game)


def settings(game, machine, cas_path, data, snap):
    keys = [(t, key_tcl(kind, value)) for t, kind, value in game.keys]
    tries = ([game.continue_key] if game.continue_key else []) + ["space", "return"]
    command = cas.load_command(data)
    s = {
        "snap": msx.tcl_word(snap),
        "boot": tcl_list("{" + msx.tcl_word(text) + " " + msx.tcl_word(msx.press(key)) + "}"
                         for text, key in machine.boot),
        # On a machine that boots DOS from its own disk, BASIC comes from DOS.
        "afterboot": "{" + msx.at_prompt(machine, "BASIC", "wait_ok") + "}",
        "cas": msx.tcl_word(cas_path),
        "cmd": msx.tcl_word(command),
        "cload": "1" if command == "CLOAD" else "0",
        "headers": tcl_list(str(h) for h in cas.headers(data)),
        "needed": str(cas.needed_end(data)),
        "side2": "1" if game.side2 else "0",
        "nosvc": "1" if game.service_no else "0",
        "keys": tcl_list(f"{t} {msx.tcl_word(tcl)}" for t, tcl in keys),
        "lastkey": str(max([t for t, _ in keys], default=0)),
        # A loader can read the keyboard rarely, so the keys that may
        # continue a load are held for 0.5 seconds.
        "tries": tcl_list("{" + k + " " + msx.tcl_word(msx.press(k, 0.5)) + "}" for k in tries),
        "snapat": "{}" if game.snapshot_at is None else str(game.snapshot_at),
        "state": f"snapcas-capture-{os.getpid()}",
    }
    return "".join(f"set ::S({k}) {v}\n" for k, v in s.items())


def main():
    parser = argparse.ArgumentParser(description="Load a cassette game in openMSX and save its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--cas", required=True, help="the folder that holds the CAS files")
    args = parser.parse_args()

    try:
        game = gamefile.read_game(game_folder(args.game), args.machine)
        machine = msx.read_machine(os.path.join(ROOT, "machines", (game.capture or args.machine) + ".txt"))
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"capture.py: {e}", file=sys.stderr)
        return 1
    cas_path = os.path.abspath(os.path.join(args.cas, game.cas))
    try:
        data = bytearray(build.read_tapes(game, args.cas)[0])
        for patch in game.patches:
            if patch.page == "side1":
                build.apply_patch(patch, data, f"side1:{patch.offset:X}")
    except OSError as e:
        print(f"capture.py: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    except build.BuildError as e:
        print(f"capture.py: {e}", file=sys.stderr)
        return 1
    data = bytes(data)
    if cas.load_command(data) is None:
        print(f"capture.py: {cas_path}: the first block is not a binary file, a BASIC "
              "program or an ASCII program", file=sys.stderr)
        return 1

    name = os.path.basename(os.path.normpath(game.folder))
    snap = os.path.join(ROOT, "out", args.machine, name, "snap")
    shutil.rmtree(snap, ignore_errors=True)
    os.makedirs(snap)
    if any(patch.page == "side1" for patch in game.patches):
        # The tape that the capture loads, with the side1 patches.
        cas_path = os.path.join(snap, "side1.cas")
        with open(cas_path, "wb") as f:
            f.write(data)
    with open(os.path.join(HERE, "capture.tcl")) as f:
        procedures = f.read()
    script = settings(game, machine, cas_path, data, snap) + procedures + "\nstep1\n"
    try:
        msx.run(machine.args, script, timeout=TIMEOUT)
    except Exception as e:
        print(f"capture.py: openMSX failed: {e}", file=sys.stderr)
        return 2
    error = os.path.join(snap, "error.txt")
    if os.path.exists(error):
        with open(error) as f:
            print(f.read().strip(), file=sys.stderr)
        return 2
    if not os.path.exists(os.path.join(snap, "state.txt")):
        print(f"capture.py: openMSX stopped before the snapshot; see {snap}", file=sys.stderr)
        return 2
    print(snap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
