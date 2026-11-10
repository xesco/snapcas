"""The RAM search patch (docs/INTERNALS.md, The RAM search patch): a loader's
search for RAM that selects the slot it finds in page 3, where the loader runs.
patches/ramsearch.tcl is the capture's watch. The kind works only in the
capture, so its find() finds nothing."""
import msx

# LD A,B / DEC A / CP 4 / JR C,+2 / SET 7,A: the slot ID from the search's
# count, marked as an expanded slot's from 4 up. The patch writes two NOPs over
# SET 7,A.
SEARCH = bytes.fromhex("78 3D FE 04 38 02 CB FF")
AT = 6
NEW = bytes.fromhex("00 00")


def find(data, context):
    """Nothing: the loader that the kind patches has finished by the
    snapshot."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: the search's bytes, the offset of the
    patch in them, and the bytes before and after the patch, as
    ramsearch.tcl's settings, and ramsearch.tcl. The capture looks for the
    search in the tape files itself."""
    return (f"set ::ramsearch [binary format H* {SEARCH.hex()}]\n"
            f"set ::ramsearch_at {AT}\n"
            f"set ::ramsearch_old {msx.tcl_bytes(SEARCH[AT:])}\n"
            f"set ::ramsearch_new {msx.tcl_bytes(NEW)}\n"
            + msx.tcl("patches/ramsearch.tcl"))
