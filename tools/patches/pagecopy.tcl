# The capture's page copy patch (docs/INTERNALS.md, The page copy patch).
# tools/patches/pagecopy.py puts its setting before this file, which follows
# slots.tcl: ::pagecopy holds each form in the tape files, as {side offset bytes
# copy subslots sum value}, where bytes is the form's bytes as hex, copy is 23
# or 31, subslots is 1 when the loader also copies the subslot register's
# fields, sum is the offset of its block's sum byte, or -1, and value is that
# byte.

# Whether slot ps is fit for page: it holds RAM there, by the slot map, or it is
# expanded and the loader copies its subslots as well.
proc pagecopy_fit {ps page subslots} {
    expr {$ps in $::ram($page) || ($subslots && $::st(sub$ps) >= 0)}
}

# The slot for page that a copy from slot ps gives: ps when it is fit, or else
# the slot map's replacement for page, or -1.
proc pagecopy_slot {ps page subslots} {
    if {[pagecopy_fit $ps $page $subslots]} { return $ps }
    return [lindex $::slots($page) 1]
}

# Step 3's part, before the load command, after the slot map: each form that
# copies a slot that is not fit for its page gets a patch that loads the value,
# and its block's sum byte gets the patch's difference. The capture stops with
# the patches, and capture.py runs it again on the patched tape.
proc pagecopy_start {} {
    set a8 $::st(a8)
    set p2 [expr {($a8 >> 4) & 3}]
    set p3 [expr {($a8 >> 6) & 3}]
    set lines {}
    array unset sums
    foreach form $::pagecopy {
        lassign $form side offset old copy subslots sum value
        set length [expr {[string length $old] / 2}]
        if {$copy == 23} {
            if {[pagecopy_fit $p2 0 $subslots] && [pagecopy_fit $p3 1 $subslots]} continue
            set s0 [pagecopy_slot $p2 0 $subslots]
            set s1 [pagecopy_slot $p3 1 $subslots]
            if {$s0 < 0 || $s1 < 0} continue
            # LD A,n: the value with the copy's slots in pages 0 and 1, and
            # BASIC's in pages 2 and 3, then NOPs.
            set new [list 0x3E [expr {$s0 | ($s1 << 2) | ($a8 & 0xF0)}]]
        } else {
            if {[pagecopy_fit $p3 1 $subslots]} continue
            set s1 [lindex $::slots(1) 1]
            if {$s1 < 0} continue
            # AND 0F3h / OR n: page 1's bits set to the slot, then NOPs.
            set new [list 0xE6 0xF3 0xF6 [expr {$s1 << 2}]]
        }
        while {[llength $new] < $length} { lappend new 0 }
        binary scan [binary format H* $old] cu* bytes
        lappend lines [patch_line $side $offset $bytes $new]
        if {$sum >= 0} {
            set key "$side $sum"
            if {![info exists sums($key)]} { set sums($key) [list $value $value] }
            lassign $sums($key) before after
            set after [expr {($after + [tcl::mathop::+ {*}$new] - [tcl::mathop::+ {*}$bytes]) & 0xFF}]
            set sums($key) [list $before $after]
        }
    }
    foreach key [array names sums] {
        lassign $key side sum
        lassign $sums($key) before after
        if {$before == $after} continue
        lappend lines [patch_line $side $sum [list $before] [list $after]]
    }
    if {[llength $lines]} {
        stop_with_patch $lines "the tape's code copies a slot that is not fit for page 0 or 1: patched"
    }
}
hook start pagecopy_start
