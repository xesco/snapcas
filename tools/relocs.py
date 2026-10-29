#!/usr/bin/env python3
"""Append to SERVICE.BIN the offsets of the bytes that move with its page 3
part (docs/DESIGN.md, SERVICE.BIN).

Usage: relocs.py <SERVICE.BIN at FCh> <SERVICE.BIN at FBh> <output>

The Makefile assembles src/service.asm with the page 3 part at FCE1h and at
FBE1h. Only the high bytes of the addresses in that part differ, by 1, so their
offsets are the bytes that build.py changes to move the part to another page.
Part 5, the last, is the list of offsets, 2 bytes each.
"""
import struct
import sys


def main():
    with open(sys.argv[1], "rb") as f:
        at_fc = bytearray(f.read())
    with open(sys.argv[2], "rb") as f:
        at_fb = f.read()
    if len(at_fc) != len(at_fb):
        sys.exit("relocs.py: the two assemblies differ in length")
    offsets = [n for n in range(len(at_fc)) if at_fc[n] != at_fb[n]]
    for n in offsets:
        if at_fc[n] != at_fb[n] + 1:
            sys.exit(f"relocs.py: byte {n:04X} differs by more than one page")
    part = 2 + 4 * (at_fc[1] - 1)
    if struct.unpack_from("<H", at_fc, part)[0] != len(at_fc):
        sys.exit("relocs.py: the last part does not start at the file's end")
    struct.pack_into("<H", at_fc, part + 2, 2 * len(offsets))
    with open(sys.argv[3], "wb") as f:
        f.write(at_fc + b"".join(struct.pack("<H", n) for n in offsets))


if __name__ == "__main__":
    main()
