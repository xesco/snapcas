"""Run openMSX for the snapcas tools: machine files, disk images and Tcl scripts.

A machine file (docs/FILES.md, Machine file) names the openMSX arguments, the
command that inserts a disk image and its size, the keys that pass a boot menu or
that are held from power-on, and the machine's capture variants. The tools
drive openMSX with a Tcl script that it runs with the throttle, the renderer and
the sound off, and read results from files that the script writes.
"""
import argparse
import glob
import os
import re
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MACHINES = os.path.join(ROOT, "machines")
# The DOS files that the checks boot, in a folder for each DOS: DOS_DIR, as the
# Makefile sets it, or dos/.
DOS = os.environ.get("DOS_DIR", os.path.join(ROOT, "dos"))
# The capture variants, which only the capture runs on.
VARIANTS = os.path.join(MACHINES, "capture")

# The special keys of the MSX keyboard matrix, rows 6 to 8 (FILES.md, Key
# names): name -> (row, bit).
KEYS = {}
for _row, _names in (
    (6, "shift ctrl graph caps code f1 f2 f3"),
    (7, "f4 f5 esc tab stop bs select return"),
    (8, "space home ins del left up down right"),
):
    for _bit, _name in enumerate(_names.split()):
        KEYS[_name] = (_row, _bit)

# openMSX ships C-BIOS, so a run that only writes a disk image needs no system
# ROMs.
DISK_MACHINE = "C-BIOS_MSX1"
# Real seconds for that run, which takes a few seconds, or a few minutes while
# the collection runs many openMSX at once.
DISK_TIMEOUT = 300


class MachineError(Exception):
    """A machine file that cannot be read, or an openMSX run that failed."""


class DiskError(Exception):
    """A disk image that make_disk did not write. broke says that openMSX
    failed or timed out, so that the error says nothing of the files."""

    def __init__(self, message, broke):
        super().__init__(message)
        self.broke = broke


class Parser(argparse.ArgumentParser):
    """The tools' argument parser."""

    def error(self, message):
        # Exit status 1, as the tools give for an error in their input, and
        # not argparse's 2, which they give when openMSX fails.
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: {message}\n")


class Failure(Exception):
    """A run of capture.py, build.py or check.py that failed, for the tool's
    main and for pipeline.py: its exit status (DESIGN.md, Files and commands),
    its error, which goes to standard error, and whether the run broke: openMSX
    failed, stopped before its result or timed out, so that the error says
    nothing of the game. output is what the tool has for standard output
    beside the error."""

    def __init__(self, status, error, broke=False, output=""):
        super().__init__(error)
        self.status, self.error, self.broke, self.output = status, error, broke, output

    def show(self):
        """Prints the output and the error, and returns the exit status."""
        sys.stdout.write(self.output)
        print(self.error, file=sys.stderr)
        return self.status


class Machine:
    def __init__(self, path, args, disk, disk_size, boot, dos, dos_files, firmware, variants):
        self.path = path
        self.args = args  # openMSX arguments, without the program name
        self.disk = disk  # command that inserts a disk image, such as hda
        self.disk_size = disk_size  # the disk image's KB, 720 or 360
        self.boot = boot  # [(text, key)], matched in order
        self.dos = dos    # (prompt, drive) when DOS boots from the machine's own disk
        self.dos_files = dos_files  # the folder below dos/ of the DOS files that it boots
        self.firmware = firmware  # the files below the openMSX home's share/ that make firmware makes
        self.variants = variants  # the capture variants' names, in the order to try them


def user_machines():
    """The names of the user machines, the machine files in machines/ itself,
    in order (FILES.md, Machine file)."""
    return sorted(f[:-4] for f in os.listdir(MACHINES)
                  if f.endswith(".txt") and os.path.isfile(os.path.join(MACHINES, f)))


def description(path):
    """What a machine file says that the machine is: its first comment's first
    sentence, up to its first full stop or colon, on one line."""
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            lines.append(line[1:].strip())
    text = " ".join(lines)
    return re.split(r"[.:](?:\s|$)", text, maxsplit=1)[0]


def machine_path(machine):
    """The machine file of a machine: its name, such as phc28s-ram64k-carnivore2,
    or a test machine's path below machines/, such as test/nms8250-128k."""
    return os.path.join(MACHINES, machine + ".txt")


def variant_path(variant):
    """The machine file of a capture variant, such as phc28s-ram64k."""
    return os.path.join(VARIANTS, variant + ".txt")


def read_machine(path):
    args, disk, disk_size, boot, dos, dos_files, variants = None, None, 720, [], None, None, []
    holds, firmware = [], []
    with open(path) as f:
        for number, line in enumerate(f, 1):
            words = shlex.split(line, comments=True)
            if not words:
                continue
            where = f"{path}:{number}"
            if words[0] == "openmsx" and args is None:
                args = words[1:]
            elif words[0] == "disk" and disk is None and len(words) in (2, 3):
                if len(words) == 3:
                    if words[2] not in ("360", "720"):
                        raise MachineError(f"{where}: a disk is 360 or 720 KB")
                    disk_size = int(words[2])
                disk = words[1]
            elif words[0] == "boot" and len(words) == 3 and words[2] in KEYS:
                boot.append((words[1], words[2]))
            elif words[0] == "hold" and len(words) == 3 and words[1] in KEYS and re.fullmatch(r"\d+", words[2]):
                holds.append(press(words[1], int(words[2])))
            elif words[0] == "press" and len(words) == 3 and words[1] in KEYS and re.fullmatch(r"\d+(\.\d+)?", words[2]):
                holds.append(f"after time {words[2]} {{{press(words[1])}}}")
            elif words[0] == "dos" and dos is None and len(words) == 3 and re.fullmatch(r"[A-H]", words[2]):
                dos = (words[1], words[2])
            elif words[0] == "dosfiles" and dos_files is None and len(words) == 2 and words[1] in ("msxdos1", "msxdos2"):
                dos_files = words[1]
            elif words[0] == "firmware" and len(words) == 2:
                firmware.append(words[1])
            elif words[0] == "variant" and len(words) == 2:
                if not os.path.isfile(variant_path(words[1])):
                    raise MachineError(f"{where}: {variant_path(words[1])} does not exist")
                variants.append(words[1])
            else:
                raise MachineError(f"{where}: cannot read this line")
    if args is None or disk is None:
        raise MachineError(f"{path}: needs one openmsx line and one disk line")
    # A key held from power-on goes down before the BIOS reads the keyboard,
    # so it is an openMSX command at startup in every run of the machine, as is
    # a key pressed at a time after power-on.
    for hold in holds:
        args += ["-command", hold]
    return Machine(path, args, disk, disk_size, boot, dos, dos_files or "nextor", firmware, variants)


def tcl_word(text):
    """Quotes text as one Tcl word: in braces, which keep every character. A
    text with a brace, a backslash or a line end, as a Windows path has, goes in
    double quotes with a backslash before each character that Tcl reads there,
    because braces cannot hold an unbalanced brace or a last backslash. The
    backslashes also keep the word whole inside another word's braces."""
    if not any(c in text for c in "{}\\\r\n"):
        return "{" + text + "}"
    text = re.sub(r'([{}\\"$\[\]])', r"\\\1", text)
    return '"' + text.replace("\r", "\\r").replace("\n", "\\n") + '"'


def press(key, hold=0.1):
    """Tcl that presses a key for hold seconds of emulated time."""
    row, bit = KEYS[key]
    mask = 1 << bit
    return f"keymatrixdown {row} {mask}; after time {hold} [list keymatrixup {row} {mask}]"


def tcl(name):
    """The text of a Tcl file below tools/, such as tcl/capture.tcl."""
    with open(os.path.join(HERE, name)) as f:
        return f.read()


def tcl_bytes(data):
    """The bytes as a Tcl list of their values."""
    return "{" + " ".join(str(b) for b in data) + "}"


def tcl_type(text):
    """Tcl that types the text. The text goes as hex, so that Tcl reads none
    of its characters, such as a $ or a [ in a load command."""
    return f"type [binary format H* {text.encode('latin-1').hex()}]"


def type_at_prompt(prompt, typed, done=""):
    """Tcl that waits for DOS's prompt, up to the deadline of the prelude's
    at_prompt, and types typed and Return, then runs done."""
    hexed = (typed + "\r").encode("latin-1").hex()
    return f"at_prompt {prompt.encode('latin-1').hex()} {hexed} {tcl_word(done)}"


def at_prompt(machine, typed, done):
    """Tcl that, on a machine that boots DOS from its own disk, waits for
    DOS's prompt and types typed and Return, then runs done."""
    if machine.dos is None:
        return done
    return type_at_prompt(machine.dos[0], typed, done)


def boot_steps(machine):
    return " ".join("{" + tcl_word(text) + " " + tcl_word(press(key)) + "}"
                    for text, key in machine.boot)


# Settings without a sound device: macOS aborts openMSX in its audio session when
# several runs start at once.
SETTINGS = os.path.join(HERE, "openmsx-settings.xml")


def home():
    """openMSX's home folder, where it writes savestates: OPENMSX_HOME, as the
    tests set it, or else openMSX's own default."""
    return os.environ.get("OPENMSX_HOME", os.path.join(os.path.expanduser("~"), ".openMSX"))


def savestates(name):
    """The savestates in openMSX's home whose names start with name and a
    hyphen, as a run's own do: name holds the tool's process ID."""
    folder = os.path.join(home(), "savestates")
    return sorted(glob.glob(os.path.join(glob.escape(folder), glob.escape(name) + "-*.oms")))


def remove_savestates(name):
    """Deletes the savestates of savestates(name): those that a run leaves when
    openMSX is stopped, and those that an earlier run with the same process ID
    left."""
    for path in savestates(name):
        try:
            os.unlink(path)
        except OSError:
            pass


def missing_firmware(machine):
    """The machine's firmware files that the openMSX home does not hold."""
    return [path for path in machine.firmware if not os.path.isfile(os.path.join(home(), "share", path))]


def check_firmware(name):
    """Stops when the openMSX home lacks a file that the machine named name
    needs."""
    missing = missing_firmware(read_machine(machine_path(name)))
    if missing:
        raise MachineError(f"{name} needs {missing[0]} in openMSX's share folder: make firmware makes it")


def dos_folder(name):
    """The folder of the DOS files that the machine named name boots: the one
    below DOS that its machine file's dosfiles line names, or Nextor's. Stops
    when the folder holds no file."""
    dos = read_machine(machine_path(name)).dos_files
    folder = os.path.join(DOS, dos)
    if not glob.glob(os.path.join(glob.escape(folder), "*")):
        raise MachineError(f"{name} boots {dos}: put its files in {os.path.relpath(folder, ROOT)}/ "
                           "(dos/README.md), or name them with --dos <dir>")
    return folder


def dos_files(folder):
    """The DOS system files in a folder, in order. Stops when it holds
    none."""
    files = sorted(glob.glob(os.path.join(glob.escape(folder), "*")))
    if not files:
        raise OSError(f"{folder}: no DOS system files")
    return files


def openmsx():
    """The openMSX program: the one that OPENMSX names, or openmsx on the
    path."""
    return os.environ.get("OPENMSX", "openmsx")


def version():
    """What openMSX says that it is: its version, flavour and components."""
    return subprocess.run([openmsx(), "-v"], capture_output=True, text=True).stdout


def last_output(stderr, lines=3):
    """The last lines of what openMSX printed on standard error, on one line,
    for a tool's error, or nothing when it printed nothing."""
    tail = [line.strip() for line in stderr.splitlines() if line.strip()][-lines:]
    return "; openMSX's last output: " + " | ".join(tail) if tail else ""


def script_files(folder, script, window=False):
    """Writes the files of a run's Tcl in folder, and returns the one that
    openMSX gets: the prelude, and then the script's text from a file of its
    own, so that an error while openMSX reads it, such as an unknown command,
    ends openMSX with status 1 and does not leave it running. With its window,
    openMSX prints the error and stays."""
    body = os.path.join(folder, "script.tcl")
    with open(body, "w") as f:
        f.write(script)
    main = os.path.join(folder, "run.tcl")
    with open(main, "w") as f:
        f.write(tcl("tcl/prelude.tcl"))
        if window:
            f.write('proc script_failed {msg} { puts stderr "script error: $msg" }\n')
        f.write(f"if {{[catch {{source {tcl_word(body)}}} e] && $::run(phase) ne \"stopping\"}} {{\n"
                '  puts stderr "script error: $e"\n'
                + ("" if window else "  exit 1\n") + "}\n")
    return main


def run(args, script, timeout):
    """Runs openMSX with the given arguments and Tcl script text, and returns
    what it printed on standard error, where openMSX reports an error of the
    script: a tool that finds no result adds last_output of it to its own
    error. Raises MachineError with openMSX's message when it stops at a fatal
    error, such as a missing system ROM, and when it ends with another exit
    status than 0 or by a signal: a script ends openMSX with exit, whose
    status is 0, or with status 1 at an error (tcl/prelude.tcl)."""
    with tempfile.TemporaryDirectory(prefix="snapcas-") as folder:
        result = subprocess.run(
            [openmsx(), *args, "-setting", SETTINGS, "-script", script_files(folder, script),
             "-command", "set renderer none; set throttle off; set mute on"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
            timeout=timeout, check=False)
    fatal = result.stderr.find("Fatal error:")
    if fatal >= 0:
        raise MachineError(result.stderr[fatal:].strip())
    if result.returncode < 0:
        raise MachineError(f"openMSX was stopped by signal {-result.returncode}")
    if result.returncode != 0:
        raise MachineError(f"openMSX ended with exit status {result.returncode}{last_output(result.stderr)}")
    return result.stderr


def run_window(args, script):
    """Runs openMSX with its window and the user's settings, sound included,
    the given arguments and Tcl script text, until the user closes it, and
    returns its exit status. An error of the script is printed, and the window
    stays."""
    with tempfile.TemporaryDirectory(prefix="snapcas-") as folder:
        return subprocess.run([openmsx(), *args, "-script", script_files(folder, script, window=True)]).returncode


def make_disk(image, files, size=720):
    """Writes a disk image of size KB, 720 or 360 for a single-sided drive,
    without a partition table, that holds the files. Nextor reads such a device
    from its first sector, and MSX-DOS 1 and MSX-DOS 2 read it as a floppy
    disk. Raises DiskError when openMSX does not write it."""
    image = os.path.abspath(image)
    os.makedirs(os.path.dirname(image), exist_ok=True)
    if os.path.exists(image):
        os.unlink(image)
    result = image + ".txt"
    lines = [f"diskmanipulator create {tcl_word(image)} {size}",
             f"virtual_drive {tcl_word(image)}"]
    lines += [f"diskmanipulator import virtual_drive {tcl_word(os.path.abspath(p))}"
              for p in files]
    lines += ["virtual_drive eject"]
    script = ("if {[catch {\n" + "\n".join(lines) + "\n} e]} { set error $e } else { set error {} }\n"
              f"catch {{ set f [open {tcl_word(result)} w]; puts $f $error; close $f }}\n"
              "exit\n")
    try:
        run(["-machine", DISK_MACHINE], script, timeout=DISK_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise DiskError(f"{image}: openMSX did not write the disk image within {DISK_TIMEOUT} seconds", True)
    except (OSError, MachineError) as e:
        raise DiskError(f"{image}: openMSX did not write the disk image: {e}", True)
    if not os.path.exists(result):
        raise DiskError(f"{image}: openMSX did not write the disk image", True)
    with open(result) as f:
        error = f.read().strip()
    os.unlink(result)
    if error:
        raise DiskError(f"{image}: {error}", False)

