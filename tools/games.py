#!/usr/bin/env python3
"""Make and check every shipped game file's image on a machine (docs/INTERNALS.md,
The games run).

Usage: games.py <machine> [--dos <dir>] [--full] [--workers <n>]

Each game file's tapes come from downloads/, where snapcas.py snap puts them.
The run downloads nothing, so as not to load File-Hunter with a download of the
whole collection: a game file whose tape is missing gets that as its result.
The other games are captured, built and checked, several at once. The results go to out/games/<machine>.txt, one
line per game file: its folder, a tab and the first line of its check's
report, the failed point with its first line, or the failed step's error. A
game file whose inputs are unchanged keeps its last result, unless --full.

Exit status: 0 when every game file that fails is in tests/openmsx-failures.txt,
1 for an error in the command line, 3 when another game file fails.
"""
import argparse
import concurrent.futures
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402
import msx  # noqa: E402

GAMES = os.path.join(ROOT, "games")
REPORTS = os.path.join(ROOT, "out", "games")
# The game files that fail on a machine in openMSX itself (PLAN.md, step 9).
OPENMSX_FAILURES = os.path.join(ROOT, "tests", "openmsx-failures.txt")


def read_openmsx_failures(machine):
    """The folders of the game files that the list gives for the machine."""
    with open(OPENMSX_FAILURES) as f:
        pairs = [line.split()[:2] for line in f if line.strip() and not line.startswith("#")]
    return {name for m, name in pairs if m == machine}


def file_hash(h, path):
    h.update(path.encode() + b"\0")
    with open(path, "rb") as f:
        h.update(f.read())


def tools_hash():
    """The hash of the code that every result depends on: bin/ and tools/."""
    h = hashlib.sha1()
    for top in ("bin", "tools"):
        for folder, dirs, files in sorted(os.walk(os.path.join(ROOT, top))):
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(".pyc"):
                    file_hash(h, os.path.join(folder, name))
    return h.hexdigest()


def inputs_hash(machine, name, tools):
    """The hash of a game file's inputs on a machine: the game's folder, its
    tape files, the machine files that it runs on, and tools, the hash of the
    code."""
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


def tool(name, *args):
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, name), *args], capture_output=True, text=True)


def run_game(machine, name, dos):
    """Captures, builds and checks one game file on the machine, and returns
    the first line of the check's report, the failure of point 2, 3 or 4 with
    its first line when that point fails, or the failed step's error."""
    folder = os.path.join(GAMES, name)
    for step in ("capture.py", "build.py"):
        result = tool(step, folder, machine, "--tapes", gamefile.DOWNLOADS)
        if result.returncode != 0:
            return (result.stderr.strip().splitlines() or [f"{step} failed"])[-1]
    result = tool("check.py", folder, machine, "--dos", dos)
    lines = result.stdout.strip().splitlines()
    for point in ("point 2: fail", "point 3: fail", "point 4: fail"):
        if point in lines:
            failed = lines.index(point)
            return point + ":" + "".join(lines[failed + 1:failed + 2])
    return (lines or [result.stderr.strip()])[0]


def main():
    parser = argparse.ArgumentParser(description="Make and check every shipped game file's image on a machine.")
    parser.add_argument("machine", help="a machine file's name below machines/, without .txt")
    parser.add_argument("--dos", default=os.path.join(ROOT, "dos", "nextor"),
                        help="the folder that holds the DOS system files (default: Nextor's, in dos/nextor/)")
    parser.add_argument("--full", action="store_true", help="give every game file a new result")
    parser.add_argument("--workers", type=int, default=11,
                        help="the number of games to run at once (default: 11, as openMSX keeps about one "
                             "core busy)")
    args = parser.parse_args()
    if not os.path.isfile(msx.machine_path(args.machine)):
        print(f"games.py: {msx.machine_path(args.machine)}: no such machine file", file=sys.stderr)
        return 1

    path = os.path.join(REPORTS, args.machine + ".txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # The cache holds each game file's inputs' hash beside its result.
    cache = {} if args.full else read_cache(path + ".cache")
    names = gamefile.game_names()
    errors = {}
    for name in names:
        try:
            game = gamefile.read_game(os.path.join(GAMES, name), args.machine)
        except gamefile.GameFileError as e:
            errors[name] = str(e)
            continue
        missing = [t for t in (game.tape, game.side2) if t and not os.path.isfile(os.path.join(gamefile.DOWNLOADS, t))]
        if missing:
            errors[name] = "no " + " or ".join(missing) + " in downloads/"
    tools = tools_hash()
    hashes = {name: inputs_hash(args.machine, name, tools) for name in names}
    todo = [name for name, h in hashes.items()
            if name not in errors and (name not in cache or cache[name][0] != h)]
    print(f"{args.machine}: {len(names) - len(todo) - len(errors)} unchanged, {len(todo)} to run, "
          f"{len(errors)} without their tapes in downloads/", flush=True)
    for name, error in errors.items():
        cache[name] = (hashes[name], error)
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(run_game, args.machine, name, args.dos): name for name in todo}
        for done, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            name = jobs[job]
            cache[name] = (hashes[name], job.result())
            print(f"{done}/{len(todo)}  {name}  {cache[name][1]}", flush=True)
            # Each result goes to the cache at once, so that a run that stops
            # keeps what it has done.
            with open(path + ".cache", "a") as f:
                f.write(f"{name}\t{hashes[name]}\t{cache[name][1]}\n")
    with open(path, "w") as report, open(path + ".cache", "w") as f:
        for name in names:
            report.write(f"{name}\t{cache[name][1]}\n")
            f.write(f"{name}\t{hashes[name]}\t{cache[name][1]}\n")

    known = read_openmsx_failures(args.machine)
    failed = {name for name in names if cache[name][1] != "point 1: pass"}
    passing = sorted(known - failed)
    if passing:
        print("In tests/openmsx-failures.txt, but passing now: " + ", ".join(passing))
    unknown = sorted(failed - known)
    print(f"{len(names) - len(failed)} of {len(names)} game files pass; the results are in {path}")
    if unknown:
        print("These game files fail, and tests/openmsx-failures.txt does not list them:\n"
              + "\n".join(f"  {name}: {cache[name][1]}" for name in unknown))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
