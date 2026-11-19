"""The ENASLT copy patch (docs/INTERNALS.md, The ENASLT copy patch): a loader's
copy of the BIOS's ENASLT that writes the subslot register with AND B, the old
slot register, where the BIOS has AND H, the mask of the other pages, and the
same loaders' selection of BASIC's ROM in page 1 by EXPTBL's entry for slot 1.
patches/enaslt.tcl patches both at step 3, on every machine. The kind works
only in the capture, so its find() finds nothing."""
import msx

# The copy's write of the subslot register: LD A,(0FFFFh) / CPL / LD L,A /
# AND B / OR D / LD (0FFFFh),A. The patch makes AND B, A0h, the BIOS's AND H,
# A4h. B holds the slot register's old value, which keeps the other pages'
# subslots only by chance: on a machine whose RAM is in slot 3, B's bits of
# slot 3 are 1s where the pages select it.
SUBSLOT = bytes.fromhex("3A FF FF 2F 6F A0 B2 32 FF FF")
SUBSLOT_NEW = bytes.fromhex("3A FF FF 2F 6F A4 B2 32 FF FF")
# The same loaders give page 1 back to BASIC with LD H,40h / LD A,(0FCC2h) and
# their ENASLT copy: FCC2h is EXPTBL's entry for slot 1, 00h, which selects slot
# 0 by the slot register alone. The patch reads FCC1h, the main ROM's slot ID,
# which also gives the subslot when slot 0 is expanded. Where slot 0 is not
# expanded both entries hold 00h.
PAGE1 = bytes.fromhex("26 40 3A C2 FC")
PAGE1_NEW = bytes.fromhex("26 40 3A C1 FC")


def places(data):
    """The offsets in data of the forms, as (offset, old, new): the subslot
    writes, and the page 1 selections when data holds a subslot write."""
    found = []
    for old, new, only_with_copy in ((SUBSLOT, SUBSLOT_NEW, False), (PAGE1, PAGE1_NEW, True)):
        if only_with_copy and SUBSLOT not in data:
            continue
        at = data.find(old)
        while at >= 0:
            found.append((at, old, new))
            at = data.find(old, at + 1)
    return sorted(found)


def find(data, context):
    """Nothing: the loader that the kind patches has finished by the
    snapshot."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each form in the tape files, as {side
    offset old new} with the bytes as numbers, as enaslt.tcl's setting, and
    enaslt.tcl."""
    found = [f"{{{side} {offset} {msx.tcl_bytes(old)} {msx.tcl_bytes(new)}}}"
             for side, data in ((1, side1), (2, side2)) for offset, old, new in places(data)]
    return f"set ::enaslt {{{' '.join(found)}}}\n" + msx.tcl("patches/enaslt.tcl")
