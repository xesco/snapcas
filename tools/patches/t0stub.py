"""The T0 stub patch (docs/INTERNALS.md, Scan): in the mode without a part in
page 3, a stub of TAPION that selects the ROM in page 0 itself, and so reaches
the ROM instead of T0.

The stub pushes TAPION's entry, the BIOS's inter-slot call routine and OUT
(C),L, then reads the slot register into H and makes page 0's field slot 0
with AND H / LD L,A, where A clears that field. The patch makes AND H / LD L,A
into LD L,n, with n the context's slot register value that selects T0.
"""
import re

from .finding import Finding

T0_STUB = "stub's selection of the ROM in page 0"
T0_STUB_CODE = re.compile(rb"\x11\xE1\x00\xD5\x11\xD9\xCD\xD5\x11\xED\x69\xD5\xE5\xD9\x0E\xA8\xED\x60(\xA4\x6F)")


def find(data, context):
    """The stubs in data, patched with the context's value for T0, in the mode
    without a part in page 3."""
    if context.t0 is None:
        return []
    return [Finding(T0_STUB, m.start(1), m.group(1), bytes([0x2E, context.t0])) for m in T0_STUB_CODE.finditer(data)]
