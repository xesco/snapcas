"""The tape model (docs/DESIGN.md, Tape files): a tape file's blocks, whatever
its format, and the tape service's tape that the capture and the build use.

Only the readers, cas.py and tsx.py, read tape files. The tape service's tape
holds the standard blocks, each after the 8-byte header at an offset that is a
multiple of 8, and the tape position is an offset in it.
"""
import collections
import os

import cas

# A block: whether the BIOS's TAPION and TAPIN read it, its bytes, their offset
# in the file, and the player's seconds at its start and end, or None.
Block = collections.namedtuple("Block", "standard data offset start end")

READERS = {".cas": cas.read}

HEADER = bytes.fromhex("1FA6DEBACC137D74")

# The type of a file's first block: its first 10 bytes, and the BASIC command
# that loads it.
LOAD_COMMANDS = {
    0xD0: 'BLOAD"CAS:",R',  # a binary file
    0xD3: "CLOAD",          # a BASIC program, then RUN
    0xEA: 'RUN"CAS:"',      # an ASCII program
}


class TapeError(Exception):
    pass


def read(name, data):
    """The blocks of a tape file's bytes, by the reader of the extension of
    the file's name."""
    reader = READERS.get(os.path.splitext(name)[1].lower())
    if reader is None:
        raise TapeError(f"{name}: not a CAS or TSX file")
    return [Block(*fields) for fields in reader(data)]


def service(blocks):
    """The tape service's tape of the blocks: each standard block after the
    header, at an offset that is a multiple of 8. A CAS file has this layout,
    so its tape is the file itself."""
    tape = bytearray()
    for block in blocks:
        if block.standard:
            tape += bytes(-len(tape) % 8) + HEADER + block.data
    return bytes(tape)


def side2_start(side1_length):
    """Side 2's position after side 1 in the tape service: side 1 padded to
    a multiple of 8 bytes, by at least 1 byte, where TAPIN turns the tape over
    (DESIGN.md, Tape service)."""
    return side1_length + (-side1_length % 8 or 8)


def headers(tape):
    """The offsets of the headers in the tape service's tape."""
    return [o for o in range(0, len(tape) - 7, 8) if tape[o:o + 8] == HEADER]


def spans(tape):
    """Each block's bytes in the tape service's tape, after its header, as
    (start, end) offsets."""
    starts = headers(tape)
    ends = starts[1:] + [len(tape)]
    return [(s + 8, e) for s, e in zip(starts, ends)]


def load_command(tape):
    """The command that loads the tape, or None for an unknown first block."""
    found = spans(tape)
    if not found:
        return None
    start, end = found[0]
    first = tape[start:start + 10]
    if len(first) == 10 and len(set(first)) == 1:
        return LOAD_COMMANDS.get(first[0])
    return None


def needed_end(tape):
    """The end of the last block that a load must read: blocks after it are
    under 16 bytes or equal to a block before them (DESIGN.md, Capture, step
    5)."""
    end, seen = 0, set()
    for start, stop in spans(tape):
        body = tape[start:stop]
        if len(body) >= 16 and body not in seen:
            end = stop
        seen.add(body)
    return end
