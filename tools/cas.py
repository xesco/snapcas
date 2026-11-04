"""The reader of CAS files (docs/FORMATS.md, CAS data, and docs/INTERNALS.md,
Tape files).

A CAS file is a sequence of blocks, each after the 8-byte header, and every
block is one that the BIOS's tape routines read. Most files put each header at
an offset that is a multiple of 8, but some do not pad their blocks, so the
header can be at any offset, as openMSX reads it. tape.py makes the tape model
of the blocks that read() returns.
"""

HEADER = bytes.fromhex("1FA6DEBACC137D74")


def read(data):
    """The file's blocks, as the fields of tape.Block: standard, the block's
    bytes, their offset in the file, and no times, because the capture follows
    a CAS file's blocks by TAPIN."""
    starts = []
    at = data.find(HEADER)
    while at >= 0:
        starts.append(at)
        at = data.find(HEADER, at + 8)
    ends = starts[1:] + [len(data)]
    return [(True, data[s + 8:e], s + 8, None, None) for s, e in zip(starts, ends)]
