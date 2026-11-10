#!/usr/bin/env python3
"""Start a game's image in openMSX, with its window, to try it by hand.

Usage: try.py <game> <machine> --dos <dir>

<game> and <machine> are as for capture.py. <dir> holds the DOS system files.
The disk holds them, SNAPCAS.COM and the image that snapcas.py snap moved to
images/<machine>/<game>/, and goes to try/disk.dsk in the game's work folder.
The run passes the machine's boot menu and types SNAPCAS <GAME> at DOS's
prompt, as the player does on the real machine. When the prompt does not
appear within the prelude's deadline, openMSX prints the error and its window
stays.

Exit status: 0 when openMSX ends, 1 for an error in the input files or no
image, 2 when openMSX cannot make the disk.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402


def script(machine, name, dos):
    """The run's Tcl: it passes the machine's boot menu, waits for DOS's
    prompt and types SNAPCAS and the image's name. dos are the DOS system
    files on the disk. On a machine that boots DOS from its own disk, the
    prompt is that DOS's, and the try's disk is another drive. Otherwise DOS
    boots from the try's disk, drive A: Nextor's and MSX-DOS 2's prompt shows
    the path, and MSX-DOS 1's, which has no COMMAND2.COM, does not."""
    if machine.dos:
        prompt, typed = machine.dos[0], f"{machine.dos[1]}:\rSNAPCAS {name}"
    elif any(os.path.basename(path).upper() == "COMMAND2.COM" for path in dos):
        prompt, typed = "A:\\>", f"SNAPCAS {name}"
    else:
        prompt, typed = "A>", f"SNAPCAS {name}"
    return f"safe {{boot {{{msx.boot_steps(machine)}}} {{{msx.type_at_prompt(prompt, typed)}}}}}\n"


def main():
    parser = msx.Parser(description="Start a game's image in openMSX, to try it by hand.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    args = parser.parse_args()

    folder = gamefile.game_folder(args.game)
    try:
        game = gamefile.read_game(folder, args.machine)
        machine = msx.read_machine(msx.machine_path(args.machine))
        dos = msx.dos_files(args.dos)
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"try.py: {e}", file=sys.stderr)
        return 1
    image = gamefile.published_path(args.machine, folder, game.name)
    if image is None or not os.path.exists(image):
        print(f"try.py: {args.game}: no image in images/{args.machine}/. ./snapcas.py snap "
              f"{gamefile.game_key(folder) or args.game} {args.machine} makes it", file=sys.stderr)
        return 1

    disk = os.path.join(gamefile.out_folder(args.machine, folder), "try", "disk.dsk")
    try:
        msx.make_disk(disk, dos + [os.path.join(ROOT, "bin", "SNAPCAS.COM"), image], machine.disk_size)
    except msx.DiskError as e:
        print(f"try.py: {e}", file=sys.stderr)
        return 2
    print(f"try       {os.path.relpath(image, ROOT)}: SNAPCAS {game.name}", flush=True)
    return msx.run_window([*machine.args, f"-{machine.disk}", disk], script(machine, game.name, dos))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
