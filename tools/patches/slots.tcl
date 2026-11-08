# The capture's watch on the slot register (docs/INTERNALS.md, Slot patches).
# tools/capture.py loads it after capture.tcl.

# Writes a found patch's lines to newpatch.txt, which stops the capture so
# that it runs again on the patched tape (INTERNALS.md, Slot patches, The RAM
# search patch). ramsearch.tcl and pagecopy.tcl, loaded after this file, write
# there too. openMSX's exit lets the watches of the same write run on, so
# ::newpatch tells them that a patch is written.
proc write_newpatch {lines} {
    set ::newpatch 1
    set f [open [file join $::S(snap) newpatch.txt] w]
    foreach line $lines { puts $f $line }
    close $f
}

# Step 3's part: the slot map, and the tape files that a patch must occur in.
proc slot_start {} {
    slot_map
    set ::tape1 [read_binary $::S(tape)]
    set ::tape2 [expr {$::S(side2tape) eq "" ? "" : [read_binary $::S(side2tape)]}]
}

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
    set f [open [file join $::S(snap) slots.txt] w]
    puts $f "# For each page: the primary slots that hold nothing there, and the slot"
    puts $f "# that replaces them in a slot register value, or -1 (INTERNALS.md, Slot patches)."
    foreach page {0 1 2 3} {
        lassign $::slots($page) empty with
        puts $f "page $page empty [expr {[llength $empty] ? [join $empty ,] : "-"}] with $with"
    }
    close $f
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

# Whether the 3Eh at address, read with the slot register at a8, can be the
# operand of an instruction that loads A with the value after it: LD A,(nn),
# 3Ah, whose address ends with the 3Eh and the value, as Knight Orc's
# LD A,(EF3Eh). The scan skips a 3Eh after any opcode with an operand
# (patches/slots.py, in_operand), but the watch knows that A holds the value
# after the 3Eh, which after another instruction holds it only by chance.
proc in_operand {a8 address} {
    binary scan [read_with $a8 [expr {$address - 1}] 1] cu one
    expr {$one == 0x3A}
}

# The code that wrote value to the slot register, read with the slot register
# before the write, as {address length}, or "" when it is not one of the two
# forms: LD A,n / OUT (0A8h),A, whose OUT is at PC, or LD A,n / CALL 013Bh,
# whose OUT is in the main ROM and whose return address is on the stack. Code
# whose 3Eh can be the operand of an LD A,(nn) is neither.
proc slot_code {value before} {
    set pc [reg pc]
    if {[read_with $before [expr {$pc - 2}] 4] eq [binary format c4 [list 0x3E $value 0xD3 0xA8]]
        && ![in_operand $before [expr {$pc - 2}]]} {
        return [list [expr {($pc - 2) & 0xFFFF}] 4]
    }
    if {$pc < 0x4000 && ($before & 3) == ([exptbl 0] & 3)} {
        binary scan [read_with $before [reg sp] 2] su ret
        if {[read_with $before [expr {$ret - 5}] 5] eq [binary format c5 [list 0x3E $value 0xCD 0x3B 0x01]]
            && ![in_operand $before [expr {$ret - 5}]]} {
            return [list [expr {($ret - 5) & 0xFFFF}] 5]
        }
    }
    return ""
}

# Each place of bytes in the tape files, as {side offset}.
proc tape_find {bytes} {
    set found {}
    foreach side {1 2} data [list $::tape1 $::tape2] {
        set i 0
        while {[set j [string first $bytes $data $i]] >= 0} {
            lappend found [list $side $j]
            set i [expr {$j + 1}]
        }
    }
    return $found
}

# A patch of the code that wrote value to the slot register, read with the
# slot register before the write, that makes the value new: the capture looks
# for the code in the tape files, with the 8 bytes before it, or else with the 8
# bytes after it, at each place where those bytes occur, or else the code alone,
# when it occurs once. When it finds the code, it writes a patch of each place
# to newpatch.txt and returns 1, and the caller stops the capture, which
# capture.py runs again. It returns 0 when the code is not one of the forms or
# is not on the tape.
proc patch_code {value before new} {
    set code [slot_code $value $before]
    if {$code eq "" || $new == $value} { return 0 }
    lassign $code address length
    # The code with the 8 bytes before it; else after it, for a loader that
    # copies a routine without the bytes before it; else alone, for a routine
    # that writes into the bytes next to the code. A tape can hold a routine
    # more than once, and each copy gets the patch.
    set found {}
    foreach {from bytes at once} [list \
            [expr {$address - 8}] [expr {$length + 8}] 8 0 \
            $address [expr {$length + 8}] 0 0 \
            $address $length 0 1] {
        set found [tape_find [read_with $before $from $bytes]]
        if {[llength $found] && (!$once || [llength $found] == 1)} break
        set found {}
    }
    if {![llength $found]} { return 0 }
    binary scan [read_with $before $address $length] cu* bytes
    set patched [lreplace $bytes 1 1 $new]
    write_newpatch [lmap place $found {
        lassign $place side offset
        format "patch side%d:%X %s > %s" $side [expr {$offset + $at}] \
            [join [lmap b $bytes {format %02X $b}]] [join [lmap b $patched {format %02X $b}]]
    }]
    return 1
}

# Step 4's watch on the slot register, for each value written, with the value
# before it. A value that names a slot that holds nothing is logged, and its
# code gets a patch that replaces those slots (slot_fix).
proc slot_watch {value before} {
    if {[info exists ::newpatch] || ![names_nothing $value]} return
    set new [slot_fix $value]
    if {[patch_code $value $before $new]} {
        decide "the slot register write of [hex 2 $value] at PC [hex 4 [reg pc]] names a slot that holds nothing: patched to [hex 2 $new]"
        catch write_log
        quit
    }
    if {[incr ::slot_logs] <= 16} {
        decide "the slot register write of [hex 2 $value] at PC [hex 4 [reg pc]] names a slot that holds nothing, for a patch line"
    }
}
set ::slot_logs 0
