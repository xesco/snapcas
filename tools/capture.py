#!/usr/bin/env python3
"""Load a cassette game in openMSX and save its snapshot (docs/INTERNALS.md,
Capture).

Usage: capture.py <game> <machine> --tapes <dir> [--capture <variant>]

<game> is a folder below games/, or the path of a folder, that holds
game.txt. <machine> is a machine file's name below machines/ without .txt.
<dir> holds the tape files. The snapshot goes to snap/ in the game's work folder. A
game file's capture line, or --capture, names a capture variant in
machines/capture/ to load the game on: the user's machine without a cartridge
that the game's loader trips over.

Exit status: 0 on success, 1 for an error in the input files, 2 when openMSX
fails or a wait times out.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import tape  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import patches  # noqa: E402

# Real seconds that one capture may take: the load's 3600 emulated seconds
# run much faster with the throttle off.
TIMEOUT = 1800
# The slot patches that one capture may add, each with a run of its own.
MAX_SLOT_PATCHES = 16


def tcl_list(items):
    return "{" + " ".join(items) + "}"


def key_tcl(kind, value):
    if kind == "key":
        return msx.press(value)
    # The text as hex, so that the command needs no quoting inside the keys
    # list's braces.
    return f"type [binary format H* {value.encode('latin-1').hex()}]"


def load_command(game, data):
    """The load command: the game file's load line, or else the type of the
    first block of the tape file's bytes, which must be a standard block then
    (INTERNALS.md, Tape files). None when neither gives one."""
    if game.load:
        return game.load
    blocks = tape.read(game.tape, data)
    if blocks and not blocks[0].standard:
        return None
    return tape.load_command(tape.service(blocks))


def settings(game, machine, tape_path, data, snap, side2_path=None, side2=b""):
    """The Tcl settings. data and side2 are the tape files' bytes, of which
    the capture uses the tape service's tapes (INTERNALS.md, Tape files)."""
    keys = [(t, key_tcl(kind, value)) for t, kind, value in game.keys]
    tries = ([game.continue_key] if game.continue_key else []) + ["space", "return"]
    command = load_command(game, data)
    data = tape.service(tape.read(game.tape, data))
    side2 = tape.service(tape.read(game.side2, side2)) if game.side2 else b""
    s = {
        "snap": msx.tcl_word(snap),
        "boot": "{" + msx.boot_steps(machine) + "}",
        # On a machine that boots DOS from its own disk, BASIC comes from DOS.
        "afterboot": "{" + msx.at_prompt(machine, "BASIC", "wait_ok") + "}",
        "tape": msx.tcl_word(tape_path),
        "cmd": msx.tcl_word(command),
        "cload": "1" if command == "CLOAD" else "0",
        "headers": tcl_list(str(h) for h in tape.headers(data)),
        "needed": str(tape.needed_end(data)),
        # Side 2 follows side 1, padded to a multiple of 8 bytes, as in the
        # tape service's positions.
        "side2tape": "{}" if side2_path is None else msx.tcl_word(side2_path),
        "s1len": str(tape.side2_start(len(data))),
        "headers2": tcl_list(str(h + tape.side2_start(len(data))) for h in tape.headers(side2)),
        "nosvc": "1" if game.service == "no" else "0",
        "keys": tcl_list(f"{t} {msx.tcl_word(tcl)}" for t, tcl in keys),
        "lastkey": str(max([t for t, _ in keys], default=0)),
        # A loader can read the keyboard rarely, so the keys that may
        # continue a load are held for 0.5 seconds.
        "tries": tcl_list("{" + k + " " + msx.tcl_word(msx.press(k, 0.5)) + "}" for k in tries),
        "snapat": "{}" if game.snapshot_at is None else str(game.snapshot_at),
        "state": f"snapcas-capture-{os.getpid()}",
        # openMSX's home, whose savestates/ folder the rewinds read.
        "home": msx.tcl_word(msx.home()),
    }
    return "".join(f"set ::S({k}) {v}\n" for k, v in s.items())


def capture_once(game, machine, tape_path, tapes_dir, snap, procedures, found):
    """Runs the capture once, on the tape files as played with the patches
    found so far (build.played_tapes). Returns "" for a snapshot, "patch" for a
    new patch, or the error."""
    data, side2 = build.played_tapes(game, tapes_dir, found)
    shutil.rmtree(snap, ignore_errors=True)
    os.makedirs(snap)
    if found or game.start or any(patch.page == "side1" for patch in game.patches):
        # The tape that the capture loads, with the side1 patches.
        tape_path = os.path.join(snap, "side1" + os.path.splitext(game.tape)[1].lower())
        with open(tape_path, "wb") as f:
            f.write(data)
    side2_path = None
    if game.side2:
        # Side 2, with the side2 patches, for the capture to insert when the
        # game reads past side 1's end.
        side2_path = os.path.join(snap, "side2" + os.path.splitext(game.side2)[1].lower())
        with open(side2_path, "wb") as f:
            f.write(side2)
    script = settings(game, machine, tape_path, bytes(data), snap, side2_path, bytes(side2)) + procedures + "\nstep1\n"
    try:
        msx.run(machine.args, script, timeout=TIMEOUT)
    except Exception as e:
        return f"capture.py: openMSX failed: {e}"
    error = os.path.join(snap, "error.txt")
    if os.path.exists(error):
        with open(error) as f:
            return f.read().strip()
    if os.path.exists(os.path.join(snap, "newpatch.txt")):
        return "patch"
    if not os.path.exists(os.path.join(snap, "state.txt")):
        return f"capture.py: openMSX stopped before the snapshot; see {snap}"
    return ""


def main():
    parser = argparse.ArgumentParser(description="Load a cassette game in openMSX and save its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--tapes", required=True, help="the folder that holds the tape files, CAS or TSX")
    parser.add_argument("--capture", help="a capture variant in machines/capture/ to load the game on, in "
                        "place of the game file's capture line")
    args = parser.parse_args()

    try:
        game = gamefile.read_game(gamefile.game_folder(args.game), args.machine)
        variant = args.capture or game.capture
        machine = msx.read_machine(msx.variant_path(variant) if variant else msx.machine_path(args.machine))
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"capture.py: {e}", file=sys.stderr)
        return 1
    tape_path = os.path.abspath(os.path.join(args.tapes, game.tape))
    try:
        data, side2 = build.played_tapes(game, args.tapes)
    except OSError as e:
        print(f"capture.py: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    except (build.BuildError, tape.TapeError) as e:
        print(f"capture.py: {e}", file=sys.stderr)
        return 1
    try:
        command = load_command(game, data)
        first = tape.read(game.tape, data)[:1]
        if game.side2:
            tape.read(game.side2, side2)
    except tape.TapeError as e:
        print(f"capture.py: {e}", file=sys.stderr)
        return 1
    if command is None and first and not first[0].standard:
        print(f"capture.py: {tape_path}: the first block is a non-standard block, so the game "
              "file needs a load line", file=sys.stderr)
        return 1
    if command is None:
        print(f"capture.py: {tape_path}: the first block is not a binary file, a BASIC "
              "program or an ASCII program", file=sys.stderr)
        return 1

    snap = os.path.join(gamefile.out_folder(args.machine, game.folder), "snap")
    procedures = (patches.slots.tcl_settings() + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/capture.tcl")
                  + msx.tcl("patches/slots.tcl") + patches.ramsearch.tcl_settings()
                  + msx.tcl("patches/ramsearch.tcl"))
    # The patches of the tape that the capture finds (INTERNALS.md, Slot patches,
    # The RAM search patch): each one stops the capture, which runs again on the
    # patched tape.
    found = []
    for run in range(MAX_SLOT_PATCHES + 1):
        result = capture_once(game, machine, tape_path, args.tapes, snap, procedures, found)
        if result != "patch":
            break
        # One line for a slot patch, one for each copy of the RAM search.
        with open(os.path.join(snap, "newpatch.txt")) as f:
            for line in f.read().splitlines():
                found.append(gamefile.read_patch(line.split()[1:], f"{snap}/newpatch.txt"))
                found[-1].line = line
    else:
        print(f"capture.py: the capture found more than {MAX_SLOT_PATCHES} slot patches", file=sys.stderr)
        return 2
    if result:
        print(result, file=sys.stderr)
        return 2
    with open(os.path.join(snap, "patches.txt"), "w") as f:
        f.write("# The capture's patches of the tape (docs/INTERNALS.md, Slot patches, The RAM search patch).\n")
        f.writelines(p.line + "\n" for p in found)
    print(snap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
