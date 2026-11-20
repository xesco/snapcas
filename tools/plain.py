#!/usr/bin/env python3
"""Load a game's tape in plain openMSX, without the capture's code, and print
the screen 60 emulated seconds after the tape's end, or "a graphics screen".

Usage: plain.py <game> <machine>

<game> and <machine> are as for capture.py, and the tape is side 1 in
downloads/. The run passes the machine's boot menu, waits for BASIC's Ok and
10 seconds more, as the capture does, and types the load command that the
capture would type, and RUN after a CLOAD once the tape has played. It plays
the tape as it is, from its start, without the game file's patch lines, keys
or side 2, so a game that needs them stops where its tape alone stops. The
screen goes to plain.txt in the game's work folder. A game that fails here as
it fails with snapcas fails in openMSX itself (docs/BUILD.md, step 9).

Exit status: 0 when the screen was read, 1 for an error in the input files,
2 when openMSX fails or stops before the screen.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import tape as tapes  # noqa: E402

# Emulated seconds: the wait after BASIC's Ok, and the time from the tape's end
# to the screen.
AFTER_BOOT = 10
AFTER_TAPE = 60


def main():
    parser = msx.Parser(description="Load a game's tape in plain openMSX and print the screen.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    args = parser.parse_args()
    try:
        folder = gamefile.game_folder(args.game)
        machine = msx.read_machine(msx.machine_path(args.machine))
        game = gamefile.read_game(folder, args.machine)
        tape = os.path.join(gamefile.DOWNLOADS, game.tape)
        with open(tape, "rb") as f:
            command = capture.load_command(game, f.read())
        if command is None:
            raise gamefile.GameFileError(f"{tape}: no load command; the game file needs a load line")
    except (OSError, gamefile.GameFileError, msx.MachineError, tapes.TapeError) as e:
        print(f"plain.py: {e}", file=sys.stderr)
        return 1
    work = gamefile.out_folder(args.machine, folder)
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "plain.txt")
    if os.path.exists(out):
        os.remove(out)
    settings = {
        "tape": msx.tcl_word(os.path.abspath(tape)),
        "load": msx.tcl_word((command + "\r").encode("latin-1").hex()),
        "run_after": msx.tcl_word("RUN\r".encode("latin-1").hex() if command == "CLOAD" else ""),
        "after_boot": str(AFTER_BOOT),
        "after_tape": str(AFTER_TAPE),
        "out": msx.tcl_word(out),
    }
    script = ("".join(f"set ::P({k}) {v}\n" for k, v in settings.items())
              + msx.tcl("tcl/plain.tcl")
              + f"safe {{boot {{{msx.boot_steps(machine)}}} {{{msx.at_prompt(machine, 'BASIC', 'plain')}}}}}\n")
    try:
        stderr = msx.run(machine.args, script, timeout=1800)
    except Exception as e:
        print(f"plain.py: openMSX failed: {e}", file=sys.stderr)
        return 2
    if not os.path.exists(out):
        print(f"plain.py: openMSX stopped before the screen; see {work}{msx.last_output(stderr)}", file=sys.stderr)
        return 2
    with open(out, encoding="utf-8", errors="replace") as f:
        text = "\n".join(line.rstrip() for line in f.read().splitlines() if line.strip())
    # As in the capture's log: a graphics mode has no text to read.
    print(text or "a graphics screen")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
