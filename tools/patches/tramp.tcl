# The capture's trampoline patch (docs/internals/patches.md, The trampoline patch).
# tools/patches/tramp.py puts its settings before this file:
#   ::tramp       each builder in the tape files, as {side offset}
#   ::tramp_old   the builder's bytes
#   ::tramp_new   by "<ROM's subslot>,<RAM's subslot>", the patched builder's
#                 bytes

# Step 3's part, before the load command. The trampoline selects slot 0 in page
# 0 by the slot register alone, for TAPION in the main ROM. Where the main ROM's
# slot is expanded and BASIC's RAM for page 3 is in another subslot of that
# slot, which also holds RAM in page 0, the game's RAM there hides the ROM from
# the slot register, and the trampoline calls the game's RAM: the SX-2 with its
# Extra-Mapper on has the ROM in 0-0 and the RAM in 0-1. There the patched
# trampoline selects the ROM's subslot in page 0 and the RAM's in the other
# pages for the call, and then writes back the subslot register's value from
# when the builder ran. Every other machine keeps the tape's bytes. The capture
# stops with the patches, and capture.py runs it again on the patched tape,
# where the builder no longer occurs.
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
