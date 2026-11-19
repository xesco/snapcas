# The capture's hook fill patch (docs/INTERNALS.md, The hook fill patch).
# tools/patches/hookfill.py puts its settings before this file:
#   ::hookfill      each fill in the tape files that goes past FFC9h, as
#                   {side offset bytes}, where bytes is its count as hex
#   ::hookfill_new  the bytes of the patch: the count that ends at FFC9h

# Step 3's part, before the load command. An MSX2's BIOS keeps its copies of
# VDP registers 8 to 23 in FFE7h to FFF6h, which an MSX1 leaves unused, and an
# MSX2+'s sub-ROM writes them to the VDP when it sets a screen. A fill of the
# hooks with RET that goes past FFC9h writes C9h there, and register 15 then
# selects status register 9, so the BIOS's interrupt handler never reads the
# interrupt off and runs inside itself. So on an MSX2 each fill gets the count
# that ends it at FFC9h. The capture stops with the patches, and capture.py
# runs it again on the patched tape, where no fill has its old count. An MSX1
# keeps the fill.
proc hookfill_start {} {
    if {!$::run(msx2) || ![llength $::hookfill]} return
    set lines [lmap form $::hookfill {
        lassign $form side offset old
        binary scan [binary format H* $old] cu* bytes
        patch_line $side $offset $bytes $::hookfill_new
    }]
    stop_with_patch $lines "the tape fills the hooks with RET past FFC9h, over an MSX2's copies of VDP registers: patched to end at FFC9h"
}
hook start hookfill_start
