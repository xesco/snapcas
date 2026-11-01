"""The reader of CAS files (docs/DESIGN.md, CAS data and Tape files).

A CAS file is a sequence of blocks, each after the 8-byte header at an offset
that is a multiple of 8, and every block is one that the BIOS's tape routines
read. tape.py makes the tape model of the blocks that read() returns.
"""

HEADER = bytes.fromhex("1FA6DEBACC137D74")


def read(data):
    """The file's blocks, as the fields of tape.Block: standard, the block's
    bytes, their offset in the file, and no times, because the capture follows
    a CAS file's blocks by TAPIN."""
    starts = [o for o in range(0, len(data) - 7, 8) if data[o:o + 8] == HEADER]
    ends = starts[1:] + [len(data)]
    return [(True, data[s + 8:e], s + 8, None, None) for s, e in zip(starts, ends)]
