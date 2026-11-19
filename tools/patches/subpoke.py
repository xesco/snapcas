"""The subslot POKE patch (docs/INTERNALS.md, The subslot POKE patch): a BASIC
program's POKE &HFFFF,&HAA, which selects subslot 2 in every page of page 3's
slot, or POKE -1,168, which selects it in pages 1 to 3. patches/subpoke.tcl
decides at step 3 whether the machine needs the patch. The kind works only in
the capture, so its find() finds nothing."""
import re

import msx

# The POKE of an MSX2 whose RAM is in subslot 2, as the user's POKE -1,170: the
# address as &HFFFF, -1, 65535 or 65535!, and the value as &HAA or 170, or as
# &HA8 or 168, which leaves subslot 0 in page 0. A program saved as text holds
# the statement's characters, and the value's digits get the patch: AA or A8,
# kind H, or 170 or 168, kind D. No digit follows the value, which would make
# it another number.
TEXT = re.compile(rb"POKE ?(?:&HFFFF|-1|65535!?) ?, ?(?:&H(AA|A8)(?![0-9A-F])|(170|168)(?![0-9]))")
# A tokenized program holds POKE as 98h, &HFFFF as 0Ch FFh FFh or -1 as F2h
# 12h, and the value as 0Ch AAh 00h or 0Fh AAh, or the same with A8h. The
# value's byte gets the patch, kind T.
TOKENS = re.compile(rb"\x98 ?(?:\x0C\xFF\xFF|\xF2 ?\x12) ?, ?(?:\x0C([\xAA\xA8])\x00|\x0F([\xAA\xA8]))")


def places(data):
    """Each such POKE in data, as (the offset of its value's digits or byte,
    the value's kind: H, D or T, the value)."""
    found = []
    for match in TEXT.finditer(data):
        if match.group(1):
            found.append((match.start(1), "H", int(match.group(1), 16)))
        else:
            found.append((match.start(2), "D", int(match.group(2))))
    for match in TOKENS.finditer(data):
        found.append((match.start(match.lastindex), "T", match.group(match.lastindex)[0]))
    return sorted(found)


def find(data, context):
    """Nothing: the capture patches every copy on the tape before the
    load."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each POKE in the tape files' bytes,
    with its side, the offset of its value, the value's kind and the value, as
    subpoke.tcl's setting, and subpoke.tcl."""
    found = [f"{{{side} {offset} {kind} {value}}}"
             for side, data in ((1, side1), (2, side2)) for offset, kind, value in places(data)]
    return f"set ::subpoke {{{' '.join(found)}}}\n" + msx.tcl("patches/subpoke.tcl")
