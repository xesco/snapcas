"""The tape model (docs/INTERNALS.md, Tape files): a tape file's blocks, whatever
its format, and the tape service's tape that the capture and the build use.
Also a game's tape files as the capture plays them, with the patch lines
applied.

Only the readers, cas.py and tsx.py, read tape files. The tape service's tape
holds the standard blocks, each after the 8-byte header at an offset that is a
multiple of 8, and the tape position is an offset in it.
"""
import collections
import hashlib
import os

import cas
import tsx

# A block: whether the BIOS's TAPION and TAPIN read it, its bytes, their offset
# in the file, and the player's seconds at its start and end, or None.
Block = collections.namedtuple("Block", "standard data offset start end")

READERS = {".cas": cas.read, ".tsx": tsx.read}

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
            tape += bytes(-len(tape) % 8) + cas.HEADER + block.data
    return bytes(tape)


def start_blocks(name, data, file):
    """The blocks of a tape file's bytes from the block of the first file named
    file on, for the game file's start line (INTERNALS.md, A game later on the
    tape). Their offsets are in data, so file_offset gives a place in the whole
    file for an offset in the tape service's tape of start_copy's copy."""
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
    return blocks[n:]


def start_copy(name, data, file):
    """The copy of a tape file's bytes that begins at the block of the first
    file named file: a CAS file's as the tape service's tape of those blocks,
    and a TSX file's as its first 10 bytes and its bytes from that 4Bh block
    on."""
    blocks = start_blocks(name, data, file)
    if os.path.splitext(name)[1].lower() == ".cas":
        return service(blocks)
    # A standard block 4Bh: its ID byte and 16 bytes of its body before the data.
    at = blocks[0].offset - 17
    if data[at] != 0x4B:
        raise TapeError(f"{name}: the file {file} is not in a block 4Bh")
    return data[:10] + data[at:]


def side2_start(side1_length):
    """Side 2's position after side 1 in the tape service: side 1 padded to
    a multiple of 8 bytes, by at least 1 byte, where TAPIN turns the tape over
    (INTERNALS.md, Tape service)."""
    return side1_length + (-side1_length % 8 or 8)


def both_sides(side1, side2):
    """The tape service's tape of both sides: side 1, padded with zeros to a
    multiple of 8 bytes, by at least 1 byte when side 2 follows, where TAPIN
    turns the tape over (side2_start), then side 2. Also side 1's end before
    the padding, which the tape does not have, when side 2 follows it, and
    side 1's end after it."""
    end = side2_start(len(side1)) if side2 else len(side1) + (-len(side1) % 8)
    return side1 + bytes(end - len(side1)) + side2, len(side1) if side2 else end, end


def headers(tape):
    """The offsets of the headers in the tape service's tape."""
    return [o for o in range(0, len(tape) - 7, 8) if tape[o:o + 8] == cas.HEADER]


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
    start, _ = found[0]
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


def read_files(game, tapes_dir):
    """The bytes of the tape files of game, a gamefile.Game: side 1's and
    side 2's, b"" without a side 2. A patch fits only the dumps that it was
    made for, so with patch lines the tape files must match the game file's
    sha1 lines."""
    side2 = b""
    with open(os.path.join(tapes_dir, game.tape), "rb") as f:
        side1 = f.read()
    if game.side2:
        with open(os.path.join(tapes_dir, game.side2), "rb") as f:
            side2 = f.read()
    if game.patches:
        dumps = [side1] + ([side2] if game.side2 else [])
        if [hashlib.sha1(d).hexdigest() for d in dumps] != game.sha1:
            raise TapeError(f"{game.folder}/game.txt: patch lines need sha1 lines that match the tape files")
    return side1, side2


def patch_sides(patch_lines, side1, side2):
    """Side 1 and side 2 with the patch lines of the two sides applied."""
    sides = [bytearray(side1), bytearray(side2)]
    for patch in patch_lines:
        if patch.side is not None:
            patch.apply(sides[patch.side - 1])
    return bytes(sides[0]), bytes(sides[1])


def played(game, tapes_dir, captured=()):
    """The bytes of side 1's and side 2's tape files as the capture plays them.
    The game file's patch lines fit the downloaded files, so they come first.
    With a start line, side 1 is then the copy from that file on, and the
    capture's patches, captured, fit the file that it played, so they come last
    (INTERNALS.md, A game later on the tape)."""
    side1, side2 = patch_sides(game.patches, *read_files(game, tapes_dir))
    if game.start:
        side1 = start_copy(game.tape, side1, game.start)
    return patch_sides(captured, side1, side2)


def played_blocks(game, tapes_dir):
    """For a game file with a start line, the blocks of side 1's downloaded
    file from that file on, which the capture played, or None without the
    line."""
    if not game.start:
        return None
    side1, _ = patch_sides(game.patches, *read_files(game, tapes_dir))
    return start_blocks(game.tape, side1, game.start)
