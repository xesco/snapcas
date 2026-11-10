"""The slot patches (docs/INTERNALS.md, Slot patches): fixed slot register values
that name a slot that holds nothing, by the capture's slot map
(snapshot.Snapshot.slots). patches/slots.tcl is the capture's watch."""
import re

import msx
from .finding import Finding

# The two forms of the code that sets a fixed slot register value: LD A,n and
# then OUT (0A8h),A, or CALL 013Bh, a call of the BIOS's WSLREG.
LOAD = bytes.fromhex("3E")
OUT = bytes.fromhex("D3 A8")
WSLREG = bytes.fromhex("CD 3B 01")
SLOT_CODE = re.compile(re.escape(LOAD) + b"(.)(?:" + re.escape(OUT) + b"|" + re.escape(WSLREG) + b")", re.S)
SLOT_VALUE = "fixed slot value"
# LD A,(nn), the one instruction that loads A with the byte after a 3Eh in its
# operand, as Knight Orc's LD A,(EF3Eh) / OUT (0A8h),A does.
LD_A_NN = 0x3A
# The opcodes of the instructions with a one-byte and with a two-byte operand.
# A 3Eh after one can be its operand.
OPERAND_1 = bytes.fromhex("06 0E 16 1E 26 2E 36 3E C6 CE D6 DE E6 EE F6 FE D3 DB 10 18 20 28 30 38")
OPERAND_2 = bytes.fromhex("01 11 21 31 22 2A 32 3A C2 C3 C4 CA CC CD D2 D4 DA DC E2 E4 EA EC F2 F4 FA FC")


def tcl(side1, side2):
    """The kind's Tcl for the capture: the forms' bytes, as slots.tcl's
    settings, and slots.tcl. The capture reads the tape files itself."""
    return (f"set ::slotcode(load) {msx.tcl_bytes(LOAD)}\n"
            f"set ::slotcode(out) {msx.tcl_bytes(OUT)}\n"
            f"set ::slotcode(wslreg) {msx.tcl_bytes(WSLREG)}\n"
            f"set ::slotcode(indirect) {LD_A_NN}\n"
            + msx.tcl("patches/slots.tcl"))


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
