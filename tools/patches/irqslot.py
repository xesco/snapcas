"""The interrupt slot patch (docs/INTERNALS.md, The interrupt slot patch): an
interrupt handler that writes the slot register back from the game's own copy
of its value, and not from the register. patches/irqslot.tcl decides at step
3 whether the machine needs the patch. The kind works only in the capture, so
its find() finds nothing."""
import re

import msx

# The handler of the interpreter of Aventuras AD's adventures:
#   DI / PUSH AF / PUSH HL / PUSH IX
#   LD A,(copy) / PUSH AF           the value to write back, from the copy
#   LD A,(nn) / OUT (0A8h),A / LD (copy),A
#   ...
#   POP AF / OUT (0A8h),A / LD (copy),A
# The second group is the handler's first LD A,(copy), which the patch
# replaces. The handler's end must follow within END bytes, so that the
# value loaded there is the one written back.
START = re.compile(rb"\xF3\xF5\xE5\xDD\xE5(\x3A(..))\xF5\x3A..\xD3\xA8\x32\2", re.S)
END = 64
# IN A,(0A8h) / NOP: the slot register's own value.
NEW = bytes.fromhex("DB A8 00")


def places(data):
    """Each handler in data, as (the offset of its LD A,(copy), that
    instruction's bytes)."""
    found = []
    for match in START.finditer(data):
        end = b"\xF1\xD3\xA8\x32" + match.group(2)
        if end in data[match.end():match.end() + END]:
            found.append((match.start(1), match.group(1)))
    return found


def find(data, context):
    """Nothing: the capture patches every copy on the tape before the
    load."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each handler in the tape files' bytes,
    with its side, the offset of its LD A,(copy) and that instruction's
    bytes, and the bytes of the patch, as irqslot.tcl's settings, and
    irqslot.tcl."""
    found = [f"{{{side} {offset} {old.hex()}}}"
             for side, data in ((1, side1), (2, side2)) for offset, old in places(data)]
    return (f"set ::irqslot {{{' '.join(found)}}}\n"
            f"set ::irqslot_new {msx.tcl_bytes(NEW)}\n"
            + msx.tcl("patches/irqslot.tcl"))
