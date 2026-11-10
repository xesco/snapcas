# The capture's watch on the slot register (docs/INTERNALS.md, Slot patches).
# tools/patches/slots.py puts its settings before this file:
#   ::slotcode(load)     the bytes of LD A,n before n
#   ::slotcode(out)      the bytes after n of the form that writes the register
#                        itself: OUT (0A8h),A
#   ::slotcode(wslreg)   the bytes after n of the form that calls the BIOS's
#                        WSLREG: CALL 013Bh
#   ::slotcode(indirect) the opcode of LD A,(nn)

# Step 3's part: the slot map, and the tape files that a patch must occur in.
proc slot_start {} {
    slot_map
    set ::run(tape1) [read_binary $::S(tape)]
    set ::run(tape2) [expr {$::S(side2tape) eq "" ? "" : [read_binary $::S(side2tape)]}]
}
hook start slot_start

# The slot map, at step 3: for each page, the primary slots that hold nothing
# there and the slot that replaces them in a slot register value, or -1, and in
# ::ram, the primary slots that hold RAM there. A
# slot holds nothing in a page when it is not expanded, does not hold RAM there,
# and its first 256 bytes there read FFh. An expanded slot holds RAM in a page
# when the subslot that its register selects there holds RAM.
proc slot_map {} {
    set a8 [debug read ioports 0xA8]
    set ffs [string repeat "\xff" 256]
    foreach page {0 1 2 3} {
        set empty {}
        set ram {}
        foreach ps {0 1 2 3} {
            if {$::st(sub$ps) >= 0} {
                set ss [expr {($::st(sub$ps) >> (2 * $page)) & 3}]
                if {[with_slot $ps $ss $page { is_ram $page }]} { lappend ram $ps }
            } elseif {[with_slot $ps x $page { is_ram $page }]} {
                lappend ram $ps
            } elseif {[with_slot $ps x $page { debug read_block memory [expr {$page * 0x4000}] 256 }] eq $ffs} {
                lappend empty $ps
            }
        }
        set basic [expr {($a8 >> (2 * $page)) & 3}]
        set page2 [expr {($a8 >> 4) & 3}]
        if {$page >= 2} {
            set with $basic
        } elseif {![llength $ram]} {
            set with -1
        } elseif {$page2 in $ram} {
            set with $page2
        } else {
            set with [lindex [lsort -integer $ram] 0]
        }
        set ::slots($page) [list $empty $with]
        set ::ram($page) $ram
    }
    set lines [list \
        "# For each page: the primary slots that hold nothing there, and the slot" \
        "# that replaces them in a slot register value, or -1 (INTERNALS.md, Slot patches)."]
    foreach page {0 1 2 3} {
        lassign $::slots($page) empty with
        lappend lines "page $page empty [expr {[llength $empty] ? [join $empty ,] : "-"}] with $with"
    }
    write_lines slots.txt $lines
}

# The slot register value with each field that names a slot that holds nothing
# replaced, where its page has a replacement.
proc slot_fix {value} {
    foreach page {0 1 2 3} {
        lassign $::slots($page) empty with
        set shift [expr {2 * $page}]
        if {(($value >> $shift) & 3) in $empty && $with >= 0} {
            set value [expr {($value & ~(3 << $shift) & 0xFF) | ($with << $shift)}]
        }
    }
    return $value
}

proc names_nothing {value} {
    foreach page {0 1 2 3} {
        if {(($value >> (2 * $page)) & 3) in [lindex $::slots($page) 0]} { return 1 }
    }
    return 0
}

# Whether the LD A,n at address, read with the slot register at a8, can be the
# operand of an instruction that loads A with the value after it: LD A,(nn),
# whose address ends with the 3Eh and the value, as Knight Orc's LD A,(EF3Eh).
# The scan skips a 3Eh after any opcode with an operand (patches/slots.py,
# in_operand), but the watch knows that A holds the value after the 3Eh, which
# after another instruction holds it only by chance.
proc in_operand {a8 address} {
    binary scan [read_with $a8 [expr {$address - 1}] 1] cu one
    expr {$one == $::slotcode(indirect)}
}

# The code that wrote value to the slot register, read with the slot register
# before the write, as {address length form}, or "" when it is neither form:
# out, LD A,n / OUT (0A8h),A, whose last byte is the last byte of the OUT at PC,
# or wslreg, LD A,n / CALL 013Bh, whose OUT is in the main ROM and whose last
# byte is the byte before the return address on the stack. Code whose LD A,n
# can be the operand of an LD A,(nn) is neither.
proc slot_code {value before} {
    set pc [reg pc]
    set ends [list out [expr {$pc + 2}]]
    if {[in_main_rom $pc $before]} {
        binary scan [read_with $before [reg sp] 2] su ret
        lappend ends wslreg $ret
    }
    foreach {form end} $ends {
        set bytes [binary format c* [concat $::slotcode(load) $value $::slotcode($form)]]
        set address [expr {($end - [string length $bytes]) & 0xFFFF}]
        if {[read_with $before $address [string length $bytes]] eq $bytes && ![in_operand $before $address]} {
            return [list $address [string length $bytes] $form]
        }
    }
    return ""
}
# Whether code at pc, with the slot register at a8, is in the main ROM.
proc in_main_rom {pc a8} { expr {$pc < 0x4000 && ($a8 & 3) == ([exptbl 0] & 3)} }

# Each place of bytes in the tape files, as {side offset}.
proc tape_find {bytes} {
    set found {}
    foreach side {1 2} data [list $::run(tape1) $::run(tape2)] {
        set i 0
        while {[set j [string first $bytes $data $i]] >= 0} {
            lappend found [list $side $j]
            set i [expr {$j + 1}]
        }
    }
    return $found
}

# The lines of a patch of code, which slot_code found, that makes its value
# new: the capture looks for the code in the tape files, read with the slot
# register before the write, with the 8 bytes before it, or else with the 8
# bytes after it, at each place where those bytes occur, or else the code
# alone, when it occurs once. It returns a patch line for each place, or none
# when there is no code, the code is not on the tape, or new is its value.
proc patch_lines {code before new} {
    if {$code eq ""} { return {} }
    lassign $code address length
    binary scan [read_with $before $address $length] cu* bytes
    set n [llength $::slotcode(load)]
    if {[lindex $bytes $n] == $new} { return {} }
    # The code with the 8 bytes before it; else after it, for a loader that
    # copies a routine without the bytes before it; else alone, for a routine
    # that writes into the bytes next to the code. A tape can hold a routine
    # more than once, and each copy gets the patch.
    set found {}
    foreach {from count at once} [list \
            [expr {$address - 8}] [expr {$length + 8}] 8 0 \
            $address [expr {$length + 8}] 0 0 \
            $address $length 0 1] {
        set found [tape_find [read_with $before $from $count]]
        if {[llength $found] && (!$once || [llength $found] == 1)} break
        set found {}
    }
    lmap place $found {
        lassign $place side offset
        patch_line $side [expr {$offset + $at}] $bytes [lreplace $bytes $n $n $new]
    }
}

# Step 4's watch on the slot register, for each value written, with the value
# before it. A value that names a slot that holds nothing gets a patch of its
# code that replaces those slots (slot_fix), or else a line in the log, for a
# patch line by hand. The log holds each pair of an address and a value once,
# up to 16 pairs. It leaves out a write from the main ROM, which is the BIOS's
# own, as its slot calls make for each slot that a loader's search tries,
# unless the code is a call of WSLREG, which the log names by its address.
proc slot_watch {value before} {
    if {![names_nothing $value]} return
    set pc [reg pc]
    set new [slot_fix $value]
    set code [slot_code $value $before]
    set lines [patch_lines $code $before $new]
    if {[llength $lines]} {
        stop_with_patch $lines "the slot register write of [hex 2 $value] at PC [hex 4 $pc] names a slot that holds nothing: patched to [hex 2 $new]"
    }
    set where "at PC [hex 4 $pc]"
    if {[in_main_rom $pc $before]} {
        if {[lindex $code 2] ne "wslreg"} return
        set where "by the WSLREG call at [hex 4 [lindex $code 0]]"
    }
    if {[dict exists $::run(slot_logs) "$where $value"] || [dict size $::run(slot_logs)] >= 16} return
    dict set ::run(slot_logs) "$where $value" 1
    decide "the slot register write of [hex 2 $value] $where names a slot that holds nothing, for a patch line"
}
set ::run(slot_logs) {}
hook slot_write slot_watch
