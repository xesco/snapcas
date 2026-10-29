"""The scan (docs/DESIGN.md, Scan): code that reaches the tape without going
through T0, in the snapshot's RAM pages and in the tape's unread blocks.

A finding that can be patched sends its call or stub to the entries in page 3,
FCE1h to FCE7h, by writing FCh over the 00h of the BIOS's jump table address.
"""
import re

# What the code is, its bytes, and the offset in the match of the byte that the
# patch sets to FCh, or None for a finding that is only listed. The stub pushes
# TAPION's entry and the BIOS's inter-slot call routine, CDD9h, and the game
# later changes the entry's low byte to E4h for TAPIN.
PATTERNS = [
    ("stub of TAPION", re.compile(rb"\x11\xE1\x00\xD5\x11\xD9\xCD\xD5|\x21\xE1\x00\xE5\x21\xD9\xCD\xE5"), 2),
    ("call of TAPION", re.compile(rb"\xCD\xE1\x00"), 2),
    ("call of TAPIN", re.compile(rb"\xCD\xE4\x00"), 2),
    ("call of TAPIOF", re.compile(rb"\xCD\xE7\x00"), 2),
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
ENTRY_PAGE = 0xFC


class Finding:
    """Code found at an offset: what it is, its bytes, and the patched bytes,
    or None when it is only listed."""

    def __init__(self, what, offset, old, new):
        self.what = what
        self.offset = offset
        self.old = old
        self.new = new

    def line(self, place):
        """The finding in a patch line's form, after its place."""
        text = f"{place}:{self.offset:04X} {self.old.hex(' ').upper()}"
        if self.new is not None:
            text += f" > {self.new.hex(' ').upper()}"
        return f"{text}  {self.what}"


def find(data):
    """The findings in data, by offset."""
    findings = []
    for what, pattern, patch_at in PATTERNS:
        for match in pattern.finditer(data):
            old = match.group()
            new = None
            if patch_at is not None:
                new = bytearray(old)
                new[patch_at] = ENTRY_PAGE
                new = bytes(new)
            findings.append(Finding(what, match.start(), old, new))
    return sorted(findings, key=lambda f: f.offset)


def patch(data, findings):
    """Writes the patched bytes of the findings into data, a bytearray."""
    for f in findings:
        if f.new is not None:
            data[f.offset:f.offset + len(f.new)] = f.new


def report(ram, tape):
    """scan.txt's text, from [(place, findings)] for the RAM pages and for the
    unread tape."""
    lines = ["# The scan's findings (docs/DESIGN.md, Scan), in patch line form.",
             "# In the RAM pages, patched, except the readers, which are only listed:"]
    lines += [f.line(place) for place, findings in ram for f in findings]
    lines += ["# In the unread blocks, not patched: a patch line there must also fix",
              "# the block's sum, when its loader checks one:"]
    lines += [f.line(place) for place, findings in tape for f in findings]
    return "\n".join(lines) + "\n"
