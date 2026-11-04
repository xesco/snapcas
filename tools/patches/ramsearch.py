"""The RAM search patch (docs/INTERNALS.md, The RAM search patch): a loader's
search for RAM that selects the slot it finds in page 3, where the loader runs.
patches/ramsearch.tcl is the capture's watch. The kind works only in the
capture, so it has no find()."""

# LD A,B / DEC A / CP 4 / JR C,+2 / SET 7,A: the slot ID from the search's
# count, marked as an expanded slot's from 4 up. The patch writes two NOPs over
# SET 7,A.
SEARCH = bytes.fromhex("78 3D FE 04 38 02 CB FF")
AT = 6
NEW = bytes.fromhex("00 00")


def tcl_settings():
    """The Tcl that gives ramsearch.tcl the search's bytes, the offset of the
    patch in them, and the bytes before and after the patch."""
    return (f"set ::ramsearch [binary format H* {SEARCH.hex()}]\n"
            f"set ::ramsearch_at {AT}\n"
            f"set ::ramsearch_old {{{SEARCH[AT:].hex(' ').upper()}}}\n"
            f"set ::ramsearch_new {{{NEW.hex(' ').upper()}}}\n")
