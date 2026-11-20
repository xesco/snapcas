# The capture's trampoline patch (docs/internals/patches.md, The trampoline patch).
# tools/patches/tramp.py puts its settings before this file:
#   ::tramp       each builder in the tape files, as {side offset}
#   ::tramp_old   the builder's bytes
#   ::tramp_new   by "<ROM's subslot>,<RAM's subslot>", the patched builder's
#                 bytes

# Step 3: when main ROM and BASIC RAM share an expanded slot 0 (e.g. SX-2
# Extra-Mapper), rewrite the FC9Ah tape trampoline to switch slot 0's subslot
# register around TAPION and restore the caller's original subslot.
proc tramp_start {} {
    if {![llength $::tramp]} return
    set rom [exptbl 0]
    if {!($rom & 0x80)} return
    set ps [expr {$rom & 3}]
    if {(([debug read ioports 0xA8] >> 6) & 3) != $ps} return
    set rom_sub [expr {($rom >> 2) & 3}]
    set ram_sub [expr {([subslot_reg $ps] >> 6) & 3}]
    if {$ram_sub == $rom_sub || ![with_slot $ps $ram_sub 0 { is_ram 0 }]} return
    set new $::tramp_new($rom_sub,$ram_sub)
    set lines [lmap place $::tramp {
        lassign $place side offset
        patch_line $side $offset $::tramp_old $new
    }]
    stop_with_patch $lines "the tape's TAPION trampoline selects the ROM in page 0 by the slot register alone, where slot $ps-$ram_sub's RAM hides it: patched to write the subslot register"
}
hook start tramp_start
