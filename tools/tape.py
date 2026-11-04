"""The tape model (docs/INTERNALS.md, Tape files): a tape file's blocks, whatever
its format, and the tape service's tape that the capture and the build use.

Only the readers, cas.py and tsx.py, read tape files. The tape service's tape
holds the standard blocks, each after the 8-byte header at an offset that is a
multiple of 8, and the tape position is an offset in it.
"""
import collections
import os

import cas
import tsx

# A block: whether the BIOS's TAPION and TAPIN read it, its bytes, their offset
# in the file, and the player's seconds at its start and end, or None.
Block = collections.namedtuple("Block", "standard data offset start end")

READERS = {".cas": cas.read, ".tsx": tsx.read}

HEADER = cas.HEADER

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
    try:
        return [Block(*fields) for fields in reader(data)]
    except tsx.TsxError as e:
        raise TapeError(f"{name}: {e}")


def service(blocks):
    """The tape service's tape of the blocks: each standard block after the
    header, at an offset that is a multiple of 8. A CAS file has this layout,
    so its tape is the file itself."""
    tape = bytearray()
    for block in blocks:
        if block.standard:
            tape += bytes(-len(tape) % 8) + HEADER + block.data
    return bytes(tape)


def start_copy(name, data, file):
    """The copy of a tape file's bytes that begins at the block of the first
    file named file, for the game file's start line (INTERNALS.md, A game later
    on the tape): a CAS file's as the tape service's tape of those blocks, and
    a TSX file's as its first 10 bytes and its bytes from that 4Bh block on."""
    blocks = read(name, data)
    for n, block in enumerate(blocks):
        head = block.data[:16]
        if (len(head) == 16 and len(set(head[:10])) == 1 and head[0] in LOAD_COMMANDS
                and head[10:].decode("latin-1").rstrip() == file):
            break
    else:
        named = [bytes([t]) * 10 + file.ljust(6).encode("latin-1") for t in LOAD_COMMANDS]
        if any(h in data for h in named):
            raise TapeError(f"{name}: the file {file} is inside a block, not at a block's start")
        raise TapeError(f"{name}: side 1 has no file named {file}")
    if os.path.splitext(name)[1].lower() == ".cas":
        return service(blocks[n:])
    # A standard block 4Bh: its ID byte and 16 bytes of its body before the data.
    at = block.offset - 17
    if data[at] != 0x4B:
        raise TapeError(f"{name}: the file {file} is not in a block 4Bh")
    return data[:10] + data[at:]


def side2_start(side1_length):
    """Side 2's position after side 1 in the tape service: side 1 padded to
    a multiple of 8 bytes, by at least 1 byte, where TAPIN turns the tape over
    (INTERNALS.md, Tape service)."""
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
    under 16 bytes or equal to a block before them (INTERNALS.md, Capture, step
    5)."""
    end, seen = 0, set()
    for start, stop in spans(tape):
        body = tape[start:stop]
        if len(body) >= 16 and body not in seen:
            end = stop
        seen.add(body)
    return end


def file_offset(blocks, offset):
    """The offset in the tape file of a byte at offset in the tape service's
    tape of the blocks, or None for a byte of a header or of the padding."""
    at = 0
    for block in blocks:
        if block.standard:
            start = at + (-at % 8) + 8
            if start <= offset < start + len(block.data):
                return block.offset + offset - start
            at = start + len(block.data)
    return None


def unread(blocks, seconds):
    """The non-standard blocks that hold bytes and end after seconds into
    the tape: the game reads them after the snapshot with its own loader, which
    the tape service cannot serve (INTERNALS.md, Tape files). A block counts as
    read when the player has passed its end, with 0.1 seconds to spare."""
    return [b for b in blocks if not b.standard and b.data and b.end > seconds + 0.1]
