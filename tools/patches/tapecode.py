"""The tape code patch (docs/INTERNALS.md, Scan): the game's code that reaches
the tape without going through T0.

A finding that can be patched sends its call or stub to the entries in page 3,
at E1h to F3h of the entry page, by writing the entry page over the 00h of the
BIOS's jump table address. In the mode without a part in page 3 there are no
entries, and each finding is only listed. The kind works only in the scan, so
its tcl() returns nothing.
"""
import re

from .finding import Finding

# What the code is, its bytes, and the offset in the match of the byte that the
# patch sets to the entry page, or None for a finding that is only listed. The stub pushes
# TAPION's entry and the BIOS's inter-slot call routine, CDD9h, and the game
# later changes the entry's low byte to E4h for TAPIN.
PATTERNS = [
    ("stub of TAPION", re.compile(rb"\x11\xE1\x00\xD5\x11\xD9\xCD\xD5|\x21\xE1\x00\xE5\x21\xD9\xCD\xE5"), 2),
    ("call of TAPION", re.compile(rb"\xCD\xE1\x00"), 2),
    ("call of TAPIN", re.compile(rb"\xCD\xE4\x00"), 2),
    ("call of TAPIOF", re.compile(rb"\xCD\xE7\x00"), 2),
    ("call of STMOTR", re.compile(rb"\xCD\xF3\x00"), 2),
    # LD HL,00E1h or 00E4h, then CALL: a routine of the game's that selects the
    # ROM in page 0 and jumps to the entry in HL.
    ("entry of TAPION in HL", re.compile(rb"\x21\xE1\x00\xCD"), 2),
    ("entry of TAPIN in HL", re.compile(rb"\x21\xE4\x00\xCD"), 2),
    # IN A,(0A2h), then within 4 bytes RLA, RLCA, BIT 7,A or AND 80h.
    ("reader of the cassette signal", re.compile(rb"\xDB\xA2.{0,3}?(?:\x17|\x07|\xCB\x7F|\xE6\x80)", re.S), None),
    # LD A,0Eh / OUT (0A0h),A / IN A,(0A2h): PSG register 14, whose bit 7 is the
    # cassette signal and whose other bits are a joystick (MSX Red Book, PSG).
    ("reader of PSG register 14, the cassette signal or a joystick", re.compile(rb"\x3E\x0E\xD3\xA0\xDB\xA2"), None),
]


def find(data, context):
    """The tape code in data, when the image has the tape service, with
    patches for the entries when the context has an entry page."""
    findings = []
    for what, pattern, patch_at in PATTERNS if context.tape else ():
        for match in pattern.finditer(data):
            old = match.group()
            new = None
            if patch_at is not None and context.entry_page is not None:
                new = bytearray(old)
                new[patch_at] = context.entry_page
                new = bytes(new)
            findings.append(Finding(what, match.start(), old, new))
    return findings


def tcl(side1, side2):
    """Nothing: in the capture the game reads openMSX's cassette player
    through the BIOS, so its tape code needs no patch."""
    return ""
