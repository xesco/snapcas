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

# Step 3: rewrite BASIC POKE &HFFFF,&HAA / &HA8 to BASIC's actual RAM subslot
# when page 3 is expanded and not in subslot 2 (preserving pages 0-1 in slot 0
# so BASIC stays mapped). Stops capture so capture.py retries on the patched tape.
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
