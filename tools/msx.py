"""Run openMSX for the snapcas tools: machine files, disk images and Tcl scripts.

A machine file (docs/DESIGN.md, Machine file) names the openMSX arguments, the
command that inserts a disk image, and the keys that pass a boot menu. The tools
drive openMSX with a Tcl script that it runs with the throttle, the renderer and
the sound off, and read results from files that the script writes.
"""
import os
import re
import shlex
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MACHINES = os.path.join(os.path.dirname(HERE), "machines")

# The special keys of the MSX keyboard matrix, rows 6 to 8 (DESIGN.md, Key
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
    """A machine file that cannot be read."""


class Machine:
    def __init__(self, path, args, disk, boot, dos):
        self.path = path
        self.args = args  # openMSX arguments, without the program name
        self.disk = disk  # command that inserts a disk image, such as hda
        self.boot = boot  # [(text, key)], matched in order
        self.dos = dos    # (prompt, drive) when DOS boots from the machine's own disk


def machine_path(machine):
    """The machine file of a machine, a path below machines/ without .txt."""
    return os.path.join(MACHINES, machine + ".txt")


def read_machine(path):
    args, disk, boot, dos = None, None, [], None
    with open(path) as f:
        for number, line in enumerate(f, 1):
            words = shlex.split(line, comments=True)
            if not words:
                continue
            where = f"{path}:{number}"
            if words[0] == "openmsx" and args is None:
                args = words[1:]
            elif words[0] == "disk" and disk is None and len(words) == 2:
                disk = words[1]
            elif words[0] == "boot" and len(words) == 3 and words[2] in KEYS:
                boot.append((words[1], words[2]))
            elif words[0] == "dos" and dos is None and len(words) == 3 and re.fullmatch(r"[A-H]", words[2]):
                dos = (words[1], words[2])
            else:
                raise MachineError(f"{where}: cannot read this line")
    if args is None or disk is None:
        raise MachineError(f"{path}: needs one openmsx line and one disk line")
    return Machine(path, args, disk, boot, dos)


def tcl_word(text):
    """Quotes text as one Tcl word."""
    if any(c in text for c in "{}\\\n"):
        raise ValueError(f"cannot quote for Tcl: {text!r}")
    return "{" + text + "}"


def press(key, hold=0.1):
    """Tcl that presses a key for hold seconds of emulated time."""
    row, bit = KEYS[key]
    mask = 1 << bit
    return f"keymatrixdown {row} {mask}; after time {hold} [list keymatrixup {row} {mask}]"


def tcl(name):
    """The text of a Tcl file below tools/, such as tcl/capture.tcl."""
    with open(os.path.join(HERE, name)) as f:
        return f.read()


def at_prompt(machine, typed, done):
    """Tcl that, on a machine that boots DOS from its own disk, waits for
    DOS's prompt and types typed and Return, then runs done."""
    if machine.dos is None:
        return done
    hexed = (typed + "\r").encode("latin-1").hex()
    return f"at_prompt {machine.dos[0].encode('latin-1').hex()} {hexed} {tcl_word(done)}"


def boot_steps(machine):
    return " ".join("{" + tcl_word(text) + " " + tcl_word(press(key)) + "}"
                    for text, key in machine.boot)


# Settings without a sound device: macOS aborts openMSX in its audio session when
# several runs start at once.
SETTINGS = os.path.join(HERE, "openmsx-settings.xml")


def run(args, script, timeout):
    """Runs openMSX with the given arguments and Tcl script text."""
    with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as f:
        f.write(tcl("tcl/prelude.tcl") + script)
        path = f.name
    try:
        subprocess.run(
            ["openmsx", *args, "-setting", SETTINGS, "-script", path,
             "-command", "set renderer none; set throttle off; set mute on"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False)
    finally:
        os.unlink(path)


def make_disk(image, files):
    """Writes a 720 KB disk image without a partition table that holds the
    files. Nextor reads such a device from its first sector, and MSX-DOS 1 and
    MSX-DOS 2 read it as a floppy disk."""
    image = os.path.abspath(image)
    os.makedirs(os.path.dirname(image), exist_ok=True)
    if os.path.exists(image):
        os.unlink(image)
    result = image + ".txt"
    lines = [f"diskmanipulator create {tcl_word(image)} 720",
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
        raise RuntimeError(f"{image}: openMSX did not write the disk image within {DISK_TIMEOUT} seconds")
    if not os.path.exists(result):
        raise RuntimeError(f"{image}: openMSX did not write the disk image")
    with open(result) as f:
        error = f.read().strip()
    os.unlink(result)
    if error:
        raise RuntimeError(f"{image}: {error}")


def screen_after(machine, image, text, out, timeout=120):
    """Boots the machine with the disk image, passes its boot menu, and waits
    until the screen shows the text or the emulated timeout passes. Writes the
    screen to out and returns it."""
    out = os.path.abspath(out)
    script = f"""
set out {tcl_word(out)}
proc finish {{}} {{
  set f [open $::out w]; puts $f [screen]; close $f; exit
}}
proc wait {{left}} {{
  if {{[string first {tcl_word(text)} [screen]] >= 0 || $left <= 0}} {{ finish }}
  after time 0.5 [list wait [expr {{$left - 1}}]]
}}
boot {{{boot_steps(machine)}}} {{wait {timeout * 2}}}
"""
    run([*machine.args, f"-{machine.disk}", os.path.abspath(image)], script,
        timeout=timeout * 4)
    with open(out) as f:
        return f.read()
