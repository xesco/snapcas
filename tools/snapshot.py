"""A snapshot's folder (docs/FORMATS.md, Snapshot files): the files that
capture.py writes in snap/, and that the build, the check and the patches read.

Snapshot gives each file under one name, so that only this module knows the
folder's layout: the state's values, the RAM pages and their files' names, the
slot map and the capture's patches.
"""
import collections
import functools
import os

import gamefile

PAGE = 16384  # the bytes of a page


class SnapshotError(Exception):
    """A snapshot's file that cannot be read."""


class RamName(collections.namedtuple("RamName", "ps ss page seg")):
    """What the name of a ram/ file holds, <ps>-<ss>-<page>-<seg>.bin: the RAM
    page's primary slot, its subslot, or None in a slot that is not expanded,
    the page, 0 to 3, that selects it, and its mapper segment, or None outside
    a mapper. The name has x for a None."""

    @classmethod
    def parse(cls, file):
        """The values of a ram/ file's name."""
        ps, ss, page, seg = file[:-len(".bin")].split("-")
        return cls(int(ps), None if ss == "x" else int(ss), int(page), None if seg == "x" else int(seg))

    @property
    def stem(self):
        """The file's name without .bin, as scan.txt names a RAM page."""
        return "-".join("x" if value is None else str(value) for value in self)

    @property
    def file(self):
        """The file's name."""
        return self.stem + ".bin"

    @property
    def cpu_page(self):
        """<ps>-<ss>-<page>, as build.txt names the page for the check."""
        return self.stem.rsplit("-", 1)[0]

    @property
    def slot_id(self):
        """The slot as a slot ID (DESIGN.md, Terms)."""
        return self.ps if self.ss is None else 0x80 | (self.ss << 2) | self.ps

    @property
    def key(self):
        """What the RAM page is: its mapper segment in its slot, or its page in
        its slot outside a mapper. A game can select one segment in two pages,
        which then have two files with one key."""
        return (self.slot_id, self.seg) if self.seg is not None else (self.slot_id, "page", self.page)


class RamPage:
    """A RAM page that the snapshot keeps: the values of its file's name, and
    its 16 KB, which the build changes."""

    def __init__(self, name, data):
        self.name = name
        self.data = data


class Snapshot:
    """The snapshot in a folder. Each file is read when it is first asked
    for."""

    def __init__(self, folder):
        self.folder = folder

    def load(self):
        """Reads state.txt now, so that a folder without a snapshot stops the
        caller here, and returns the snapshot."""
        self.state
        return self

    def path(self, name):
        """The path of a file of the snapshot, such as log.txt."""
        return os.path.join(self.folder, name)

    def read(self, name):
        """The bytes of a file of the snapshot, such as rom.bin."""
        with open(self.path(name), "rb") as f:
            return f.read()

    @functools.cached_property
    def state(self):
        """state.txt as {name: text}: the machine's state at the snapshot."""
        state = {}
        with open(self.path("state.txt")) as f:
            for line in f.read().splitlines():
                name, value = line.split(" ", 1)
                state[name] = value
        return state

    def num(self, name):
        """A value of state.txt as a number, 0 for "-"."""
        value = self.state[name]
        return 0 if value == "-" else int(value, 16)

    def selected_slot(self, page):
        """The (primary slot, subslot) that the snapshot selects in a page, 0
        to 3. The subslot is None in a slot that is not expanded."""
        ps = (self.num("a8") >> (2 * page)) & 3
        sub = self.state[f"sub{ps}"]
        ss = None if sub == "-" else (int(sub, 16) >> (2 * page)) & 3
        return ps, ss

    def mapper_size(self, slot):
        """The size in segments of the mapper in a slot, (primary slot,
        subslot), which the capture writes for each mapper that holds a kept
        page, or None: for a slot without one, and for a snapshot of an older
        capture, which wrote no sizes."""
        ps, ss = slot
        size = self.state.get(f"mapper{ps}-{'x' if ss is None else ss}")
        return int(size, 16) if size else None

    @functools.cached_property
    def ram_names(self):
        """The names of the ram/ files, in the order of their text."""
        return [RamName.parse(file) for file in sorted(os.listdir(self.path("ram")))]

    @functools.cached_property
    def ram_pages(self):
        """The RAM pages of ram/, each mapper segment and each page outside a
        mapper once, under the first of its files' names."""
        pages, seen = [], set()
        for name in self.ram_names:
            data = bytearray(self.read(os.path.join("ram", name.file)))
            if len(data) != PAGE:
                raise SnapshotError(f"{self.folder}/ram/{name.file}: not 16 KB")
            if name.key not in seen:
                seen.add(name.key)
                pages.append(RamPage(name, data))
        return pages

    def names_of(self, ram_page):
        """The names of a RAM page's files: one for each page that selects
        it."""
        return [name for name in self.ram_names if name.key == ram_page.name.key]

    def selected_ram(self, page):
        """The kept RAM page that the snapshot selects in a page, 0 to 3, or
        None. A mapper's page is found by its segment, which a game can select
        in two pages: the mapper register's value modulo the mapper's size, as
        the capture names the page's file. state.txt holds the value as the
        game wrote it."""
        slot = self.selected_slot(page)
        seg = self.num("f" + "cdef"[page])
        size = self.mapper_size(slot)
        if size:
            seg %= size
        found = [p for p in self.ram_pages if (p.name.ps, p.name.ss) == slot and p.name.seg == seg]
        found += [p for p in self.ram_pages if (p.name.ps, p.name.ss, p.name.page) == (*slot, page)
                  and p.name.seg is None]
        return found[0] if found else None

    @functools.cached_property
    def slots(self):
        """slots.txt, the capture's slot map: for each page, the primary slots
        that hold nothing there and the slot that replaces them, or -1. None
        for a snapshot without it."""
        if not os.path.exists(self.path("slots.txt")):
            return None
        slots = {}
        with open(self.path("slots.txt")) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    _, page, _, empty, _, with_ = line.split()
                    slots[int(page)] = (set() if empty == "-" else {int(v) for v in empty.split(",")}, int(with_))
        return slots

    def error(self):
        """error.txt, the error of a capture that failed, or None."""
        if not os.path.exists(self.path("error.txt")):
            return None
        with open(self.path("error.txt")) as f:
            return f.read().strip()

    def new_patches(self):
        """newpatch.txt, the patch lines that a capture stopped with, or None:
        one line for a slot patch, and one for each copy of the RAM search."""
        return self.patch_lines("newpatch.txt") if os.path.exists(self.path("newpatch.txt")) else None

    def write_patches(self, found):
        """Writes patches.txt, the capture's patches of the tape, from the
        patches that new_patches gave."""
        with open(self.path("patches.txt"), "w") as f:
            f.write("# The capture's patches of the tape (docs/INTERNALS.md, Slot patches, The RAM search patch).\n")
            f.writelines(patch.line + "\n" for patch in found)

    def capture_patches(self):
        """patches.txt, the capture's patches of the tape: the slot patches
        and the RAM search patch. None of them without the file."""
        return self.patch_lines("patches.txt") if os.path.exists(self.path("patches.txt")) else []

    def patch_lines(self, name):
        """The patch lines of a file of the snapshot, each with its text as
        line."""
        patches = []
        with open(self.path(name)) as f:
            for line in f.read().splitlines():
                if line.strip() and not line.startswith("#"):
                    patches.append(gamefile.read_patch(line.split()[1:], self.path(name)))
                    patches[-1].line = line
        return patches
