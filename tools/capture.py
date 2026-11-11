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

Exit status: 0 on success, 1 for an error in the command line or the input
files, 2 when openMSX fails or a wait times out.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tape  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import patches  # noqa: E402
from snapshot import Snapshot  # noqa: E402

# Real seconds that one capture may take: the load's 3600 emulated seconds
# run much faster with the throttle off.
TIMEOUT = 1800
# The slot patches that one capture may add, each with a run of its own.
MAX_SLOT_PATCHES = 16


def tcl_list(items):
    return "{" + " ".join(items) + "}"


def key_tcl(kind, value):
    return msx.press(value) if kind == "key" else msx.tcl_type(value)


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


def settings(game, machine, tape_path, data, snap, state, side2_path=None, side2=b""):
    """The Tcl settings. data and side2 are the tape files' bytes, of which
    the capture uses the tape service's tapes (INTERNALS.md, Tape files). snap
    is the snapshot's folder, and state starts the names of the capture's
    savestates."""
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
        "subkeep": "1" if game.subslots_keep else "0",
        "keys": tcl_list(f"{t} {msx.tcl_word(tcl)}" for t, tcl in keys),
        "lastkey": str(max([t for t, _ in keys], default=0)),
        # A loader can read the keyboard rarely, so the keys that may
        # continue a load are held for 0.5 seconds.
        "tries": tcl_list("{" + k + " " + msx.tcl_word(msx.press(k, 0.5)) + "}" for k in tries),
        "snapat": "{}" if game.snapshot_at is None else str(game.snapshot_at),
        "state": state,
        # openMSX's home, whose savestates/ folder holds the savestates.
        "home": msx.tcl_word(msx.home()),
    }
    return "".join(f"set ::S({k}) {v}\n" for k, v in s.items())


def capture_once(game, machine, tape_path, tapes_dir, snapshot, state, found):
    """Runs the capture once, on the tape files as played with the patches
    found so far (tape.played), into the folder of snapshot, a Snapshot.
    Returns the new patches that the capture stopped with, or None for a
    snapshot. Raises msx.Failure for a capture that fails, and an exception of
    INPUT_ERRORS for an error in the input files."""
    data, side2 = tape.played(game, tapes_dir, found)
    shutil.rmtree(snapshot.folder, ignore_errors=True)
    os.makedirs(snapshot.folder)
    if found or game.start or any(patch.side == 1 for patch in game.patches):
        # The tape that the capture loads, with the side1 patches.
        tape_path = snapshot.path("side1" + os.path.splitext(game.tape)[1].lower())
        with open(tape_path, "wb") as f:
            f.write(data)
    side2_path = None
    if game.side2:
        # Side 2, with the side2 patches, for the capture to insert when the
        # game reads past side 1's end.
        side2_path = snapshot.path("side2" + os.path.splitext(game.side2)[1].lower())
        with open(side2_path, "wb") as f:
            f.write(side2)
    # The settings, the procedures, the patch kinds, each with its settings
    # for these tape files, and the start.
    script = (settings(game, machine, tape_path, data, snapshot.folder, state, side2_path, side2)
              + msx.tcl("tcl/memory.tcl") + msx.tcl("tcl/capture.tcl")
              + patches.tcl(data, side2) + "\nsafe step1\n")
    try:
        stderr = msx.run(machine.args, script, timeout=TIMEOUT)
    except Exception as e:
        raise msx.Failure(2, f"capture.py: openMSX failed: {e}", broke=True)
    finally:
        # openMSX leaves the capture's savestates, also when it is stopped.
        msx.remove_savestates(state)
    error = snapshot.error()
    if error is not None:
        raise msx.Failure(2, error)
    new = snapshot.new_patches()
    if new is None and not os.path.exists(snapshot.path("state.txt")):
        raise msx.Failure(2, "capture.py: openMSX stopped before the snapshot; see "
                          f"{snapshot.folder}{msx.last_output(stderr)}", broke=True)
    return new


# What an error in the input files raises.
INPUT_ERRORS = (OSError, gamefile.GameFileError, msx.MachineError, tape.TapeError)


def input_error(e):
    """The one line that the capture prints for an error of INPUT_ERRORS."""
    if isinstance(e, OSError) and e.filename and e.strerror:
        return f"capture.py: {e.filename}: {e.strerror}"
    return f"capture.py: {e}"


def capture(game_arg, machine_name, tapes_dir, variant=None):
    """Loads a game in openMSX on a machine and saves its snapshot, as
    capture.py's arguments name them. variant is the capture variant to load
    the game on, in place of the game file's. Returns the snapshot's folder.
    Raises msx.Failure for a capture that fails."""
    try:
        game = gamefile.read_game(gamefile.game_folder(game_arg), machine_name)
        variant = variant or game.capture
        machine = msx.read_machine(msx.variant_path(variant) if variant else msx.machine_path(machine_name))
        tape_path = os.path.abspath(os.path.join(tapes_dir, game.tape))
        data, side2 = tape.played(game, tapes_dir)
        command = load_command(game, data)
        first = tape.read(game.tape, data)[:1]
        if game.side2:
            tape.read(game.side2, side2)
    except INPUT_ERRORS as e:
        raise msx.Failure(1, input_error(e))
    if command is None and first and not first[0].standard:
        raise msx.Failure(1, f"capture.py: {tape_path}: the first block is a non-standard block, so the game "
                          "file needs a load line")
    if command is None:
        raise msx.Failure(1, f"capture.py: {tape_path}: the first block is not a binary file, a BASIC "
                          "program or an ASCII program")

    snapshot = Snapshot(os.path.join(gamefile.out_folder(machine_name, game.folder), "snap"))
    # The savestates' names hold the process ID, so that captures can run side
    # by side. An earlier run with the same ID can have left some.
    state = f"snapcas-capture-{os.getpid()}"
    msx.remove_savestates(state)
    # The patches of the tape that the capture finds (INTERNALS.md, Slot patches,
    # The RAM search patch): each one stops the capture, which runs again on the
    # patched tape.
    found = []
    try:
        for _ in range(MAX_SLOT_PATCHES + 1):
            new = capture_once(game, machine, tape_path, tapes_dir, snapshot, state, found)
            if new is None:
                break
            found += new
        else:
            raise msx.Failure(2, f"capture.py: the capture found more than {MAX_SLOT_PATCHES} slot patches")
    except INPUT_ERRORS as e:
        raise msx.Failure(1, input_error(e))
    snapshot.write_patches(found)
    return snapshot.folder


def main():
    parser = msx.Parser(description="Load a cassette game in openMSX and save its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--tapes", required=True, help="the folder that holds the tape files, CAS or TSX")
    parser.add_argument("--capture", help="a capture variant in machines/capture/ to load the game on, in "
                        "place of the game file's capture line")
    args = parser.parse_args()
    try:
        print(capture(args.game, args.machine, args.tapes, args.capture))
    except msx.Failure as e:
        return e.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
