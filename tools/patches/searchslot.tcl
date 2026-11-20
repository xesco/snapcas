# The capture's search slot patch (docs/internals/patches.md, The search slot patch).
# tools/patches/searchslot.py puts its settings before this file: ::searchslot
# holds each search's end in the tape files, as {side offset}, and
# ::searchslot_old and ::searchslot_new the bytes that the patch replaces and
# writes.

# Step 3's part, before the load command: each search's end gets the patch on
# every machine, because the slot that the search found holds RAM in page 1
# wherever the search runs. Page 2's slot does not, when it is an expanded slot
# whose subslot register selects no RAM in page 1. The capture stops with the
# patches, and capture.py runs it again on the patched tape, where the end no
# longer occurs.
proc searchslot_start {} {
    set lines {}
    foreach form $::searchslot {
        lassign $form side offset
        lappend lines [patch_line $side $offset $::searchslot_old $::searchslot_new]
    }
    if {[llength $lines]} {
        stop_with_patch $lines "the tape's RAM search gives page 1 the slot of page 2, not the slot that it found: patched"
    }
}
hook start searchslot_start
