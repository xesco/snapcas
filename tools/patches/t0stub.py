"""The T0 stub patch (docs/INTERNALS.md, Scan): in the mode without a part in
page 3, a stub of TAPION that selects the ROM in page 0 itself, and so reaches
the ROM instead of T0.

The stub pushes TAPION's entry, the BIOS's inter-slot call routine and OUT
(C),L, then reads the slot register into H and makes page 0's field slot 0
with AND H / LD L,A, where A clears that field. The patch makes AND H / LD L,A
into LD L,n. n is the slot register value that selects DOS's mapper, where T0
is, in page 0. Only the restorer knows DOS's mapper, so the build leaves n at
0 and the finding names its place, which the image's header lists for the
restorer (docs/FORMATS.md, Image). The kind works only in the scan, so its
tcl() returns nothing.
"""
import re

from .finding import Finding

T0_STUB = "stub's selection of the ROM in page 0"
T0_STUB_CODE = re.compile(rb"\x11\xE1\x00\xD5\x11\xD9\xCD\xD5\x11\xED\x69\xD5\xE5\xD9\x0E\xA8\xED\x60(\xA4\x6F)")


def find(data, context):
    """The stubs in data, in the mode without a part in page 3: patched in a
    RAM page, where the restorer fills in the value, and otherwise only
    listed."""
    if not context.tape or context.entry_page is not None:
        return []
    if not context.ram:
        return [Finding(T0_STUB, m.start(1), m.group(1), None) for m in T0_STUB_CODE.finditer(data)]
    return [Finding(T0_STUB, m.start(1), m.group(1), bytes([0x2E, 0x00]), place=1)
            for m in T0_STUB_CODE.finditer(data)]


def tcl(side1, side2):
    """Nothing: the capture runs without T0, so the stub reaches the ROM as
    it must."""
    return ""
