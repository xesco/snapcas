"""The hook fill patch (docs/INTERNALS.md, The hook fill patch): a loader's fill
of the BIOS's hooks with RET that goes on past them, over an MSX2's copies of
VDP registers 8 to 23. patches/hookfill.tcl decides at step 3 whether the
machine needs the patch. The kind works only in the capture, so its find()
finds nothing."""
import re
import struct

import msx

# LD HL,0FD9Ah / LD DE,0FD9Bh / LD BC,nn / LD (HL),0C9h / LDIR, which writes
# RET from FD9Ah to FD9Ah plus nn. The group is nn.
FILL = re.compile(rb"\x21\x9A\xFD\x11\x9B\xFD\x01(..)\x36\xC9\xED\xB0", re.S)
HOOKS = 0xFD9A
# The last byte of the hooks: FFC9h, the end of the last hook of MSX1's table.
# An MSX2 keeps RG8SAV to RG23SAV in FFE7h to FFF6h, its sub-ROM writes them to
# the VDP, and the fill's C9h there makes register 15 select status register 9.
LAST = 0xFFC9
# The count that ends the fill at LAST.
NEW = struct.pack("<H", LAST - HOOKS)


def places(data):
    """Each such fill in data that writes past LAST, as (the offset of its
    count, the count's two bytes)."""
    found = []
    for match in FILL.finditer(data):
        count = struct.unpack("<H", match.group(1))[0]
        if HOOKS + count > LAST:
            found.append((match.start(1), match.group(1)))
    return found


def find(data, context):
    """Nothing: the capture patches every copy on the tape before the
    load."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each fill in the tape files' bytes,
    with its side, the offset of its count and the count's bytes, and the
    bytes of the patch, as hookfill.tcl's settings, and hookfill.tcl."""
    found = [f"{{{side} {offset} {old.hex()}}}"
             for side, data in ((1, side1), (2, side2)) for offset, old in places(data)]
    return (f"set ::hookfill {{{' '.join(found)}}}\n"
            f"set ::hookfill_new {msx.tcl_bytes(NEW)}\n"
            + msx.tcl("patches/hookfill.tcl"))
