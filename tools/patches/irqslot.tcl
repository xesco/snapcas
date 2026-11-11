# The capture's interrupt slot patch (docs/INTERNALS.md, The interrupt slot
# patch). tools/patches/irqslot.py puts its settings before this file:
#   ::irqslot      each handler in the tape files, as {side offset bytes}, where
#                  bytes is its LD A,(copy) as hex
#   ::irqslot_new  the bytes of the patch: IN A,(0A8h) / NOP

# Step 3's part, before the load command. An MSX2's BIOS selects the sub-ROM in
# page 0 during some calls, and the game's copy does not hold that value. So
# on an MSX2 each handler gets the patch, which reads the slot register
# itself. The capture stops with the patches, and capture.py runs it again on
# the patched tape, where no handler has its old bytes.
proc irqslot_start {} {
    if {!$::run(msx2) || ![llength $::irqslot]} return
    set lines [lmap form $::irqslot {
        lassign $form side offset old
        binary scan [binary format H* $old] cu* bytes
        patch_line $side $offset $bytes $::irqslot_new
    }]
    stop_with_patch $lines "the tape's interrupt handler writes the slot register from the game's copy of it: patched to read the register"
}
hook start irqslot_start
