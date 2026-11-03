#!/usr/bin/env python3
"""The snapcas command (docs/CLI.md): makes a game's image for a machine, starts
it in openMSX, and lists the games and the machines.

Usage: snapcas.py snap <game> <machine> [--check [--dos <dir>]]
       snapcas.py try <game> <machine> [--dos <dir>]
       snapcas.py sync <machine> <destination>
       snapcas.py list [text]
       snapcas.py machines

snap downloads the game's tape files that are not in downloads/, then
captures, builds and, with --check, checks the image, and when they pass it
moves the image to images/<machine>/<game>/<GAME>.SNP. When a step fails and the game file names no
capture variant, the steps run again on each capture variant that the machine
file lists, and the first that passes gives the capture line for the machine's
game file. try starts openMSX with a disk of the DOS files, SNAPCAS.COM and the
game's image, and types SNAPCAS <GAME>. sync copies a machine's images and
SNAPCAS.COM to a card. Without arguments, the command prints
its help.

Exit status: 0 on success, 1 for an error in the command line or the input
files, 2 when openMSX fails or a wait times out, 3 when a check fails: that of
the first step that fails.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import card  # noqa: E402
import download  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402

# The DOS files that snap --check uses without --dos: Nextor's, which make test
# downloads (Makefile).
NEXTOR = os.path.join(ROOT, "dos", "nextor")

# What each point of check.py's report checks (DESIGN.md, Check).
POINTS = {"1": "the restored machine equals the snapshot",
          "2": "the game does not write to the tape service in page 3",
          "3": "the machine does not reboot",
          "4": "the game does not stop at a BASIC error"}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Exit status 1, as the tools give for an error in their input, and
        # not argparse's 2, which they give when openMSX fails.
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: {message}\n")


class Choice(Exception):
    """A game or a machine that the command line does not name."""


def games_with(text):
    """The games whose folder or title holds the text, in any case, as
    (folder, title)."""
    text = text.lower()
    games = [(name, gamefile.title(gamefile.game_folder(name)))
             for name in gamefile.game_names() + gamefile.custom_names()]
    return [(name, title) for name, title in games if text in name.lower() or text in title.lower()]


def columns(rows):
    """Lines of two columns, the first as wide as its widest value."""
    width = max((len(a) for a, _ in rows), default=0)
    return [f"{a:{width}}  {b}".rstrip() for a, b in rows]


def find_game(arg):
    """The folder of the game that arg names, in any case: a shipped or custom
    game's name, as snapcas.py list shows it, or a folder's path, which the
    tests give."""
    names = {name.lower(): name for name in gamefile.game_names() + gamefile.custom_names()}
    if arg.lower() in names:
        return gamefile.game_folder(names[arg.lower()])
    if os.path.isfile(os.path.join(arg, "game.txt")):
        return os.path.abspath(arg)
    raise Choice(f'no game is named "{arg}": snapcas.py list shows the games')


def find_machine(arg):
    """The name of the machine that arg names."""
    if not os.path.isfile(msx.machine_path(arg)):
        raise Choice(f'no machine is named "{arg}": snapcas.py machines shows the machines')
    return arg


def step(name, *args):
    """Runs one of the tools with its output shown, and returns its exit status."""
    return subprocess.run([sys.executable, "-I", os.path.join(TOOLS, name), *args]).returncode


def tapes_folder(game):
    """The folder of the game's tapes: a custom game's own folder, or
    downloads/."""
    return game if gamefile.is_custom(game) else gamefile.DOWNLOADS


def steps(args, game, machine, variant=None):
    """Captures, builds and, with --check, checks the image, and returns the
    exit status of the first step that fails, or 0."""
    extra = ["--capture", variant] if variant else []
    tapes = ["--tapes", tapes_folder(game)]
    for name, options in (("capture.py", [*tapes, *extra]), ("build.py", tapes)):
        status = step(name, game, machine, *options)
        if status != 0:
            return status
    if args.check:
        return check(game, machine, args.dos or NEXTOR)
    return 0


def check(game, machine, dos):
    """Runs check.py, prints each point of its report with what the point
    checks, and returns check.py's exit status."""
    result = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "check.py"), game, machine, "--dos", dos],
                            stdout=subprocess.PIPE, text=True)
    for line in result.stdout.splitlines():
        words = line.split()
        if len(words) == 3 and words[0] == "point" and words[1][:-1] in POINTS:
            print(f"check     {words[2]}  {POINTS[words[1][:-1]]}")
        else:
            # A failed point's lines, under its text.
            print(" " * 16 + line.strip())
    return result.returncode


def publish(game, machine):
    """Moves a shipped or custom game's image from its work folder to images/,
    where the user takes it, and prints where it went."""
    name = gamefile.read_game(game, machine).name
    target = gamefile.published_path(machine, game, name)
    if target is None:
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(gamefile.image_path(machine, game, name), target)
    print(f"image     {os.path.relpath(target, ROOT)}")


def snap(args):
    """Downloads the game's tapes that are missing, makes the game's image for
    the machine, and tries the machine's capture variants when a step fails and
    the game file names none. The image goes to images/ once every step
    passes."""
    try:
        game = find_game(args.game)
        machine = find_machine(args.machine)
        if args.dos and not args.check:
            raise Choice("--dos gives the DOS files for --check")
        if args.check and not args.dos and not os.path.isfile(os.path.join(NEXTOR, "NEXTOR.SYS")):
            raise Choice(f"--check needs --dos <dir>, or Nextor's files in {NEXTOR}, which make test downloads")
        if not gamefile.is_custom(game):
            download.tapes(gamefile.read_game(game, machine), gamefile.DOWNLOADS)
    except (Choice, OSError, gamefile.GameFileError, download.DownloadError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    status = steps(args, game, machine)
    if status == 0:
        publish(game, machine)
        return 0
    try:
        capture = gamefile.read_game(game, machine).capture
        variants = msx.read_machine(msx.machine_path(machine)).variants
    except (OSError, gamefile.GameFileError, msx.MachineError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    if capture:
        return status
    for variant in variants:
        print(f"snapcas.py: trying the capture variant {variant}", file=sys.stderr)
        if steps(args, game, machine, variant) == 0:
            publish(game, machine)
            print(f"snapcas.py: it passes, so the machine's game file needs: capture {variant}")
            return 0
    if variants:
        # Leaves the image of the game file's own lines.
        steps(args, game, machine)
    return status


def try_game(args):
    """Starts the game's image for the machine in openMSX, to try it by hand."""
    try:
        game = find_game(args.game)
        machine = find_machine(args.machine)
        if not args.dos and not os.path.isfile(os.path.join(NEXTOR, "NEXTOR.SYS")):
            raise Choice(f"try needs --dos <dir>, or Nextor's files in {NEXTOR}, which make test downloads")
    except Choice as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    return step("try.py", game, machine, "--dos", args.dos or NEXTOR)


def sync_card(args):
    """Copies the machine's images and SNAPCAS.COM to the card, and prints what
    it copied."""
    try:
        machine = find_machine(args.machine)
        card.check_destination(args.destination)
        files = card.card_files(os.path.join(gamefile.IMAGES, machine), os.path.join(ROOT, "bin", "SNAPCAS.COM"))
        copied, unchanged = card.sync(files, args.destination)
    except (Choice, OSError, card.CardError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    print(f"copied {copied}, unchanged {unchanged}")
    return 0


def list_games(args):
    """Prints the games whose folder or title holds the text, and their number."""
    games = games_with(args.text or "")
    for line in columns(games):
        print(line)
    print(f"{len(games)} game" + ("" if len(games) == 1 else "s"))
    return 0


def list_machines(args):
    """Prints the user machines, each with what its machine file says it is."""
    for line in columns([(name, msx.description(msx.machine_path(name))) for name in msx.user_machines()]):
        print(line)
    return 0


def main():
    parser = Parser(prog="snapcas.py", description="Make snapcas images of MSX cassette games.")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="<command>", parser_class=Parser)
    snap_ = verbs.add_parser("snap", help="make a game's image for a machine",
                             description="Make a game's image for a machine: download its tape files that are "
                                         "missing, capture, build and, with --check, check it.")
    snap_.add_argument("game", help="a game's name, as snapcas.py list shows it")
    snap_.add_argument("machine", help="a machine's name, as snapcas.py machines lists it")
    snap_.add_argument("--check", action="store_true", help="check the image in openMSX")
    snap_.add_argument("--dos", help="the folder that holds the DOS system files for --check (default: Nextor's, "
                                     "in dos/nextor/)")
    snap_.set_defaults(run=snap)
    try_ = verbs.add_parser("try", help="start a game's image in openMSX",
                            description="Start a game's image in openMSX, and type the command that "
                                        "restores it, to try it before the real machine.")
    try_.add_argument("game", help="a game's name, as snapcas.py list shows it")
    try_.add_argument("machine", help="a machine's name, as snapcas.py machines lists it")
    try_.add_argument("--dos", help="the folder that holds the DOS system files (default: Nextor's, "
                                    "in dos/nextor/)")
    try_.set_defaults(run=try_game)
    sync_ = verbs.add_parser("sync", help="copy a machine's images and SNAPCAS.COM to a card",
                             description="Copy a machine's images and SNAPCAS.COM to a card: the files that are "
                                         "new or changed, each read back and compared. Nothing on the card is "
                                         "deleted.")
    sync_.add_argument("machine", help="a machine's name, as snapcas.py machines lists it")
    sync_.add_argument("destination", help="the card's top folder, such as /Volumes/MSX")
    sync_.set_defaults(run=sync_card)
    games = verbs.add_parser("list", help="list the games snapcas supports, or search them by name",
                             description="List the games snapcas supports, or search them by name.")
    games.add_argument("text", nargs="?", help="part of a game's folder or title, such as gaunt, in any case")
    games.set_defaults(run=list_games)
    machines = verbs.add_parser("machines", help="list the machines that snapcas makes images for",
                                description="List the machines that snapcas makes images for.")
    machines.set_defaults(run=list_machines)
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    if len(sys.argv) == 2 and sys.argv[1] in ("snap", "try", "sync"):
        {"snap": snap_, "try": try_, "sync": sync_}[sys.argv[1]].print_help()
        return 0
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
