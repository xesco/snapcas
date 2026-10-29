"""CAS files (docs/DESIGN.md, CAS data).

A CAS file is a sequence of blocks, each starting with the 8-byte header at an
offset that is a multiple of 8. The tape position is an offset in this data.
"""

HEADER = bytes.fromhex("1FA6DEBACC137D74")

# The type of a file's first block: its first 10 bytes, and the BASIC command
# that loads it.
LOAD_COMMANDS = {
    0xD0: 'BLOAD"CAS:",R',  # a binary file
    0xD3: "CLOAD",          # a BASIC program, then RUN
    0xEA: 'RUN"CAS:"',      # an ASCII program
}


def side2_start(side1_length):
    """Side 2's position after side 1 in the tape service: side 1 padded to
    a multiple of 8 bytes, by at least 1 byte, where TAPIN turns the tape over
    (DESIGN.md, Tape service)."""
    return side1_length + (-side1_length % 8 or 8)


def headers(data):
    """The offsets of the headers, at multiples of 8."""
    return [o for o in range(0, len(data) - 7, 8) if data[o:o + 8] == HEADER]


def blocks(data):
    """Each block's data, after its header, as (start, end) offsets."""
    starts = headers(data)
    ends = starts[1:] + [len(data)]
    return [(s + 8, e) for s, e in zip(starts, ends)]


def load_command(data):
    """The command that loads the file, or None for an unknown first block."""
    found = blocks(data)
    if not found:
        return None
    start, end = found[0]
    first = data[start:start + 10]
    if len(first) == 10 and len(set(first)) == 1:
        return LOAD_COMMANDS.get(first[0])
    return None


def needed_end(data):
    """The end of the last block that a load must read: blocks after it are
    under 16 bytes or equal to a block before them (DESIGN.md, Capture, step
    5)."""
    end, seen = 0, set()
    for start, stop in blocks(data):
        body = data[start:stop]
        if len(body) >= 16 and body not in seen:
            end = stop
        seen.add(body)
    return end
