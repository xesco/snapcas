# The check (docs/DESIGN.md, Check), after memory.tcl's procedures, which it
# uses to read memory through the CPU's view. tools/check.py sets ::C.

array set ::K $::C(kv)
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

proc start_check {} {
    # EXPTBL, read while the system area is still DOS's.
    set ::exptbl [lmap ps {0 1 2 3} {debug read memory [expr {0xFCC1 + $ps}]}]
    # RAMAD3 at F344h: DOS's mapper's slot ID, read when SNAPCAS.COM starts,
    # after DOS has set it.
    set ::dosslot 0
    lassign $::C(com) b0 b1 b2
    debug set_bp 0x0100 "\[debug read memory 0x100\] == $b0 && \[debug read memory 0x101\] == $b1 && \[debug read memory 0x102\] == $b2" { set ::dosslot [debug read memory 0xF344] }
    # With the tape service, page 0's bits of the slot register, of DOS's
    # mapper's subslot register, and of SLTTBL, and mapper register FCh, can
    # select T0 (DESIGN.md, Restorer, step 3).
    set ::p0mask [expr {$::C(service) ? 0xFC : 0xFF}]
    set jp [expr {$::C(tail) + 21}]
    set ::reached 0
    # The slot register alone can match DOS's own, so the breakpoint also
    # needs the jump to the snapshot's program counter.
    set target [expr {$::C(tail) + 22}]
    debug set_bp $jp "(\[debug read ioports 0xA8\] & $::p0mask) == ($::C(a8) & $::p0mask) && \[debug read memory $target\] == [expr {$::C(pc) & 0xFF}] && \[debug read memory [expr {$target + 1}]\] == [expr {$::C(pc) >> 8}]" { if {!$::reached} { set ::reached 1; safe_check } }
    after time 120 {
        if {!$::reached} {
            lappend ::diffs "the tail's jump did not run within 120 seconds"
            lappend ::diffs "screen: [string trim [regsub -all {\s+} [screen] { }]]"
            write_report
            exit
        }
    }
}

proc safe_check {} {
    if {[catch compare e]} { lappend ::diffs "check: $e" }
    write_report
    set ::n 0
    after time 10 point2
}

# Point 2: the game runs for 60 seconds, saved every 10 seconds.
proc point2 {} {
    incr ::n
    savestate "$::C(state)-[expr {$::n * 10}]s"
    if {$::n < 6} { after time 10 point2 } else { exit }
}

proc hex2 {v} { format %02X $v }

proc compare {} {
    # The registers, at the tail's jump: AF and SP are the snapshot's, and the
    # jump goes to its PC.
    foreach {r v} $::C(regs) {
        if {[reg $r] != $v} { note "register $r is [format %04X [reg $r]], expected [format %04X $v]" }
    }
    set target [expr {[debug read memory [expr {$::C(tail) + 22}]] | ([debug read memory [expr {$::C(tail) + 23}]] << 8)}]
    if {$target != $::C(pc)} { note "the tail jumps to [format %04X $target], expected [format %04X $::C(pc)]" }
    foreach {r name} {I i IM im} {
        if {[reg $r] != [scan $::K($name) %x]} { note "$r is [reg $r], expected $::K($name)" }
    }
    if {([reg IFF] & 1) != ([scan $::K(iff) %x] & 1)} { note "IFF1 is [expr {[reg IFF] & 1}], expected $::K(iff)" }
    set a8 [debug read ioports 0xA8]
    if {($a8 & $::p0mask) != ([scan $::K(a8) %x] & $::p0mask)} { note "the slot register is [hex2 $a8], expected $::K(a8)" }
    if {[debug read ioports 0xAA] != [scan $::K(ppic) %x]} { note "PPI port C is [hex2 [debug read ioports 0xAA]], expected $::K(ppic)" }
    # When the worker's page does not select DOS's mapper's slot at the
    # snapshot, that page's bits of the slot's subslot register can differ
    # (DESIGN.md, Restorer, step 1).
    set wpage [expr {[debug read memory [expr {$::C(tail) + 3}]] - 0xFC}]
    set mps [expr {$::dosslot & 3}]
    foreach ps {0 1 2 3} {
        if {$::K(sub$ps) eq "-"} { continue }
        set mask [expr {$ps == $mps ? $::p0mask : 0xFF}]
        if {$ps == $mps && (([scan $::K(a8) %x] >> (2 * $wpage)) & 3) != $mps} {
            set mask [expr {$mask & ~(3 << (2 * $wpage))}]
        }
        if {([subslot_reg $ps] & $mask) != ([scan $::K(sub$ps) %x] & $mask)} {
            note "slot $ps's subslot register is [hex2 [subslot_reg $ps]], expected $::K(sub$ps)"
        }
    }
    if {"MSX Memory Mapper I/O" in [debug list]} {
        foreach p {0 1 2 3} r {fc fd fe ff} {
            if {$::K($r) ne "-" && !($p == 0 && $::C(service)) && [debug read {MSX Memory Mapper I/O} $p] != [scan $::K($r) %x]} {
                note "mapper register $r is [hex2 [debug read {MSX Memory Mapper I/O} $p]], expected $::K($r)"
            }
        }
    }
    # Register 14 is an input on an MSX, the joystick lines and the cassette
    # signal at the moment it is read, so the restore cannot set it.
    for {set r 0} {$r < 16} {incr r} {
        if {$r == 14} continue
        set v [debug read {PSG regs} $r]
        set e [scan $::K(psg$r) %x]
        if {$r == 7} { set v [expr {$v & 0x3F}]; set e [expr {$e & 0x3F}] }
        if {$v != $e} { note "PSG register $r is [hex2 $v], expected $::K(psg$r)" }
    }
    set v9938 [v9938]
    set regs [expr {$v9938 ? [concat [lrange {0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23} 0 end] {32 33 34 35 36 37 38 39 40 41 42 43 44 45}] : {0 1 2 3 4 5 6 7}}]
    foreach r $regs {
        if {[debug read {VDP regs} $r] != [scan $::K(vdp$r) %x]} { note "VDP register $r is [hex2 [debug read {VDP regs} $r]], expected $::K(vdp$r)" }
    }
    if {$v9938} {
        for {set c 0} {$c < 16} {incr c} {
            set v "[hex2 [debug read {VDP palette} [expr {2 * $c}]]][hex2 [debug read {VDP palette} [expr {2 * $c + 1}]]]"
            if {$v ne $::K(pal$c)} { note "palette entry $c is $v, expected $::K(pal$c)" }
        }
    }
    set ptr [expr {[debug read {VRAM pointer} 0] | (([debug read {VRAM pointer} 1] & 0x3F) << 8)}]
    if {$v9938} { set ptr [expr {$ptr | (([debug read {VDP regs} 14] & 7) << 14)}] }
    if {$ptr != [scan $::K(vramptr) %x]} { note "the VRAM pointer is [format %05X $ptr], expected $::K(vramptr)" }
    if {[debug read {VRAM access status} 0] != $::K(vramwrite)} { note "the VRAM access is [debug read {VRAM access status} 0], expected $::K(vramwrite)" }

    # VRAM.
    set f [open [file join $::C(snap) vram.bin] rb]
    set want [read $f]
    close $f
    # With VR set, as the capture reads it.
    set have [physical_vram]
    if {$have ne $want} { note "VRAM differs at [format %05X [first_difference $have $want]]" }

    # The RAM pages, except the tail's bytes, FCC9h to FD88h, the service's
    # page 3 part when it moved, FFFFh in an expanded slot, the patched bytes,
    # and with the tape service SLTTBL.
    # A mapper's segment that the game also selects in page 3, or in the tail's
    # page, holds those bytes too, at the same offsets.
    set paths [lsort [glob -nocomplain [file join $::C(snap) ram *.bin]]]
    set p3seg ""; set tailseg ""
    foreach path $paths {
        lassign [split [file rootname [file tail $path]] -] ps ss page seg
        if {$seg eq "x"} continue
        if {$page == 3} { set p3seg "$ps-$ss-$seg" }
        if {$page == ($::C(tail) >> 14)} { set tailseg "$ps-$ss-$seg" }
    }
    foreach path $paths {
        lassign [split [file rootname [file tail $path]] -] ps ss page seg
        set f [open $path rb]
        set want [read $f]
        close $f
        set have [with_slot $ps $ss $page { read_page $page }]
        set base [expr {$page * 0x4000}]
        set as3 [expr {$page == 3 || ($seg ne "x" && "$ps-$ss-$seg" eq $p3seg)}]
        set astail [expr {$page == ($::C(tail) >> 14) || ($seg ne "x" && "$ps-$ss-$seg" eq $tailseg)}]
        set skip {}
        if {$astail} { lappend skip [expr {$::C(tail) & 0x3FFF}] [expr {($::C(tail) & 0x3FFF) + 25}] }
        if {$as3} { lappend skip [expr {0xFCC9 - 0xC000}] [expr {0xFD88 - 0xC000}] }
        foreach {from to} $::C(p3) { if {$as3} { lappend skip [expr {$from - 0xC000}] [expr {$to - 0xC000}] } }
        if {$as3 && $::C(service)} { lappend skip [expr {0xFCC5 - 0xC000}] [expr {0xFCC8 - 0xC000}] }
        if {$page == 3 && $ss ne "x"} { lappend skip 0x3FFF 0x3FFF }
        foreach {at from to} $::C(patched) { if {$at eq "$ps-$ss-$page"} { lappend skip $from $to } }
        set at [first_difference $have $want $skip]
        if {$at >= 0} { note "RAM $ps-$ss-$page differs at [format %04X [expr {$base + $at}]]" }
    }
}

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
