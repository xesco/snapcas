"""Step 9 (docs/PLAN.md): the shipped game files, and a game's file for one
machine beside its game.txt (DESIGN.md, Game file and Shipped files)."""
import concurrent.futures
import hashlib
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gamefile  # noqa: E402
import msx  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_step4  # noqa: E402

GAMES = os.path.join(ROOT, "games")
WORK = os.path.join(ROOT, "out", "test", "step9")

# The shipped machines and the DOS that each boots (PLAN.md, Test setup).
SHIPPED = {machine: test_step4.MACHINES[machine][0]
           for machine in ("advanced/phc28s", "basic/vg8020", "basic/nms8250", "advanced/hbf700p")}
SHIPPED.update({"basic/msx2ide": test_step4.NEXTOR, "advanced/mfrsd": test_step4.NEXTOR,
                "basic/picoverse": test_step4.NEXTOR})
# A single-load game that fits each of them, the NMS 8250's 128 KB included.
SINGLE = "CALDERO.CAS"


class MachineFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write("cas GAME.CAS\nsnapshot at 10\n")
        with open(os.path.join(self.folder, "advanced-phc28s.txt"), "w") as f:
            f.write("# Only for the PHC-28S.\ncapture advanced/phc28s-nodisk\nsnapshot at 20\n")

    def test_the_machine_file_adds_its_lines_for_its_machine(self):
        game = gamefile.read_game(self.folder, "advanced/phc28s")
        self.assertEqual(game.capture, "advanced/phc28s-nodisk")

    def test_the_machine_file_gives_a_value_that_both_give(self):
        self.assertEqual(gamefile.read_game(self.folder, "advanced/phc28s").snapshot_at, 20)

    def test_other_machines_read_only_game_txt(self):
        game = gamefile.read_game(self.folder, "basic/vg8020")
        self.assertIsNone(game.capture)
        self.assertEqual(game.snapshot_at, 10)


@unittest.skipUnless(os.path.isdir(GAMES), "no games/ folder")
class ShippedGameFiles(unittest.TestCase):
    def test_every_game_file_reads_on_each_machine(self):
        for name in sorted(os.listdir(GAMES)):
            for machine in ("advanced/phc28s", "basic/vg8020"):
                with self.subTest(game=name, machine=machine):
                    game = gamefile.read_game(os.path.join(GAMES, name), machine)
                    self.assertTrue(game.sha1)

    def test_machine_files_name_a_machine_file(self):
        for name in sorted(os.listdir(GAMES)):
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        machine = file[:-4].replace("-", "/", 1)
                        self.assertTrue(os.path.isfile(msx.machine_path(machine)))


def single_load(machine):
    """Captures, builds and checks SINGLE on a machine, and returns the check's
    report or the failed step's error."""
    folder = os.path.join(WORK, "games", "single-" + machine.replace("/", "-"))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {SINGLE}\n")
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--cas", test_step4.CAS_DIR)
        if result.returncode != 0:
            return f"{step}: {result.stderr.strip()}"
    return test_step4.tool("check.py", folder, machine, "--dos", SHIPPED[machine]).stdout


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class Machines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            cls.reports = dict(zip(SHIPPED, pool.map(single_load, SHIPPED)))

    def test_a_single_load_game_restores_on_each_shipped_machine(self):
        for machine, report in self.reports.items():
            with self.subTest(machine=machine):
                self.assertTrue(report.startswith("point 1: pass"), report)


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class OneCommand(unittest.TestCase):
    def test_snapcas_py_makes_and_checks_the_image(self):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        folder = os.path.join(WORK, "games", "one-command")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(f"cas {SINGLE}\n")
        result = test_step4.tool("snapcas.py", folder, "advanced/phc28s", "--cas", test_step4.CAS_DIR,
                                 "--dos", test_step4.NEXTOR)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("point 1: pass", result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "out", "advanced/phc28s", "one-command", "ONECOMMA.SNP")))


# The collection's CAS files, for the run over every game file, which takes
# hours: make collection sets it.
COLLECTION_DIR = os.environ.get("COLLECTION_DIR")
# The machines of the run, which COLLECTION_MACHINES can name, and the folder
# of their reports, one per machine.
COLLECTION_MACHINES = tuple(os.environ.get("COLLECTION_MACHINES", "advanced/phc28s basic/vg8020").split())
REPORTS = os.path.join(WORK, "collection")
# The runs at once: openMSX keeps about one core busy, and the machine's
# efficiency cores count as well.
COLLECTION_WORKERS = int(os.environ.get("COLLECTION_WORKERS", "11"))
# Set to 1, the run gives every game file a new result. Otherwise a game file
# on a machine keeps its last result while its inputs are unchanged.
COLLECTION_FULL = os.environ.get("COLLECTION_FULL") == "1"


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
    CAS files, the machine files that it runs on, and tools, the hash of the
    code."""
    h = hashlib.sha1(tools.encode())
    folder = os.path.join(GAMES, name)
    for f in sorted(os.listdir(folder)):
        file_hash(h, os.path.join(folder, f))
    try:
        game = gamefile.read_game(folder, machine)
    except gamefile.GameFileError:
        return h.hexdigest()
    for cas in (game.cas, game.side2):
        if cas and os.path.isfile(os.path.join(COLLECTION_DIR, cas)):
            file_hash(h, os.path.join(COLLECTION_DIR, cas))
    for m in sorted({machine, game.capture or machine}):
        file_hash(h, msx.machine_path(m))
    return h.hexdigest()


def read_cache(path):
    """A machine's last results, by game file: (inputs' hash, result)."""
    if COLLECTION_FULL or not os.path.exists(path):
        return {}
    with open(path) as f:
        return {name: (h, result) for name, h, result in
                (line.rstrip("\n").split("\t", 2) for line in f if line.count("\t") >= 2)}


def collection_game(item):
    """Captures, builds and checks one game file on one machine, and returns
    the first line of the check's report, point 2's failure with its first
    line when point 2 fails, or the failed step's error."""
    machine, name = item
    folder = os.path.join(GAMES, name)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--cas", COLLECTION_DIR)
        if result.returncode != 0:
            return (result.stderr.strip().splitlines() or [f"{step} failed"])[-1]
    result = test_step4.tool("check.py", folder, machine, "--dos", SHIPPED[machine])
    lines = result.stdout.strip().splitlines()
    if "point 2: fail" in lines:
        failed = lines.index("point 2: fail")
        return "point 2: fail:" + "".join(lines[failed + 1:failed + 2])
    return (lines or [result.stderr.strip()])[0]


@unittest.skipUnless(COLLECTION_DIR and os.path.isdir(COLLECTION_DIR), "COLLECTION_DIR names no folder")
class Collection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        cls.results = {}
        tools = tools_hash()
        for machine in COLLECTION_MACHINES:
            path = os.path.join(REPORTS, machine + ".txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # The cache holds each game file's inputs' hash beside its result.
            cache = read_cache(path + ".cache")
            hashes = {name: inputs_hash(machine, name, tools) for name in sorted(os.listdir(GAMES))}
            todo = [(machine, name) for name, h in hashes.items()
                    if name not in cache or cache[name][0] != h]
            print(f"{machine}: {len(hashes) - len(todo)} unchanged, {len(todo)} to run",
                  file=sys.stderr, flush=True)
            with concurrent.futures.ThreadPoolExecutor(COLLECTION_WORKERS) as pool:
                for item, result in zip(todo, pool.map(collection_game, todo)):
                    cache[item[1]] = (hashes[item[1]], result)
                    # Each result goes to the cache at once, so that a run
                    # that stops keeps what it has done.
                    with open(path + ".cache", "a") as f:
                        f.write(f"{item[1]}\t{hashes[item[1]]}\t{result}\n")
            with open(path, "w") as report, open(path + ".cache", "w") as f:
                for name, h in hashes.items():
                    cls.results[(machine, name)] = cache[name][1]
                    report.write(f"{name}\t{cache[name][1]}\n")
                    f.write(f"{name}\t{h}\t{cache[name][1]}\n")

    def test_every_game_file_gets_a_result_on_each_machine(self):
        self.assertEqual(len(self.results), len(COLLECTION_MACHINES) * len(os.listdir(GAMES)))


if __name__ == "__main__":
    unittest.main()
