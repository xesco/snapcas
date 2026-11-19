#!/usr/bin/env python3
"""Append to SERVICE.BIN its symbols, the offsets of the bytes that move with
its page 3 part, and the offsets of the addresses that move with that part's
code block (docs/FORMATS.md, SERVICE.BIN).

Usage: relocs.py <binary at FCh> <exports at FCh> <binary at FBh> <exports at FBh>
                 <binary with the code block moved> <its exports> <output>

The Makefile assembles src/service.asm with the page 3 part at FCE1h, at FBE1h,
and at FCE1h with the part's code block CODE_MOVE bytes higher, each time with
the file of the symbols that its EXPORT lines name. The symbols become part 6:
build.py reads the service's addresses there by name, so it holds no copy of
them. Only the high bytes of the addresses in the page 3 part differ between
the first two assemblies, by 1, so their offsets are the bytes that build.py
changes to move the part to another page: part 7. Only the addresses in the
code block differ between the first and the third, by CODE_MOVE, so their
offsets are the words that build.py changes to put the code block at another
address: part 8. Parts 7 and 8 come after the symbols, so that they also list
the symbols in the part.
"""
import struct
import sys

# The third assembly's move of the code block, which changes both bytes of
# every address in it.
CODE_MOVE = 0x0111
PARTS = 9  # the parts of SERVICE.BIN, of which 6 to 8 are this file's


def read_exports(path):
    """The symbols of an export file of sjasmplus, whose lines are
    "name: EQU 0x0000FCF9", as {name: value}."""
    symbols = {}
    with open(path) as f:
        for line in f:
            name, _, value = line.strip().partition(": EQU ")
            if not value:
                sys.exit(f"relocs.py: {path}: cannot read the line {line.strip()!r}")
            symbols[name] = int(value, 16)
            if not 0 <= symbols[name] <= 0xFFFF or len(name) > 255:
                sys.exit(f"relocs.py: {path}: {name} does not fit a symbol's entry")
    return symbols


def with_symbols(path, exports):
    """An assembly's bytes with its symbols appended as part 6: for each, in
    the order of their names, the value in 2 bytes, the name's length in 1
    and the name."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    if data[1] != PARTS:
        sys.exit(f"relocs.py: {path}: {data[1]} parts, expected {PARTS}")
    symbols = read_exports(exports)
    part = 2 + 4 * 6
    if struct.unpack_from("<HH", data, part) != (len(data), 0):
        sys.exit(f"relocs.py: {path}: the symbols' part does not start at the file's end")
    entries = b"".join(struct.pack("<HB", symbols[name], len(name)) + name.encode("ascii")
                       for name in sorted(symbols))
    struct.pack_into("<HH", data, part, len(data), len(entries))
    return data + entries


def page_offsets(at_fc, at_fb):
    """The offsets of the bytes that differ by 1 between the part at FCh and
    at FBh: the high bytes of the part's addresses."""
    offsets = [n for n in range(len(at_fc)) if at_fc[n] != at_fb[n]]
    for n in offsets:
        if at_fc[n] != at_fb[n] + 1:
            sys.exit(f"relocs.py: byte {n:04X} differs by more than one page")
    return offsets


def code_offsets(at_fc, moved):
    """The offsets of the words that differ by CODE_MOVE between the code
    block at its place and moved: the code block's addresses. A byte that
    differs and is not half of such a word is an address that build.py could
    not move, so the run stops."""
    differ = [n for n in range(len(at_fc)) if at_fc[n] != moved[n]]
    words, n = [], 0
    while n < len(differ):
        at = differ[n]
        old, new = struct.unpack_from("<H", at_fc, at)[0], struct.unpack_from("<H", moved, at)[0]
        if n + 1 >= len(differ) or differ[n + 1] != at + 1 or (new - old) & 0xFFFF != CODE_MOVE:
            sys.exit(f"relocs.py: byte {at:04X} moves with the code block but is not the low byte of an "
                     f"address in it")
        words.append(at)
        n += 2
    return words


def main():
    at_fc = with_symbols(sys.argv[1], sys.argv[2])
    at_fb = with_symbols(sys.argv[3], sys.argv[4])
    moved = with_symbols(sys.argv[5], sys.argv[6])
    if not len(at_fc) == len(at_fb) == len(moved):
        sys.exit("relocs.py: the three assemblies differ in length")
    pages = page_offsets(at_fc, at_fb)
    words = code_offsets(at_fc, moved)
    start = len(at_fc)
    struct.pack_into("<HH", at_fc, 2 + 4 * 7, start, 2 * len(pages))
    struct.pack_into("<HH", at_fc, 2 + 4 * 8, start + 2 * len(pages), 2 * len(words))
    with open(sys.argv[7], "wb") as f:
        f.write(at_fc + b"".join(struct.pack("<H", n) for n in pages + words))


if __name__ == "__main__":
    main()
