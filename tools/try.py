#!/usr/bin/env python3
"""Start a game's image in openMSX, with its window, to try it by hand.

Usage: try.py <game> <machine> --dos <dir>

<game> and <machine> are as for capture.py. <dir> holds the DOS system files.
The disk holds them, SNAPCAS.COM and the image that snapcas.py snap moved to
images/<machine>/<game>/, and goes to try/disk.dsk in the game's work folder.
The run passes the machine's boot menu and types SNAPCAS <GAME> at DOS's
prompt, as the player does on the real machine.

Exit status: 0 when openMSX ends, 1 for an error in the input files or no
image, 2 when openMSX cannot make the disk.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402

# DOS's prompts on the disk's drive, for a machine that boots DOS from the
# disk: Nextor's and MSX-DOS 2's with the path, and MSX-DOS 1's.
PROMPTS = ("A:\\>", "A>")

# Waits for one of the prompts, given in hex, and types the text in hex.
TYPE_AT_PROMPT = """
proc type_at_prompt {prompts hex {tries 0}} {
  foreach prompt $prompts {
    if {[string first [binary format H* $prompt] [screen]] >= 0} { type [binary format H* $hex]; return }
  }
  if {$tries < 240} { after time 0.5 [list type_at_prompt $prompts $hex [expr {$tries + 1}]] }
}
"""


def main():
    parser = argparse.ArgumentParser(description="Start a game's image in openMSX, to try it by hand.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--dos", required=True, help="the folder that holds the DOS system files")
    args = parser.parse_args()

    folder = gamefile.game_folder(args.game)
    try:
        game = gamefile.read_game(folder, args.machine)
        machine = msx.read_machine(msx.machine_path(args.machine))
        dos = sorted(glob.glob(os.path.join(args.dos, "*")))
        if not dos:
            raise OSError(f"{args.dos}: no DOS system files")
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
    except RuntimeError as e:
        print(f"try.py: {e}", file=sys.stderr)
        return 2
    # On a machine that boots DOS from its own disk, the try's disk is another
    # drive.
    if machine.dos:
        prompts, typed = [machine.dos[0]], f"{machine.dos[1]}:\rSNAPCAS {game.name}\r"
    else:
        prompts, typed = PROMPTS, f"SNAPCAS {game.name}\r"
    hexed = " ".join(p.encode("latin-1").hex() for p in prompts)
    script = (TYPE_AT_PROMPT + f"boot {{{msx.boot_steps(machine)}}} "
              f"{{type_at_prompt {{{hexed}}} {typed.encode('latin-1').hex()}}}\n")
    print(f"try       {os.path.relpath(image, ROOT)}: SNAPCAS {game.name}", flush=True)
    return msx.run_window([*machine.args, f"-{machine.disk}", disk], script)


if __name__ == "__main__":
    sys.exit(main())
