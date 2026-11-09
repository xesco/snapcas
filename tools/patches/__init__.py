"""The automatic patches (docs/INTERNALS.md, The tools' code): the changes that the
tools make to a game without a line in its game file, one module for each kind.

Each kind has find(data, context), which returns its findings in data. KINDS
lists them in the order that the scan runs them.
"""
import collections

from . import pagecopy, ramsearch, slots, t0stub, tape  # noqa: F401

KINDS = [tape, slots, t0stub]

# The page of the entries, E1h to F3h in it, the capture's slot map or None,
# whether the image has the tape service, and in the mode without a part in
# page 3, the slot register value that selects T0 in page 0, or None.
Context = collections.namedtuple("Context", "page slots tape t0", defaults=(tape.ENTRY_PAGE, None, True, None))

# The findings that the scan also patches when it patches no others.
ALWAYS = (slots.SLOT_VALUE, t0stub.T0_STUB)


def find(data, context=Context()):
    """The findings of every kind in data, by offset."""
    return sorted((f for kind in KINDS for f in kind.find(data, context)), key=lambda f: f.offset)


def patch(data, findings):
    """Writes the patched bytes of the findings into data, a bytearray."""
    for f in findings:
        if f.new is not None:
            data[f.offset:f.offset + len(f.new)] = f.new


def report(ram, unread):
    """scan.txt's text, from [(place, findings)] for the RAM pages and for the
    unread tape."""
    lines = ["# The scan's findings (docs/INTERNALS.md, Scan), in patch line form.",
             "# In the RAM pages, patched, except the readers, which are only listed:"]
    lines += [f.line(place) for place, findings in ram for f in findings]
    lines += ["# In the unread blocks, not patched: a patch line there must also fix",
              "# the block's sum, when its loader checks one:"]
    lines += [f.line(place) for place, findings in unread for f in findings]
    return "\n".join(lines) + "\n"
