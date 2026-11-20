"""Machine-file parser and data models (docs/FILES.md, Machine file)."""
import collections
import os
import re
import shlex

import paths

MACHINES = paths.MACHINES
VARIANTS = paths.VARIANTS

# MSX keyboard matrix special keys, rows 6 to 8: name -> (row, bit).
KEYS = {}
for _row, _names in (
    (6, "shift ctrl graph caps code f1 f2 f3"),
    (7, "f4 f5 esc tab stop bs select return"),
    (8, "space home ins del left up down right"),
):
    for _bit, _name in enumerate(_names.split()):
        KEYS[_name] = (_row, _bit)

RESIDENT_SIGNATURE = 5


class MachineError(Exception):
    """A machine file that cannot be read, or an openMSX run that failed."""


class Resident(collections.namedtuple("Resident", "slot_id address code")):
    """A machine file's resident line: slot ID, entry address, and leading bytes."""

    @property
    def signature(self):
        return self.code[:RESIDENT_SIGNATURE]


class Machine:
    def __init__(self, path, args, disk, disk_size, boot, dos, dos_files, firmware, variants, width=None,
                 resident=None, parent=None):
        self.path = path
        self.args = args  # openMSX arguments, without the program name
        self.disk = disk  # command that inserts a disk image, such as hda
        self.disk_size = disk_size  # the disk image's KB, 720 or 360
        self.boot = boot  # [(text, key)], matched in order
        self.dos = dos    # (prompt, drive) when DOS boots from the machine's own disk
        self.dos_files = dos_files  # the folder below dos/ of the DOS files that it boots
        self.firmware = firmware  # files below the openMSX home's share/ that make firmware makes
        self.width = width  # text width that the capture sets in BASIC, or None
        self.variants = variants  # capture variants' names, in the order to try them
        self.resident = resident  # a Resident, or None
        self.parent = parent  # parent machine whose game files this machine inherits, or None


def press(key, hold=0.1):
    """Tcl that presses a key for hold seconds of emulated time."""
    row, bit = KEYS[key]
    mask = 1 << bit
    return f"keymatrixdown {row} {mask}; after time {hold} [list keymatrixup {row} {mask}]"


def user_machines():
    """The names of the user machines in machines/, sorted."""
    return sorted(f[:-4] for f in os.listdir(MACHINES)
                  if f.endswith(".txt") and os.path.isfile(os.path.join(MACHINES, f)))


def description(path):
    """A machine file's first comment sentence, up to its first full stop or colon."""
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            lines.append(line[1:].strip())
    text = " ".join(lines)
    return re.split(r"[.:](?:\s|$)", text, maxsplit=1)[0]


def machine_path(machine):
    """The machine file path for a machine name or test/<name>."""
    return os.path.join(MACHINES, machine + ".txt")


def variant_path(variant):
    """The machine file path for a capture variant."""
    return os.path.join(VARIANTS, variant + ".txt")


def _parse_resident(words):
    ps, _, ss = words[1].partition("-")
    slot_id = int(ps) | (0x80 | int(ss) << 2 if ss else 0)
    return Resident(slot_id, int(words[2], 16), bytes(int(w, 16) for w in words[3:]))


def read_machine(path):
    args, disk, disk_size, boot, dos, dos_files, variants = None, None, 720, [], None, None, []
    holds, firmware, width, resident, parent = [], [], None, None, None
    with open(path) as f:
        for number, line in enumerate(f, 1):
            words = shlex.split(line, comments=True)
            if not words:
                continue
            where = f"{path}:{number}"
            key = words[0]
            if key == "openmsx" and args is None:
                args = words[1:]
            elif key == "disk" and disk is None and len(words) in (2, 3):
                if len(words) == 3:
                    if words[2] not in ("360", "720"):
                        raise MachineError(f"{where}: a disk is 360 or 720 KB")
                    disk_size = int(words[2])
                disk = words[1]
            elif key == "boot" and len(words) == 3 and words[2] in KEYS:
                boot.append((words[1], words[2]))
            elif key == "hold" and len(words) == 3 and words[1] in KEYS and re.fullmatch(r"\d+", words[2]):
                holds.append(press(words[1], int(words[2])))
            elif key == "press" and len(words) == 3 and words[1] in KEYS and re.fullmatch(r"\d+(\.\d+)?", words[2]):
                holds.append(f"after time {words[2]} {{{press(words[1])}}}")
            elif key == "dos" and dos is None and len(words) == 3 and re.fullmatch(r"[A-H]", words[2]):
                dos = (words[1], words[2])
            elif key == "dosfiles" and dos_files is None and len(words) == 2 and words[1] in ("msxdos1", "msxdos2"):
                dos_files = words[1]
            elif key == "width" and width is None and len(words) == 2 and re.fullmatch(r"\d+", words[1]):
                if not 1 <= int(words[1]) <= 80:
                    raise MachineError(f"{where}: a width is 1 to 80")
                width = int(words[1])
            elif key == "firmware" and len(words) == 2:
                firmware.append(words[1])
            elif (key == "resident" and resident is None and len(words) >= 3 + RESIDENT_SIGNATURE
                  and re.fullmatch(r"[0-3](-[0-3])?", words[1]) and re.fullmatch(r"[0-9A-Fa-f]{4}", words[2])
                  and all(re.fullmatch(r"[0-9A-Fa-f]{2}", w) for w in words[3:])):
                resident = _parse_resident(words)
            elif key == "variant" and len(words) == 2:
                if not os.path.isfile(variant_path(words[1])):
                    raise MachineError(f"{where}: {variant_path(words[1])} does not exist")
                variants.append(words[1])
            elif key == "parent" and parent is None and len(words) == 2:
                if not os.path.isfile(machine_path(words[1])):
                    raise MachineError(f"{where}: {machine_path(words[1])} does not exist")
                parent = words[1]
            else:
                raise MachineError(f"{where}: cannot read this line")
    if args is None or disk is None:
        raise MachineError(f"{path}: needs one openmsx line and one disk line")
    for hold in holds:
        args += ["-command", hold]
    return Machine(path, args, disk, disk_size, boot, dos, dos_files or "nextor", firmware, variants, width,
                   resident, parent)


def machine_chain(machine):
    """The inheritance chain of machine, root parent first: [..., machine].
    Unknown machine names (e.g. in unit tests) return [machine]."""
    chain, seen, cur = [], set(), machine
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        path = machine_path(cur)
        if not os.path.isfile(path):
            break
        cur = read_machine(path).parent
    chain.reverse()
    return chain
