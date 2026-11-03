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


def game_names():
    """The game files' folders below games/: a game's, or a compilation's
    program's in its collection's folder, such as SUPERMSX/GOLF, for a folder
    without a game.txt (DESIGN.md, A game later on the tape)."""
    names = []
    for name in sorted(os.listdir(GAMES)):
        if os.path.isfile(os.path.join(GAMES, name, "game.txt")):
            names.append(name)
        elif os.path.isdir(os.path.join(GAMES, name)):
            names += [f"{name}/{n}" for n in sorted(os.listdir(os.path.join(GAMES, name)))
                      if os.path.isdir(os.path.join(GAMES, name, n))]
    return names


WORK = os.path.join(ROOT, "out", "test", "step9")

# The shipped machines and the DOS that each boots (PLAN.md, Test setup).
SHIPPED = {machine: test_step4.MACHINES[machine][0]
           for machine in ("phc28s-ram64k-carnivore2", "vg8020-carnivore2", "nms8250-carnivore2", "hbf700p-ram512k-msxdos2")}
SHIPPED.update({"nms8245-ram512k-sunriseide": test_step4.NEXTOR, "hb75p-mfrsd": test_step4.NEXTOR,
                "vg8020-picoverse": test_step4.NEXTOR, "vg8020-sdmapper": test_step4.NEXTOR,
                "xp800-sdmapper": test_step4.NEXTOR, "fsa1-mfrsd": test_step4.NEXTOR,
                "hbf1xd-mfrsd": test_step4.NEXTOR, "vg8235": os.path.join(test_step4.DOS_DIR, "msxdos1")})
# A single-load game that fits each of them, the NMS 8250's 128 KB included.
SINGLE = "CALDERO.CAS"


class MachineFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        with open(os.path.join(self.folder, "game.txt"), "w") as f:
            f.write("cas GAME.CAS\nsnapshot at 10\n")
        with open(os.path.join(self.folder, "phc28s-ram64k-carnivore2.txt"), "w") as f:
            f.write("# Only for the PHC-28S.\ncapture phc28s-ram64k\nsnapshot at 20\n")

    def test_the_machine_file_adds_its_lines_for_its_machine(self):
        game = gamefile.read_game(self.folder, "phc28s-ram64k-carnivore2")
        self.assertEqual(game.capture, "phc28s-ram64k")

    def test_the_machine_file_gives_a_value_that_both_give(self):
        self.assertEqual(gamefile.read_game(self.folder, "phc28s-ram64k-carnivore2").snapshot_at, 20)

    def test_other_machines_read_only_game_txt(self):
        game = gamefile.read_game(self.folder, "vg8020-carnivore2")
        self.assertIsNone(game.capture)
        self.assertEqual(game.snapshot_at, 10)


class UrlLine(unittest.TestCase):
    def read(self, text):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(text)
        return gamefile.read_game(folder)

    def test_a_link_for_each_side(self):
        game = self.read("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip https://example.org/b.ZIP\n")
        self.assertEqual(game.urls, ["https://example.org/a.zip", "https://example.org/b.ZIP"])

    def test_a_link_missing_for_side_2_is_refused(self):
        with self.assertRaisesRegex(gamefile.GameFileError, "a link for each side"):
            self.read("cas A.CAS\nside2 B.CAS\nurl https://example.org/a.zip\n")

    def test_a_link_that_is_not_https_to_a_zip_is_refused(self):
        with self.assertRaisesRegex(gamefile.GameFileError, "https links to zip files"):
            self.read("cas A.CAS\nurl http://example.org/a.zip\n")


@unittest.skipUnless(os.path.isdir(GAMES), "no games/ folder")
class ShippedGameFiles(unittest.TestCase):
    def test_each_game_file_links_its_zips_on_file_hunter(self):
        for name in game_names():
            with self.subTest(game=name):
                game = gamefile.read_game(os.path.join(GAMES, name))
                self.assertTrue(game.urls)
                for url in game.urls:
                    self.assertTrue(url.startswith("https://download.file-hunter.com/Games/MSX1/CAS/"), url)

    def test_every_game_file_reads_on_each_machine(self):
        for name in game_names():
            for machine in ("phc28s-ram64k-carnivore2", "vg8020-carnivore2"):
                with self.subTest(game=name, machine=machine):
                    game = gamefile.read_game(os.path.join(GAMES, name), machine)
                    self.assertTrue(game.sha1)

    def test_machine_files_name_a_machine_file(self):
        for name in game_names():
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        self.assertTrue(os.path.isfile(msx.machine_path(file[:-4])))

    def test_capture_lines_name_a_variant_of_their_machine(self):
        for name in game_names():
            for file in os.listdir(os.path.join(GAMES, name)):
                if file.endswith(".txt") and file != "game.txt":
                    with self.subTest(game=name, file=file):
                        machine = file[:-4]
                        game = gamefile.read_game(os.path.join(GAMES, name), machine)
                        if game.capture:
                            variants = msx.read_machine(msx.machine_path(machine)).variants
                            self.assertIn(game.capture, variants)


def single_load(machine):
    """Captures, builds and checks SINGLE on a machine, and returns the check's
    report or the failed step's error."""
    folder = os.path.join(WORK, "games", "single-" + machine.replace("/", "-"))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "game.txt"), "w") as f:
        f.write(f"cas {SINGLE}\n")
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--tapes", test_step4.CAS_DIR)
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
                # The check's own boot, before the restore, is no reboot
                # (PLAN.md, step 16).
                self.assertIn("point 3: pass", report)
                self.assertIn("point 4: pass", report)


@unittest.skipUnless(os.path.isfile(os.path.join(test_step4.CAS_DIR, SINGLE)), f"CAS_DIR holds no {SINGLE}")
class OneCommand(unittest.TestCase):
    def test_snapcas_py_makes_and_checks_the_image(self):
        os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "openmsx-home"))
        folder = os.path.join(WORK, "games", "one-command")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "game.txt"), "w") as f:
            f.write(f"cas {SINGLE}\n")
        result = test_step4.tool("snapcas.py", folder, "phc28s-ram64k-carnivore2", "--tapes", test_step4.CAS_DIR,
                                 "--dos", test_step4.NEXTOR)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("point 1: pass", result.stdout)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "out", "phc28s-ram64k-carnivore2", "one-command", "ONECOMMA.SNP")))


# The collection's CAS files, for the run over every game file, which takes
# hours: make collection sets it.
COLLECTION_DIR = os.environ.get("COLLECTION_DIR")
# The machines of the run, which COLLECTION_MACHINES can name, and the folder
# of their reports, one per machine.
COLLECTION_MACHINES = tuple(os.environ.get("COLLECTION_MACHINES", "phc28s-ram64k-carnivore2 vg8020-carnivore2").split())
REPORTS = os.path.join(WORK, "collection")
# The runs at once: openMSX keeps about one core busy, and the machine's
# efficiency cores count as well.
COLLECTION_WORKERS = int(os.environ.get("COLLECTION_WORKERS", "11"))
# Set to 1, the run gives every game file a new result. Otherwise a game file
# on a machine keeps its last result while its inputs are unchanged.
COLLECTION_FULL = os.environ.get("COLLECTION_FULL") == "1"


# The game files that fail on a machine in openMSX itself (PLAN.md, step 9).
OPENMSX_FAILURES = os.path.join(ROOT, "tests", "openmsx-failures.txt")


def read_openmsx_failures():
    """The list's (machine, game file's folder) pairs."""
    with open(OPENMSX_FAILURES) as f:
        return {tuple(line.split()[:2]) for line in f if line.strip() and not line.startswith("#")}


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
    for cas in (game.tape, game.side2):
        if cas and os.path.isfile(os.path.join(COLLECTION_DIR, cas)):
            file_hash(h, os.path.join(COLLECTION_DIR, cas))
    file_hash(h, msx.machine_path(machine))
    if game.capture:
        file_hash(h, msx.variant_path(game.capture))
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
    the first line of the check's report, the failure of point 2, 3 or 4 with
    its first line when that point fails, or the failed step's error."""
    machine, name = item
    folder = os.path.join(GAMES, name)
    for step in ("capture.py", "build.py"):
        result = test_step4.tool(step, folder, machine, "--tapes", COLLECTION_DIR)
        if result.returncode != 0:
            return (result.stderr.strip().splitlines() or [f"{step} failed"])[-1]
    result = test_step4.tool("check.py", folder, machine, "--dos", SHIPPED[machine])
    lines = result.stdout.strip().splitlines()
    for point in ("point 2: fail", "point 3: fail", "point 4: fail"):
        if point in lines:
            failed = lines.index(point)
            return point + ":" + "".join(lines[failed + 1:failed + 2])
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
            hashes = {name: inputs_hash(machine, name, tools) for name in game_names()}
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
        self.assertEqual(len(self.results), len(COLLECTION_MACHINES) * len(game_names()))

    def test_every_game_file_that_fails_fails_in_openmsx_itself(self):
        known = read_openmsx_failures()
        failed = {item for item, result in self.results.items() if result != "point 1: pass"}
        passing = sorted(item for item in known - failed if item in self.results)
        if passing:
            print("\nIn tests/openmsx-failures.txt, but passing now: "
                  + ", ".join(f"{name} on {machine}" for machine, name in passing), file=sys.stderr)
        unknown = sorted(failed - known)
        if unknown:
            self.fail("These game files fail, and tests/openmsx-failures.txt does not list them:\n"
                      + "\n".join(f"{name} on {machine}: {self.results[(machine, name)]}" for machine, name in unknown))


if __name__ == "__main__":
    unittest.main()
