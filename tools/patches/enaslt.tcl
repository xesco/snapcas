# The capture's ENASLT copy patch (docs/internals/patches.md, The ENASLT copy patch).
# tools/patches/enaslt.py puts its setting before this file: ::enaslt holds
# each form in the tape files, as {side offset old new}.

# Step 3's part, before the load command: each form gets the patch on every
# machine, because the patched code is the BIOS's own and works wherever the
# loader runs. The capture stops with the patches, and capture.py runs it again
# on the patched tape, where the forms no longer occur.
proc enaslt_start {} {
    set lines {}
    foreach form $::enaslt {
        lassign $form side offset old new
        lappend lines [patch_line $side $offset $old $new]
    }
    if {[llength $lines]} {
        stop_with_patch $lines "the tape's copy of ENASLT writes the subslot register with AND B, not the BIOS's AND H: patched"
    }
}
hook start enaslt_start
