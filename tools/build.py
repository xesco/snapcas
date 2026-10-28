#!/usr/bin/env python3
"""Write a game's image from its snapshot (docs/DESIGN.md, Build).

Usage: build.py <game> <machine> --cas <dir> [--service <file>]

<game> and <machine> are as for capture.py. The image goes to
out/<machine>/<game>/<GAME>.IMG, with scan.txt beside it. --service names the
SERVICE.BIN to use, by default bin/SERVICE.BIN.

Exit status: 0 on success, 1 for an error in the input files.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gamefile  # noqa: E402

SERVICE_VERSION = 1
PAGE = 16384
HEADER_SIZE = 4096
MAGIC = b"SNAPCAS1"
TAIL_SIZE = 21

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


def read_service(path):
    """SERVICE.BIN's parts: [bytes], checked against its version byte."""
    with open(path, "rb") as f:
        data = f.read()
    if not data or data[0] != SERVICE_VERSION:
        raise BuildError(f"{path}: version {data[0] if data else 'none'}, "
                         f"expected {SERVICE_VERSION}: build it from this snapcas")
    parts = []
    for n in range(data[1]):
        offset, length = struct.unpack_from("<HH", data, 2 + 4 * n)
        parts.append(data[offset:offset + length])
    return parts


class Page:
    """A RAM page of the snapshot: ram/<ps>-<ss>-<page>-<seg>.bin."""

    def __init__(self, snap, name):
        ps, ss, page, seg = name[:-4].split("-")
        self.ps, self.page = int(ps), int(page)
        self.ss = None if ss == "x" else int(ss)
        self.seg = None if seg == "x" else int(seg)
        with open(os.path.join(snap, "ram", name), "rb") as f:
            self.data = bytearray(f.read())
        if len(self.data) != PAGE:
            raise BuildError(f"{snap}/ram/{name}: not 16 KB")

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


def place_tail(state, pages, tail):
    """Writes the tail into the 21 bytes below the stack pointer, and returns
    its address."""
    sp = num(state, "sp")
    address = (sp - TAIL_SIZE) & 0xFFFF
    end = address + TAIL_SIZE - 1
    if end > 0xFFFE or address >> 14 != end >> 14:
        raise BuildError(f"the 21 bytes below SP {sp:04X} cross a page boundary or include FFFFh")
    page = address >> 14
    ps, ss = selected(state, page)
    target = [p for p in pages if (p.ps, p.ss, p.page) == (ps, ss, page)]
    if not target:
        raise BuildError(f"the 21 bytes below SP {sp:04X} are not in a RAM page that the snapshot keeps")
    code = bytearray(tail)
    struct.pack_into("<H", code, 9, address + 19)
    struct.pack_into("<H", code, 13, sp)
    code[15] = 0xFB if num(state, "iff") & 1 else 0x00
    struct.pack_into("<H", code, 17, num(state, "pc"))
    struct.pack_into("<H", code, 19, num(state, "af"))
    offset = address & 0x3FFF
    target[0].data[offset:offset + TAIL_SIZE] = code
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


def build(snap, service_path):
    """Returns (header and tables, the records' data, a report)."""
    state = read_state(snap)
    if state["service"] != "0":
        raise BuildError(f"{snap}: the game needs the tape service, which this version does not build")
    tail = read_service(service_path)[0]

    pages, seen = [], set()
    for name in sorted(os.listdir(os.path.join(snap, "ram"))):
        page = Page(snap, name)
        key = (page.slot_id(), page.seg) if page.seg is not None else (page.slot_id(), "page", page.page)
        if key not in seen:
            seen.add(key)
            pages.append(page)
    tail_address = place_tail(state, pages, tail)

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
    writes = port_writes(state, len(vram) > PAGE)
    if len(records) > 255 or len(writes) > 255:
        raise BuildError(f"{snap}: too many records or port writes for the image")

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
    struct.pack_into("<12H", header, 16, *[num(state, r) for r in
                     "af bc de hl af2 bc2 de2 hl2 ix iy sp pc".split()])
    header[40] = num(state, "i")
    header[41] = num(state, "im")
    header[42] = num(state, "iff") & 1
    header[43] = num(state, "a8")
    for ps in range(4):
        header[44 + ps] = num(state, f"sub{ps}")
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

    mapper = sum(1 for r in records if r[0] == RAM_IN_MAPPER)
    report = (f"{len(records)} records, {len(writes)} port writes, "
              f"up to {mapper + 1} free mapper segments")
    return bytes(header), data, report


def main():
    parser = argparse.ArgumentParser(description="Write a game's image from its snapshot.")
    parser.add_argument("game", help="a folder below games/, or a folder's path, that holds game.txt")
    parser.add_argument("machine", help="a machine file's path below machines/, without .txt")
    parser.add_argument("--cas", required=True, help="the folder that holds the CAS files")
    parser.add_argument("--service", default=os.path.join(ROOT, "bin", "SERVICE.BIN"),
                        help="the SERVICE.BIN to use")
    args = parser.parse_args()

    folder = (os.path.abspath(args.game) if os.sep in args.game or os.path.isdir(args.game)
              else os.path.join(ROOT, "games", args.game))
    try:
        game = gamefile.read_game(folder)
        if game.patches:
            raise BuildError(f"{folder}/game.txt: patch lines need the scan, which this version does not have")
        name = os.path.basename(os.path.normpath(folder))
        out = os.path.join(ROOT, "out", args.machine, name)
        header, data, report = build(os.path.join(out, "snap"), args.service)
    except (OSError, gamefile.GameFileError, BuildError) as e:
        print(f"build.py: {e}", file=sys.stderr)
        return 1
    image = os.path.join(out, f"{game.name}.IMG")
    with open(image, "wb") as f:
        f.write(header)
        for chunk in data:
            f.write(chunk)
    with open(os.path.join(out, "scan.txt"), "w") as f:
        f.write("No tape service, so no scan.\n")
    print(f"{game.name}: {image}: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
