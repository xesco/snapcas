#!/usr/bin/env python3
"""Append to SERVICE.BIN its symbols and the offsets of the bytes that move
with its page 3 part (docs/FORMATS.md, SERVICE.BIN).

Usage: relocs.py <binary at FCh> <exports at FCh> <binary at FBh> <exports at FBh> <output>

The Makefile assembles src/service.asm with the page 3 part at FCE1h and at
FBE1h, each time with the file of the symbols that its EXPORT lines name. The
symbols become part 5: build.py reads the service's addresses there by name,
so it holds no copy of them. Only the high bytes of the addresses in the page
3 part differ between the two assemblies, by 1, so their offsets are the bytes
that build.py changes to move the part to another page. Part 6, the last, is
the list of those offsets, 2 bytes each. It comes after the symbols, so that it
also lists the high bytes of the symbols in the page 3 part.
"""
import struct
import sys


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
    """An assembly's bytes with its symbols appended as part 5: for each, in
    the order of their names, the value in 2 bytes, the name's length in 1
    and the name."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    symbols = read_exports(exports)
    part = 2 + 4 * (data[1] - 2)
    if struct.unpack_from("<HH", data, part) != (len(data), 0):
        sys.exit(f"relocs.py: {path}: the symbols' part does not start at the file's end")
    entries = b"".join(struct.pack("<HB", symbols[name], len(name)) + name.encode("ascii")
                       for name in sorted(symbols))
    struct.pack_into("<HH", data, part, len(data), len(entries))
    return data + entries


def main():
    at_fc = with_symbols(sys.argv[1], sys.argv[2])
    at_fb = with_symbols(sys.argv[3], sys.argv[4])
    if len(at_fc) != len(at_fb):
        sys.exit("relocs.py: the two assemblies differ in length")
    offsets = [n for n in range(len(at_fc)) if at_fc[n] != at_fb[n]]
    for n in offsets:
        if at_fc[n] != at_fb[n] + 1:
            sys.exit(f"relocs.py: byte {n:04X} differs by more than one page")
    part = 2 + 4 * (at_fc[1] - 1)
    struct.pack_into("<HH", at_fc, part, len(at_fc), 2 * len(offsets))
    with open(sys.argv[5], "wb") as f:
        f.write(at_fc + b"".join(struct.pack("<H", n) for n in offsets))


if __name__ == "__main__":
    main()
