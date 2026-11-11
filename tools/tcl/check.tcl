# The check (docs/INTERNALS.md, Check), after memory.tcl's procedures, which it
# uses to read memory through the CPU's view. tools/check.py sets these:
#   ::C(report)   the report's file
#   ::C(restore)  the seconds that the restore may take, by the image's size
#   ::C(snap)     the snapshot folder
#   ::C(pages)    the number of RAM pages in it
#   ::C(kv)       the names and values of its state.txt
#   ::C(capreset) the seconds from the snapshot to the capture's first reset
#                 after it, or ""
#   ::C(state)    the start of the names of the check's savestates
#   ::C(name)     the image's name, which starts the restorer's messages
#   ::C(com)      the first 3 bytes of SNAPCAS.COM
#   ::C(stop)     the address of the restorer's stop_message and the 3 bytes
#                 there, or nothing without out/snapcas.sym
#   ::C(service), ::C(tail), ::C(free), ::C(patched), ::C(part), ::C(moved),
#   ::C(cpos), ::C(ended)
#                 build.txt's facts, under their names (tools/build.py,
#                 Image.facts)
#
# ::run(phase) is boot until SNAPCAS.COM's command is typed, restore until the
# tail's jump, refused when the restorer has stopped with a message, and play
# in the 60 seconds after the restore.

array set ::K $::C(kv)
# The tail (FORMATS.md, Tail): its address, and the offsets in it of its last
# byte, of the port of the worker's page's mapper register, and of its last
# instruction, the jump to the game, whose target follows the opcode.
lassign $::C(tail) ::tail(at) ::tail(last) ::tail(port) ::tail(jp)
# A value of the snapshot's state.txt, as a number.
proc want {name} { scan $::K($name) %x }
set ::diffs {}

proc note {msg} { if {[llength $::diffs] < 40} { lappend ::diffs $msg } }

proc write_report {} {
    set f [open $::C(report) w]
    if {[llength $::diffs] == 0} {
        puts $f "point 1: pass"
    } else {
        puts $f "point 1: fail"
        foreach d $::diffs { puts $f "  $d" }
    }
    close $f
}
# A point after point 1, with the lines of what failed it.
proc write_point {n lines} {
    set f [open $::C(report) a]
    puts $f [expr {[llength $lines] ? "point $n: fail" : "point $n: pass"}]
    foreach line $lines { puts $f "  $line" }
    close $f
}

# An error of a callback fails the point that the check is at, with the error
# in the report, and ends the check: point 1 until its lines are written, and
# then point 2, or the point that for_point names around the code of another.
set ::point 1
proc for_point {n body} {
    set before $::point
    set ::point $n
    uplevel 1 $body
    set ::point $before
}
proc script_failed {msg} {
    if {$::point == 1} {
        lappend ::diffs "check: $msg"
        write_report
    } else {
        write_point $::point [list "check: $msg"]
    }
    stop
}
# The check ends within DEADLINE emulated seconds of its start, whatever the
# machine does: the boot steps, the restore and the 60 seconds take far less.
# The deadline is 600 seconds for a restore that may take 120, and grows with
# the seconds that the restore of a large image may take.
set ::DEADLINE [expr {480 + $::C(restore)}]
later $::DEADLINE { error "the check did not end within $::DEADLINE seconds" }

# The screen's text on one line. DOS breaks a long line at LINLEN, the text
# width at F3B0h, in the middle of a word, so a row that is full to that width
# joins the next row without a space. The screen's rows start with a margin
# when LINLEN is less than the screen's width: the fewest spaces that start a
# row with text.
proc screen_line {} {
    set width [debug read memory 0xF3B0]
    set rows [split [screen] \n]
    set margin -1
    foreach row $rows {
        if {[string trim $row] eq ""} continue
        set n [expr {[string length $row] - [string length [string trimleft $row]]}]
        if {$margin < 0 || $n < $margin} { set margin $n }
    }
    set text ""
    foreach row $rows {
        set row [string trimright $row]
        append text [string trimleft $row]
        if {[string length $row] - $margin != $width} { append text " " }
    }
    string trim [regsub -all {\s+} $text { }]
}

# A breakpoint's condition: memory at address holds the bytes.
proc holds {address bytes} {
    set tests {}
    foreach b $bytes {
        lappend tests "\[debug read memory $address\] == $b"
        incr address
    }
    join $tests " && "
}

proc start_check {} {
    set ::run(phase) restore
    # EXPTBL and RAMAD3 at F344h, DOS's mapper's slot ID, read when
    # SNAPCAS.COM starts, while the system area is DOS's. On a machine whose
    # boot steps end before the BIOS has set EXPTBL, as the Sanyo PHC-28S's do,
    # it does not hold the slots yet when start_check runs. A start after the
    # restore is point 3's reboot into DOS.
    set ::dosslot 0
    set com [holds 0x0100 $::C(com)]
    debug set_bp 0x0100 $com {safe at_start}
    # The restorer stops with a message when it refuses the image
    # (src/snapcas.asm, stop_message), which ends point 1 at once.
    if {[llength $::C(stop)]} {
        debug set_bp [lindex $::C(stop) 0] "$com && [holds [lindex $::C(stop) 0] [lrange $::C(stop) 1 end]]" {safe at_stop}
    }
    # With the tape service, page 0's bits of the slot register, of DOS's
    # mapper's subslot register, and of SLTTBL, and mapper register FCh, can
    # select T0 (INTERNALS.md, Restorer, step 1).
    set ::p0mask [expr {$::C(service) ? 0xFC : 0xFF}]
    set jp [expr {$::tail(at) + $::tail(jp)}]
    # The slot register alone can match DOS's own, so the breakpoint also
    # needs the jump to the snapshot's program counter.
    set pc [want pc]
    debug set_bp $jp "(\[debug read ioports 0xA8\] & $::p0mask) == ([want a8] & $::p0mask) && [holds [expr {$jp + 1}] [list [expr {$pc & 0xFF}] [expr {$pc >> 8}]]]" {safe at_tail}
    later $::C(restore) {
        if {$::run(phase) eq "restore"} {
            note "the tail's jump did not run within $::C(restore) seconds"
            note "screen: [screen_line]"
            write_report
            stop
        }
    }
}
proc at_start {} {
    if {$::run(phase) eq "play"} {
        for_point 3 rerun
    } else {
        read_exptbl
        set ::dosslot [debug read memory 0xF344]
    }
}
# The restorer's message is on the screen a moment after stop_message starts:
# from the image's name, which starts it, to DOS's prompt after it.
proc at_stop {} {
    if {$::run(phase) ne "restore"} return
    set ::run(phase) refused
    later 2 {
        set text [screen_line]
        set at [string last "$::C(name).SNP" $text]
        if {$at >= 0} { set text [string range $text $at end] }
        regsub {\s+[A-H](:\S*)?>$} $text {} text
        note "the restorer stopped: $text"
        write_report
        stop
    }
}
proc at_tail {} {
    if {$::run(phase) ne "restore"} return
    set ::run(phase) play
    if {[catch compare e]} { note "check: $e" }
    write_report
    set ::point 2
    set ::n 0
    watch_part
    set ::restored [machine_info time]
    for_point 3 watch_reset
    later 10 point2
}

# Point 2: the game runs for 60 seconds, saved every 10 seconds, and must not
# write the tape service's part of page 3.
proc point2 {} {
    incr ::n
    savestate "$::C(state)-[expr {$::n * 10}]s"
    for_point 3 look_for_boot
    for_point 4 look_for_error
    if {$::n < 6} { later 10 point2; return }
    write_point2
    for_point 3 write_point3
    for_point 4 { write_point 4 $::basic_errors }
    stop
}

# Point 3: in the same 60 seconds the restored machine must not reboot
# (INTERNALS.md, Check, point 3). A reboot shows itself as SNAPCAS.COM starting
# again, when a reset has booted DOS and AUTOEXEC.BAT runs it, or as the MSX1
# BIOS's boot screen, whose first line is "MSX  system", at a savestate. BASIC's
# banner, which a game's restored screen can still hold, does not count. A reset
# alone does not fail the point, because a loader can reset on purpose to start a
# ROM copy, but the report notes each one. The reset breakpoint is the capture's:
# the BIOS's reset routine, where 0000h's DI / JP jumps, while page 0 selects
# the main ROM. It is set after point 1, because the check's own boot passes
# there, and the routine's address is read in the main ROM's slot, whose ID
# EXPTBL holds, because page 0 is DOS's RAM now.
set ::resets {}
set ::reboots {}
proc after_restore {} { format %.1f [expr {[machine_info time] - $::restored}] }
proc rerun {} {
    if {[llength $::reboots] < 10} { lappend ::reboots "SNAPCAS.COM starts again [after_restore] seconds after the restore" }
}
# The boot screen counts at two savestates or more: a reset on purpose shows
# it for a few seconds before the game starts, so one savestate can catch it.
set ::boots {}
proc look_for_boot {} {
    if {[regexp {MSX +system} [screen]]} {
        lappend ::boots "the screen shows the BIOS's boot screen [after_restore] seconds after the restore"
    }
}
proc watch_reset {} {
    lassign [slot_parts [exptbl 0]] ps ss
    set reset [with_slot $ps $ss 0 { word_at 2 }]
    debug set_bp $reset {[page0_selects [exptbl 0] subslot_reg]} {safe {for_point 3 noted_reset}}
}
proc noted_reset {} {
    if {[llength $::resets] < 10} { lappend ::resets "the machine resets [after_restore] seconds after the restore" }
}
# Point 4: in the same 60 seconds the game must not stop at a BASIC error
# (INTERNALS.md, Check, point 4). BASIC prints the message, with "in" and the line
# number in a program, and then Ok, in a text mode. The message counts only with
# the Ok after it, so that a game's own words do not.
set ::basic_errors {}
set ::basic_messages {
    {NEXT without FOR} {Syntax error} {RETURN without GOSUB} {Out of DATA}
    {Illegal function call} {Overflow} {Out of memory} {Undefined line number}
    {Subscript out of range} {Redimensioned array} {Division by zero}
    {Illegal direct} {Type mismatch} {Out of string space} {String too long}
    {String formula too complex} {Can't CONTINUE} {Undefined user function}
    {Device I/O error} {Verify error} {No RESUME} {RESUME without error}
    {Unprintable error} {Missing operand} {Line buffer overflow} {FIELD overflow}
    {Internal error} {Bad file number} {File not found} {File already open}
    {Input past end} {Bad file name} {Direct statement in file}
    {Sequential I/O only} {File not OPEN} {Bad allocation table} {Disk I/O error}
    {Disk full} {Disk offline} {Bad drive name}
}
proc look_for_error {} {
    set text [regsub -all {\s+} [screen] { }]
    foreach message $::basic_messages {
        if {[regexp "(${message}(?: in \\d+)?) Ok" $text -> found]} {
            lappend ::basic_errors "the screen shows $found [after_restore] seconds after the restore"
            return
        }
    }
}
proc write_point3 {} {
    # The capture reset the machine after the snapshot, and the restored game
    # does not.
    if {$::C(capreset) ne "" && [llength $::resets] == 0} {
        lappend ::reboots "the capture resets the machine $::C(capreset) seconds after the snapshot, and the restored game does not"
    }
    set failed [expr {[llength $::reboots] || [llength $::boots] >= 2}]
    set f [open $::C(report) a]
    puts $f [expr {$failed ? "point 3: fail" : "point 3: pass"}]
    foreach line [concat $::reboots $::boots $::resets] { puts $f "  $line" }
    close $f
}

# The watch on the service's part of page 3 without its scratch bytes,
# ::C(part) = {first last E_CODE segment}. A write counts when it comes from
# code outside the part and goes to the snapshot's page 3: its slot in the slot
# register and, in a mapper, its segment in register FFh. The service's own
# writes come from the part's code, which sets E_STOP for TAPIOF and STMOTR, and
# from the code segment, in page 0, which sets it for the manual tape. So a
# write from page 0 does not count while page 0 selects DOS's mapper with the
# code segment, whose number E_CODE holds, or with another segment than the
# snapshot's. A write after the service has read the tape to its end does not
# count: the tape is at its end at the write, as tape_read finds it, or the
# service has read its last byte since the restore, as at_tape_end notes.
set ::part_writes {}
proc in_service_segment {} {
    if {![page0_selects $::dosslot subslot_reg]} { return 0 }
    set fc [debug read {MSX Memory Mapper I/O} 0]
    expr {$fc != [want fc] || $fc == [debug read memory [lindex $::C(part) 2]]}
}
# Whether the tape is at its end: at most 7 bytes, a block's padding, between
# the tape position and the tape's end in the code segment, whose number E_CODE
# holds (src/tape.inc: D_POS, D_TOTAL). The code segment is read in page 1 of
# DOS's mapper, through port FDh, at the two addresses of build.txt's cpos, 3
# bytes each. That holds for a tape that was at its end at the snapshot. The
# automatic tape that reaches its end after the restore goes back to a side's
# start at once (src/tape.inc, wrap), so its position says nothing: the two
# breakpoints of watch_part note that end instead.
proc tape_read {} {
    set code [debug read memory [lindex $::C(part) 2]]
    lassign [slot_parts $::dosslot] ps ss
    set fd [debug read {MSX Memory Mapper I/O} 1]
    debug write ioports 0xFD $code
    foreach name {pos total} address $::C(cpos) {
        binary scan [with_slot $ps $ss 1 { debug read_block memory $address 3 }] cu* b
        set $name [expr {[lindex $b 0] | ([lindex $b 1] << 8) | ([lindex $b 2] << 16)}]
    }
    debug write ioports 0xFD $fd
    expr {$total - $pos <= 7}
}
# Whether the CPU runs the code segment: page 0 selects DOS's mapper with the
# segment that E_CODE holds.
proc in_code_segment {} {
    expr {[page0_selects $::dosslot subslot_reg] &&
          [debug read {MSX Memory Mapper I/O} 0] == [debug read memory [lindex $::C(part) 2]]}
}
# ::C(ended) holds the addresses of the service's two jumps at the end of the
# tape's last side, in the code segment: the first is taken with Z, for a tape
# of one side, and the second without carry, for side 2. Side 1's end of a tape
# with a side 2 takes neither. A build.txt of an older build has none.
set ::tape_ended 0
proc at_tape_end {} { set ::tape_ended 1 }
proc watch_part {} {
    if {[llength $::C(part)] == 0} return
    lassign $::C(part) first last
    debug set_watchpoint write_mem [list $first $last] {} {safe part_write}
    if {[llength $::C(ended)] == 0} return
    lassign $::C(ended) one two
    debug set_bp $one {[in_code_segment] && ([reg AF] & 0x40)} {safe at_tape_end}
    debug set_bp $two {[in_code_segment] && !([reg AF] & 0x01)} {safe at_tape_end}
}
proc part_write {} {
    lassign $::C(part) first last code segment
    set pc [reg pc]
    if {$pc >= $first && $pc <= $last} return
    if {([debug read ioports 0xA8] >> 6) != ([want a8] >> 6)} return
    if {$segment >= 0 && [debug read {MSX Memory Mapper I/O} 3] != $segment} return
    if {$pc < 0x4000 && [in_service_segment]} return
    if {$::tape_ended || [tape_read]} return
    set address [format %04X $::wp_last_address]
    if {![dict exists $::part_writes $address] && [dict size $::part_writes] < 40} {
        dict set ::part_writes $address [format %04X $pc]
    }
}
proc write_point2 {} {
    set lines {}
    dict for {address pc} $::part_writes {
        lappend lines "the game writes ${address}h, in the tape service's part of page 3, from ${pc}h"
    }
    write_point 2 $lines
}

# Point 1: the machine at the tail's jump against the snapshot.
proc compare {} {
    # The tail's jump goes to the snapshot's program counter.
    set target [word_at [expr {$::tail(at) + $::tail(jp) + 1}]]
    if {$target != [want pc]} { note "the tail jumps to [hex 4 $target], expected $::K(pc)" }
    # The machine's state, under state.txt's names, each value under its mask.
    foreach {name have} [machine_state] {
        set mask [state_mask $name]
        if {$mask eq "" || $::K($name) eq "-"} continue
        if {$have eq "-" || ([scan $have %x] & $mask) != ([want $name] & $mask)} {
            note "$name is $have, expected $::K($name)"
        }
    }

    # VRAM.
    set f [open [file join $::C(snap) vram.bin] rb]
    set want [read $f]
    close $f
    # With VR set, as the capture reads it.
    set have [physical_vram]
    if {$have ne $want} { note "VRAM differs at [format %05X [first_difference $have $want]]" }

    # The RAM pages, except the tail's bytes, the area of ::C(free), FCC9h to
    # FD88h, the service's page 3 part when it moved, FFFFh in an expanded
    # slot, the patched bytes, and with the tape service SLTTBL, FCC5h to
    # FCC8h (MSX Red Book, chapter 6).
    # A mapper's segment that the game also selects in page 3, or in the tail's
    # page, holds those bytes too, at the same offsets.
    set paths [lsort [glob -nocomplain -directory [file join $::C(snap) ram] *.bin]]
    if {[llength $paths] != $::C(pages)} {
        note "the check found [llength $paths] of the snapshot's $::C(pages) RAM pages"
    }
    set p3seg ""; set tailseg ""
    foreach path $paths {
        lassign [split [file rootname [file tail $path]] -] ps ss page seg
        if {$seg eq "x"} continue
        if {$page == 3} { set p3seg "$ps-$ss-$seg" }
        if {$page == ($::tail(at) >> 14)} { set tailseg "$ps-$ss-$seg" }
    }
    foreach path $paths {
        lassign [split [file rootname [file tail $path]] -] ps ss page seg
        set f [open $path rb]
        set want [read $f]
        close $f
        set have [with_slot $ps $ss $page { read_page $page }]
        set base [expr {$page * 0x4000}]
        set as3 [expr {$page == 3 || ($seg ne "x" && "$ps-$ss-$seg" eq $p3seg)}]
        set astail [expr {$page == ($::tail(at) >> 14) || ($seg ne "x" && "$ps-$ss-$seg" eq $tailseg)}]
        set skip {}
        if {$astail} { lappend skip [expr {$::tail(at) & 0x3FFF}] [expr {($::tail(at) & 0x3FFF) + $::tail(last)}] }
        foreach {from to} [concat $::C(free) $::C(moved)] {
            if {$as3} { lappend skip [expr {$from - 0xC000}] [expr {$to - 0xC000}] }
        }
        if {$as3 && $::C(service)} { lappend skip [expr {0xFCC5 - 0xC000}] [expr {0xFCC8 - 0xC000}] }
        if {$page == 3 && $ss ne "x"} { lappend skip 0x3FFF 0x3FFF }
        foreach {at from to} $::C(patched) { if {$at eq "$ps-$ss-$page"} { lappend skip $from $to } }
        set at [first_difference $have $want $skip]
        if {$at >= 0} { note "RAM $ps-$ss-$page differs at [format %04X [expr {$base + $at}]]" }
    }
}

# The bits of a state.txt value that the restored machine must have, or
# nothing for a value that the restore cannot or need not set.
proc state_mask {name} {
    switch -regexp -matchvar m -- $name {
        {^pc$} {
            # The tail's jump goes there, and compare reads its target.
            return ""
        }
        {^a8$} { return $::p0mask }
        {^fc$} {
            # With the tape service, mapper register FCh can select T0.
            return [expr {$::C(service) || ![has_mapper] ? "" : 0xFF}]
        }
        {^f[def]$} { return [expr {[has_mapper] ? 0xFF : ""}] }
        {^sub([0-3])$} {
            # When the worker's page does not select DOS's mapper's slot at
            # the snapshot, that page's bits of the slot's subslot register can
            # differ (INTERNALS.md, Restorer, step 1).
            set ps [lindex $m 1]
            if {$ps != ($::dosslot & 3)} { return 0xFF }
            set wpage [expr {[debug read memory [expr {$::tail(at) + $::tail(port)}]] - 0xFC}]
            set mask $::p0mask
            if {(([want a8] >> (2 * $wpage)) & 3) != $ps} { set mask [expr {$mask & ~(3 << (2 * $wpage))}] }
            return $mask
        }
        {^psg7$} {
            # Bits 7 and 6 set the direction of the PSG's I/O ports.
            return 0x3F
        }
        {^psg14$} {
            # Register 14 is an input on an MSX, the joystick lines and the
            # cassette signal at the moment it is read.
            return ""
        }
        default { return 0xFFFFFF }
    }
}
proc has_mapper {} { expr {"MSX Memory Mapper I/O" in [debug list]} }

# The first offset at which a and b differ, outside the ranges in skip, or -1.
proc first_difference {a b {skip {}}} {
    binary scan $a cu* la
    binary scan $b cu* lb
    set n [llength $la]
    for {set i 0} {$i < $n} {incr i} {
        if {[lindex $la $i] != [lindex $lb $i]} {
            set skipped 0
            foreach {from to} $skip { if {$i >= $from && $i <= $to} { set skipped 1 } }
            if {!$skipped} { return $i }
        }
    }
    return -1
}
