# Procedures of the capture (docs/INTERNALS.md, Capture). tools/capture.py puts
# the game file's settings and memory.tcl before them, the settings and the Tcl
# file of each patch kind that works in the capture after them
# (tools/patches/), and then the start, safe step1.
#
# capture.py sets these before the procedures:
#   ::S(snap)     the snapshot folder
#   ::S(boot)     the boot steps, for boot (prelude.tcl)
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
#   ::S(state)    the start of the names of the capture's savestates, its own
#                 so that captures can run side by side. capture.py deletes
#                 them
#   ::S(home)     openMSX's home folder, whose savestates/ folder holds them
#
# ::st holds the state that follows the machine: what the capture logs and
# tracks. A rewind puts back its copy from the saved moment, because openMSX's
# loadstate restores the machine but neither Tcl variables nor timers.
#
# ::run holds the rest of the run's state, which a rewind leaves alone:
#   phase       boot until BASIC's Ok (step 1); load while the capture prepares
#               and follows the load (steps 2 to 5); try during a key try of
#               step 5; wait in step 6, until the snapshot's moment; snap while
#               take_snapshot reads the machine; stopping once the capture has
#               ended (prelude.tcl)
#   msx2, exbrsa  1 on an MSX2, and the sub-ROM's slot ID, read in step 2
#   t0          the moment of the load command
#   elapsed     the emulated seconds since then, counted across rewinds
#   restarts    the restarts of step 5 so far
#   since       when the motor last stopped, or "" while it runs (step 5)
#   saved       whether the wait has a saved moment
#   moment,<name>  ::st at the moment saved under that name
#   trying, tried_at  the keys left to try, and when the last one went
#   decisions   what the capture decided, kept across rewinds
#   accepted, irq_probe, irq_bp, fallback_pc  the snapshot's wait for an
#               interrupt (step 6)
#   psg         the watchpoints on the PSG's ports
array set ::run {msx2 0 t0 0 elapsed 0 restarts 0 since "" saved 0 decisions {} psg {}}
set ::st(log) {}

proc now {} { machine_info time }
# The emulated seconds since the load command.
proc since_load {} { expr {[now] - $::run(t0)} }
# Two logs: ::st(log) follows the machine and goes back with a rewind, and
# ::run(decisions) keeps what the capture decided, across rewinds. log.txt holds
# both, in time order.
proc logev {msg} { lappend ::st(log) [list [since_load] $msg] }
proc decide {msg} { lappend ::run(decisions) [list [since_load] $msg] }

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
proc write_lines {name lines} {
    set f [open [file join $::S(snap) $name] w]
    foreach line $lines { puts $f $line }
    close $f
}

# log.txt, also after a failure, with what the capture has logged by then.
proc write_log {} {
    set lines {}
    foreach e [lsort -real -index 0 [concat $::st(log) $::run(decisions)]] {
        lappend lines "[format %.2f [lindex $e 0]] [lindex $e 1]"
    }
    if {[info exists ::st(continue)]} { lappend lines "continue [lindex $::st(continue) 0]" }
    write_lines log.txt $lines
}

# fail stops the capture with an error: error.txt holds it, and the log's last
# line holds it with the screen's text. An error of a callback stops the
# capture in the same way.
proc fail {msg} {
    write_lines error.txt [list "capture: $msg"]
    catch { decide "the capture stops: $msg, screen: [screen_lines]" }
    catch write_log
    stop
}
proc script_failed {msg} { fail $msg }

# Emulated seconds since the load command, counted across rewinds.
proc tick {secs} {
    set ::run(elapsed) [expr {$::run(elapsed) + $secs}]
    if {$::run(elapsed) > 3600} { fail "the load ran for more than 3600 seconds" }
}

proc motor_on {} { expr {([debug read ioports 0xAA] & 0x10) == 0} }
proc at_end {} {
    expr {[cassetteplayer getpos] >= [cassetteplayer getlength] - 0.01}
}
proc screen_lines {} {
    if {[string trim [screen]] eq ""} { return "a graphics screen" }
    join [lmap l [split [screen] \n] {expr {[string trim $l] eq "" ? [continue] : [string trim $l]}}] " | "
}

# ---- The patch kinds (INTERNALS.md, The tools' code) ----
#
# A patch kind that works in the capture adds a procedure to a hook's list:
#   start       runs in step 3, before the load command
#   slot_write  runs in step 4's watch on the slot register, for each value
#               written, with the value before it
set ::hooks(start) {}
set ::hooks(slot_write) {}
proc hook {name procedure} { lappend ::hooks($name) $procedure }
proc run_hooks {name args} { foreach procedure $::hooks($name) { $procedure {*}$args } }

# A patch line of a tape file: its side and offset, and the old and the new
# bytes, each a list of numbers.
proc hex_bytes {bytes} { join [lmap b $bytes {format %02X $b}] }
proc patch_line {side offset old new} {
    format "patch side%d:%X %s > %s" $side $offset [hex_bytes $old] [hex_bytes $new]
}
# Stops the capture with a patch of the tape that a kind has found: its lines
# go to newpatch.txt, and why to the log. capture.py adds the lines to the
# tape's patches and runs the capture again on the patched tape (INTERNALS.md,
# Slot patches).
proc stop_with_patch {lines why} {
    write_lines newpatch.txt $lines
    decide $why
    catch write_log
    stop
}

# ---- A saved moment ----
#
# A moment is the machine, which savestate saves, and ::st then. openMSX's
# loadstate restores the machine but not the script's variables, and it removes
# the watchpoints, though it keeps the breakpoints. So moment_load puts ::st
# back and sets the PSG's watchpoints again, which only keep two values. The
# watchpoints on the slot register and on FFFFh stay removed (INTERNALS.md,
# Capture, step 5).
proc moment_file {name} { file join $::S(home) savestates $::S(state)-$name.oms }
proc moment_saved {name} { info exists ::run(moment,$name) }
proc moment_forget {name} { unset -nocomplain ::run(moment,$name) }
proc moment_save {name} {
    savestate $::S(state)-$name
    set ::run(moment,$name) [array get ::st]
}
proc moment_copy {from to} {
    file copy -force [moment_file $from] [moment_file $to]
    set ::run(moment,$to) $::run(moment,$from)
}
proc moment_load {name} {
    loadstate $::S(state)-$name
    array unset ::st
    array set ::st $::run(moment,$name)
    watch_psg
}

# ---- What the capture tracks (INTERNALS.md, Capture, steps 1 and 4) ----

# The PSG register selected last, from port A0h, and the last value written to
# register 15, from port A1h, which openMSX does not show.
proc watch_psg {} {
    foreach wp $::run(psg) { catch { debug remove_watchpoint $wp } }
    set ::run(psg) [list \
        [debug set_watchpoint write_io 0xA0 {} {safe {set ::st(psgsel) $::wp_last_value}}] \
        [debug set_watchpoint write_io 0xA1 {} {safe {if {$::st(psgsel) == 15} {set ::st(psg15) $::wp_last_value}}}]]
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
# The watchpoints on the slot register and on FFFFh. While they are set, the
# capture's own slot switches also pass them: those of take_snapshot, in a
# capture without a rewind. They are not the game's writes, so the snap phase
# leaves them out.
proc on_ffff {value} {
    if {$::run(phase) eq "snap"} return
    set a8 [debug read ioports 0xA8]
    set ps [expr {($a8 >> 6) & 3}]
    if {$::st(sub$ps) >= 0} {
        set ::st(sub$ps) $value
        note_selection $a8
    }
}
proc on_a8 {value} {
    if {$::run(phase) eq "snap"} return
    set before $::st(a8)
    set ::st(a8) $value
    note_selection $value
    run_hooks slot_write $value $before
}

# The tape position goes past the next header at or after it, as TAPION's
# does.
proc next_header {} {
    foreach h [concat $::S(headers) $::S(headers2)] {
        if {$h >= $::st(pos)} { set ::st(pos) [expr {$h + 8}]; return }
    }
}
# Each TAPION call's entry is saved as a moment, for the snapshot when it would
# otherwise come inside the BIOS's tape routines (step 6).
proc on_tapion {} {
    if {!$::S(nosvc)} { moment_save tapion }
    incr ::st(tapion)
    # A TAPION call at side 1's end, with a side 2: the player turns the tape
    # over, so side 2 goes in, at its start, and TAPION finds its first header.
    if {$::S(side2tape) ne "" && !$::st(side2in) && [at_end]} { insert_side2 }
    next_header
    logev "TAPION, tape position $::st(pos)"
}
# TAPIN reads the byte at the tape position. A header there is a tone on the
# tape, which TAPIN waits through, so the position first goes past its 8 bytes,
# as the tape service's TAPIN does (src/tape.inc, tapin): a game can read on
# into the next block without a TAPION call.
proc on_tapin {} {
    incr ::st(tapin)
    if {$::st(pos) in $::S(headers) || $::st(pos) in $::S(headers2)} { incr ::st(pos) 8 }
    incr ::st(pos)
}
# Side 2 goes in, at its start in the tape service's tape.
proc insert_side2 {} {
    cassetteplayer insert $::S(side2tape)
    set ::st(side2in) 1
    set ::st(pos) $::S(s1len)
    logev "side 2 inserted"
}
# A game that reads on past side 1's end, with the motor on and the CPU waiting
# in the BIOS's tape code, waits for side 2: the player turns the tape over, so
# side 2 goes in, and the read goes on after side 2's first header, or at side
# 2's start when it holds no standard block. A motor that a game only switches,
# with no read, does not turn the tape over.
proc turn_over {} {
    if {$::S(side2tape) eq "" || $::st(side2in) || ![motor_on] || ![at_end]} { return }
    if {![in_tape_code [reg PC]]} { return }
    insert_side2
    next_header
}

# The BIOS's reset routine. The log keeps a reset across a rewind, so that it
# holds the resets of the seconds after the snapshot's moment, which the check
# looks for (INTERNALS.md, Check, point 3). A reset during a key try follows the
# machine instead, and goes with the try's rewind, because the restored game
# gets no such key.
proc on_reset {} {
    set msg "the game reset the machine [format %.2f [since_load]] seconds after the load command"
    if {$::run(phase) eq "try"} { logev $msg } else { decide $msg }
}

# The tape service's tape pads each block to a multiple of 8 bytes, so a block
# counts as read when at most 7 bytes of it are left.
proc side1_read {} {
    expr {$::st(tapion) > 0 && $::st(tapin) > 0 && $::st(pos) >= $::S(needed) - 7}
}

# ---- The steps (INTERNALS.md, Capture) ----

# 1. Watch the PSG's ports, boot, pass the boot menu, wait for BASIC's Ok.
proc step1 {} {
    set ::st(psgsel) 0
    set ::st(psg15) -1
    watch_psg
    later 120 { if {$::run(phase) eq "boot"} { fail "BASIC's Ok did not appear within 120 seconds" } }
    boot $::S(boot) $::S(afterboot)
}
# The disk system can still be busy just after BASIC's Ok (a load that
# starts 5 seconds after the Carnivore2's boot behaves differently from one that
# starts 9 seconds after it), so the capture waits 10 seconds, as a person
# would, before it goes on.
proc wait_ok {} {
    wait_screen "Ok" 120 { set ::run(phase) load; later 10 step2 } \
        { fail "BASIC's Ok did not appear within 120 seconds" }
}

# 2. Remove the disk system from page 3, and set HIMEM as on a cassette
#    machine.
proc step2 {} {
    set v [debug read memory 0x002D]
    if {$v > 1} { fail "the machine is not an MSX1 or an MSX2: 002Dh holds $v" }
    set ::run(msx2) $v
    read_exptbl
    # EXBRSA at FAF8h: the slot ID of the MSX2 sub-ROM.
    set ::run(exbrsa) [debug read memory 0xFAF8]
    for {set a 0xFD9A} {$a <= 0xFFC9} {incr a 5} { debug write memory $a 0xC9 }
    foreach a {0xFFCA 0xFFCF 0xFFD4} { debug write memory $a 0xC9 }
    debug write memory 0xF37D 0
    for {set a 0xFCC9} {$a <= 0xFD88} {incr a} { debug write memory $a 0 }
    type "CLEAR200,&HF380\r"
    later 3 step3
}

# 3. Note the slots, run the patch kinds' start, which makes the slot map,
#    insert side 1, and type the load command.
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
    set ::run(t0) [now]
    run_hooks start
    cassetteplayer insert $::S(tape)
    type "$::S(cmd)\r"
    logev "typed $::S(cmd)"
    step4
}

# 4. Follow the tape position, the slots and the resets, and press the keys,
#    each at its time from the load command.
proc step4 {} {
    # TAPION and TAPIN: the addresses that the jump table entries 00E1h and
    # 00E4h jump to.
    debug set_bp [word_at 0xE2] {[rom0]} {safe on_tapion}
    debug set_bp [word_at 0xE5] {[rom0]} {safe on_tapin}
    # The BIOS's reset routine, where 0000h's DI / JP jumps: a loader that has
    # crashed or rebooted the machine can also jump there itself.
    debug set_bp [word_at 2] {[rom0]} {safe on_reset}
    debug set_watchpoint write_io 0xA8 {} {safe {on_a8 $::wp_last_value}}
    debug set_watchpoint write_mem 0xFFFF {} {safe {on_ffff $::wp_last_value}}
    schedule_keys
    step5
}
# The keys still to come after a rewind are scheduled again.
proc schedule_keys {} {
    foreach {t tcl} $::S(keys) {
        set due [expr {$::run(t0) + $t - [now]}]
        if {$due > 0} { later $due [list press_key $t $tcl] }
    }
}
proc press_key {t tcl} { logev "keys $t"; eval $tcl }

# 5. Wait for the load to stop, then decide. With snapshot at, wait for that
#    time instead.
proc step5 {} {
    set ::run(phase) load
    set ::run(since) ""
    set ::run(saved) 0
    if {$::S(snapat) eq ""} { poll; return }
    later $::S(snapat) step6
    if {$::S(cload)} { run_after_cload }
    if {$::S(side2tape) ne ""} { watch_turn }
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
        set ::run(since) ""
    } elseif {$::st(on_seen)} {
        if {$::run(since) eq ""} { set ::run(since) [now] }
        if {[now] - $::run(since) >= 1} {
            type_run
            return
        }
    }
    later 0.1 run_after_cload
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
        set ::run(since) ""
        set ::run(saved) 0
    } else {
        if {$::run(since) eq ""} { set ::run(since) [now] }
        set off [expr {[now] - $::run(since)}]
        if {$::S(cload) && !$::st(ran) && $::st(on_seen) && $off >= 1} {
            type_run
            set ::run(since) ""
        } elseif {!$::run(saved) && $off >= 1} {
            moment_save wait
            set ::run(saved) 1
            # The last TAPION entry as at this moment, for a rewind to it.
            if {[moment_saved tapion]} { moment_copy tapion wait-tapion } else { moment_forget wait-tapion }
        } elseif {$off >= 30 && [since_load] >= $::S(lastkey)} {
            wait_ended
            return
        }
    }
    later 0.1 poll
}

# Back to the wait's saved moment. The last TAPION entry is then the one at
# that moment: one saved after it is not in the new run.
proc rewind {} {
    if {[moment_saved wait-tapion]} { moment_copy wait-tapion tapion } else { moment_forget tapion }
    moment_load wait
    schedule_keys
}

proc wait_ended {} {
    rewind
    decide "load stopped at tape position $::st(pos), the cassette player at [format %.1f [cassetteplayer getpos]] of [format %.1f [cassetteplayer getlength]] seconds, screen: [screen_lines]"
    if {[side1_read]} { step6; return }
    set ::run(trying) $::S(tries)
    try_next
}
proc try_next {} {
    rewind
    if {[llength $::run(trying)] == 0} {
        set ::run(phase) load
        decide "no key continues the load"
        step6
        return
    }
    lassign [lindex $::run(trying) 0] name tcl
    set ::run(trying) [lrange $::run(trying) 1 end]
    set ::run(phase) try
    eval $tcl
    set ::run(tried_at) [now]
    watch_motor $name
}
# A key continues the load when the motor starts, unless the tape is at its
# end, where a game can start the motor and read nothing.
proc watch_motor {name} {
    tick 0.1
    if {[motor_on] && ![at_end]} {
        decide "continue $name"
        lappend ::st(continue) $name
        if {[incr ::run(restarts)] > 20} { fail "step 5 restarted more than 20 times" }
        step5
        return
    }
    if {[now] - $::run(tried_at) >= 10} { try_next; return }
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
    set ::run(phase) wait
    set ::st(service) [expr {!$::S(nosvc) && $::st(tapion) > 0 && $::st(tapin) > 0 &&
                             (![side1_read] || $::S(side2tape) ne "")}]
    if {[reg IM] == 2} {
        set v [expr {[reg I] * 256 + 0xFF}]
        set handler [word_at $v]
    } else {
        set handler 0x0038
    }
    set ::run(accepted) 0
    set ::run(irq_probe) [debug probe set_bp z80.acceptIRQ {} {set ::run(accepted) 1}]
    set ::run(irq_bp) [debug set_bp $handler {$::run(accepted)} {safe at_handler}]
    later 1 fallback
}
proc at_handler {} {
    set ::run(accepted) 0
    if {$::run(phase) ne "wait" || ![vdp_quiet]} { return }
    decide "snapshot at an interrupt's entry"
    take_snapshot
}
# Without an interrupt within 1 second, the snapshot is taken where the CPU
# is. A halted CPU has its program counter just after the HALT (76h) and does
# not move.
proc fallback {} {
    if {$::run(phase) ne "wait"} { return }
    debug probe remove_bp $::run(irq_probe)
    debug remove_bp $::run(irq_bp)
    set ::run(fallback_pc) [reg PC]
    later 0.02 [list fallback2 0]
}
# The fallback's snapshot needs a quiet VDP as well: a game that keeps its
# interrupts off can be between the two writes that set a VDP register, or in a
# V9938 command. So fallback2 looks again each QUIET_STEP seconds, up to
# QUIET_TRIES times, and then takes the snapshot as it is, with a line in the
# log.
set ::QUIET_STEP 0.003
set ::QUIET_TRIES 100
proc fallback2 {tries} {
    set pc [reg PC]
    if {$tries == 0 && $pc == $::run(fallback_pc) &&
        [debug read memory [expr {($pc - 1) & 0xFFFF}]] == 0x76} {
        fail "the CPU is halted with no interrupt, at [format %04X $pc]"
    }
    if {$::st(service) && [in_tape_code $pc]} {
        # T0 replaces that code, so the snapshot goes back to the last TAPION
        # call's entry, where the call has not run: at its jump table entry,
        # the restored game reaches the tape service.
        if {![moment_saved tapion]} {
            fail "the CPU is in the BIOS's tape code, at [format %04X $pc], with no TAPION call saved"
        }
        set service $::st(service)
        moment_load tapion
        set ::st(service) $service
        decide "snapshot at the last TAPION call's entry, because the CPU is in the BIOS's tape code"
        take_snapshot 0x00E1
        return
    }
    set waited [format %.3f [expr {$tries * $::QUIET_STEP}]]
    if {![vdp_quiet]} {
        if {$tries < $::QUIET_TRIES} {
            later $::QUIET_STEP [list fallback2 [expr {$tries + 1}]]
            return
        }
        decide "the VDP is not quiet after $waited seconds more"
    } elseif {$tries > 0} {
        decide "the snapshot waited $waited seconds for a quiet VDP"
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

# Reads the machine, writes the snapshot's files and the log, and ends the
# capture. pc, when given, takes the program counter's place: a TAPION call's
# jump table entry.
proc take_snapshot {{pc {}}} {
    set ::run(phase) snap
    set state [machine_state]
    if {$pc ne ""} { dict set state pc [hex 4 $pc] }
    # While register 7's bit 7 is clear, I/O port B is an input, and register
    # 15 reads its pins, FFh, not the value written, which the restore writes
    # with port B an output. So register 15 is then the last value written.
    if {!([debug read {PSG regs} 7] & 0x80) && $::st(psg15) >= 0} { dict set state psg15 [hex 2 $::st(psg15)] }
    dict set state psgsel [hex 2 $::st(psgsel)]
    dict set state tapepos [hex 6 $::st(pos)]
    dict set state service $::st(service)
    # The player's position and side, for the non-standard blocks that the
    # game has read by its own loader (INTERNALS.md, Tape files).
    dict set state tapetime [format %.2f [cassetteplayer getpos]]
    dict set state tapeside [expr {$::st(side2in) ? 2 : 1}]

    # The pages selected at the snapshot count as selected during the load.
    note_selection [debug read ioports 0xA8]
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
    if {$::run(msx2)} {
        lassign [slot_parts $::run(exbrsa)] ps ss
        write_file subrom.bin [with_slot $ps $ss 0 { read_page 0 }]
    }
    write_file vram.bin [physical_vram]

    set ram {}
    dict for {key bytes} $data {
        lassign [split $key -] ps ss page
        if {[with_slot $ps $ss $page { is_ram $page }]} { dict set ram $key $bytes }
    }
    # A mapper's page gets its segment in its file's name: the mapper
    # register's value modulo the mapper's size, which state.txt keeps for the
    # build.
    set mapper [expr {"MSX Memory Mapper I/O" in [debug list]}]
    file mkdir [file join $::S(snap) ram]
    dict for {key bytes} $ram {
        lassign [split $key -] ps ss page
        set seg x
        if {$mapper && [with_slot $ps $ss $page { is_mapper $page }]} {
            if {![info exists sizes($ps-$ss)]} {
                set sizes($ps-$ss) [with_slot $ps $ss $page { mapper_size $page }]
                decide "the mapper in slot $ps-$ss has $sizes($ps-$ss) segments"
                dict set state mapper$ps-$ss [hex 2 $sizes($ps-$ss)]
            }
            set seg [expr {[debug read {MSX Memory Mapper I/O} $page] % $sizes($ps-$ss)}]
        }
        write_file [file join ram "$key-$seg.bin"] $bytes
    }

    write_lines state.txt [lmap {name value} $state {string cat "$name $value"}]
    write_log
    stop
}
