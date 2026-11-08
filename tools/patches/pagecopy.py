"""The page copy patch (docs/INTERNALS.md, The page copy patch): a loader's code
that gives pages 0 and 1 the slots of pages 2 and 3, or page 1 the slot of page
3, from the slot register's value. patches/pagecopy.tcl decides at step 4, by
step 3's slot map, whether the machine needs the patch. The kind works only in
the capture, so it has no find()."""
import re

# CAS's block header, which starts each block at a multiple of 8 bytes.
CAS_HEADER = bytes.fromhex("1F A6 DE BA CC 13 7D 74")

# What the code is, its bytes, what it copies: "23" for pages 2 and 3 into
# pages 0 and 1, "31" for page 3 into page 1, and whether the loader also copies
# the subslot register's fields, so that an expanded slot is fit for any page.
FORMS = [
    # IN A,(0A8h) / SRA A four times / AND 0Fh / OR C, where C holds the
    # value's bits of pages 2 and 3: Level 9's adventures.
    ("Level 9's copy of pages 2 and 3", re.compile(rb"\xDB\xA8\xCB\x2F\xCB\x2F\xCB\x2F\xCB\x2F\xE6\x0F\xB1"), "23", False),
    # AND 0F0h / LD B,A / RRCA four times / AND 0Fh / OR B: each part of a tape
    # made by CasLink3, which copies the subslot register's fields as well.
    ("CasLink3's copy of pages 2 and 3", re.compile(rb"\xE6\xF0\x47\x0F\x0F\x0F\x0F\xE6\x0F\xB0"), "23", True),
    # AND 0F0h / LD B,A / RLCA four times / OR B: The Wall's LOADER.
    ("a copy of pages 2 and 3 with RLCA", re.compile(rb"\xE6\xF0\x47\x07\x07\x07\x07\xB0"), "23", False),
    # BIT 7,A / JR Z,+2 / SET 3,A / BIT 6,A / JR Z,+2 / SET 2,A: Engesoft's
    # loaders.
    ("a copy of page 3 with BIT and JR", re.compile(rb"\xCB\x7F\x28\x02\xCB\xDF\xCB\x77\x28\x02\xCB\xD7"), "31", False),
    # The same with JP Z: M-Droid's core.
    ("a copy of page 3 with BIT and JP", re.compile(rb"\xCB\x7F\xCA..\xCB\xDF\xCB\x77\xCA..\xCB\xD7", re.S), "31", False),
]


def sum_byte(data, offset):
    """The offset of the last byte of the CAS block that holds offset, when
    that byte is the 8-bit sum of the block's other bytes, as Level 9's
    loader checks, or -1."""
    if not data.startswith(CAS_HEADER):
        return -1
    start = data.rfind(CAS_HEADER, 0, offset + 1)
    while start % 8:
        start = data.rfind(CAS_HEADER, 0, start)
    start += len(CAS_HEADER)
    end = data.find(CAS_HEADER, offset)
    while end >= 0 and end % 8:
        end = data.find(CAS_HEADER, end + 1)
    if end < 0:
        end = len(data)
    if end - start < 2:
        return -1
    return end - 1 if sum(data[start:end - 1]) & 0xFF == data[end - 1] else -1


def tcl_settings(side1, side2):
    """The Tcl that gives pagecopy.tcl each form in the tape files: its side,
    offset, bytes, copy and whether it copies the subslots, and its block's sum
    byte's offset and value."""
    found = []
    for side, data in ((1, side1), (2, side2)):
        for _, pattern, copy, subslots in FORMS:
            for match in pattern.finditer(data):
                at = sum_byte(data, match.start())
                found.append(f"{{{side} {match.start()} {match.group().hex()} {copy} {int(subslots)} {at} "
                             f"{data[at] if at >= 0 else 0}}}")
    return f"set ::pagecopy {{{' '.join(found)}}}\n"
