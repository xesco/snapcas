#!/usr/bin/env python3
"""The snapcas command (docs/CLI.md): makes a game's image for a machine, starts
it in openMSX, and lists the games and the machines.

Usage: snapcas.py snap <game> <machine> [--check [--dos <dir>]]
       snapcas.py try <game> <machine> [--dos <dir>]
       snapcas.py sync <machine> <destination>
       snapcas.py list [text] [--all]
       snapcas.py machines

snap downloads the game's tape files that are not in downloads/, then
captures, builds and, with --check, checks the image, and when they pass it
moves the image to images/<machine>/<game>/<GAME>.SNP. When a step fails and the game file names no
capture variant, the steps run again on each capture variant that the machine
file lists, and the first that passes gives the capture line for the machine's
game file. An error in the input files, which stops the capture with status 1,
stops the command at once. try starts openMSX with a disk of the DOS files,
SNAPCAS.COM and the game's image, and types SNAPCAS <GAME>. sync copies a
machine's images and SNAPCAS.COM to a card. Without arguments, the command
prints its help.

Exit status: 0 on success, 1 for an error in the command line or the input
files, 2 when openMSX fails or a wait times out, 3 when a check fails: that of
the first step that fails. 130 when Ctrl-C stops the command.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import card  # noqa: E402
import check  # noqa: E402
import download  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import pipeline  # noqa: E402

# The DOS files that snap --check and try use without --dos: the folder below
# dos/ that the machine file names (msx.dos_folder), by default Nextor's, which
# make test downloads (Makefile).
NEXTOR = os.path.join(msx.DOS, "nextor")
# The openMSX home that make firmware makes, with the user's system ROMs and the
# firmware of the machines that need it (Makefile).
EMU_HOME = os.path.join(ROOT, "out", "cache", "openmsx-home")
# Nextor 2.1.0's tools.zip, which holds NEXTOR.SYS 2.11 and COMMAND2.COM 2.44,
# and its SHA-256: the Makefile pins the same file.
NEXTOR_ZIP = ("https://github.com/Konamiman/Nextor/releases/download/v2.1.0/tools.zip",
              "5792ff3fe7ab684b8afd405cdd898e25f6efdb84ca1f2cb9ac1428cc848d924e")

# What each point of check.py's report checks (INTERNALS.md, Check).
POINTS = {1: "the restored machine equals the snapshot",
          2: "the game does not write to the tape service in page 3",
          3: "the machine does not reboot",
          4: "the game does not stop at a BASIC error"}


class Choice(Exception):
    """A game or a machine that the command line does not name."""


def games_with(text):
    """The games whose folder or title holds the text, in any case, as
    (folder, title)."""
    text = text.lower()
    games = [(name, gamefile.title(gamefile.game_folder(name)))
             for name in gamefile.game_names() + gamefile.custom_names()]
    return [(name, title) for name, title in games if text in name.lower() or text in title.lower()]


def compilation_programs():
    """The game files that list shows only with --all: a compilation's
    programs, in a collection's folder such as SUPERMSX/GOLF, or one of 4 or
    more game files from one zip, as Turbo Pack A's are. Fewer game files from
    one zip are a game's parts or versions, as RUR-1 and RUR-2 are."""
    names = gamefile.game_names()
    by_zip = {}
    for name in names:
        with open(os.path.join(gamefile.game_folder(name), "game.txt"), encoding="utf-8") as f:
            url = next((line.split()[1] for line in f if line.startswith("url ")), None)
        if url:
            by_zip.setdefault(url, []).append(name)
    shared = {name for group in by_zip.values() if len(group) >= 4 for name in group}
    return {name for name in names if "/" in name} | shared


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


def tool(name, *args):
    """Runs one of the tools with its output shown, and returns its exit status."""
    return subprocess.run([sys.executable, "-I", os.path.join(TOOLS, name), *args]).returncode


def nextor():
    """Downloads Nextor's DOS files into dos/nextor/ when they are missing, and
    returns the folder."""
    if all(os.path.isfile(os.path.join(NEXTOR, f)) for f in ("NEXTOR.SYS", "COMMAND2.COM")):
        return NEXTOR
    print(f"download  Nextor 2.1.0's NEXTOR.SYS and COMMAND2.COM into {os.path.relpath(NEXTOR, ROOT)}/", flush=True)
    if tool("fetch.py", *NEXTOR_ZIP, NEXTOR, "NEXTOR.SYS", "COMMAND2.COM") != 0:
        raise Choice("Nextor's files could not be downloaded; --dos <dir> names other DOS files")
    return NEXTOR


def dos_folder(machine):
    """The folder of the DOS files that the machine boots: Nextor's, downloaded
    when missing, or the one that its machine file names, which the user fills."""
    if msx.read_machine(msx.machine_path(machine)).dos_files == "nextor":
        return nextor()
    return msx.dos_folder(machine)


def show_step(step):
    """Prints how a step of snap ended (pipeline.Step): a line for a capture
    or a build that passes, the error of a step that fails, and each point of
    the check's report with what the point checks."""
    if step.error:
        print(step.error, file=sys.stderr)
    if step.name == "check":
        for number, passed, lines in check.points(step.output):
            if number is not None:
                print(f"check     {'pass' if passed else 'fail'}  {POINTS[number]}")
            # A failed point's lines, under its text.
            for line in lines:
                print(" " * 16 + line.strip())
    elif step.status == 0 and step.name == "capture":
        print("capture   done", flush=True)
    elif step.status == 0:
        # The build's output is what the image holds.
        print("build     done: " + step.output, flush=True)


def show_trial(variant):
    """Prints the capture variant that snap tries next."""
    print(f"snapcas.py: trying the capture variant {variant}", file=sys.stderr)


def snap(args):
    """Downloads the game's tapes that are missing, makes the game's image for
    the machine, and tries the machine's capture variants when a step fails and
    the game file names none (pipeline.run). The image goes to images/ once
    every step passes."""
    try:
        game = find_game(args.game)
        machine = find_machine(args.machine)
        msx.check_firmware(machine)
        if args.dos and not args.check:
            raise Choice("--dos gives the DOS files for --check")
        print(f"{gamefile.title(game) or os.path.basename(game)} for {machine}", flush=True)
        if args.check and not args.dos:
            args.dos = dos_folder(machine)
        if not gamefile.is_custom(game):
            download.tapes(gamefile.read_game(game, machine), gamefile.DOWNLOADS)
        result = pipeline.run(game, machine, args.dos if args.check else None, try_variants=True,
                              show=show_step, trying=show_trial)
    except (Choice, OSError, gamefile.GameFileError, msx.MachineError, download.DownloadError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    if result.image:
        print(f"image     {os.path.relpath(result.image, ROOT)}")
    if result.passed and result.variant:
        print(f"snapcas.py: it passes, so the machine's game file needs: capture {result.variant}")
    return result.status


def try_game(args):
    """Starts the game's image for the machine in openMSX, to try it by hand."""
    try:
        game = find_game(args.game)
        machine = find_machine(args.machine)
        msx.check_firmware(machine)
        dos = args.dos or dos_folder(machine)
    except (Choice, OSError, msx.MachineError) as e:
        print(f"snapcas.py: {e}", file=sys.stderr)
        return 1
    return tool("try.py", game, machine, "--dos", dos)


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
    """Prints the games whose folder or title holds the text, and their number.
    A compilation's programs only with --all; without it, the count says how
    many of them hold the text."""
    games = games_with(args.text or "")
    programs = compilation_programs()
    shown = games if args.all else [(name, title) for name, title in games if name not in programs]
    for line in columns(shown):
        print(line)
    hidden = len(games) - len(shown)
    print(f"{len(shown)} game" + ("" if len(shown) == 1 else "s")
          + (f", and {hidden} in compilations, which --all lists" if hidden else ""))
    return 0


def list_machines(args):
    """Prints the user machines, each with what its machine file says it is."""
    for line in columns([(name, msx.description(msx.machine_path(name))) for name in msx.user_machines()]):
        print(line)
    return 0


def main():
    if os.path.isdir(EMU_HOME):
        os.environ.setdefault("OPENMSX_HOME", EMU_HOME)
    parser = msx.Parser(prog="snapcas.py", description="Make snapcas images of MSX cassette games.")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="<command>", parser_class=msx.Parser)
    snap_ = verbs.add_parser("snap", help="make a game's image for a machine",
                             description="Make a game's image for a machine: download its tape files that are "
                                         "missing, capture, build and, with --check, check it.")
    snap_.add_argument("game", help="a game's name, as snapcas.py list shows it")
    snap_.add_argument("machine", help="a machine's name, as snapcas.py machines lists it")
    snap_.add_argument("--check", action="store_true", help="check the image in openMSX")
    snap_.add_argument("--dos", help="the folder that holds the DOS system files for --check (default: the "
                                     "machine's, below dos/)")
    snap_.set_defaults(run=snap)
    try_ = verbs.add_parser("try", help="start a game's image in openMSX",
                            description="Start a game's image in openMSX, and type the command that "
                                        "restores it, to try it before the real machine.")
    try_.add_argument("game", help="a game's name, as snapcas.py list shows it")
    try_.add_argument("machine", help="a machine's name, as snapcas.py machines lists it")
    try_.add_argument("--dos", help="the folder that holds the DOS system files (default: the machine's, "
                                    "below dos/)")
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
    games.add_argument("--all", action="store_true", help="also list the compilations' programs, such as "
                                                          "SUPERMSX/GOLF and Turbo Pack A's")
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
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Ctrl-C reaches the running tool and its openMSX as well.
        sys.exit(130)
