# The capture's subslot POKE patch (docs/internals/patches.md, The subslot POKE patch).
# tools/patches/subpoke.py puts its setting before this file:
#   ::subpoke  each POKE &HFFFF,&HAA or POKE -1,168 in the tape files, as
#              {side offset kind value}, where offset is its value's, kind is
#              H for two hex digits, D for three decimal digits and T for a
#              tokenized byte, and value is 170 or 168

# A value's bytes on the tape, by its kind.
proc subpoke_bytes {kind value} {
    switch $kind {
        H { binary scan [format %02X $value] cu* bytes }
        D { binary scan [format %03d $value] cu* bytes }
        T { set bytes [list $value] }
    }
    return $bytes
}

# Step 3's part, before the load command. The POKE writes AAh to the subslot
# register of page 3's slot, which selects subslot 2 in every page, or A8h,
# which selects it in pages 1 to 3 and subslot 0 in page 0. Where BASIC's RAM
# is in another subslot, the POKE takes the RAM away from under the program.
# So each POKE gets that subslot in the same pages as its value: in every
# page, as step 2 sets the register, or in pages 1 to 3. In the main ROM's
# slot, as on the SX-2 with its Extra-Mapper on, the RAM's subslot in pages 0
# and 1 would take BASIC away, so the POKE gets it in pages 2 and 3 only, and
# subslot 0 in pages 0 and 1, as BASIC has them. A slot that is not
# expanded has RAM at FFFFh, and a RAM in subslot 2 is what the POKE expects,
# so those tapes keep their bytes. The capture stops with the patches, and
# capture.py runs it again on the patched tape, where no POKE has its old
# value.
proc subpoke_start {} {
    if {![llength $::subpoke]} return
    set ps [expr {([debug read ioports 0xA8] >> 6) & 3}]
    if {![expanded $ps]} return
    set ss [expr {([subslot_reg $ps] >> 6) & 3}]
    if {$ss == 2} return
    set rom [expr {$ps == ([exptbl 0] & 3)}]
    set lines [lmap form $::subpoke {
        lassign $form side offset kind value
        patch_line $side $offset [subpoke_bytes $kind $value] \
            [subpoke_bytes $kind [expr {$ss * ($rom ? 0x50 : ($value == 0xAA ? 0x55 : 0x54))}]]
    }]
    stop_with_patch $lines "the tape's BASIC program selects subslot 2 with a POKE to FFFFh: patched to the RAM's subslot"
}
hook start subpoke_start
