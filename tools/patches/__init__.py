"""The automatic patches (docs/INTERNALS.md, The tools' code): the changes that the
tools make to a game without a line in its game file, one module for each kind.

Each kind has two functions. find(data, context) returns the kind's findings in
data, for the scan. tcl(side1, side2) returns the kind's Tcl for the capture,
for the tape files' bytes: its settings and its Tcl file. A kind that works in
only one of the two returns nothing in the other. KINDS lists the kinds.
"""
import collections

from . import pagecopy, ramsearch, slots, t0stub, tapecode

# The kinds, in the order that the scan runs them and that the capture loads
# their Tcl. slots comes before ramsearch and pagecopy, because its Tcl makes
# the slot map and holds the procedures that the other two use.
KINDS = [tapecode, slots, t0stub, ramsearch, pagecopy]

# What a search depends on: the entry page, at whose E1h to F3h the entries
# are, or None when the image has no entries, the capture's slot map or None,
# whether the image has the tape service, and whether the data is a RAM page,
# where the restorer can fill in a byte, and not a block of the tape.
Context = collections.namedtuple("Context", "entry_page slots tape ram", defaults=(None, None, True, True))


def find(data, context):
    """The findings of every kind in data, by offset."""
    return sorted((f for kind in KINDS for f in kind.find(data, context)), key=lambda f: f.offset)


def tcl(side1, side2):
    """The Tcl of every kind for the capture, for the tape files' bytes as the
    capture plays them."""
    return "".join(kind.tcl(side1, side2) for kind in KINDS)


def patch(data, findings):
    """Writes the patched bytes of the findings into data, a bytearray."""
    for f in findings:
        if f.new is not None:
            data[f.offset:f.offset + len(f.new)] = f.new


def report(ram, unread):
    """scan.txt's text, from [(place, findings)] for the RAM pages and for the
    unread tape."""
    lines = ["# The scan's findings (docs/INTERNALS.md, Scan), in patch line form.",
             "# In the RAM pages, patched where the line has new bytes after >, otherwise only listed:"]
    lines += [f.line(place) for place, findings in ram for f in findings]
    lines += ["# In the unread blocks, not patched: a patch line there must also fix",
              "# the block's sum, when its loader checks one:"]
    lines += [f.line(place) for place, findings in unread for f in findings]
    return "\n".join(lines) + "\n"
