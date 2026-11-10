#!/usr/bin/env python3
"""Make and check every shipped game file's image on a machine (docs/INTERNALS.md,
The games run).

Usage: games.py <machine> [--dos <dir>] [--full] [--workers <n>]

Each game file's tapes come from downloads/, where snapcas.py snap puts them.
The run downloads nothing, so as not to load File-Hunter with a download of the
whole collection: a game file whose tape is missing gets that as its result.
The other games are captured, built and checked, several at once, and the
image of each that passes goes to images/<machine>/, as with snapcas.py snap.
The check boots the DOS files of the machine's folder below dos/, as snapcas.py
snap --check does, or those of --dos. The results go to
out/games/<machine>.txt, one line per game file: its folder, a tab and the
first line of its check's report, the failed point with its first line, or the
failed step's error. A game file whose inputs are unchanged keeps its last
result and its image in images/, unless --full. A result that says that the
run broke, as an openMSX that stopped, is not kept, so the next run makes it
again.

The failures are printed in three groups: those that tests/openmsx-failures.txt
lists, which fail in openMSX itself, those that tests/snapcas-failures.txt
lists, which are known failures of snapcas, and the new ones, in neither list.

Exit status: 0 when every game file that fails is in one of the two lists, 1
for an error in the command line, a list or the machine's files, 3 when
another game file fails, 130 when Ctrl-C stops the run.
"""
import concurrent.futures
import hashlib
import os
import signal
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402
import pipeline  # noqa: E402

GAMES = os.path.join(ROOT, "games")
REPORTS = os.path.join(ROOT, "out", "games")
# The game files that fail on a machine in openMSX itself, and those that fail
# because of snapcas (PLAN.md, step 9).
OPENMSX_FAILURES = os.path.join(ROOT, "tests", "openmsx-failures.txt")
SNAPCAS_FAILURES = os.path.join(ROOT, "tests", "snapcas-failures.txt")


class ListError(Exception):
    """A list of failures that cannot be read."""


def read_failures(path, machine, names):
    """The folders of the game files that a list gives for the machine. Each
    line holds a machine, a game file's folder and what fails."""
    found = set()
    with open(path) as f:
        for number, line in enumerate(f, 1):
            if not line.strip() or line.startswith("#"):
                continue
            words = line.split()
            where = f"{os.path.relpath(path, ROOT)}:{number}"
            if len(words) < 3:
                raise ListError(f"{where}: a line holds a machine, a game file's folder and what fails")
            if not os.path.isfile(msx.machine_path(words[0])):
                raise ListError(f"{where}: no machine is named {words[0]}")
            if words[1] not in names:
                raise ListError(f"{where}: no game file is in games/{words[1]}/")
            if words[0] == machine:
                found.add(words[1])
    return found


def file_hash(h, path):
    h.update(path.encode() + b"\0")
    with open(path, "rb") as f:
        h.update(f.read())


def tools_hash(dos, version):
    """The hash of what every result depends on: the code in bin/ and tools/,
    the DOS files that the check boots, in the folder dos, and openMSX's
    version."""
    h = hashlib.sha1(version.encode())
    for top in (os.path.join(ROOT, "bin"), os.path.join(ROOT, "tools"), dos):
        for folder, dirs, files in sorted(os.walk(top)):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(".pyc"):
                    file_hash(h, os.path.join(folder, name))
    return h.hexdigest()


def inputs_hash(machine, name, tools):
    """The hash of a game file's inputs on a machine: the game's folder, its
    tape files, the machine files that it runs on, and tools, the hash of the
    code, the DOS files and openMSX's version."""
    h = hashlib.sha1(tools.encode())
    folder = os.path.join(GAMES, name)
    for f in sorted(os.listdir(folder)):
        file_hash(h, os.path.join(folder, f))
    try:
        game = gamefile.read_game(folder, machine)
    except gamefile.GameFileError:
        return h.hexdigest()
    for cas in (game.tape, game.side2):
        if cas and os.path.isfile(os.path.join(gamefile.DOWNLOADS, cas)):
            file_hash(h, os.path.join(gamefile.DOWNLOADS, cas))
    file_hash(h, msx.machine_path(machine))
    if game.capture:
        file_hash(h, msx.variant_path(game.capture))
    return h.hexdigest()


def read_cache(path):
    """A machine's last results, by game file: (inputs' hash, result)."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {name: (h, result) for name, h, result in
                (line.rstrip("\n").split("\t", 2) for line in f if line.count("\t") >= 2)}


# The games' processes that run now, for Ctrl-C to stop them, and whether it
# has.
RUNNING = set()
STOPPED = threading.Event()
LOCK = threading.Lock()


def run_game(machine, name, dos):
    """Captures, builds and checks one game file on the machine, and returns
    the pipeline.Result. The steps run in pipeline.py as a program, which
    moves the image of a game that passes to images/, as snapcas.py snap does,
    so that snapcas.py sync copies it to a card. The program gets a process
    group of its own, so that stop_games stops it with its openMSX."""
    command = [sys.executable, "-I", os.path.join(HERE, "pipeline.py"), os.path.join(GAMES, name), machine,
               "--dos", dos]
    with LOCK:
        if STOPPED.is_set():
            return pipeline.broken("games.py: stopped")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True)
        RUNNING.add(process)
    try:
        out, err = process.communicate()
    finally:
        with LOCK:
            RUNNING.discard(process)
    return pipeline.read_result(process.returncode, out, err)


def stop_games():
    """Stops the games' processes that run, each with its openMSX, as Ctrl-C
    stops a tool run by hand, and starts no other."""
    with LOCK:
        STOPPED.set()
        for process in RUNNING:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGINT)
                else:
                    process.terminate()
            except OSError:
                pass


def image_missing(machine, name, game):
    """Whether images/ lacks the image of a game file, which a pass moved
    there."""
    return not os.path.isfile(gamefile.published_path(machine, os.path.join(GAMES, name), game.name))


def group(title, names, results):
    """Prints a group of failures, each with its result."""
    if names:
        print(title + "\n" + "\n".join(f"  {name}: {results[name]}" for name in names))


def main():
    parser = msx.Parser(description="Make and check every shipped game file's image on a machine.")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--dos", help="the folder that holds the DOS system files (default: the machine's, "
                                      "below dos/)")
    parser.add_argument("--full", action="store_true", help="give every game file a new result")
    parser.add_argument("--workers", type=int, default=11,
                        help="the number of games to run at once (default: 11, as openMSX keeps about one "
                             "core busy)")
    args = parser.parse_args()
    if not os.path.isfile(msx.machine_path(args.machine)):
        print(f"games.py: {msx.machine_path(args.machine)}: no such machine file", file=sys.stderr)
        return 1
    names = gamefile.game_names()
    try:
        # What stops the run is found before it starts, not hours later.
        msx.check_firmware(args.machine)
        dos = os.path.abspath(args.dos) if args.dos else msx.dos_folder(args.machine)
        msx.dos_files(dos)
        in_openmsx = read_failures(OPENMSX_FAILURES, args.machine, names)
        in_snapcas = read_failures(SNAPCAS_FAILURES, args.machine, names)
        if in_openmsx & in_snapcas:
            raise ListError(f"{sorted(in_openmsx & in_snapcas)[0]} is in both lists of failures for {args.machine}")
        tools = tools_hash(dos, msx.version())
    except (OSError, msx.MachineError, ListError) as e:
        print(f"games.py: {e}", file=sys.stderr)
        return 1

    path = os.path.join(REPORTS, args.machine + ".txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # The cache holds each game file's inputs' hash beside its result.
    cache = {} if args.full else read_cache(path + ".cache")
    errors, games = {}, {}
    for name in names:
        try:
            games[name] = game = gamefile.read_game(os.path.join(GAMES, name), args.machine)
        except gamefile.GameFileError as e:
            errors[name] = str(e)
            continue
        missing = [t for t in (game.tape, game.side2) if t and not os.path.isfile(os.path.join(gamefile.DOWNLOADS, t))]
        if missing:
            errors[name] = "no " + " or ".join(missing) + " in downloads/"
    hashes = {name: inputs_hash(args.machine, name, tools) for name in names}
    # A pass whose image is gone from images/ runs again, to make the image.
    todo = [name for name, h in hashes.items()
            if name not in errors and (name not in cache or cache[name][0] != h or (
                cache[name][1] == pipeline.PASS and image_missing(args.machine, name, games[name])))]
    print(f"{args.machine}: {len(names) - len(todo) - len(errors)} unchanged, {len(todo)} to run, "
          f"{len(errors)} without their tapes in downloads/", flush=True)
    results = {name: cache[name][1] for name in names if name in cache}
    results.update(errors)
    # The results that the cache keeps: not those of a run that broke.
    kept = set(results) - set(todo)
    pool = concurrent.futures.ThreadPoolExecutor(args.workers)
    try:
        jobs = {pool.submit(run_game, args.machine, name, dos): name for name in todo}
        for done, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            name = jobs[job]
            result = job.result()
            results[name] = result.message
            print(f"{done}/{len(todo)}  {name}  {results[name]}" + ("  (not kept)" if result.transient else ""),
                  flush=True)
            if not result.transient:
                kept.add(name)
                # Each result goes to the cache at once, so that a run that
                # stops keeps what it has done.
                with open(path + ".cache", "a") as f:
                    f.write(f"{name}\t{hashes[name]}\t{results[name]}\n")
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        stop_games()
        print(f"\ngames.py: stopped by Ctrl-C. {path}.cache keeps the results so far, and the next run "
              "goes on from them", file=sys.stderr)
        return 130
    pool.shutdown()
    with open(path, "w") as report, open(path + ".cache", "w") as f:
        for name in names:
            report.write(f"{name}\t{results[name]}\n")
            if name in kept:
                f.write(f"{name}\t{hashes[name]}\t{results[name]}\n")

    failed = {name for name in names if results[name] != pipeline.PASS}
    for listed, file in ((in_openmsx, OPENMSX_FAILURES), (in_snapcas, SNAPCAS_FAILURES)):
        if listed - failed:
            print(f"In {os.path.relpath(file, ROOT)}, but passing now: " + ", ".join(sorted(listed - failed)))
    print(f"{len(names) - len(failed)} of {len(names)} game files pass; the results are in {path}")
    new = sorted(failed - in_openmsx - in_snapcas)
    group("These game files fail in openMSX itself, as tests/openmsx-failures.txt lists:",
          sorted(failed & in_openmsx), results)
    group("These game files fail because of snapcas, as tests/snapcas-failures.txt lists:",
          sorted(failed & in_snapcas), results)
    group("These game files fail, and neither list holds them:", new, results)
    return 3 if new else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
