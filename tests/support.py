"""What the tests share (docs/PLAN.md, Test setup): the folders, the tools as
programs, the files that a test writes in place of a capture's, an image's
header, and the runs in openMSX.

The tests are in two tiers, by module. PURE lists the modules of the pure
tier, whose tests start no openMSX and read no tape of tests/tapes/: make unit
runs them alone, in a few seconds. Every other test module is in the emulator
tier, which make test runs with the pure tier. tests/run.py runs the pure tier
with PURE_RUN set and with OPENMSX naming no program, so a test there that
asks for a tape or starts openMSX fails.

No test module imports another: what two modules need is here.
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _path in (ROOT, os.path.join(ROOT, "tools")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import build  # noqa: E402
from cas import HEADER as CAS_HEADER  # noqa: E402
import check  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
from snapshot import Snapshot  # noqa: E402

# The pure tier's modules.
PURE = ("test_build", "test_card", "test_cli", "test_custom", "test_download", "test_gamefile", "test_gamesrun",
        "test_gate", "test_msx", "test_patches", "test_pipeline", "test_snapshot", "test_tape")
# What tests/run.py sets for a run of the pure tier.
PURE_RUN = os.environ.get("SNAPCAS_TESTS") == "pure"

# The openMSX home of the tests, which the Makefile makes (OPENMSX_HOME).
os.environ.setdefault("OPENMSX_HOME", os.path.join(ROOT, "out", "cache", "openmsx-home"))

# The tests' tape files, which git holds.
TAPES = os.path.join(HERE, "tapes")
# The folders of the DOS system files: Nextor's, which the Makefile downloads,
# and the others below DOS_DIR, which the user fills.
DOS_DIR = msx.DOS
NEXTOR = os.environ.get("NEXTOR_DIR", os.path.join(DOS_DIR, "nextor"))
SERVICE = os.path.join(ROOT, "bin", "SERVICE.BIN")
COM = os.path.join(ROOT, "bin", "SNAPCAS.COM")
PHC28S = "phc28s-ram64k-carnivore2"
VG8020 = "vg8020-carnivore2"


class SetupError(Exception):
    """A file that make test makes or git holds is missing: an error of the
    setup, which fails the test. It is not a reason to skip it."""


def emulator():
    """Stops a test of the pure tier that needs openMSX or a tape."""
    if PURE_RUN:
        raise AssertionError("a test of the pure tier (tests/support.py, PURE) needs openMSX or a tape of "
                             "tests/tapes/")


def tape(name):
    """The path of a tape file of tests/tapes/."""
    emulator()
    path = os.path.join(TAPES, name)
    if not os.path.isfile(path):
        raise SetupError(f"tests/tapes/{name} is missing: git holds the tests' tapes, and the Makefile's "
                         "TEST_TAPES lists them")
    return path


def read_tape(name):
    with open(tape(name), "rb") as f:
        return f.read()


def dos(name):
    """The folder of a DOS's system files: nextor, msxdos1 or msxdos2."""
    return NEXTOR if name == "nextor" else os.path.join(DOS_DIR, name)


def dos_of(machine):
    """The folder of the DOS files that a machine boots, by its machine
    file's dosfiles line."""
    return dos(msx.read_machine(msx.machine_path(machine)).dos_files)


def needs_dos(*names):
    """Skips a test or a class without the files of MSX-DOS 1 or MSX-DOS 2,
    which snapcas cannot ship, so the Makefile cannot make them."""
    missing = [name for name in names if not os.path.isdir(dos(name))]
    return unittest.skipIf(missing, f"DOS_DIR holds no {' or '.join(missing)} folder (dos/README.md)")


def work(name):
    """A module's folder below out/test/, for the output of its openMSX
    runs, which stays for the user to look at."""
    emulator()
    return os.path.join(ROOT, "out", "test", name)


def temp(case):
    """A temporary folder that goes when the test ends, or the class when
    case is a class."""
    folder = tempfile.mkdtemp(prefix="snapcas-test-")
    cleanup = case.addClassCleanup if isinstance(case, type) else case.addCleanup
    cleanup(shutil.rmtree, folder, ignore_errors=True)
    return folder


def symbols(name):
    """The symbols of an assembly, {label: address}, from out/<name>.sym,
    which make all and make test write: snapcas, service, and the test games
    borrow, contract and guard."""
    path = os.path.join(ROOT, "out", name + ".sym")
    if not os.path.isfile(path):
        raise SetupError(f"out/{name}.sym is missing: make all and make test write it")
    with open(path) as f:
        return {label: int(value, 16) for label, _, value in (line.strip().partition(": EQU ") for line in f)}


def service():
    """bin/SERVICE.BIN as build.py reads it."""
    return build.read_service(SERVICE)


# ---- The tools as programs ----

def tool(name, *args):
    """Runs a tool of tools/ as a program."""
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", name), *args],
                          capture_output=True, text=True)


def command(*args, **options):
    """Runs the snapcas command, snapcas.py at the repository's top, with the
    tests' tapes in place of downloads/."""
    env = dict(options.pop("env", os.environ), SNAPCAS_DOWNLOADS=TAPES)
    return subprocess.run([os.path.join(ROOT, "snapcas.py"), *args], capture_output=True, text=True, env=env,
                          **options)


# ---- Game folders ----

def game_folder(folder, text="cas GAME.CAS\n", machines=None):
    """Writes a game folder, new: game.txt with the text, and the machines'
    game files, as {machine: text}. Returns the folder."""
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    with open(os.path.join(folder, "game.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    for machine, lines in (machines or {}).items():
        with open(gamefile.machine_file(folder, machine), "w", encoding="utf-8") as f:
            f.write(lines)
    return folder


def shipped_copy(folder, name):
    """Copies the shipped game's folder games/<name>/ to folder, outside
    games/, so that the tools keep its work files in the copy
    (gamefile.out_folder). Returns the folder."""
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "games", name), folder)
    return folder


# ---- Tapes that a test writes ----

def cas_file(*blocks, pad=True):
    """A CAS file of the blocks: each after the header, at a multiple of 8
    bytes with pad."""
    data = b""
    for block in blocks:
        if pad:
            data += bytes(-len(data) % 8)
        data += CAS_HEADER + block
    return data


def binary_tape(name, code, start, *blocks):
    """A CAS file that BLOAD"CAS:",R loads: the binary file name, of 6
    characters, with the code that loads and starts at start, and then the
    blocks."""
    return cas_file(b"\xD0" * 10 + name.encode(), struct.pack("<3H", start, start + len(code) - 1, start) + code,
                    *blocks)


# A BASIC program on tape, for CLOAD: 10 END.
BASIC_TAPE = cas_file(b"\xD3" * 10 + b"GAME  ", bytes.fromhex("07 80 0A 00 81 00 00 00") + bytes(7))


# ---- A snapshot that a test writes ----

def snapshot(folder, ram=None, mapper=True, service=False, shared=False, v9938=False, **state):
    """Writes a small snapshot in folder (FORMATS.md, Snapshot files), and
    returns the folder. It has what the build and check.py read: state.txt,
    ram/, vram.bin at zero, rom.bin, slots.txt and log.txt.

    The ROM is in slot 0, and its rom.bin holds only the tape's jump table.
    The RAM of pages 1 to 3 is in slot 3: with mapper, in segments 2, 1 and 0
    of a mapper of 32 segments, or else outside a mapper. With shared, pages
    2 and 3 select one segment, 5, which the capture writes once for each
    page. With service, the snapshot has the tape service. With v9938, the
    state and VRAM are an MSX2's. ram gives the RAM pages in place of these,
    as {name of the ram/ file without .bin: bytes}, and state the values of
    state.txt that differ: the stack pointer is F000h, in page 3."""
    os.makedirs(os.path.join(folder, "ram"), exist_ok=True)
    values = {name: "0000" for name in "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()}
    values.update({f"psg{r}": "00" for r in range(16)})
    values.update({f"vdp{r}": "00" for r in (list(range(24)) + list(range(32, 46)) if v9938 else range(8))})
    if v9938:
        values.update({f"pal{c}": "0000" for c in range(16)})
    values.update({f"sub{ps}": "-" for ps in range(4)})
    values.update(i="00", im="01", iff="1", a8="FC", ppic="50", psgsel="00", vramptr="00000", vramwrite="1",
                  service="1" if service else "0", tapepos="000000", tapetime="0.00", tapeside="1", sp="F000",
                  pc="C000", fc="03", fd="02", fe="01", ff="00")
    if ram is None:
        if mapper:
            segments = (2, 5, 5) if shared else (2, 1, 0)
            values.update({"mapper3-x": "20", "fd": f"{segments[0]:02X}", "fe": f"{segments[1]:02X}",
                           "ff": f"{segments[2]:02X}"})
            ram = {f"3-x-{page}-{segment}": bytes(build.PAGE) for page, segment in zip((1, 2, 3), segments)}
        else:
            ram = {f"3-x-{page}-x": bytes(build.PAGE) for page in (1, 2, 3)}
    values.update(state)
    for name, data in ram.items():
        with open(os.path.join(folder, "ram", name + ".bin"), "wb") as f:
            f.write(data)
    found = build.read_service(SERVICE)
    rom = bytearray(2 * build.PAGE)
    jumps = {entry: found[f"t_{name}"] for name, entry in build.TAPE_ENTRIES.items() if name != build.UNCHECKED}
    jumps[build.OUTDO] = found["T0_END"]
    for entry, target in jumps.items():
        rom[entry:entry + 3] = bytes([0xC3]) + struct.pack("<H", target)
    for name, data in (("rom.bin", rom), ("vram.bin", bytes((8 if v9938 else 1) * build.PAGE))):
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
    texts = {"state.txt": "".join(f"{name} {value}\n" for name, value in values.items()),
             # No slot holds nothing, so the scan finds no slot value to fix.
             "slots.txt": "".join(f"page {page} empty - with -1\n" for page in range(4)),
             "log.txt": "0.00 typed RUN\n1.00 load stopped at tape position 0\n1.02 snapshot at an interrupt's entry\n"}
    for name, text in texts.items():
        with open(os.path.join(folder, name), "w") as f:
            f.write(text)
    return folder


def snapshot_game(folder, machine=VG8020, text="cas GAME.CAS\n", side1=BASIC_TAPE, **options):
    """Writes a game folder outside games/ with a snapshot of snapshot() for a
    machine, as a capture leaves it, and its tape beside game.txt. Returns
    the folder, which is also the folder of its tapes."""
    game_folder(folder, text)
    with open(os.path.join(folder, "GAME.CAS"), "wb") as f:
        f.write(side1)
    snapshot(os.path.join(gamefile.out_folder(machine, folder), "snap"), **options)
    return folder


class Header:
    """An image's header and tables, read by the names of SERVICE.BIN's
    symbols."""

    def __init__(self, header):
        self.bytes = header
        self.service = build.read_service(SERVICE)

    def __getitem__(self, name):
        return self.bytes[self.service[name]]

    def word(self, name):
        return struct.unpack_from("<H", self.bytes, self.service[name])[0]

    @property
    def records(self):
        at = self.service["H_TABLE"]
        return [tuple(self.bytes[at + 4 * n:at + 4 * n + 4]) for n in range(self["H_RECS"])]

    @property
    def writes(self):
        at = self.service["H_TABLE"] + 4 * self["H_RECS"]
        return [tuple(self.bytes[at + 2 * n:at + 2 * n + 2]) for n in range(self["H_WRITES"])]

    @property
    def places(self):
        at = self.service["H_TABLE"] + 4 * self["H_RECS"] + 2 * self["H_WRITES"]
        return [struct.unpack_from("<BH", self.bytes, at + 3 * n) for n in range(self["H_PLACES"])]


# ---- A game's capture, build and check, as programs ----

class Restored:
    """How the capture, the build and the check of a game ended, as the tools
    say it as programs:

    step    the tool that failed before the check, capture.py or build.py, or
            None
    status  the exit status of the last tool that ran: check.py's, when the
            capture and the build pass
    error   what that tool printed on standard error
    report  the check's report, or "" without a check
    """

    def __init__(self, folder, machine, step, status, error, report=""):
        self.folder, self.machine = folder, machine
        self.step, self.status, self.error, self.report = step, status, error, report
        self.out = gamefile.out_folder(machine, folder)
        self.snap = os.path.join(self.out, "snap")

    def __repr__(self):
        return f"{self.step or 'check.py'}: exit status {self.status}\n{self.error}{self.report}"

    @property
    def points(self):
        """The report's points, as {number: whether it passes}."""
        return {number: passed for number, passed, _ in check.points(self.report)}

    def lines(self, point):
        """The lines of the report under a point, without their indent."""
        return [line.strip() for number, _, lines in check.points(self.report) if number == point for line in lines]

    @property
    def snapshot(self):
        return Snapshot(self.snap)

    def read(self, name, binary=False):
        """A file of the game's work folder, such as scan.txt or
        snap/log.txt."""
        with open(os.path.join(self.out, name), "rb" if binary else "r") as f:
            return f.read()

    @property
    def header(self):
        """The header of the game's image."""
        name = gamefile.read_game(self.folder, self.machine).name
        with open(gamefile.image_path(self.machine, self.folder, name), "rb") as f:
            return Header(f.read(4096))


def make_image(folder, machine, tapes=TAPES):
    """Captures and builds the game of a folder on a machine. Returns the
    Restored, without a check."""
    emulator()
    for step in ("capture.py", "build.py"):
        result = tool(step, folder, machine, "--tapes", tapes)
        if result.returncode != 0:
            return Restored(folder, machine, step, result.returncode, result.stderr)
    return Restored(folder, machine, None, 0, result.stderr)


def check_image(folder, machine, dos_folder=None):
    """Runs check.py on the image of a folder's game, with the DOS files that
    the machine's file names, or those of dos_folder. Returns the Restored."""
    emulator()
    result = tool("check.py", folder, machine, "--dos", dos_folder or dos_of(machine))
    return Restored(folder, machine, None, result.returncode, result.stderr, result.stdout)


def restore(folder, machine, tapes=TAPES, dos_folder=None):
    """Captures, builds and checks the game of a folder on a machine, and
    returns the Restored."""
    made = make_image(folder, machine, tapes)
    return made if made.step else check_image(folder, machine, dos_folder)


ALL_PASS = {1: True, 2: True, 3: True, 4: True}


def assert_passes(test, restored):
    """The gate: the capture and the build pass, and check.py exits with 0 for
    a report whose four points pass."""
    test.assertIsNone(restored.step, restored)
    test.assertEqual((restored.status, restored.points), (0, ALL_PASS), restored)


def assert_fails(test, restored, point, line):
    """check.py exits with 3 for a report whose one failed point is point,
    with a line under it that holds the text line."""
    test.assertIsNone(restored.step, restored)
    test.assertEqual((restored.status, restored.points), (3, {**ALL_PASS, point: False}), restored)
    test.assertTrue(any(line in text for text in restored.lines(point)), restored)


# ---- Runs in openMSX ----

def cbios(script, timeout=120):
    """Runs a Tcl script, after the prelude, in openMSX's C-BIOS machine,
    which needs no system ROMs."""
    emulator()
    return msx.run(["-machine", msx.DISK_MACHINE], script, timeout=timeout)


def screen_after(machine, image, text, out, timeout=120):
    """Boots the machine with the disk image, passes its boot menu, and waits
    until the screen shows the text or the emulated timeout passes. Writes the
    screen to out and returns it."""
    emulator()
    out = os.path.abspath(out)
    if os.path.exists(out):
        os.unlink(out)
    script = f"""
proc finish {{}} {{
  set f [open {msx.tcl_word(out)} w]; puts $f [screen]; close $f; stop
}}
safe {{boot {{{msx.boot_steps(machine)}}} {{wait_screen {msx.tcl_word(text)} {timeout} finish finish}}}}
"""
    stderr = msx.run([*machine.args, f"-{machine.disk}", os.path.abspath(image)], script, timeout=timeout * 4)
    if not os.path.exists(out):
        raise msx.MachineError(f"openMSX stopped before the screen{msx.last_output(stderr)}")
    with open(out) as f:
        return f.read()


# ---- The restorer on an image that a test writes ----

def synthetic_image(crcs, records, cut=0, **fields):
    """An image that the test writes (FORMATS.md, Image): the ROMs' CRC-16s,
    the records, each as (type, 3 bytes by type, its data's byte, or None for
    a record without its data), and the header's other fields by their names,
    with a tail in page 2. cut leaves out the file's last bytes."""
    found = service()
    header = bytearray(found["H_SIZE"])
    header[:8] = found.mark
    struct.pack_into("<HH", header, found["H_ROM"], *crcs)
    struct.pack_into("<H", header, found["H_TAIL"], 0x8000)
    header[found["H_RECS"]] = len(records)
    for name, value in fields.items():
        value = value if isinstance(value, tuple) else (value,)
        header[found[name]:found[name] + len(value)] = bytes(value)
    data = b""
    for n, (kind, b1, b2, b3, fill) in enumerate(records):
        at = found["H_TABLE"] + found["REC_SIZE"] * n
        header[at:at + 4] = bytes([kind, b1, b2, b3])
        if kind != found["REC_ZEROS"] and fill is not None:
            data += bytes([fill]) * found["DATA_SIZE"]
    image = bytes(header) + data
    return image[:len(image) - cut]


def restorer_run(machine, dos_folder, folder, files, lines, tcl):
    """Boots a machine with a disk of the DOS files, SNAPCAS.COM, the files
    and an AUTOEXEC.BAT of the lines, with the Tcl before the boot. The Tcl
    ends the run. A breakpoint's condition $::snapcas holds while SNAPCAS.COM
    is the program at 0100h."""
    emulator()
    os.makedirs(folder, exist_ok=True)
    paths = [os.path.join(dos_folder, name) for name in sorted(os.listdir(dos_folder))] + [COM]
    for name, data in dict(files, **{"AUTOEXEC.BAT": "".join(line + "\r\n" for line in lines).encode()}).items():
        paths.append(os.path.join(folder, name))
        with open(paths[-1], "wb") as f:
            f.write(data)
    disk = os.path.join(folder, "disk.dsk")
    machine = msx.read_machine(msx.machine_path(machine))
    msx.make_disk(disk, paths, machine.disk_size)
    with open(COM, "rb") as f:
        com = " ".join(str(b) for b in f.read(3))
    script = (f"set ::snapcas {{[debug read_block memory 0x0100 3] eq [binary format c3 {{{com}}}]}}\n"
              + msx.tcl("tcl/memory.tcl") + tcl
              + "\nlater 300 { error {the run did not end within 300 seconds} }\n"
              + "safe {boot {" + msx.boot_steps(machine) + "} {}}\n")
    msx.run([*machine.args, f"-{machine.disk}", disk], script, timeout=600)


def restorer_facts(machine, dos_folder, folder):
    """What an image for a machine depends on, read when the restorer has
    found DOS's mapper: the CRC-16s of the main ROM and the sub-ROM, DOS's
    mapper's slot ID, and its size in segments, 0 for 256."""
    restorer = symbols("snapcas")
    out = os.path.join(folder, "facts.bin")
    if os.path.exists(out):
        os.remove(out)
    tcl = f"""
debug set_bp {restorer["check_roms"]} $::snapcas {{safe {{
    read_exptbl
    lassign [slot_parts [exptbl 0]] ps ss
    set data [binary format cc [debug read memory {restorer["dos_slot"]}] [debug read memory {restorer["map_size"]}]]
    append data [with_slot $ps $ss 0 {{ read_page 0 }}] [with_slot $ps $ss 1 {{ read_page 1 }}]
    # EXBRSA: the sub-ROM's slot ID, 0 on an MSX1.
    set id [debug read memory 0xFAF8]
    if {{$id}} {{ lassign [slot_parts $id] ps ss; append data [with_slot $ps $ss 0 {{ read_page 0 }}] }}
    set f [open {msx.tcl_word(out)} wb]; puts -nonewline $f $data; close $f
    stop
}}}}
"""
    restorer_run(machine, dos_folder, os.path.join(folder, "facts"), {"FACTS.SNP": synthetic_image((0, 0), [])},
                 ["SNAPCAS FACTS"], tcl)
    with open(out, "rb") as f:
        data = f.read()
    roms = data[2:]
    return {"crcs": (build.crc16(roms[:32768]), build.crc16(roms[32768:]) if len(roms) > 32768 else 0),
            "dos_slot": data[0], "map_size": data[1]}


# The Tcl that ends a run of restorer_run: when the screen shows the message
# for NONE, which no file is, it writes the screen to the file out.
def _look_for_none(out):
    return f"""
proc finish {{}} {{ set f [open {msx.tcl_word(out)} w]; puts $f [screen]; close $f; stop }}
proc look {{}} {{
    if {{[string first "NONE.SNPnotfound" [regsub -all {{\\s}} [screen] ""]] >= 0}} {{ finish }}
    later 0.5 look
}}
later 1 look
"""


def restorer_screen(machine, dos_folder, folder, files, tcl="", options=""):
    """Runs SNAPCAS on each file, in the files' order, with the options after
    its name, and then on NONE, which no file is. Returns the screen's text
    after NONE's message, without its spaces, because a message wraps at the
    screen's width."""
    out = os.path.join(folder, "screen.txt")
    if os.path.exists(out):
        os.remove(out)
    restorer_run(machine, dos_folder, folder, files,
                 [f"SNAPCAS {name[:-4]}{options}" for name in files] + ["SNAPCAS NONE"], tcl + _look_for_none(out))
    with open(out) as f:
        return re.sub(r"\s", "", f.read())


def said(text):
    """A message as restorer_screen returns it."""
    return re.sub(r"\s", "", text)


def restorer_memory(machine, dos_folder, folder, image, jump, code, reads, seconds=120):
    """Restores an image, as GAME.SNP, to the end: the run stops when the CPU
    is at the address jump while the bytes of code are there, as at the tail's
    jump to the game. Returns the restored machine's memory then, as the CPU
    sees it, for each of reads: {name: (address, length)} gives {name: bytes}.
    The image can have any CRC-16s, because the run leaves out the restorer's
    check of the ROMs. A restore that does not reach the jump within the
    emulated seconds ends openMSX with an error."""
    restorer = symbols("snapcas")
    out = os.path.join(folder, "memory.txt")
    if os.path.exists(out):
        os.remove(out)
    tcl = f"""
debug set_bp {restorer["check_roms"]} $::snapcas {{safe {{
    reg PC [word_at [reg SP]]
    reg SP [expr {{[reg SP] + 2}}]
}}}}
debug set_bp {jump} {{[debug read_block memory {jump} {len(code)}] eq [binary format c{len(code)} {msx.tcl_bytes(code)}]}} {{safe {{
    set f [open {msx.tcl_word(out)} w]
    foreach {{name address length}} {{{" ".join(f"{name} {at} {length}" for name, (at, length) in reads.items())}}} {{
        binary scan [debug read_block memory $address $length] H* hex
        puts $f "$name $hex"
    }}
    close $f
    stop
}}}}
later {seconds} {{ error "the restore did not reach {jump:04X}h within {seconds} seconds, screen: [screen]" }}
"""
    restorer_run(machine, dos_folder, folder, {"GAME.SNP": image}, ["SNAPCAS GAME"], tcl)
    with open(out) as f:
        return {name: bytes.fromhex(value) for name, value in (line.split() for line in f)}


# The restorer's plan (src/snapcas.asm, plan), as restorer_plans reads it: each
# name is a label of the restorer's data, with its length in bytes.
PLAN = {"dos_slot": 1, "map_size": 1, "dos_seg0": 4, "free_count": 1, "hold_count": 1, "holds": 128, "dest": 256,
        "svc_segs": 65, "t0_fixed": 1, "t0_fix": 1, "t0_direct": 1, "worker_seg": 1, "manual": 1}


def restorer_plans(machine, dos_folder, folder, files, options=""):
    """Runs SNAPCAS on each file, in the files' order, with the options after
    its name, and ends each run when its plan is made, before the restorer
    reads a record. An image here needs only its header, with any CRC-16s,
    because the run leaves out the restorer's checks of the ROMs and of the
    file's size. Returns {the file's name without .SNP: its plan}, without the
    files that the restorer refuses, and the screen as restorer_screen returns
    it. A plan is {name of PLAN: its bytes}, and the header's mapper registers
    as the plan leaves them, under map."""
    restorer = symbols("snapcas")
    out = os.path.join(folder, "plans.txt")
    if os.path.exists(out):
        os.remove(out)
    fields = dict({name: (restorer[name], length) for name, length in PLAN.items()},
                  map=(restorer["HDR"] + service()["H_MAP"], 4), name=(restorer["fcb"] + 1, 8))
    tcl = f"""
# The ROMs and the file's size are not checked: the restorer's check_roms and
# check_size return at once.
foreach address {{{restorer["check_roms"]} {restorer["check_size"]}}} {{
    debug set_bp $address $::snapcas {{safe {{
        reg PC [word_at [reg SP]]
        reg SP [expr {{[reg SP] + 2}}]
    }}}}
}}
# The plan is made when the restorer starts to read the records. The run ends
# there as a stop does, with an empty message.
debug set_bp {restorer["read_records"]} $::snapcas {{safe {{
    set f [open {msx.tcl_word(out)} a]
    foreach {{name address length}} {{{" ".join(f"{name} {at} {length}" for name, (at, length) in fields.items())}}} {{
        binary scan [debug read_block memory $address $length] H* hex
        puts $f "$name $hex"
    }}
    puts $f end
    close $f
    reg DE {restorer["t_crlf"]}
    reg PC {restorer["stop_message"]}
}}}}
"""
    screen = restorer_screen(machine, dos_folder, folder, files, tcl, options)
    plans = {}
    if os.path.exists(out):
        with open(out) as f:
            for text in f.read().split("end\n")[:-1]:
                plan = {name: bytes.fromhex(value) for name, value in (line.split() for line in text.splitlines())}
                plans[plan.pop("name").decode().strip()] = plan
    return plans, screen
