#!/usr/bin/env python3
"""Write a game's image from its snapshot (docs/INTERNALS.md, Build).

Usage: build.py <game> <machine> --tapes <dir> [--service <file>]
                [--capture <variant>]

<game> and <machine> are as for capture.py. The image, <GAME>.SNP, scan.txt and
build.txt go to the game's work folder (gamefile.out_folder). --service names
the SERVICE.BIN to use, by default bin/SERVICE.BIN. --capture names the capture
variant that capture.py's --capture gave, in place of the game file's capture
line.

Exit status: 0 on success, 1 for an error in the input files.
"""
import binascii
import collections
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import tape  # noqa: E402
import gamefile  # noqa: E402
import msx  # noqa: E402
import patches  # noqa: E402
from snapshot import PAGE, RamName, Snapshot, SnapshotError  # noqa: E402

SERVICE = os.path.join(ROOT, "bin", "SERVICE.BIN")
SERVICE_VERSION = 15
TAIL_SIZE = 26
# The image's mark without its last character, the format's number, which is
# SERVICE.BIN's symbol IMAGE_FORMAT. The image's layout has no other copy
# here: its offsets, flags and record types are SERVICE.BIN's symbols, from
# src/service.inc (FORMATS.md, Image).
MARK = b"SNAPCAS"


class BuildError(Exception):
    """A snapshot or a file that cannot become an image."""


def crc16(data):
    """CRC-16/CCITT-FALSE: polynomial 1021h, initial value FFFFh, not
    reflected, no final XOR."""
    return binascii.crc_hqx(data, 0xFFFF)


# SERVICE.BIN's parts, in the order of its table (FORMATS.md, SERVICE.BIN).
PARTS = ("tail", "stubs", "page3", "code", "t0", "symbols", "relocs")


class Service:
    """SERVICE.BIN (FORMATS.md, SERVICE.BIN): its parts' bytes and the
    assembly's symbols, by name. Its part of page 3 is at an entry page, the
    high byte of the part's addresses: the one that it was assembled for, or
    another. The last part lists the bytes that move with that part, and the
    symbols in it are among them, so every address is the one that the entry
    page gives it."""

    def __init__(self, data, entry_page=None):
        self.source = bytes(data)
        data = bytearray(data)
        table = dict(zip(PARTS, struct.iter_unpack("<HH", bytes(data[2:2 + 4 * len(PARTS)]))))
        # The entry page that the part was assembled for, before any byte moves.
        self.assembled = self.read_symbols(data, *table["symbols"])["E_PAGE"]
        offset, length = table["relocs"]
        for (n,) in struct.iter_unpack("<H", bytes(data[offset:offset + length])):
            data[n] = (data[n] + (self.assembled if entry_page is None else entry_page) - self.assembled) & 0xFF
        self.parts = {name: bytes(data[offset:offset + length]) for name, (offset, length) in table.items()}
        self.symbols = self.read_symbols(data, *table["symbols"])
        self.entry_page = self.symbols["E_PAGE"]

    @staticmethod
    def read_symbols(data, offset, length):
        """The symbols' part as {name: value}: for each symbol, its value in 2
        bytes, its name's length in 1 and its name."""
        symbols, at = {}, offset
        while at < offset + length:
            value, size = struct.unpack_from("<HB", data, at)
            symbols[bytes(data[at + 3:at + 3 + size]).decode("ascii")] = value
            at += 3 + size
        return symbols

    def __getitem__(self, name):
        """A symbol's value."""
        if name not in self.symbols:
            raise BuildError(f"SERVICE.BIN has no symbol {name}: build it from this snapcas")
        return self.symbols[name]

    def field(self, name, t0_mode):
        """The address of a field of the service's data, by its name in
        src/tape.inc: in the code segment, or in T0 for the mode without a part
        in page 3, whose copy is the module t0m."""
        return self[("t0m." if t0_mode else "") + name]

    def at(self, entry_page):
        """This SERVICE.BIN with its part of page 3 at an entry page."""
        return Service(self.source, entry_page)

    @property
    def mark(self):
        """The image's mark: MARK and the format's number."""
        return MARK + bytes([self["IMAGE_FORMAT"]])

    @property
    def moved(self):
        """Whether the part of page 3 is at another entry page than its
        assembly's."""
        return self.entry_page != self.assembled


def read_service(path):
    """SERVICE.BIN as a Service, checked against its version byte, its number
    of parts and the tail's length."""
    with open(path, "rb") as f:
        data = f.read()
    if not data or data[0] != SERVICE_VERSION:
        raise BuildError(f"{path}: version {data[0] if data else 'none'}, "
                         f"expected {SERVICE_VERSION}: build it from this snapcas")
    if data[1] != len(PARTS):
        raise BuildError(f"{path}: {data[1]} parts, expected {len(PARTS)}: build it from this snapcas")
    service = Service(data)
    if len(service.parts["tail"]) != TAIL_SIZE:
        raise BuildError(f"{path}: a tail of {len(service.parts['tail'])} bytes, expected {TAIL_SIZE}: "
                         "build it from this snapcas")
    return service


# The entries of the BIOS's jump table for the tape (MSX Red Book, chapter 4),
# by the names that SERVICE.BIN's symbols give their routines: t_<name> is T0's
# stub, at the address that the ROM's entry must jump to, and t0m.<name> the
# routine of the mode without a part in page 3.
TAPE_ENTRIES = {"tapion": 0x00E1, "tapin": 0x00E4, "tapiof": 0x00E7, "tapoon": 0x00EA,
                "tapout": 0x00ED, "tapoof": 0x00F0, "stmotr": 0x00F3}
# STMOTR's code is outside the BIOS's tape code, at an address that differs
# between an MSX1 and an MSX2, so its entry in the ROM is not checked.
UNCHECKED = "stmotr"
OUTDO = 0x0018  # the entry of OUTDO, whose code follows the tape code
# Another entry page for the service's part of page 3 must leave the part
# below the BIOS's work area at F380h.
LAST_OTHER_PAGE = 0xF1
RG1SAV, RG7SAV = 0xF3E0, 0xF3E6  # the BIOS's copies of VDP registers 1 and 7


# How an image gets the tape service: whether it has it, the entry page of the
# service's part of page 3, or None without that part, and the page, 1 or 2,
# that TAPIN borrows without that part, or 0.
Mode = collections.namedtuple("Mode", "service entry_page borrowed")
# The mode without a part in page 3 (INTERNALS.md, Without a part in page 3).
Mode.t0 = property(lambda self: self.service and self.entry_page is None)

# Where the tail goes: its address, and the RAM page that holds it.
Tail = collections.namedtuple("Tail", "address ram_page")

# What build() returns: the image's header and tables, the records' data, what
# the image holds, for build.py's output, scan.txt's text and build.txt's text.
Built = collections.namedtuple("Built", "header data report scan facts")


def tail_address(snapshot):
    """The address of the tail: the 26 bytes below the stack pointer."""
    sp = snapshot.num("sp")
    address = (sp - TAIL_SIZE) & 0xFFFF
    if sp >= TAIL_SIZE and address >> 14 != (sp - 1) >> 14:
        # Across a page boundary: the 26 bytes below it, as free.
        address = (sp & 0xC000) - TAIL_SIZE
    end = address + TAIL_SIZE - 1
    if end > 0xFFFE or address >> 14 != end >> 14:
        raise BuildError(f"the {TAIL_SIZE} bytes below SP {sp:04X}h cross a page boundary or include FFFFh")
    return address


def port_writes(snapshot, v9938):
    """The PSG, PPI and VDP state as (port, value) writes (FORMATS.md, Port
    writes)."""
    num = snapshot.num
    w = []
    for r in range(16):
        value = num(f"psg{r}")
        if r == 7:
            value = (value & 0x3F) | 0x80  # port A input, port B output
        w += [(0xA0, r), (0xA1, value)]
    w.append((0xA0, num("psgsel")))
    w.append((0xAA, num("ppic")))
    if v9938:
        w += [(0x99, 0), (0x99, 0x80 | 16)]
        for c in range(16):
            pal = num(f"pal{c}")
            w += [(0x9A, pal >> 8), (0x9A, pal & 0xFF)]
        w += [(0x99, 32), (0x99, 0x80 | 17)]
        w += [(0x9B, num(f"vdp{r}")) for r in range(32, 46)]
    for r in range(24 if v9938 else 8):
        w += [(0x99, num(f"vdp{r}")), (0x99, 0x80 | r)]
    pointer = num("vramptr")
    if num("vramwrite"):
        w += [(0x99, pointer & 0xFF), (0x99, 0x40 | ((pointer >> 8) & 0x3F))]
    else:
        bits = 17 if v9938 else 14
        before = (pointer - 1) % (1 << bits)
        if v9938 and pointer & 0x3FFF == 0:
            w += [(0x99, before >> 14), (0x99, 0x80 | 14)]
        w += [(0x99, before & 0xFF), (0x99, (before >> 8) & 0x3F)]
    return w


def find_entry_page(p3, service, wanted=None, tail=None):
    """The entry page of the service's part of page 3 in p3, the game's RAM
    page of page 3. The part starts at E1h of the entry page: the game file's,
    wanted, or the one that it was assembled for when FCC9h to FD88h are zero,
    or else the highest below the BIOS's work area whose bytes there are zero,
    or None when no part has room (INTERNALS.md, Build). The bytes of the tail,
    at the address tail, are zero at the snapshot too, so a part that holds one
    of them has no room."""
    length = len(service.parts["page3"])
    default = service["P3_FREE"], service["P3_FREE_END"]

    def free(first, last):
        return not any(p3.data[first & 0x3FFF:(last & 0x3FFF) + 1])

    def span(entry_page):
        first = entry_page * 256 + (service["E_ENTRY"] & 0xFF)
        return first, first + length - 1

    def clear(first, last):
        return tail is None or tail > last or tail + TAIL_SIZE <= first
    if wanted is not None:
        if span(wanted)[1] > 0xFFFE:
            raise BuildError(f"a part of the tape service at {span(wanted)[0]:04X}h would pass FFFEh")
        if not free(*span(wanted)):
            raise BuildError(f"{span(wanted)[0]:04X}h to {span(wanted)[1]:04X}h are not zero at the snapshot")
        return wanted
    if free(*default) and clear(*default):
        return service.assembled
    for entry_page in range(LAST_OTHER_PAGE, 0xBF, -1):
        if free(*span(entry_page)) and clear(*span(entry_page)):
            return entry_page
    return None


def borrowed_page(snapshot):
    """For the mode without a part in page 3: the page that TAPIN borrows. It
    is page 2 or page 1, the first that is in a mapper at the snapshot, or else
    page 2 (INTERNALS.md, Without a part in page 3)."""

    def in_mapper(page):
        ram_page = snapshot.selected_ram(page)
        return ram_page is not None and ram_page.name.seg is not None
    return 2 if in_mapper(2) or not in_mapper(1) else 1


def service_mode(snapshot, p3, service, game, tail=None):
    """How the image gets the tape service, a Mode: without it, with its part
    of page 3 at an entry page, or in the mode without that part, by the game
    file's service t0, or when p3, the game's RAM page of page 3, has no room
    for the part beside the tail, at the address tail. A game file with rom
    keep cannot take that mode (FILES.md, Game file)."""
    if snapshot.state["service"] != "1":
        return Mode(False, None, 0)
    if p3 is None:
        raise BuildError("page 3 is not a RAM page that the snapshot keeps")
    if game.service != "t0":
        entry_page = find_entry_page(p3, service, game.entry_page, tail)
        if entry_page is not None:
            return Mode(True, entry_page, 0)
    if game.rom_keep:
        raise BuildError(f"{game.folder}: page 3 has no room for the tape service's part, and rom keep "
                         "needs it, because the mode without a part in page 3 has no entries there")
    check_t0_page0(snapshot.ram_pages, game)
    return Mode(True, None, borrowed_page(snapshot))


def check_t0_page0(ram_pages, game):
    """Stops when a RAM page kept for page 0 is in DOS's mapper, where the
    mode without a part in page 3 keeps T0 in mapper register FCh for good
    (INTERNALS.md, Without a part in page 3). The build knows DOS's mapper
    only when the capture ran on the user's machine itself, without a capture
    variant, and the snapshot's mapper pages are all in one slot, which is then
    DOS's. In every other case the restorer checks it, because it knows DOS's
    mapper."""
    mapper = {p.name.slot_id for p in ram_pages if p.name.seg is not None}
    if game.capture or len(mapper) != 1:
        return
    if any(p.name.page == 0 and p.name.slot_id in mapper for p in ram_pages):
        raise BuildError(f"{game.folder}: the tape service without a part in page 3 keeps T0 in page 0 of "
                         "DOS's mapper, where the snapshot has a RAM page of the game. The game needs a "
                         "capture variant, whose RAM is outside DOS's mapper, or service at and an "
                         "address in page 3 that the game leaves alone")


def check_unread(state, blocks, names, service_no):
    """Stops when a non-standard block follows the snapshot: the game reads it
    with its own loader, which the tape service cannot serve, unless the game
    file has service no (INTERNALS.md, Tape files). state is the snapshot's
    state."""
    if service_no or not any(not b.standard and b.data for side in blocks for b in side):
        return
    if "tapetime" not in state:
        raise BuildError("the snapshot has no tapetime: capture the game again")
    seconds, side = float(state["tapetime"]), int(state["tapeside"])
    late = [(names[0], b) for b in tape.unread(blocks[0], seconds if side == 1 else float("inf"))]
    late += [(names[1], b) for b in tape.unread(blocks[1], seconds if side == 2 else -1)]
    if late:
        name, b = late[0]
        raise BuildError(f"{name}: the non-standard block at {b.offset:X}h, {b.start:.1f} seconds into "
                         "the tape, comes after the snapshot, and the tape service cannot serve it. "
                         "The game file needs service no if the game never reads it")


def patch_pages(patch_lines, snapshot):
    """Applies the patch lines of pages 0 to 3 to the RAM pages that the
    snapshot selects there, and returns their ranges for the check."""
    ranges = []
    for patch in patch_lines:
        if patch.page is not None:
            found = snapshot.selected_ram(patch.page)
            if found is None:
                raise BuildError(f"{patch.where}: page {patch.page} is not a RAM page that the snapshot keeps")
            patch.apply(found.data)
            ranges.append(patched_range(RamName(*snapshot.selected_slot(patch.page), patch.page, None),
                                        patch.offset, len(patch.old)))
    return ranges


def patched_range(name, offset, length):
    """A patched range of a ram/ file as the check reads it: its page as
    build.txt names it, the first and the last offset."""
    return f"{name.cpu_page} {offset} {offset + length - 1}"


def scan_ram(snapshot, context):
    """Patches the scan's findings in the snapshot's RAM pages (INTERNALS.md,
    Scan), and returns [(RAM page, findings)]."""
    found = []
    for ram_page in snapshot.ram_pages:
        findings = patches.find(ram_page.data, context)
        patches.patch(ram_page.data, findings)
        found.append((ram_page, findings))
    return found


def scan_unread(side1, side2, blocks, position, context):
    """The scan's findings in the unread blocks of the tape service's tapes
    side1 and side2: side 1 from the tape position, and side 2. Returns
    [(side, findings)], with each finding at its offset in the tape file of
    blocks, where a patch line has its place (INTERNALS.md, Tape files): a CAS
    file's offsets are the tape service's, and a TSX file's are found through
    the blocks."""
    found = [[f for f in patches.find(side1, context) if f.offset >= position], patches.find(side2, context)]
    for side, side_blocks in zip(found, blocks):
        for f in side:
            f.offset = tape.file_offset(side_blocks, f.offset)
    return [(place, [f for f in side if f.offset is not None]) for place, side in zip(("side1", "side2"), found)]


def scanned_ranges(snapshot, found):
    """The ranges that the scan patched, from scan_ram's findings, for the
    check: under each ram/ file of the page's segment, in the order of the
    files' names."""
    ranges = {}
    for ram_page, findings in found:
        for name in snapshot.names_of(ram_page):
            ranges[name.file] = [patched_range(name, f.offset, len(f.old)) for f in findings if f.new is not None]
    return [r for file in sorted(ranges) for r in ranges[file]]


def ram_place(snapshot, ram_page):
    """A RAM page's place in scan.txt: page<n> when the snapshot selects it in
    its page, as a patch line names it, or else ram and its file's name."""
    if ram_page is snapshot.selected_ram(ram_page.name.page):
        return f"page{ram_page.name.page}"
    return "ram " + ram_page.name.stem


class Image:
    """A game's image in the making (FORMATS.md, Image). It holds what the
    layout needs, each under one name:

    snapshot  the Snapshot, whose RAM pages the build changes
    game      the gamefile.Game
    p3        the RAM page that the snapshot selects in page 3, or None
    mode      the Mode
    service   the Service, with its part of page 3 at the mode's entry page
    tail      the Tail, once place_tail has run
    """

    def __init__(self, snapshot, service, game):
        self.snapshot = snapshot
        self.game = game
        self.p3 = snapshot.selected_ram(3)
        self.mode = service_mode(snapshot, self.p3, service, game, tail_address(snapshot))
        self.service = service if self.mode.entry_page is None else service.at(self.mode.entry_page)
        self.tail = None

    def field(self, name):
        """The address of a field of the service's data, in the image's
        mode."""
        return self.service.field(name, self.mode.t0)

    def scan(self, side1, side2, blocks):
        """Patches the scan's findings in the RAM pages, and returns scan.txt's
        text, the patched ranges for the check, and (RAM page, offset) for each
        byte that the restorer fills in (FORMATS.md, Image). With the tape
        service, the text also lists the findings in the unread blocks of the
        service's tapes side1 and side2, at their offsets in the tape files of
        blocks. Without it, the scan looks only for fixed slot values, and
        without a part in page 3, it patches only those."""
        slots, mode, service = self.snapshot.slots, self.mode, self.service
        unread, note = [], ""
        if not mode.service:
            found = scan_ram(self.snapshot, patches.Context(slots=slots, tape=False))
            note = "# Without the tape service, the scan looks only for fixed slot values.\n"
        else:
            found = scan_ram(self.snapshot, patches.Context(mode.entry_page, slots))
            # A finding in an unread block is only listed, and the restorer
            # fills in no byte of the tape, so the stub's patch has no form
            # there.
            unread = scan_unread(side1, side2, blocks, self.snapshot.num("tapepos"),
                                 patches.Context(mode.entry_page, slots, ram=False))
            if mode.t0:
                note = ("# The tape service has no part in page 3, so the code that reaches the tape is only\n"
                        "# listed. The restorer writes the value of a stub's selection of the ROM in page 0.\n")
            elif service.moved:
                note = (f"# The tape service's part of page 3 is at {service['E_ENTRY']:04X}h: the game uses "
                        f"{service['P3_FREE']:04X}h to {service['P3_FREE_END']:04X}h.\n")
        text = note + patches.report([(ram_place(self.snapshot, ram_page), findings) for ram_page, findings in found],
                                     unread)
        places = [(ram_page, f.offset + f.place) for ram_page, findings in found for f in findings
                  if f.place is not None]
        return text, scanned_ranges(self.snapshot, found), places

    def place_tail(self):
        """Writes the tail at its address, with the fields that the build
        fills in (FORMATS.md, Tail), and keeps the address and the RAM page
        that holds it as tail."""
        snapshot, service = self.snapshot, self.service
        sp, address = snapshot.num("sp"), tail_address(snapshot)
        target = snapshot.selected_ram(address >> 14)
        if target is None:
            raise BuildError(f"the {TAIL_SIZE} bytes below SP {sp:04X}h are not in a RAM page that the snapshot "
                             "keeps. The usual cause is a load that failed on this machine: "
                             f"{snapshot.path('log.txt')} shows where it stopped and the screen then")
        code = bytearray(service.parts["tail"])
        struct.pack_into("<H", code, service["TAIL_STACK"], address + service["TAIL_AF"])
        struct.pack_into("<H", code, service["TAIL_SP"], sp)
        code[service["TAIL_EI"]] = 0xFB if snapshot.num("iff") & 1 else 0x00
        struct.pack_into("<H", code, service["TAIL_PC"], snapshot.num("pc"))
        struct.pack_into("<H", code, service["TAIL_AF"], snapshot.num("af"))
        offset = address & 0x3FFF
        target.data[offset:offset + TAIL_SIZE] = code
        self.tail = Tail(address, target)

    def tape_rom(self):
        """T0's start: page 0 of the main ROM, whose jump table entries must
        go to the BIOS's tape routines that the service replaces. T0's stubs
        have those routines' addresses, and OUTDO's code follows the tape
        code."""
        service = self.service
        t0 = bytearray(self.snapshot.read("rom.bin")[:PAGE])
        targets = {entry: service[f"t_{name}"] for name, entry in TAPE_ENTRIES.items() if name != UNCHECKED}
        targets[OUTDO] = service["T0_END"]
        for entry, target in targets.items():
            if t0[entry] != 0xC3 or struct.unpack_from("<H", t0, entry + 1)[0] != target:
                raise BuildError(f"{self.snapshot.folder}/rom.bin: the jump at {entry:04X}h does not go to "
                                 f"{target:04X}h")
        return t0

    def build_t0(self):
        """T0: the ROM's page 0 with the service's stubs over the BIOS's tape
        code, or, in the mode without a part in page 3, with the service's
        data and routines there (INTERNALS.md, Tape service). The jump table
        goes to them where the ROM's does not: at STMOTR's entry, and in that
        mode at every entry."""
        service, t0_mode = self.service, self.mode.t0
        t0 = self.tape_rom()
        code = service.parts["t0" if t0_mode else "stubs"]
        first = service["T0_CODE"]
        if first + len(code) != service["T0_END"]:
            raise BuildError(f"SERVICE.BIN's code for T0 is {len(code)} bytes, which is not {first:04X}h to "
                             f"{service['T0_END'] - 1:04X}h: build it from this snapcas")
        t0[first:first + len(code)] = code
        for name, entry in TAPE_ENTRIES.items():
            if t0_mode or name == UNCHECKED:
                target = service[("t0m." if t0_mode else "t_") + name]
                t0[entry:entry + 3] = bytes([0xC3]) + struct.pack("<H", target)
        return t0

    def write_borrowed(self, t0):
        """T0's data for the page that TAPIN borrows: the slot register's mask
        for the page, its mapper register's port, its first address's high
        byte and the game's segment there. The restorer fills in DOS's
        mapper's slot."""
        page = self.mode.borrowed
        found = self.snapshot.selected_ram(page)
        # Without a mapper at the snapshot, as in a capture variant without the
        # Carnivore2, the segment written back is 0, which only DOS's mapper sees.
        if found is not None and found.name.seg is not None:
            seg = found.name.seg
        else:
            seg = self.snapshot.num("f" + "cdef"[page])
        for name, value in (("D_PAGE_MASK", ~(3 << 2 * page) & 0xFF), ("D_PAGE_PORT", 0xFC + page),
                            ("D_PAGE_HIGH", page * 0x40), ("D_PAGE_SEG", seg)):
            t0[self.field(name)] = value

    def write_positions(self, data, start, pos, real, side1, total):
        """The tape's position, side 1's end, side 2's end and side 1's start,
        3 bytes each, in the service's data in data, and outside the mode
        without a part in page 3 also side 1's end before its padding, real.
        The tape starts at offset start of the tape segments, and side1 and
        total are offsets in the tape."""
        values = {"D_POS": pos, "D_S1END": start + side1, "D_TOTAL": start + total, "D_START": start}
        if not self.mode.t0:
            values["D_S1REAL"] = start + real
        for name, value in values.items():
            at = self.field(name)
            data[at:at + 3] = value.to_bytes(3, "little")

    def write_flash(self, data, t0, side, two_sides):
        """The flash's data in the service's data in data, with the side that
        the tape is on and whether it has two. The flash restores VDP registers
        7 and 1 from RG7SAV and RG1SAV when the game keeps them, and otherwise
        from the snapshot's values. It counts 0.1 second of frames, at the rate
        of bit 7 of the ROM's byte 002Bh, in t0: 50 Hz when set."""
        pal = t0[0x2B] & 0x80
        vdp7, vdp1 = self.snapshot.num("vdp7"), self.snapshot.num("vdp1")
        border = RG7SAV if self.p3.data[RG7SAV & 0x3FFF] == vdp7 else self.field("D_VDP7")
        screen = RG1SAV if self.p3.data[RG1SAV & 0x3FFF] == vdp1 else self.field("D_VDP1")
        for name, value, size in (("D_BORDER", border, 2), ("D_FRAMES", 5 if pal else 6, 1), ("D_VDP7", vdp7, 1),
                                  ("D_SIDE", side, 1), ("D_SCREEN", screen, 2), ("D_VDP1", vdp1, 1),
                                  ("D_TWO", 1 if two_sides else 0, 1)):
            at = self.field(name)
            data[at:at + size] = value.to_bytes(size, "little")

    def write_page3_part(self):
        """The service's part of page 3 in the game's page 3, at its entry
        page, with E_FC and E_STOP filled in."""
        service, tail = self.service, self.tail.address
        block = bytearray(service.parts["page3"])
        start = service["E_ENTRY"]
        first, last = start, start + len(block) - 1
        if not service.moved:
            first, last = service["P3_FREE"], service["P3_FREE_END"]
        if tail <= last and tail + TAIL_SIZE > first:
            raise BuildError(f"the tail at {tail:04X}h overlaps {first:04X}h to {last:04X}h")
        block[service["E_FC"] - start] = self.snapshot.num("fc")
        # The manual tape starts stopped when the motor, PPI port C bit 4 (0 = on),
        # is off at the snapshot.
        block[service["E_STOP"] - start] = (self.snapshot.num("ppic") >> 4) & 1
        self.p3.data[start & 0x3FFF:(start & 0x3FFF) + len(block)] = block

    def service_segments(self, side1, side2):
        """T0, then the code segment and the tape, as 16 KB blocks
        (INTERNALS.md, Tape service), for the service's tapes side1 and side2.
        In the mode without a part in page 3, T0 holds the service's data and
        no code segment comes before the tape."""
        service, t0_mode = self.service, self.mode.t0
        t0 = self.build_t0()
        stream = bytearray() if t0_mode else bytearray(service.parts["code"])
        start = len(stream)
        sides, real, side1_end = tape.both_sides(side1, side2)
        stream += sides
        # The service's data is at the start of T0's code in that mode, and
        # otherwise at the start of the code segment.
        data = t0 if t0_mode else stream
        pos = start + self.snapshot.num("tapepos")
        self.write_positions(data, start, pos, real, side1_end, len(sides))
        side = 1 if side2 and pos >= start + side1_end else 0
        self.write_flash(data, t0, side, bool(side2))
        if t0_mode:
            self.write_borrowed(t0)
        stream += bytes(-len(stream) % PAGE)
        segs_max = service["T_SEGS_MAX" if t0_mode else "SEGS_MAX"]
        if len(stream) // PAGE > segs_max:
            raise BuildError(f"the tape needs {len(stream) // PAGE} segments, more than {segs_max}")
        return [bytes(t0)] + [bytes(stream[n:n + PAGE]) for n in range(0, len(stream), PAGE)]

    def records_and_data(self, segments):
        """The image's records and their data: the RAM pages, in the
        snapshot's order, so that a RAM page's place there is its record's
        number, then VRAM in 16 KB blocks, and the service's segments. Also
        whether VRAM is a V9938's."""
        service = self.service
        records, data = [], []
        for ram_page in self.snapshot.ram_pages:
            name = ram_page.name
            kind = service["REC_MAPPER"] if name.seg is not None else service["REC_RAM"]
            records.append(bytes([kind, name.slot_id, name.page, name.seg or 0]))
            data.append(bytes(ram_page.data))
        vram = self.snapshot.read("vram.bin")
        for block in range(len(vram) // PAGE):
            chunk = vram[block * PAGE:(block + 1) * PAGE]
            if any(chunk):
                records.append(bytes([service["REC_VRAM"], block, 0, 0]))
                data.append(chunk)
            else:
                records.append(bytes([service["REC_ZEROS"], block, 0, 0]))
        for segment in segments:
            records.append(bytes([service["REC_SERVICE"], 0, 0, 0]))
            data.append(segment)
        return records, data, len(vram) > PAGE

    def header(self, records, writes, places):
        """The image's header and tables (FORMATS.md, Image), by the offsets
        that SERVICE.BIN's symbols name. places are (RAM page, offset in the
        page), from scan. A RAM page's record has the page's place in the
        snapshot's RAM pages as its number. A segment that the game selects in
        two pages has one record, so the header names the records that hold the
        tail and the game's page 3."""
        snapshot, service, mode = self.snapshot, self.service, self.mode
        num = snapshot.num
        rom = crc16(snapshot.read("rom.bin"))
        subrom = crc16(snapshot.read("subrom.bin")) if os.path.exists(snapshot.path("subrom.bin")) else 0

        # A record's number and each table's length are one byte, and three
        # tables of 255 entries fit the header.
        if max(len(records), len(writes), len(places)) > 255:
            raise BuildError(f"{snapshot.folder}: too many records, port writes or places for the image")
        number = {id(ram_page): n for n, ram_page in enumerate(snapshot.ram_pages)}
        flags = (service["FLAG_ROM_KEEP"] if self.game.rom_keep else 0) | (service["FLAG_T0"] if mode.t0 else 0)
        header = bytearray(service["H_SIZE"])
        header[0:len(service.mark)] = service.mark
        struct.pack_into("<H", header, service["H_ROM"], rom)
        struct.pack_into("<H", header, service["H_SUBROM"], subrom)
        for name, value in (("H_RECS", len(records)), ("H_WRITES", len(writes)), ("H_PLACES", len(places)),
                            ("H_FLAGS", flags), ("H_P3", mode.entry_page or 0), ("H_I", num("i")),
                            ("H_IM", num("im")), ("H_IFF", num("iff") & 1), ("H_A8", num("a8")),
                            ("H_VDP1", num("vdp1")), ("H_BORROW", mode.borrowed),
                            ("H_TAILREC", number[id(self.tail.ram_page)]),
                            ("H_P3REC", number[id(self.p3)] if mode.service else 0)):
            header[service[name]] = value
        struct.pack_into("<12H", header, service["H_REGS"], *[num(r) for r in
                         "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()])
        for ps in range(4):
            header[service["H_SUB"] + ps] = num(f"sub{ps}")
            if snapshot.state[f"sub{ps}"] == "-":
                header[service["H_NOEXP"]] |= 1 << ps
        for n, reg in enumerate("fc fd fe ff".split()):
            header[service["H_MAP"] + n] = num(reg)
        struct.pack_into("<H", header, service["H_TAIL"], self.tail.address)
        tables = (b"".join(records) + b"".join(bytes(w) for w in writes)
                  + b"".join(struct.pack("<BH", number[id(ram_page)], offset) for ram_page, offset in places))
        assert all(len(r) == service["REC_SIZE"] for r in records)
        assert (service["WRITE_SIZE"], service["PLACE_SIZE"]) == (2, 3)
        assert service["H_TABLE"] + len(tables) <= len(header)
        header[service["H_TABLE"]:service["H_TABLE"] + len(tables)] = tables
        return bytes(header)

    def facts(self, ranges):
        """build.txt's text: what the check takes from the build (INTERNALS.md,
        Check). tail is the tail's address, then the offsets in the tail of its
        last byte, of the port of the worker's page's mapper register, and of
        its last instruction, the jump to the game. free is the first and the
        last byte of the area that the service's part of page 3 takes by
        default. patched is each of ranges. The part, when the image has one,
        is {first last E_CODE segment}: its first byte, its last before the
        scratch bytes from e_sp on, which the service sets before it reads
        them, the address of E_CODE, which holds the code segment, and the
        mapper segment at the snapshot of the game's page 3, or -1 outside a
        mapper. When the part is not at the entry page of its assembly, moved
        is its first and last byte. cpos is the addresses of the tape position
        and of the tape's end in the code segment, selected in page 1. ended
        is the addresses in the code segment, selected in page 0, of the two
        jumps that the automatic tape takes at its last side's end: the first
        with Z for a tape of one side, the second without carry for side 2
        (src/tape.inc, wrap)."""
        service, mode = self.service, self.mode
        lines = ["# What the check takes from the build (docs/INTERNALS.md, Check).",
                 f"service {1 if mode.service else 0}",
                 f"tail {self.tail.address} {TAIL_SIZE - 1} {service['TAIL_PORT']} {service['TAIL_JP']}",
                 f"free {service['P3_FREE']} {service['P3_FREE_END']}"]
        lines += [f"patched {r}" for r in ranges]
        if mode.entry_page is not None:
            first = service["E_ENTRY"]
            segment = self.p3.name.seg if self.p3.name.seg is not None else -1
            lines.append(f"part {first} {service['e_sp'] - 1} {service['E_CODE']} {segment}")
            lines.append(f"cpos {0x4000 + service['D_POS']} {0x4000 + service['D_TOTAL']}")
            lines.append(f"ended {service['wrap.one']} {service['wrap.two']}")
            if service.moved:
                lines.append(f"moved {first} {first + len(service.parts['page3']) - 1}")
        return "\n".join(lines) + "\n"


def build(snapshot, service_path, game, side1=b"", side2=b"", patch_lines=(), file_blocks=None):
    """Builds the image of game, a gamefile.Game, from snapshot, a Snapshot,
    and returns a Built. side1 and side2 are the bytes of the tape files that
    the capture played (tape.played), and patch_lines the game file's patches
    and the capture's. file_blocks are the blocks of side 1's downloaded file
    that the capture played, for a game file with a start line
    (tape.played_blocks)."""
    # state.txt comes first: without it, the folder holds no snapshot.
    state = snapshot.state
    names = (game.tape, game.side2 or "")
    # The tape service's tapes of the played files (INTERNALS.md, Tape files).
    blocks = (tape.read(names[0], side1) if side1 else [], tape.read(names[1], side2) if side2 else [])
    check_unread(state, blocks, names, game.service == "no")
    side1, side2 = tape.service(blocks[0]), tape.service(blocks[1])
    service = read_service(service_path)
    ranges = patch_pages(patch_lines, snapshot)

    image = Image(snapshot, service, game)
    # A patch line's place is in the downloaded file, so scan.txt gives side
    # 1's findings there, and not in the copy from the start line's file on.
    scanned, scan_ranges, places = image.scan(side1, side2, (blocks[0] if file_blocks is None else file_blocks,
                                                             blocks[1]))
    image.place_tail()
    segments = []
    if image.mode.service:
        segments = image.service_segments(side1, side2)
        if not image.mode.t0:
            image.write_page3_part()

    records, data, v9938 = image.records_and_data(segments)
    writes = port_writes(snapshot, v9938)
    header = image.header(records, writes, places)

    mapper = sum(1 for r in records if r[0] in (image.service["REC_MAPPER"], image.service["REC_SERVICE"]))
    report = (f"{len(records)} records, {len(writes)} port writes, "
              f"up to {mapper + 1} free mapper segments")
    return Built(header, data, report, scanned, image.facts(ranges + scan_ranges))


def write_image(game_arg, machine, tapes_dir, service_path=SERVICE, variant=None):
    """Builds the image of a game on a machine, as build.py's arguments name
    them, and writes it with scan.txt and build.txt. variant is the capture
    variant that the capture ran on, in place of the game file's. Returns the
    image's name, its path and what it holds. Raises msx.Failure for an error
    in the input files."""
    folder = gamefile.game_folder(game_arg)
    try:
        game = gamefile.read_game(folder, machine)
        game.capture = variant or game.capture
        out = gamefile.out_folder(machine, folder)
        snapshot = Snapshot(os.path.join(out, "snap"))
        captured = snapshot.capture_patches()
        side1, side2 = tape.played(game, tapes_dir, captured)
        built = build(snapshot, service_path, game, side1, side2, list(game.patches) + captured,
                      tape.played_blocks(game, tapes_dir))
    except (OSError, gamefile.GameFileError, BuildError, SnapshotError, tape.TapeError) as e:
        raise msx.Failure(1, f"build.py: {e}")
    image = gamefile.image_path(machine, folder, game.name)
    with open(image, "wb") as f:
        f.write(built.header)
        for chunk in built.data:
            f.write(chunk)
    with open(os.path.join(out, "scan.txt"), "w") as f:
        f.write(built.scan)
    with open(os.path.join(out, "build.txt"), "w") as f:
        f.write(built.facts)
    return game.name, image, built.report


def main():
    parser = msx.Parser(description="Write a game's image from its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--tapes", required=True, help="the folder that holds the tape files, CAS or TSX")
    parser.add_argument("--service", default=SERVICE, help="the SERVICE.BIN to use")
    parser.add_argument("--capture", help="the capture variant that capture.py's --capture gave, in place of "
                        "the game file's capture line")
    args = parser.parse_args()
    try:
        name, image, report = write_image(args.game, args.machine, args.tapes, args.service, args.capture)
    except msx.Failure as e:
        return e.show()
    print(f"{name}: {image}: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
