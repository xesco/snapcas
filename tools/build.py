#!/usr/bin/env python3
"""Write a game's image from its snapshot (docs/DESIGN.md, Build).

Usage: build.py <game> <machine> --tapes <dir> [--service <file>]

<game> and <machine> are as for capture.py. The image, <GAME>.SNP, scan.txt and
build.txt go to the game's work folder (gamefile.out_folder). --service names
the SERVICE.BIN to use, by default bin/SERVICE.BIN.

Exit status: 0 on success, 1 for an error in the input files.
"""
import argparse
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import tape  # noqa: E402
import gamefile  # noqa: E402
import patches  # noqa: E402

SERVICE_VERSION = 12
PAGE = 16384
HEADER_SIZE = 4096
MAGIC = b"SNAPCAS4"
TAIL_SIZE = 26
FLAG_ROM_KEEP = 1  # header byte 14, bit 0: T0 does not replace the ROM
FLAG_T0 = 2  # bit 1: the tape service without a part in page 3
DEFAULT_PAGE = patches.tape.ENTRY_PAGE  # the page of the service's page 3 part, as assembled

# Record types (DESIGN.md, Image).
RAM_IN_MAPPER, RAM, SERVICE_SEGMENT, VRAM, VRAM_ZEROS = 1, 2, 3, 4, 5


class BuildError(Exception):
    """A snapshot or a file that cannot become an image."""


def crc16(data):
    """CRC-16/CCITT-FALSE: polynomial 1021h, initial value FFFFh, not
    reflected, no final XOR."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def read_state(snap):
    state = {}
    with open(os.path.join(snap, "state.txt")) as f:
        for line in f.read().splitlines():
            name, value = line.split(" ", 1)
            state[name] = value
    return state


def num(state, name):
    """A state.txt value as a number, 0 for "-"."""
    value = state[name]
    return 0 if value == "-" else int(value, 16)


def read_service(path, page=DEFAULT_PAGE):
    """SERVICE.BIN's parts: [bytes], checked against its version byte, with
    the page 3 part moved to page: its last part lists the bytes that add the
    difference (DESIGN.md, SERVICE.BIN)."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    if not data or data[0] != SERVICE_VERSION:
        raise BuildError(f"{path}: version {data[0] if data else 'none'}, "
                         f"expected {SERVICE_VERSION}: build it from this snapcas")
    offset, length = struct.unpack_from("<HH", data, 2 + 4 * (data[1] - 1))
    for (n,) in struct.iter_unpack("<H", bytes(data[offset:offset + length])):
        data[n] = (data[n] + page - DEFAULT_PAGE) & 0xFF
    parts = []
    for n in range(data[1]):
        offset, length = struct.unpack_from("<HH", data, 2 + 4 * n)
        parts.append(data[offset:offset + length])
    return parts


class Page:
    """A RAM page of the snapshot: ram/<ps>-<ss>-<page>-<seg>.bin."""

    def __init__(self, snap, name):
        ps, ss, page, seg = name[:-4].split("-")
        self.snap = snap
        self.ps, self.page = int(ps), int(page)
        self.ss = None if ss == "x" else int(ss)
        self.seg = None if seg == "x" else int(seg)
        with open(os.path.join(snap, "ram", name), "rb") as f:
            self.data = bytearray(f.read())
        if len(self.data) != PAGE:
            raise BuildError(f"{snap}/ram/{name}: not 16 KB")

    def key(self):
        return (self.ps, self.ss, self.page)

    def slot_id(self):
        if self.ss is None:
            return self.ps
        return 0x80 | (self.ss << 2) | self.ps


def selected(state, page):
    """The (primary slot, subslot) that the snapshot selects in a page."""
    ps = (num(state, "a8") >> (2 * page)) & 3
    sub = state[f"sub{ps}"]
    ss = None if sub == "-" else (int(sub, 16) >> (2 * page)) & 3
    return ps, ss


def selected_page(state, pages, page):
    """The kept RAM page that the snapshot selects in a page, or None. A mapper's
    page is found by its segment, which a game can select in two pages."""
    slot = selected(state, page)
    seg = num(state, "f" + "cdef"[page])
    found = [p for p in pages if (p.ps, p.ss) == slot and p.seg == seg]
    found += [p for p in pages if p.key() == (*slot, page) and p.seg is None]
    return found[0] if found else None


def place_tail(state, pages, tail):
    """Writes the tail into the 26 bytes below the stack pointer, and returns
    its address."""
    sp = num(state, "sp")
    address = (sp - TAIL_SIZE) & 0xFFFF
    if sp >= TAIL_SIZE and address >> 14 != (sp - 1) >> 14:
        # Across a page boundary: the 26 bytes below it, as free.
        address = (sp & 0xC000) - TAIL_SIZE
    end = address + TAIL_SIZE - 1
    if end > 0xFFFE or address >> 14 != end >> 14:
        raise BuildError(f"the {TAIL_SIZE} bytes below SP {sp:04X} cross a page boundary or include FFFFh")
    target = selected_page(state, pages, address >> 14)
    if target is None:
        raise BuildError(f"the {TAIL_SIZE} bytes below SP {sp:04X} are not in a RAM page that the snapshot keeps")
    code = bytearray(tail)
    struct.pack_into("<H", code, 14, address + 24)
    struct.pack_into("<H", code, 18, sp)
    code[20] = 0xFB if num(state, "iff") & 1 else 0x00
    struct.pack_into("<H", code, 22, num(state, "pc"))
    struct.pack_into("<H", code, 24, num(state, "af"))
    offset = address & 0x3FFF
    target.data[offset:offset + TAIL_SIZE] = code
    return address


def port_writes(state, v9938):
    """The PSG, PPI and VDP state as (port, value) writes (DESIGN.md, Port
    writes)."""
    w = []
    for r in range(16):
        value = num(state, f"psg{r}")
        if r == 7:
            value = (value & 0x3F) | 0x80  # port A input, port B output
        w += [(0xA0, r), (0xA1, value)]
    w.append((0xA0, num(state, "psgsel")))
    w.append((0xAA, num(state, "ppic")))
    if v9938:
        w += [(0x99, 0), (0x99, 0x80 | 16)]
        for c in range(16):
            pal = num(state, f"pal{c}")
            w += [(0x9A, pal >> 8), (0x9A, pal & 0xFF)]
        w += [(0x99, 32), (0x99, 0x80 | 17)]
        w += [(0x9B, num(state, f"vdp{r}")) for r in range(32, 46)]
    for r in range(24 if v9938 else 8):
        w += [(0x99, num(state, f"vdp{r}")), (0x99, 0x80 | r)]
    pointer = num(state, "vramptr")
    if num(state, "vramwrite"):
        w += [(0x99, pointer & 0xFF), (0x99, 0x40 | ((pointer >> 8) & 0x3F))]
    else:
        bits = 17 if v9938 else 14
        before = (pointer - 1) % (1 << bits)
        if v9938 and pointer & 0x3FFF == 0:
            w += [(0x99, before >> 14), (0x99, 0x80 | 14)]
        w += [(0x99, before & 0xFF), (0x99, (before >> 8) & 0x3F)]
    return w


# The BIOS's jump table entries for the tape and the addresses that they must
# jump to (DESIGN.md, Tape service).
TAPE_ENTRIES = {0x00E1: 0x1A63, 0x00E4: 0x1ABC, 0x00E7: 0x19E9, 0x00EA: 0x19F1,
                0x00ED: 0x1A19, 0x00F0: 0x19DD, 0x0018: 0x1B45}
TAPE_CODE = 0x19DD
STMOTR = 0x00F3
# The area of page 3 that the service's page 3 part takes by default, from
# FCE1h, and that must be zero at the snapshot.
P3_FREE, P3_END = 0xFCC9, 0xFD88
# Another page for that part must leave it below the BIOS's work area at F380h.
LAST_OTHER_PAGE = 0xF1
RG1SAV, RG7SAV = 0xF3E0, 0xF3E6  # the BIOS's copies of VDP registers 1 and 7


def service_page(state, pages, length, wanted=None):
    """The page of the service's page 3 part, which starts at E1h of it: the
    game file's, FCh when FCC9h to FD88h are zero, or else the highest page
    below the BIOS's work area whose bytes there are zero, or None when no part
    has room (DESIGN.md, Build)."""
    p3 = selected_page(state, pages, 3)
    if p3 is None:
        raise BuildError("page 3 is not a RAM page that the snapshot keeps")

    def free(first, last):
        return not any(p3.data[first & 0x3FFF:(last & 0x3FFF) + 1])

    def span(page):
        return page * 256 + 0xE1, page * 256 + 0xE1 + length - 1
    if wanted is not None:
        if not free(*span(wanted)):
            raise BuildError(f"{span(wanted)[0]:04X}h to {span(wanted)[1]:04X}h are not zero at the snapshot")
        return wanted
    if free(P3_FREE, P3_END):
        return DEFAULT_PAGE
    for page in range(LAST_OTHER_PAGE, 0xBF, -1):
        if free(*span(page)):
            return page
    return None


def borrowed_page(state, pages):
    """For the mode without a part in page 3: the page that TAPIN borrows, and
    T0's data for it: TAPIN's byte, the slot register's mask for the page, the
    restorer's byte, the mapper register's port, the page's first address's
    high byte and the game's segment there. The page is page 2 or page 1, the
    first that is in a mapper at the snapshot, or else page 2 (DESIGN.md,
    Without a part in page 3)."""
    mapped = [page for page in (2, 1) if getattr(selected_page(state, pages, page), "seg", None) is not None]
    page = (mapped + [2])[0]
    found = selected_page(state, pages, page)
    register = "f" + "cdef"[page]
    # Without a mapper at the snapshot, as in a capture variant without the
    # Carnivore2, the segment written back is 0, which only DOS's mapper sees.
    seg = found.seg if found is not None and found.seg is not None else num(state, register)
    return page, bytes([0, ~(3 << 2 * page) & 0xFF, 0, 0xFC + page, page * 0x40, seg])


def tape_rom(snap):
    """T0's start: page 0 of the main ROM, whose jump table entries must go to
    the BIOS's tape routines that the service replaces."""
    with open(os.path.join(snap, "rom.bin"), "rb") as f:
        t0 = bytearray(f.read(PAGE))
    for entry, target in TAPE_ENTRIES.items():
        if t0[entry] != 0xC3 or struct.unpack_from("<H", t0, entry + 1)[0] != target:
            raise BuildError(f"{snap}/rom.bin: the jump at {entry:04X}h does not go to {target:04X}h")
    return t0


def write_positions(data, at, start, pos, side1, side2):
    """The tape's position, side 1's end, side 2's end and the tape's start,
    3 bytes each, at offset at of data. The tape starts at offset start of
    the service's tape, and side1 and side2 are lengths."""
    for n, value in enumerate((pos, start + side1, start + side1 + side2, start)):
        data[at + 3 * n:at + 3 * n + 3] = value.to_bytes(3, "little")


def write_flash(data, base, t0, p3, state, side, two_sides):
    """The flash's data at offset base of data, and the side that the tape is
    on. The flash restores VDP registers 7 and 1 from RG7SAV and RG1SAV when
    the game keeps them, and otherwise from the snapshot's values. It counts
    0.1 second of frames, at the rate of bit 7 of the ROM's byte 002Bh: 50 Hz
    when set."""
    pal = t0[0x2B] & 0x80
    vdp7, vdp1 = num(state, "vdp7"), num(state, "vdp1")
    border = RG7SAV if p3.data[RG7SAV & 0x3FFF] == vdp7 else base + 3
    screen = RG1SAV if p3.data[RG1SAV & 0x3FFF] == vdp1 else base + 7
    struct.pack_into("<HBBBHBBB", data, base, border, 5 if pal else 6, vdp7, side, screen, vdp1,
                     0, 1 if two_sides else 0)


def write_page3_part(p3, page3, page, tail_address, e_fc, state):
    """The service's part of page 3, at page's E1h of the game's page 3 p3,
    with E_FC and E_STOP filled in."""
    start = page * 256 + 0xE1
    first, last = (P3_FREE, P3_END) if page == DEFAULT_PAGE else (start, start + len(page3) - 1)
    if tail_address <= last and tail_address + TAIL_SIZE > first:
        raise BuildError(f"the tail at {tail_address:04X}h overlaps {first:04X}h to {last:04X}h")
    block = bytearray(page3)
    block[e_fc - start] = num(state, "fc")
    # E_STOP, after E_FC and E_INSIDE: the manual tape starts stopped when
    # the motor, PPI port C bit 4 (0 = on), is off at the snapshot.
    block[e_fc + 2 - start] = (num(state, "ppic") >> 4) & 1
    p3.data[start & 0x3FFF:(start & 0x3FFF) + len(block)] = block


def service_segments(snap, parts, side1, side2, pages, state, tail_address, page, t0_mode):
    """T0, then the code segment and the tape, or only the tape without a part
    in page 3, as 16 KB blocks, after writing the service's part of page 3
    into the game's page 3 at page's E1h (DESIGN.md, Tape service)."""
    _, stubs, page3, code, fields, t0m, t0m_fields = parts[:7]
    stmotr, c_pos, segs_max, e_fc, c_border, _ = struct.unpack("<6H", fields)
    t0 = tape_rom(snap)
    p3 = selected_page(state, pages, 3)
    if p3 is None:
        raise BuildError(f"{snap}: page 3 is not a RAM page that the snapshot keeps")

    side1_end = len(side1)
    side1 = side1 + bytes((tape.side2_start(len(side1)) if side2 else len(side1) + (-len(side1) % 8)) - len(side1))
    if t0_mode:
        # T0 holds the routines and their data, and the jump table's entries
        # from 00E1h to 00F3h go to them.
        targets = struct.unpack("<11H", t0m_fields)
        t_pos, t_page, base, segs_max = targets[7:]
        t0[TAPE_CODE:TAPE_CODE + len(t0m)] = t0m
        for n, target in enumerate(targets[:7]):
            t0[0xE1 + 3 * n:0xE4 + 3 * n] = bytes([0xC3]) + struct.pack("<H", target)
        t0[t_page:t_page + 6] = borrowed_page(state, pages)[1]
        start, data = 0, t0
        stream = bytearray(side1 + side2)
    else:
        t0[TAPE_CODE:TAPE_CODE + len(stubs)] = stubs
        struct.pack_into("<H", t0, STMOTR + 1, stmotr)
        start, t_pos, base = len(code), c_pos, c_border
        stream = bytearray(code) + side1 + side2
        data = stream
    pos = start + num(state, "tapepos")
    write_positions(data, t_pos, start, pos, len(side1), len(side2))
    side = 1 if side2 and pos >= start + len(side1) else 0
    write_flash(data, base, t0, p3, state, side, bool(side2))
    if not t0_mode:
        # C_S1REAL, after C_SAVE: side 1's end without its padding, which the
        # tape does not have, when side 2 follows it.
        real = start + (side1_end if side2 else len(side1))
        data[base + 13:base + 16] = real.to_bytes(3, "little")
    stream += bytes(-len(stream) % PAGE)
    if len(stream) // PAGE > segs_max:
        raise BuildError(f"the tape needs {len(stream) // PAGE} segments, more than {segs_max}")
    if not t0_mode:
        write_page3_part(p3, page3, page, tail_address, e_fc, state)
    return [bytes(t0)] + [bytes(stream[n:n + PAGE]) for n in range(0, len(stream), PAGE)]


def apply_patch(patch, data, place):
    """Writes a patch's new bytes over its old ones in data."""
    end = patch.offset + len(patch.old)
    if bytes(data[patch.offset:end]) != patch.old:
        raise BuildError(f"{patch.where}: the bytes at {place} are not the patch's old bytes")
    data[patch.offset:end] = patch.new


def scan_snapshot(state, pages, side1, side2, page, slots, with_tape=True, patch=True, blocks=((), ()),
                  patched=None):
    """Patches the scan's findings in the RAM pages, for the entries at page's
    E1h, and returns scan.txt's text, with the findings in the unread blocks:
    side 1 from the tape position, and side 2 (DESIGN.md, Scan), at their
    offsets in the tape files of blocks. Without with_tape, it looks only for
    fixed slot values, and without patch, it patches only those. patched,
    a dict, gets each ram/ file's patched ranges for the check."""
    ram = []
    for p in pages:
        findings = patches.find(p.data, patches.Context(page, slots, with_tape))
        applied = [f for f in findings if patch or f.what == patches.slots.SLOT_VALUE]
        patches.patch(p.data, applied)
        if patched is not None:
            for name in ram_names(p.snap, p):
                patched.setdefault(name, []).extend(patched_range(name, f.offset, len(f.old))
                                                    for f in applied if f.new is not None)
        if p is selected_page(state, pages, p.page):
            place = f"page{p.page}"
        else:
            place = "ram " + "-".join("x" if v is None else str(v) for v in (p.ps, p.ss, p.page, p.seg))
        ram.append((place, findings))
    unread_blocks = []
    if with_tape:
        # Without the tape service, no block is read after the snapshot.
        unread = num(state, "tapepos")
        context = patches.Context(page, slots)
        found = [[f for f in patches.find(side1, context) if f.offset >= unread], patches.find(side2, context)]
        # A patch line's offset is an offset in the tape file (DESIGN.md, Tape
        # files): a CAS file's offsets are the tape service's, and a TSX file's are
        # found through the blocks.
        for side, side_blocks in zip(found, blocks):
            for f in side:
                f.offset = tape.file_offset(side_blocks, f.offset)
        unread_blocks = [(place, [f for f in side if f.offset is not None])
                         for place, side in zip(("side1", "side2"), found)]
    text = patches.report(ram, unread_blocks)
    if not with_tape:
        text = "# Without the tape service, the scan looks only for fixed slot values.\n" + text
    elif not patch:
        text = "# The tape service has no part in page 3, so only fixed slot values are patched.\n" + text
    if page != DEFAULT_PAGE:
        text = f"# The tape service's part of page 3 is at {page:02X}E1h: the game uses FCC9h to FD88h.\n" + text
    return text


def patch_sides(patch_lines, side1, side2):
    """Side 1 and side 2 with the side1 and side2 patch lines applied."""
    sides = {"side1": bytearray(side1), "side2": bytearray(side2)}
    for patch in patch_lines:
        if patch.page in sides:
            apply_patch(patch, sides[patch.page], f"{patch.page}:{patch.offset:X}")
    return bytes(sides["side1"]), bytes(sides["side2"])


def ram_key(slot_id, page, seg):
    """What a RAM page is: its mapper segment in its slot, or its page in its
    slot outside a mapper. A game can select one segment in two pages."""
    return (slot_id, seg) if seg is not None else (slot_id, "page", page)


def read_pages(snap):
    """The RAM pages of snap/ram/, each mapper segment and each page outside a
    mapper once."""
    pages, seen = [], set()
    for name in sorted(os.listdir(os.path.join(snap, "ram"))):
        page = Page(snap, name)
        key = name_key(name)
        if key not in seen:
            seen.add(key)
            pages.append(page)
    return pages


def name_key(name):
    """ram_key of a ram/ file's name, <ps>-<ss>-<page>-<seg>.bin."""
    ps, ss, page, seg = name[:-4].split("-")
    slot_id = int(ps) if ss == "x" else 0x80 | (int(ss) << 2) | int(ps)
    return ram_key(slot_id, int(page), None if seg == "x" else int(seg))


def ram_names(snap, page):
    """The ram/ file names of a RAM page: one per CPU page that selects it."""
    key = ram_key(page.slot_id(), page.page, page.seg)
    return [name for name in sorted(os.listdir(os.path.join(snap, "ram"))) if name_key(name) == key]


def patched_range(name, offset, length):
    """A patched range of a ram/ file as the check reads it: ps-ss-page, the
    first and the last offset."""
    return f"{name[:-4].rsplit('-', 1)[0]} {offset} {offset + length - 1}"


def patch_pages(patch_lines, state, pages):
    """Applies the patch lines of pages 0 to 3 to the RAM pages that the
    snapshot selects there, and returns their ranges for the check."""
    ranges = []
    for patch in patch_lines:
        if patch.page not in ("side1", "side2"):
            found = selected_page(state, pages, patch.page)
            if found is None:
                raise BuildError(f"{patch.where}: page {patch.page} is not a RAM page that the snapshot keeps")
            apply_patch(patch, found.data, f"{patch.page * 0x4000 + patch.offset:04X}")
            ps, ss = selected(state, patch.page)
            ranges.append(f"{ps}-{'x' if ss is None else ss}-{patch.page} "
                          f"{patch.offset} {patch.offset + len(patch.old) - 1}")
    return ranges


def service_mode(state, pages, length, game):
    """The page of the service's page 3 part, 0 without one, and whether the
    image has the mode without a part in page 3: by the game file's service
    t0, or when page 3 has no room for the part's length. A game file with rom
    keep cannot take that mode (DESIGN.md, Game file)."""
    if state["service"] != "1":
        return 0, False
    if game.service != "t0":
        wanted = game.service if isinstance(game.service, int) else None
        page = service_page(state, pages, length, wanted)
        if page is not None:
            return page, False
    if game.rom_keep:
        raise BuildError(f"{game.folder}: page 3 has no room for the tape service's part, and rom keep "
                         "needs it, because the mode without a part in page 3 has no entries there")
    return 0, True


def records_and_data(snap, pages, service):
    """The image's records and their data: the RAM pages, VRAM in 16 KB
    blocks, and the service's segments. Also whether VRAM is a V9938's."""
    records, data = [], []
    for p in pages:
        kind = RAM_IN_MAPPER if p.seg is not None else RAM
        records.append(bytes([kind, p.slot_id(), p.page, p.seg or 0]))
        data.append(bytes(p.data))
    with open(os.path.join(snap, "vram.bin"), "rb") as f:
        vram = f.read()
    for block in range(len(vram) // PAGE):
        chunk = vram[block * PAGE:(block + 1) * PAGE]
        if any(chunk):
            records.append(bytes([VRAM, block, 0, 0]))
            data.append(chunk)
        else:
            records.append(bytes([VRAM_ZEROS, block, 0, 0]))
    for segment in service:
        records.append(bytes([SERVICE_SEGMENT, 0, 0, 0]))
        data.append(segment)
    return records, data, len(vram) > PAGE


def image_header(snap, state, records, writes, flags, page, borrowed, tail_address):
    """The image's header and tables (DESIGN.md, Image)."""
    with open(os.path.join(snap, "rom.bin"), "rb") as f:
        rom = crc16(f.read())
    subrom_path = os.path.join(snap, "subrom.bin")
    subrom = 0
    if os.path.exists(subrom_path):
        with open(subrom_path, "rb") as f:
            subrom = crc16(f.read())

    header = bytearray(HEADER_SIZE)
    header[0:8] = MAGIC
    struct.pack_into("<HHBB", header, 8, rom, subrom, len(records), len(writes))
    header[14] = flags
    header[15] = page
    header[54] = num(state, "vdp1")
    header[55] = borrowed
    struct.pack_into("<12H", header, 16, *[num(state, r) for r in
                     "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()])
    header[40] = num(state, "i")
    header[41] = num(state, "im")
    header[42] = num(state, "iff") & 1
    header[43] = num(state, "a8")
    for ps in range(4):
        header[44 + ps] = num(state, f"sub{ps}")
        if state[f"sub{ps}"] == "-":
            header[56] |= 1 << ps
    for n, reg in enumerate("fc fd fe ff".split()):
        header[48 + n] = num(state, reg)
    struct.pack_into("<H", header, 52, tail_address)
    offset = 64
    for r in records:
        header[offset:offset + 4] = r
        offset += 4
    for port, value in writes:
        header[offset:offset + 2] = bytes([port, value])
        offset += 2
    return bytes(header)


def check_unread(state, blocks, names, service_no):
    """Stops when a non-standard block follows the snapshot: the game reads it
    with its own loader, which the tape service cannot serve, unless the game
    file has service no (DESIGN.md, Tape files)."""
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


def build(snap, service_path, game, side1=b"", side2=b"", patch_lines=()):
    """Returns (header and tables, the records' data, a report, scan.txt's
    text, build.txt's text) for game, a gamefile.Game. side1 and side2 are the
    bytes of the tape files that the capture played (played_tapes), and
    patch_lines the game file's patches and the capture's."""
    state = read_state(snap)
    slots = patches.slots.read_slots(snap)
    names = (game.tape, game.side2 or "")
    # The tape service's tapes of the played files (DESIGN.md, Tape files).
    blocks = (tape.read(names[0], side1) if side1 else [], tape.read(names[1], side2) if side2 else [])
    check_unread(state, blocks, names, game.service == "no")
    side1, side2 = tape.service(blocks[0]), tape.service(blocks[1])
    parts = read_service(service_path)
    tail = parts[0]
    pages = read_pages(snap)
    ranges = patch_pages(patch_lines, state, pages)
    scan_ranges = {}

    # The tape service and its mode: without it, the scan looks only for fixed
    # slot values, and without a part in page 3, it patches only those.
    with_service = state["service"] == "1"
    page, t0_mode = service_mode(state, pages, len(parts[2]), game)
    if not with_service:
        scanned = scan_snapshot(state, pages, side1, side2, DEFAULT_PAGE, slots, with_tape=False,
                                patched=scan_ranges)
    elif t0_mode:
        scanned = scan_snapshot(state, pages, side1, side2, DEFAULT_PAGE, slots, patch=False, blocks=blocks,
                                patched=scan_ranges)
    else:
        parts = read_service(service_path, page)
        scanned = scan_snapshot(state, pages, side1, side2, page, slots, blocks=blocks, patched=scan_ranges)
    tail_address = place_tail(state, pages, tail)
    service = []
    if with_service:
        service = service_segments(snap, parts, side1, side2, pages, state, tail_address, page, t0_mode)

    records, data, v9938 = records_and_data(snap, pages, service)
    writes = port_writes(state, v9938)
    if len(records) > 255 or len(writes) > 255:
        raise BuildError(f"{snap}: too many records or port writes for the image")
    flags = (FLAG_ROM_KEEP if game.rom_keep else 0) | (FLAG_T0 if t0_mode else 0)
    borrowed = borrowed_page(state, pages)[0] if t0_mode else 0
    header = image_header(snap, state, records, writes, flags, page, borrowed, tail_address)

    mapper = sum(1 for r in records if r[0] in (RAM_IN_MAPPER, SERVICE_SEGMENT))
    report = (f"{len(records)} records, {len(writes)} port writes, "
              f"up to {mapper + 1} free mapper segments")
    for name in sorted(scan_ranges):
        ranges += scan_ranges[name]
    checked = check_facts(state, pages, parts, page, bool(service), ranges)
    return header, data, report, scanned, checked


def check_facts(state, pages, parts, page, service, ranges):
    """build.txt's text: what the check takes from the build (DESIGN.md,
    Check). The tape service's part of page 3, when the image has one, is
    {first last E_INSIDE segment} without the scratch bytes from e_sp on, which
    the service sets before it reads them, with page 3's mapper segment at the
    snapshot, or -1 outside a mapper. When the part moved from FCE1h, moved is
    its first and last byte. cpos is the address of C_POS in the code segment,
    selected in page 1."""
    lines = ["# What the check takes from the build (docs/DESIGN.md, Check).",
             f"service {1 if service else 0}"]
    lines += [f"patched {r}" for r in ranges]
    if page:
        _, c_pos, _, e_fc, _, e_sp = struct.unpack("<6H", parts[4])
        p3 = selected_page(state, pages, 3)
        segment = p3.seg if p3 is not None and p3.seg is not None else -1
        first = page * 256 + 0xE1
        lines.append(f"part {first} {e_sp - 1} {e_fc + 1} {segment}")
        lines.append(f"cpos {0x4000 + c_pos}")
        if page != DEFAULT_PAGE:
            lines.append(f"moved {first} {first + len(parts[2]) - 1}")
    return "\n".join(lines) + "\n"


def read_tapes(game, tapes_dir):
    """The bytes of side 1's and side 2's tape files, b"" without a side 2. A patch fits
    only the dumps that it was made for, so with patch lines the tape files
    must match the game file's sha1 lines."""
    side2 = b""
    with open(os.path.join(tapes_dir, game.tape), "rb") as f:
        side1 = f.read()
    if game.side2:
        with open(os.path.join(tapes_dir, game.side2), "rb") as f:
            side2 = f.read()
    if game.patches:
        dumps = [side1] + ([side2] if game.side2 else [])
        if [hashlib.sha1(d).hexdigest() for d in dumps] != game.sha1:
            raise BuildError(f"{game.folder}/game.txt: patch lines need sha1 lines that match the tape files")
    return side1, side2


def played_tapes(game, tapes_dir, captured=()):
    """The bytes of side 1's and side 2's tape files as the capture plays them.
    The game file's patch lines fit the downloaded files, so they come first.
    With a start line, side 1 is then the copy from that file on, and the
    capture's patches, captured, fit the file that it played, so they come last
    (DESIGN.md, A game later on the tape)."""
    side1, side2 = patch_sides(game.patches, *read_tapes(game, tapes_dir))
    if game.start:
        side1 = tape.start_copy(game.tape, side1, game.start)
    return patch_sides(captured, side1, side2)


def main():
    parser = argparse.ArgumentParser(description="Write a game's image from its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--tapes", required=True, help="the folder that holds the tape files, CAS or TSX")
    parser.add_argument("--service", default=os.path.join(ROOT, "bin", "SERVICE.BIN"),
                        help="the SERVICE.BIN to use")
    args = parser.parse_args()

    folder = gamefile.game_folder(args.game)
    try:
        game = gamefile.read_game(folder, args.machine)
        out = gamefile.out_folder(args.machine, folder)
        snap = os.path.join(out, "snap")
        captured = patches.slots.capture_patches(snap)
        side1, side2 = played_tapes(game, args.tapes, captured)
        header, data, report, scanned, checked = build(snap, args.service, game, side1, side2,
                                                       list(game.patches) + captured)
    except (OSError, gamefile.GameFileError, BuildError, tape.TapeError) as e:
        print(f"build.py: {e}", file=sys.stderr)
        return 1
    image = gamefile.image_path(args.machine, folder, game.name)
    with open(image, "wb") as f:
        f.write(header)
        for chunk in data:
            f.write(chunk)
    with open(os.path.join(out, "scan.txt"), "w") as f:
        f.write(scanned)
    with open(os.path.join(out, "build.txt"), "w") as f:
        f.write(checked)
    print(f"{game.name}: {image}: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
