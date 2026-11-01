"""The slot patches (docs/DESIGN.md, Slot patches): fixed slot register values
that name a slot that holds nothing, the capture's slot map, and the capture's
patches of the tape. patches/slots.tcl is the capture's watch."""
import os
import re

import gamefile
from .finding import Finding

# LD A,n / OUT (0A8h),A, and LD A,n / CALL 013Bh, a call of the BIOS's WSLREG:
# a fixed slot register value.
SLOT_CODE = re.compile(rb"\x3E(.)(?:\xD3\xA8|\xCD\x3B\x01)", re.S)
SLOT_VALUE = "fixed slot value"
# The opcodes of the instructions with a one-byte and with a two-byte operand.
# A 3Eh after one can be its operand, as in Knight Orc's LD A,(EF3Eh) / OUT
# (0A8h),A.
OPERAND_1 = bytes.fromhex("06 0E 16 1E 26 2E 36 3E C6 CE D6 DE E6 EE F6 FE D3 DB 10 18 20 28 30 38")
OPERAND_2 = bytes.fromhex("01 11 21 31 22 2A 32 3A C2 C3 C4 CA CC CD D2 D4 DA DC E2 E4 EA EC F2 F4 FA FC")


def in_operand(data, offset):
    """Whether the byte at offset in data can be an operand of the instruction
    before it."""
    return ((offset >= 1 and data[offset - 1] in OPERAND_1 + OPERAND_2)
            or (offset >= 2 and data[offset - 2] in OPERAND_2))


def slot_fix(value, slots):
    """The slot register value with each field that names a slot that holds
    nothing replaced, where slots, the capture's slot map, has a replacement
    for its page."""
    for page, (empty, with_) in slots.items():
        shift = 2 * page
        if (value >> shift) & 3 in empty and with_ >= 0:
            value = (value & ~(3 << shift) & 0xFF) | (with_ << shift)
    return value


def find(data, context):
    """The fixed slot values in data that name a slot that holds nothing, by
    the context's slot map, when there is one."""
    findings = []
    for match in SLOT_CODE.finditer(data) if context.slots else ():
        value = match.group(1)[0]
        fixed = slot_fix(value, context.slots)
        if fixed != value and not in_operand(data, match.start()):
            old = match.group()
            findings.append(Finding(SLOT_VALUE, match.start(), old, old[:1] + bytes([fixed]) + old[2:]))
    return findings


def tcl_settings():
    """The Tcl that gives slots.tcl the opcodes of OPERAND_1 and OPERAND_2."""
    return "".join(f"set ::{name} {{{' '.join(str(b) for b in data)}}}\n"
                   for name, data in (("operand1", OPERAND_1), ("operand2", OPERAND_2)))


def read_slots(snap):
    """snap/slots.txt, the capture's slot map: for each page, the primary slots
    that hold nothing there and the slot that replaces them, or -1. None for a
    snapshot without it."""
    path = os.path.join(snap, "slots.txt")
    if not os.path.exists(path):
        return None
    slots = {}
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                _, page, _, empty, _, with_ = line.split()
                slots[int(page)] = (set() if empty == "-" else {int(v) for v in empty.split(",")}, int(with_))
    return slots


def capture_patches(snap):
    """The capture's patches of the tape, in snap/patches.txt: the slot
    patches and the RAM search patch."""
    path = os.path.join(snap, "patches.txt")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [gamefile.read_patch(line.split()[1:], path) for line in f if line.startswith("patch ")]
