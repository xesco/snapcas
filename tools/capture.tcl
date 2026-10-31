# Procedures of the capture (docs/DESIGN.md, Capture). tools/capture.py puts
# the game file's settings before them and the steps' start after them.

# The CPU's view of memory, after selecting a slot in a page (DESIGN.md, RAM).

# EXPTBL at FCC1h: bit 7 of each slot's byte is set when it is expanded. The
# capture reads it once, in step 2, because a game can overwrite page 3.
proc exptbl {ps} {
    if {[info exists ::exptbl]} { return [lindex $::exptbl $ps] }
    debug read memory [expr {0xFCC1 + $ps}]
}
proc expanded {ps} { expr {([exptbl $ps] & 0x80) != 0} }

proc a8_with {a8 page ps} {
    set shift [expr {$page * 2}]
    expr {($a8 & ~(3 << $shift) & 0xFF) | ($ps << $shift)}
}

# The subslot register of an expanded slot, read at FFFFh, inverted, while
# page 3 selects that slot.
proc subslot_reg {ps} {
    set a8 [debug read ioports 0xA8]
    debug write ioports 0xA8 [a8_with $a8 3 $ps]
    set v [expr {~[debug read memory 0xFFFF] & 0xFF}]
    debug write ioports 0xA8 $a8
    return $v
}

proc set_subslot_reg {ps value} {
    set a8 [debug read ioports 0xA8]
    debug write ioports 0xA8 [a8_with $a8 3 $ps]
    debug write memory 0xFFFF $value
    debug write ioports 0xA8 $a8
}

# Runs body with slot ps, subslot ss ("x" when not expanded) selected in page,
# and puts the slot register and the subslot register back afterwards.
proc with_slot {ps ss page body} {
    set a8 [debug read ioports 0xA8]
    if {$ss ne "x"} {
        set sub [subslot_reg $ps]
        set shift [expr {$page * 2}]
        set_subslot_reg $ps [expr {($sub & ~(3 << $shift) & 0xFF) | ($ss << $shift)}]
    }
    debug write ioports 0xA8 [a8_with $a8 $page $ps]
    set code [catch {uplevel 1 $body} result]
    debug write ioports 0xA8 $a8
    if {$ss ne "x"} { set_subslot_reg $ps $sub }
    return -code $code $result
}

proc read_page {page} {
    debug read_block memory [expr {$page * 0x4000}] 0x4000
}

# A page holds RAM when the byte at its first address takes a written value
# and its complement. Run inside with_slot.
proc is_ram {page} {
    set a [expr {$page * 0x4000}]
    set v [debug read memory $a]
    set x [expr {$v ^ 0xFF}]
    debug write memory $a $x
    set ok [expr {[debug read memory $a] == $x}]
    debug write memory $a $v
    expr {$ok && [debug read memory $a] == $v}
}

# A RAM page is in a mapper when two marker bytes, written at its first address
# under two values of its mapper register, each read back under their own
# value. Run inside with_slot.
proc is_mapper {page} {
    set port [expr {0xFC + $page}]
    set a [expr {$page * 0x4000}]
    set orig [debug read "MSX Memory Mapper I/O" $page]
    set other [expr {$orig ^ 1}]
    debug write ioports $port $orig
    debug write memory $a 0x5A
    debug write ioports $port $other
    debug write memory $a 0xA5
    debug write ioports $port $orig
    set ok [expr {[debug read memory $a] == 0x5A}]
    debug write ioports $port $other
    set ok [expr {$ok && [debug read memory $a] == 0xA5}]
    debug write ioports $port $orig
    return $ok
}

# The mapper's size in segments: each segment's number written into its first
# byte from 255 down to 0, then read back from 4 up to the first mismatch, as
# the restorer counts under MSX-DOS 1. It overwrites the segments, so the
# capture runs it only after it has read the pages. Run inside with_slot.
proc mapper_size {page} {
    set port [expr {0xFC + $page}]
    set a [expr {$page * 0x4000}]
    set orig [debug read "MSX Memory Mapper I/O" $page]
    for {set n 255} {$n >= 0} {incr n -1} {
        debug write ioports $port $n
        debug write memory $a $n
    }
    for {set n 4} {$n < 256} {incr n} {
        debug write ioports $port $n
        if {[debug read memory $a] != $n} { break }
    }
    debug write ioports $port $orig
    return $n
}

# ---- The steps (DESIGN.md, Capture) ----
#
# capture.py sets these before the procedures:
#   ::S(snap)     the snapshot folder
#   ::S(boot)     the boot steps, for boot (tools/msx.py)
#   ::S(afterboot) what follows them: wait_ok, after BASIC typed at DOS's prompt
#                 on a machine that boots DOS from its own disk
#   ::S(cas)      the CAS file of side 1
#   ::S(cmd)      the load command; ::S(cload) is 1 for CLOAD, then RUN
#   ::S(headers)  the offsets of side 1's headers
#   ::S(needed)   the end of the last block that the load must read
#   ::S(side2)    1 when the game file has side2
#   ::S(side2cas) side 2's CAS file, or "" without a side 2
#   ::S(s1len)    side 1's length, padded to a multiple of 8: side 2's start
#   ::S(headers2) the positions of side 2's headers, from side 1's start
#   ::S(nosvc)    1 when the game file has service no
#   ::S(keys)     [list time tcl] pairs, times from the load command
#   ::S(lastkey)  the last keys time
#   ::S(tries)    [list name tcl] pairs: the keys that may continue a load
#   ::S(snapat)   the snapshot at time, or ""
#   ::S(state)    the name of the capture's savestate, its own so that
#                 captures can run side by side
#
# ::st holds the state that the capture logs. A rewind puts back its copy
# from the savestate's moment, because openMSX's loadstate restores the machine
# but neither Tcl variables nor timers.

proc quit {} {
    catch { delete_savestate $::S(state) }
    catch { delete_savestate $::S(state)-tapion }
    catch { delete_savestate $::S(state)-tapion-saved }
    exit
}
proc savestate_file {name} { file join $::env(OPENMSX_HOME) savestates $name.oms }
proc fail {msg} {
    set f [open [file join $::S(snap) error.txt] w]
    puts $f "capture: $msg"
    close $f
    catch write_log
    quit
}
proc safe {body} { if {[catch {uplevel #0 $body} e]} { fail $e } }
proc later {secs body} { after time $secs [list safe $body] }
proc now {} { machine_info time }
# Two logs: ::st(log) follows the machine and goes back with a rewind, and
# ::decisions keeps what the capture decided, across rewinds. log.txt holds
# both, in time order.
proc logev {msg} {
    lappend ::st(log) [list [expr {[now] - $::t0}] $msg]
}
set ::decisions {}
proc decide {msg} {
    lappend ::decisions [list [expr {[now] - $::t0}] $msg]
}

# Emulated seconds since the load command, counted across rewinds.
set ::elapsed 0
proc tick {secs} {
    set ::elapsed [expr {$::elapsed + $secs}]
    if {$::elapsed > 3600} { fail "the load ran for more than 3600 seconds" }
}

proc motor_on {} { expr {([debug read ioports 0xAA] & 0x10) == 0} }
proc at_end {} {
    expr {[cassetteplayer getpos] >= [cassetteplayer getlength] - 0.01}
}

# Whether page 0 selects the main ROM, whose slot ID is EXPTBL's first byte.
proc rom0 {} {
    set id [exptbl 0]
    set a8 [debug read ioports 0xA8]
    if {($a8 & 3) != ($id & 3)} { return 0 }
    if {!($id & 0x80)} { return 1 }
    expr {($::st(sub[expr {$id & 3}]) & 3) == (($id >> 2) & 3)}
}

proc note_selection {a8} {
    foreach page {0 1 2 3} {
        set ps [expr {($a8 >> (2 * $page)) & 3}]
        set sub $::st(sub$ps)
        set ss [expr {$sub < 0 ? "x" : ($sub >> (2 * $page)) & 3}]
        dict set ::st(sel) "$ps-$ss-$page" 1
    }
}
proc on_ffff {value} {
    set a8 [debug read ioports 0xA8]
    set ps [expr {($a8 >> 6) & 3}]
    if {$::st(sub$ps) >= 0} {
        set ::st(sub$ps) $value
        note_selection $a8
    }
}

# ---- Slot patches (DESIGN.md, Slot patches) ----

# The slot map, at step 3: for each page, the primary slots that hold nothing
# there and the slot that replaces them in a slot register value, or -1. A
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
    }
    set f [open [file join $::S(snap) slots.txt] w]
    puts $f "# For each page: the primary slots that hold nothing there, and the slot"
    puts $f "# that replaces them in a slot register value, or -1 (DESIGN.md, Slot patches)."
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

# n bytes at address, read with the slot register at a8.
proc read_with {a8 address n} {
    set now [debug read ioports 0xA8]
    debug write ioports 0xA8 $a8
    set bytes [debug read_block memory [expr {$address & 0xFFFF}] $n]
    debug write ioports 0xA8 $now
    return $bytes
}

# The opcodes of the instructions with a one-byte and with a two-byte operand,
# as scan.py's OPERAND_1 and OPERAND_2 (DESIGN.md, Slot patches).
set ::operand1 [lmap b {06 0E 16 1E 26 2E 36 3E C6 CE D6 DE E6 EE F6 FE D3 DB 10 18 20 28 30 38} {expr 0x$b}]
set ::operand2 [lmap b {01 11 21 31 22 2A 32 3A C2 C3 C4 CA CC CD D2 D4 DA DC E2 E4 EA EC F2 F4 FA FC} {expr 0x$b}]

# Whether the byte at address, read with the slot register at a8, can be an
# operand of the instruction before it.
proc in_operand {a8 address} {
    binary scan [read_with $a8 [expr {$address - 2}] 2] cu2 bytes
    lassign $bytes two one
    expr {$one in $::operand1 || $one in $::operand2 || $two in $::operand2}
}

# The code that wrote value to the slot register, read with the slot register
# before the write, as {address length}, or "" when it is not one of the two
# forms: LD A,n / OUT (0A8h),A, whose OUT is at PC, or LD A,n / CALL 013Bh,
# whose OUT is in the main ROM and whose return address is on the stack. Code
# whose 3Eh can be an operand of the instruction before it is neither.
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

# Each place of bytes in the CAS files, as {side offset}.
proc cas_find {bytes} {
    set found {}
    foreach side {1 2} data [list $::cas1 $::cas2] {
        set i 0
        while {[set j [string first $bytes $data $i]] >= 0} {
            lappend found [list $side $j]
            set i [expr {$j + 1}]
        }
    }
    return $found
}

# Step 4's watch on the slot register. A value that names a slot that holds
# nothing is logged. When its code is one of the two forms, and the code with
# the 8 bytes before it, or else after it, occurs once in the CAS files, the
# capture writes the patch to newpatch.txt and stops, and capture.py runs it
# again.
proc on_a8 {value} {
    set before $::st(a8)
    set ::st(a8) $value
    note_selection $value
    if {![names_nothing $value]} return
    set new [slot_fix $value]
    set code [slot_code $value $before]
    if {$code ne "" && $new != $value} {
        lassign $code address length
        # The code with the 8 bytes before it, or else after it, for a loader
        # that copies a routine without the bytes before it.
        set found [cas_find [read_with $before [expr {$address - 8}] [expr {$length + 8}]]]
        set at 8
        if {[llength $found] != 1} {
            set found [cas_find [read_with $before $address [expr {$length + 8}]]]
            set at 0
        }
        if {[llength $found] == 1} {
            lassign [lindex $found 0] side offset
            set offset [expr {$offset + $at}]
            set old [read_with $before $address $length]
            binary scan $old cu* bytes
            set patched [lreplace $bytes 1 1 $new]
            set f [open [file join $::S(snap) newpatch.txt] w]
            puts $f [format "patch side%d:%X %s > %s" $side $offset \
                [join [lmap b $bytes {format %02X $b}]] [join [lmap b $patched {format %02X $b}]]]
            close $f
            decide "the slot register write of [hex 2 $value] at [hex 4 $address] names a slot that holds nothing: patched to [hex 2 $new]"
            catch write_log
            quit
        }
    }
    if {[incr ::slot_logs] <= 16} {
        decide "the slot register write of [hex 2 $value] at PC [hex 4 [reg pc]] names a slot that holds nothing, for a patch line"
    }
}
set ::slot_logs 0

# Each TAPION call's entry is saved, with ::st, as a moment for the snapshot
# when it would otherwise come inside the BIOS's tape routines (step 6).
proc on_tapion {} {
    if {!$::S(nosvc)} {
        savestate $::S(state)-tapion
        set ::tapion_st [array get ::st]
    }
    incr ::st(tapion)
    # A TAPION call at side 1's end, with a side 2: the player turns the tape
    # over, so side 2 goes in, at its start.
    if {$::S(side2cas) ne "" && !$::st(side2in) && [at_end]} {
        cassetteplayer insert $::S(side2cas)
        set ::st(side2in) 1
        set ::st(pos) $::S(s1len)
        logev "side 2 inserted"
    }
    set next ""
    foreach h [concat $::S(headers) $::S(headers2)] { if {$h >= $::st(pos)} { set next $h; break } }
    set ::st(pos) [expr {$next eq "" ? $::st(pos) : $next + 8}]
    logev "TAPION, tape position $::st(pos)"
}
proc on_tapin {} { incr ::st(tapin); incr ::st(pos) }
# A game that reads on past side 1's end, with the motor on and the CPU waiting
# in the BIOS's tape code, waits for side 2: the player turns the tape over, so
# side 2 goes in, and the read goes on after side 2's first header. A motor
# that a game only switches, with no read, does not turn the tape over.
proc turn_over {} {
    if {$::S(side2cas) eq "" || $::st(side2in) || ![motor_on] || ![at_end]} { return }
    if {![in_tape_code [reg PC]]} { return }
    cassetteplayer insert $::S(side2cas)
    set ::st(side2in) 1
    set ::st(pos) [expr {[lindex $::S(headers2) 0] + 8}]
    logev "side 2 inserted"
}

# A CAS file pads each block to a multiple of 8 bytes, so a block counts as
# read when at most 7 bytes of it are left.
proc side1_read {} {
    expr {$::st(tapion) > 0 && $::st(tapin) > 0 && $::st(pos) >= $::S(needed) - 7}
}

# 1. Boot, pass the boot menu, wait for BASIC's Ok.
proc step1 {} {
    set ::st(psgsel) 0
    debug set_watchpoint write_io 0xA0 {} {set ::st(psgsel) $::wp_last_value}
    set ::booted 0
    later 120 { if {!$::booted} { fail "BASIC's Ok did not appear within 120 seconds" } }
    boot $::S(boot) $::S(afterboot)
}
# The disk system can still be busy just after BASIC's Ok (a load that
# starts 5 seconds after the Carnivore2's boot behaves differently from one that
# starts 9 seconds after it), so the capture waits 10 seconds, as a person
# would, before it goes on.
proc wait_ok {} {
    if {[string first "Ok" [screen]] >= 0} { set ::booted 1; later 10 step2; return }
    later 0.5 wait_ok
}

# 2. Remove the disk system from page 3, and set HIMEM as on a cassette
#    machine.
proc step2 {} {
    set v [debug read memory 0x002D]
    if {$v > 1} { fail "the machine is not an MSX1 or an MSX2: 002Dh holds $v" }
    set ::S(msx2) $v
    set ::exptbl [lmap ps {0 1 2 3} {debug read memory [expr {0xFCC1 + $ps}]}]
    # EXBRSA at FAF8h: the slot ID of the MSX2 sub-ROM.
    set ::exbrsa [debug read memory 0xFAF8]
    for {set a 0xFD9A} {$a <= 0xFFC9} {incr a 5} { debug write memory $a 0xC9 }
    foreach a {0xFFCA 0xFFCF 0xFFD4} { debug write memory $a 0xC9 }
    debug write memory 0xF37D 0
    for {set a 0xFCC9} {$a <= 0xFD88} {incr a} { debug write memory $a 0 }
    type "CLEAR200,&HF380\r"
    later 3 step3
}

# 3. Insert side 1, note the slots, type the load command.
proc step3 {} {
    foreach ps {0 1 2 3} {
        set ::st(sub$ps) [expr {[expanded $ps] ? [subslot_reg $ps] : -1}]
    }
    set ::st(sel) {}
    set ::st(log) {}
    set ::st(pos) 0
    set ::st(side2in) 0
    set ::st(tapion) 0
    set ::st(tapin) 0
    set ::st(ran) 0
    set ::st(on_seen) 0
    set ::st(a8) [debug read ioports 0xA8]
    note_selection $::st(a8)
    slot_map
    set ::cas1 [read_binary $::S(cas)]
    set ::cas2 [expr {$::S(side2cas) eq "" ? "" : [read_binary $::S(side2cas)]}]
    # TAPION and TAPIN: the addresses that the jump table entries 00E1h and
    # 00E4h jump to.
    set tapion [expr {[debug read memory 0xE2] | ([debug read memory 0xE3] << 8)}]
    set tapin [expr {[debug read memory 0xE5] | ([debug read memory 0xE6] << 8)}]
    debug set_bp $tapion {[rom0]} {safe on_tapion}
    debug set_bp $tapin {[rom0]} {safe on_tapin}
    debug set_watchpoint write_io 0xA8 {} {safe {on_a8 $::wp_last_value}}
    debug set_watchpoint write_mem 0xFFFF {} {safe {on_ffff $::wp_last_value}}
    cassetteplayer insert $::S(cas)
    set ::t0 [now]
    set ::restarts 0
    type "$::S(cmd)\r"
    logev "typed $::S(cmd)"
    schedule_keys
    if {$::S(snapat) ne ""} {
        later $::S(snapat) step6
        if {$::S(cload)} { set ::since ""; run_after_cload }
        if {$::S(side2cas) ne ""} { watch_turn }
    } else {
        start_wait
    }
}

# With snapshot at, side 2 still goes in when side 1 runs out.
proc watch_turn {} { turn_over; later 0.1 watch_turn }

# With snapshot at, no wait decides anything, but a CLOAD still needs its RUN:
# typed as poll types it, when the motor has run and stopped for 1 second.
proc run_after_cload {} {
    note_motor
    if {[motor_on]} {
        set ::st(on_seen) 1
        set ::since ""
    } elseif {$::st(on_seen)} {
        if {$::since eq ""} { set ::since [now] }
        if {[now] - $::since >= 1} {
            set ::st(ran) 1
            type "RUN\r"
            logev "typed RUN"
            return
        }
    }
    later 0.1 run_after_cload
}

# 4. The keys, each at its time from the load command; those still to come
#    after a rewind are scheduled again.
proc schedule_keys {} {
    foreach {t tcl} $::S(keys) {
        set due [expr {$::t0 + $t - [now]}]
        if {$due > 0} { later $due [list press_key $t $tcl] }
    }
}
proc press_key {t tcl} { logev "keys $t"; eval $tcl }

# 5. Wait for the load to stop, then decide.
proc start_wait {} {
    set ::since ""
    set ::saved 0
    poll
}
proc screen_lines {} {
    if {[string trim [screen]] eq ""} { return "a graphics screen" }
    join [lmap l [split [screen] \n] {expr {[string trim $l] eq "" ? [continue] : [string trim $l]}}] " | "
}
proc note_motor {} {
    set on [motor_on]
    if {![info exists ::st(motor)] || $::st(motor) != $on} {
        set ::st(motor) $on
        logev [expr {$on ? "motor on" : "motor off"}]
    }
}
proc poll {} {
    tick 0.1
    note_motor
    turn_over
    if {[motor_on] && ![at_end]} {
        set ::st(on_seen) 1
        set ::since ""
        set ::saved 0
    } else {
        if {$::since eq ""} { set ::since [now] }
        set off [expr {[now] - $::since}]
        if {$::S(cload) && !$::st(ran) && $::st(on_seen) && $off >= 1} {
            set ::st(ran) 1
            type "RUN\r"
            logev "typed RUN"
            set ::since ""
        } elseif {!$::saved && $off >= 1} {
            savestate $::S(state)
            set ::saved 1
            set ::saved_st [array get ::st]
            # The last TAPION entry as at this moment, for a rewind to it.
            unset -nocomplain ::saved_tapion_st
            if {[info exists ::tapion_st]} {
                file copy -force [savestate_file $::S(state)-tapion] [savestate_file $::S(state)-tapion-saved]
                set ::saved_tapion_st $::tapion_st
            }
        } elseif {$off >= 30 && [now] - $::t0 >= $::S(lastkey)} {
            wait_ended
            return
        }
    }
    later 0.1 poll
}

proc rewind {} {
    # The last TAPION entry is the one at the rewind's moment: one saved
    # after it is not in the new run.
    unset -nocomplain ::tapion_st
    if {[info exists ::saved_tapion_st]} {
        file copy -force [savestate_file $::S(state)-tapion-saved] [savestate_file $::S(state)-tapion]
        set ::tapion_st $::saved_tapion_st
    }
    loadstate $::S(state)
    array unset ::st
    array set ::st $::saved_st
    schedule_keys
}

proc wait_ended {} {
    rewind
    decide "load stopped at tape position $::st(pos), the cassette player at [format %.1f [cassetteplayer getpos]] of [format %.1f [cassetteplayer getlength]] seconds, screen: [screen_lines]"
    if {[side1_read]} { step6; return }
    set ::trying $::S(tries)
    try_next
}
proc try_next {} {
    if {[llength $::trying] == 0} {
        rewind
        decide "no key continues the load"
        step6
        return
    }
    lassign [lindex $::trying 0] name tcl
    set ::trying [lrange $::trying 1 end]
    rewind
    eval $tcl
    set ::tried_at [now]
    watch_motor $name
}
# A key continues the load when the motor starts, unless the tape is at its
# end, where a game can start the motor and read nothing.
proc watch_motor {name} {
    tick 0.1
    if {[motor_on] && ![at_end]} {
        decide "continue $name"
        lappend ::st(continue) $name
        if {[incr ::restarts] > 20} { fail "step 5 restarted more than 20 times" }
        start_wait
        return
    }
    if {[now] - $::tried_at >= 10} { try_next; return }
    later 0.1 [list watch_motor $name]
}

# 6. The snapshot, at the entry of the next interrupt that the CPU accepts
#    while no VDP command runs and both VDP latches are empty.
proc v9938 {} { expr {[debug size "physical VRAM"] > 0x4000} }

# VRAM's cells. openMSX shows a V9938's VRAM through the addressing of
# register 8's bit 3, VR, which a game can clear (DESIGN.md, Snapshot files),
# and the restorer writes the cells with VR set, so VR is set for the read.
proc physical_vram {} {
    set size [debug size "physical VRAM"]
    if {$size <= 0x4000} { return [debug read_block "physical VRAM" 0 $size] }
    set r8 [debug read {VDP regs} 8]
    debug write {VDP regs} 8 [expr {$r8 | 8}]
    set v [debug read_block "physical VRAM" 0 $size]
    debug write {VDP regs} 8 $r8
    return $v
}

proc vdp_quiet {} {
    if {[debug read "VDP register latch status" 0] != 0} { return 0 }
    if {[v9938]} {
        if {[debug read "VDP palette latch status" 0] != 0} { return 0 }
        if {[debug read "VDP status regs" 2] & 1} { return 0 }
    }
    return 1
}
proc step6 {} {
    set ::st(service) [expr {!$::S(nosvc) && $::st(tapion) > 0 && $::st(tapin) > 0 &&
                             (![side1_read] || $::S(side2))}]
    if {[reg IM] == 2} {
        set v [expr {[reg I] * 256 + 0xFF}]
        set handler [expr {[debug read memory $v] | ([debug read memory [expr {($v + 1) & 0xFFFF}]] << 8)}]
    } else {
        set handler 0x0038
    }
    set ::accepted 0
    set ::done 0
    set ::irq_probe [debug probe set_bp z80.acceptIRQ {} {set ::accepted 1}]
    set ::irq_bp [debug set_bp $handler {$::accepted} {safe at_handler}]
    later 1 fallback
}
proc at_handler {} {
    set ::accepted 0
    if {$::done || ![vdp_quiet]} { return }
    set ::done 1
    decide "snapshot at an interrupt's entry"
    take_snapshot
}
# Without an interrupt within 1 second, the snapshot is taken where the CPU
# is. A halted CPU has its program counter just after the HALT (76h) and does
# not move.
proc fallback {} {
    if {$::done} { return }
    set ::done 1
    debug probe remove_bp $::irq_probe
    debug remove_bp $::irq_bp
    set ::fallback_pc [reg PC]
    later 0.02 fallback2
}
proc fallback2 {} {
    set pc [reg PC]
    if {$pc == $::fallback_pc &&
        [debug read memory [expr {($pc - 1) & 0xFFFF}]] == 0x76} {
        fail "the CPU is halted with no interrupt, at [format %04X $pc]"
    }
    if {$::st(service) && [in_tape_code $pc]} {
        # T0 replaces that code, so the snapshot goes back to the last TAPION
        # call's entry, where the call has not run: at its jump table entry,
        # the restored game reaches the tape service.
        if {![info exists ::tapion_st]} {
            fail "the CPU is in the BIOS's tape code, at [format %04X $pc], with no TAPION call saved"
        }
        set service $::st(service)
        loadstate $::S(state)-tapion
        array unset ::st
        array set ::st $::tapion_st
        set ::st(service) $service
        decide "snapshot at the last TAPION call's entry, because the CPU is in the BIOS's tape code"
        take_snapshot 0x00E1
        return
    }
    decide "snapshot without an interrupt"
    take_snapshot
}
# The CPU is in the BIOS's tape code, 19DDh to 1B44h, or in a routine of page
# 0's ROM that it calls, such as BREAKX, when one of the 8 words on top of the
# stack is an address there.
proc in_tape_code {pc} {
    if {![rom0]} { return 0 }
    if {$pc >= 0x19DD && $pc <= 0x1B44} { return 1 }
    if {$pc >= 0x4000} { return 0 }
    set sp [reg SP]
    for {set n 0} {$n < 8} {incr n} {
        set a [expr {($sp + 2 * $n) & 0xFFFF}]
        set w [expr {[debug read memory $a] | ([debug read memory [expr {($a + 1) & 0xFFFF}]] << 8)}]
        if {$w >= 0x19DD && $w <= 0x1B44} { return 1 }
    }
    return 0
}

proc hex {width value} { format %0${width}X $value }
proc read_binary {path} {
    set f [open $path rb]
    set data [read $f]
    close $f
    return $data
}
proc write_file {name data} {
    set f [open [file join $::S(snap) $name] wb]
    puts -nonewline $f $data
    close $f
}

# pc, when given, takes the program counter's place: a TAPION call's jump
# table entry.
proc take_snapshot {{pc {}}} {
    set state {}
    foreach r {AF BC DE HL AF2 BC2 DE2 HL2 IX IY SP PC} {
        set v [expr {$r eq "PC" && $pc ne "" ? $pc : [reg $r]}]
        lappend state "[string tolower $r] [hex 4 $v]"
    }
    lappend state "i [hex 2 [reg I]]" "im [hex 1 [reg IM]]" "iff [hex 1 [expr {[reg IFF] & 1}]]"
    set a8 [debug read ioports 0xA8]
    lappend state "a8 [hex 2 $a8]" "ppic [hex 2 [debug read ioports 0xAA]]"
    foreach ps {0 1 2 3} {
        lappend state "sub$ps [expr {[expanded $ps] ? [hex 2 [subslot_reg $ps]] : "-"}]"
    }
    set mapper [expr {"MSX Memory Mapper I/O" in [debug list]}]
    foreach p {0 1 2 3} r {fc fd fe ff} {
        lappend state "$r [expr {$mapper ? [hex 2 [debug read {MSX Memory Mapper I/O} $p]] : "-"}]"
    }
    set v9938 [v9938]
    set regs [expr {$v9938 ? 24 : 8}]
    for {set r 0} {$r < $regs} {incr r} {
        lappend state "vdp$r [hex 2 [debug read {VDP regs} $r]]"
    }
    if {$v9938} {
        for {set r 32} {$r <= 45} {incr r} {
            lappend state "vdp$r [hex 2 [debug read {VDP regs} $r]]"
        }
        for {set c 0} {$c < 16} {incr c} {
            lappend state "pal$c [hex 2 [debug read {VDP palette} [expr {2 * $c}]]][hex 2 [debug read {VDP palette} [expr {2 * $c + 1}]]]"
        }
    }
    set ptr [expr {[debug read {VRAM pointer} 0] | (([debug read {VRAM pointer} 1] & 0x3F) << 8)}]
    if {$v9938} { set ptr [expr {$ptr | (([debug read {VDP regs} 14] & 7) << 14)}] }
    lappend state "vramptr [hex 5 $ptr]" "vramwrite [debug read {VRAM access status} 0]"
    for {set r 0} {$r < 16} {incr r} {
        lappend state "psg$r [hex 2 [debug read {PSG regs} $r]]"
    }
    lappend state "psgsel [hex 2 $::st(psgsel)]"
    lappend state "tapepos [hex 6 $::st(pos)]" "service $::st(service)"

    # The pages selected at the snapshot count as selected during the load.
    note_selection $a8
    # Read every page, the ROMs and VRAM before any test, because the tests
    # write.
    set data {}
    dict for {key _} $::st(sel) {
        lassign [split $key -] ps ss page
        dict set data $key [with_slot $ps $ss $page { read_page $page }]
    }
    set id [exptbl 0]
    set ss [expr {$id & 0x80 ? ($id >> 2) & 3 : "x"}]
    set rom [with_slot [expr {$id & 3}] $ss 0 { read_page 0 }]
    append rom [with_slot [expr {$id & 3}] $ss 1 { read_page 1 }]
    write_file rom.bin $rom
    if {$::S(msx2)} {
        set id $::exbrsa
        set ss [expr {$id & 0x80 ? ($id >> 2) & 3 : "x"}]
        write_file subrom.bin [with_slot [expr {$id & 3}] $ss 0 { read_page 0 }]
    }
    write_file vram.bin [physical_vram]

    set ram {}
    dict for {key bytes} $data {
        lassign [split $key -] ps ss page
        if {[with_slot $ps $ss $page { is_ram $page }]} { dict set ram $key $bytes }
    }
    file mkdir [file join $::S(snap) ram]
    dict for {key bytes} $ram {
        lassign [split $key -] ps ss page
        set seg x
        if {$mapper && [with_slot $ps $ss $page { is_mapper $page }]} {
            set size [with_slot $ps $ss $page { mapper_size $page }]
            set seg [expr {[debug read {MSX Memory Mapper I/O} $page] % $size}]
            if {![info exists sizes($ps-$ss)]} {
                set sizes($ps-$ss) $size
                decide "the mapper in slot $ps-$ss has $size segments"
            }
        }
        write_file [file join ram "$key-$seg.bin"] $bytes
    }

    set f [open [file join $::S(snap) state.txt] w]
    puts $f [join $state \n]
    close $f
    write_log
    quit
}

# log.txt, also after a failure.
proc write_log {} {
    set f [open [file join $::S(snap) log.txt] w]
    foreach e [lsort -real -index 0 [concat $::st(log) $::decisions]] {
        puts $f "[format %.2f [lindex $e 0]] [lindex $e 1]"
    }
    if {[info exists ::st(continue)]} { puts $f "continue [lindex $::st(continue) 0]" }
    close $f
}
