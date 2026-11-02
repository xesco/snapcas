# Procedures of the capture (docs/DESIGN.md, Capture). tools/capture.py puts
# the game file's settings and memory.tcl before them, patches/slots.tcl and
# patches/ramsearch.tcl after them, and then the steps' start.

# ---- The steps (DESIGN.md, Capture) ----
#
# capture.py sets these before the procedures:
#   ::S(snap)     the snapshot folder
#   ::S(boot)     the boot steps, for boot (tools/msx.py)
#   ::S(afterboot) what follows them: wait_ok, after BASIC typed at DOS's prompt
#                 on a machine that boots DOS from its own disk
#   ::S(tape)     the tape file of side 1, CAS or TSX
#   ::S(cmd)      the load command; ::S(cload) is 1 for CLOAD, then RUN
#   ::S(headers)  the offsets of side 1's headers
#   ::S(needed)   the end of the last block that the load must read
#   ::S(side2tape) side 2's tape file, or "" without a side 2
#   ::S(s1len)    side 1's length, padded to a multiple of 8: side 2's start
#   ::S(headers2) the positions of side 2's headers, from side 1's start
#   ::S(nosvc)    1 when the game file has service no
#   ::S(keys)     [list time tcl] pairs, times from the load command
#   ::S(lastkey)  the last keys time
#   ::S(tries)    [list name tcl] pairs: the keys that may continue a load
#   ::S(snapat)   the snapshot at time, or ""
#   ::S(state)    the name of the capture's savestate, its own so that
#                 captures can run side by side
#   ::S(home)     openMSX's home folder, whose savestates/ folder a rewind reads
#
# ::st holds the state that the capture logs. A rewind puts back its copy
# from the savestate's moment, because openMSX's loadstate restores the machine
# but neither Tcl variables nor timers.
#
# The run's other variables:
#   ::booted      1 once BASIC's Ok has appeared (step 1)
#   ::exptbl, ::exbrsa  EXPTBL and the sub-ROM's slot ID, read in step 2
#   ::t0          the moment of the load command; ::elapsed the emulated
#                 seconds since then, across rewinds
#   ::restarts    the rewinds so far
#   ::since       when the motor last stopped, or "" while it runs (step 5)
#   ::saved, ::saved_st  whether the wait has a savestate, and ::st then
#   ::tapion_st, ::saved_tapion_st  ::st at the last TAPION entry, and at the
#                 moment of the saved wait, for a rewind to it
#   ::trying, ::tried_at  the keys left to try, and when the last one went
#   ::decisions   what the capture decided, kept across rewinds
#   ::done, ::accepted, ::irq_probe, ::irq_bp, ::fallback_pc  the snapshot's
#                 wait for an interrupt (step 6)

proc quit {} {
    catch { delete_savestate $::S(state) }
    catch { delete_savestate $::S(state)-tapion }
    catch { delete_savestate $::S(state)-tapion-saved }
    exit
}
proc savestate_file {name} { file join $::S(home) savestates $name.oms }
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

# Whether page 0 selects the main ROM, whose slot ID is EXPTBL's first byte,
# by the tracked subslot registers.
proc tracked_sub {ps} { return $::st(sub$ps) }
proc rom0 {} { page0_selects [exptbl 0] tracked_sub }

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
proc on_a8 {value} {
    set before $::st(a8)
    set ::st(a8) $value
    note_selection $value
    slot_watch $value $before
    ramsearch_watch $value $before
}

# Each TAPION call's entry is saved, with ::st, as a moment for the snapshot
# when it would otherwise come inside the BIOS's tape routines (step 6).
proc on_tapion {} {
    if {!$::S(nosvc)} {
        savestate $::S(state)-tapion
        set ::tapion_st [array get ::st]
    }
    incr ::st(tapion)
    # A TAPION call at side 1's end, with a side 2: the player turns the tape
    # over, so side 2 goes in, at its start, and TAPION finds its first header.
    if {$::S(side2tape) ne "" && !$::st(side2in) && [at_end]} { insert_side2 $::S(s1len) }
    set next ""
    foreach h [concat $::S(headers) $::S(headers2)] { if {$h >= $::st(pos)} { set next $h; break } }
    set ::st(pos) [expr {$next eq "" ? $::st(pos) : $next + 8}]
    logev "TAPION, tape position $::st(pos)"
}
proc on_tapin {} { incr ::st(tapin); incr ::st(pos) }
# Side 2 goes in, with the tape service's position pos.
proc insert_side2 {pos} {
    cassetteplayer insert $::S(side2tape)
    set ::st(side2in) 1
    set ::st(pos) $pos
    logev "side 2 inserted"
}
# A game that reads on past side 1's end, with the motor on and the CPU waiting
# in the BIOS's tape code, waits for side 2: the player turns the tape over, so
# side 2 goes in, and the read goes on after side 2's first header. A motor
# that a game only switches, with no read, does not turn the tape over.
proc turn_over {} {
    if {$::S(side2tape) eq "" || $::st(side2in) || ![motor_on] || ![at_end]} { return }
    if {![in_tape_code [reg PC]]} { return }
    insert_side2 [expr {[lindex $::S(headers2) 0] + 8}]
}

# The tape service's tape pads each block to a multiple of 8 bytes, so a block
# counts as read when at most 7 bytes of it are left.
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
    read_exptbl
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
proc on_reset {} {
    decide "the game reset the machine [format %.2f [expr {[now] - $::t0}]] seconds after the load command"
}
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
    slot_start
    # TAPION and TAPIN: the addresses that the jump table entries 00E1h and
    # 00E4h jump to.
    set tapion [word_at 0xE2]
    set tapin [word_at 0xE5]
    debug set_bp $tapion {[rom0]} {safe on_tapion}
    debug set_bp $tapin {[rom0]} {safe on_tapin}
    # The BIOS's reset routine, where 0000h's DI / JP jumps: a loader that has
    # crashed or rebooted the machine can also jump there itself (DESIGN.md,
    # Capture, step 4).
    set reset [word_at 2]
    debug set_bp $reset {[rom0]} {safe on_reset}
    debug set_watchpoint write_io 0xA8 {} {safe {on_a8 $::wp_last_value}}
    debug set_watchpoint write_mem 0xFFFF {} {safe {on_ffff $::wp_last_value}}
    cassetteplayer insert $::S(tape)
    set ::t0 [now]
    set ::restarts 0
    type "$::S(cmd)\r"
    logev "typed $::S(cmd)"
    schedule_keys
    if {$::S(snapat) ne ""} {
        later $::S(snapat) step6
        if {$::S(cload)} { set ::since ""; run_after_cload }
        if {$::S(side2tape) ne ""} { watch_turn }
    } else {
        start_wait
    }
}

# With snapshot at, side 2 still goes in when side 1 runs out.
proc watch_turn {} { turn_over; later 0.1 watch_turn }

# After CLOAD, the program runs when the capture types RUN, once.
proc type_run {} {
    set ::st(ran) 1
    type "RUN\r"
    logev "typed RUN"
}

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
            type_run
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
            type_run
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
                             (![side1_read] || $::S(side2tape) ne "")}]
    if {[reg IM] == 2} {
        set v [expr {[reg I] * 256 + 0xFF}]
        set handler [word_at $v]
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
        set w [word_at $a]
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
    # The player's position and side, for the non-standard blocks that the
    # game has read by its own loader (DESIGN.md, Tape files).
    lappend state "tapetime [format %.2f [cassetteplayer getpos]]" "tapeside [expr {$::st(side2in) ? 2 : 1}]"

    # The pages selected at the snapshot count as selected during the load.
    note_selection $a8
    # Read every page, the ROMs and VRAM before any test, because the tests
    # write.
    set data {}
    dict for {key _} $::st(sel) {
        lassign [split $key -] ps ss page
        dict set data $key [with_slot $ps $ss $page { read_page $page }]
    }
    lassign [slot_parts [exptbl 0]] ps ss
    set rom [with_slot $ps $ss 0 { read_page 0 }]
    append rom [with_slot $ps $ss 1 { read_page 1 }]
    write_file rom.bin $rom
    if {$::S(msx2)} {
        lassign [slot_parts $::exbrsa] ps ss
        write_file subrom.bin [with_slot $ps $ss 0 { read_page 0 }]
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
