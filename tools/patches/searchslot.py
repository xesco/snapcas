"""The search slot patch (docs/INTERNALS.md, The search slot patch): a loader's
RAM search that finds the slot of page 1's RAM, and then stores for page 1 the
slot of BASIC's page 2. patches/searchslot.tcl patches each search's end at step
3, on every machine. The kind works only in the capture, so its find() finds
nothing."""
import msx

# The search's start: DI / IN A,(0A8h) / LD B,A / EX AF,AF' / LD A,B / AND 30h /
# LD B,A / IN A,(0A8h) / AND 0F0h / DEC A. It tests page 0's slots and then page
# 1's, and leaves the value with the RAM that it found in C.
START = bytes.fromhex("F3 DB A8 47 08 78 E6 30 47 DB A8 E6 F0 3D")
# The search's end, DISTANCE bytes after its start: IN A,(0A8h) / LD C,A / SRL A
# / SRL A / AND 0Ch / OR C, BASIC's slot register value with page 2's slot in page
# 1, which the next LD (nn),A stores.
END = bytes.fromhex("DB A8 4F CB 3F CB 3F E6 0C B1 32")
DISTANCE = 144
# LD A,C / AND 0Ch / LD C,A / IN A,(0A8h) / AND 0F3h / OR C / NOP: BASIC's value
# with page 1's slot from the search. The patch leaves the LD (nn),A alone.
OLD = END[:10]
NEW = bytes.fromhex("79 E6 0C 4F DB A8 E6 F3 B1 00")


def ends(data):
    """The offsets in data of the ends of the searches."""
    found = []
    at = data.find(START)
    while at >= 0:
        end = at + DISTANCE
        if data[end:end + len(END)] == END:
            found.append(end)
        at = data.find(START, at + 1)
    return found


def find(data, context):
    """Nothing: the loader that the kind patches has finished by the
    snapshot."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each search's end in the tape files, as
    {side offset}, and the patch's bytes, as searchslot.tcl's settings, and
    searchslot.tcl."""
    found = [f"{{{side} {offset}}}" for side, data in ((1, side1), (2, side2)) for offset in ends(data)]
    return (f"set ::searchslot {{{' '.join(found)}}}\n"
            f"set ::searchslot_old {msx.tcl_bytes(OLD)}\n"
            f"set ::searchslot_new {msx.tcl_bytes(NEW)}\n"
            + msx.tcl("patches/searchslot.tcl"))
