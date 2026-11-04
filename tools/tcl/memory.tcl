# Procedures that the capture and the check share (docs/INTERNALS.md, The tools'
# code): the CPU's view of memory with a slot selected, and the read of VRAM.

# The CPU's view of memory, after selecting a slot in a page (INTERNALS.md, RAM).

# EXPTBL at FCC1h: bit 7 of each slot's byte is set when it is expanded. The
# capture reads it once, in step 2, because a game can overwrite page 3.
proc exptbl {ps} {
    if {[info exists ::exptbl]} { return [lindex $::exptbl $ps] }
    debug read memory [expr {0xFCC1 + $ps}]
}
proc expanded {ps} { expr {([exptbl $ps] & 0x80) != 0} }
proc read_exptbl {} {
    set ::exptbl [lmap ps {0 1 2 3} {debug read memory [expr {0xFCC1 + $ps}]}]
}

# A slot ID's primary slot and subslot, "x" when the slot is not expanded.
proc slot_parts {id} {
    list [expr {$id & 3}] [expr {$id & 0x80 ? ($id >> 2) & 3 : "x"}]
}

# The 16-bit word at an address, low byte first.
proc word_at {a} {
    expr {[debug read memory $a] | ([debug read memory [expr {($a + 1) & 0xFFFF}]] << 8)}
}

# Whether page 0 selects the slot of a slot ID. sub_of gives an expanded
# slot's subslot register: the check reads it, while the capture keeps track
# of it, because a read writes port A8h, which the capture watches.
proc page0_selects {id sub_of} {
    lassign [slot_parts $id] ps ss
    if {([debug read ioports 0xA8] & 3) != $ps} { return 0 }
    if {$ss eq "x"} { return 1 }
    expr {([{*}$sub_of $ps] & 3) == $ss}
}

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

# n bytes at address, read with the slot register at a8.
proc read_with {a8 address n} {
    set now [debug read ioports 0xA8]
    debug write ioports 0xA8 $a8
    set bytes [debug read_block memory [expr {$address & 0xFFFF}] $n]
    debug write ioports 0xA8 $now
    return $bytes
}

proc v9938 {} { expr {[debug size "physical VRAM"] > 0x4000} }

# VRAM's cells. openMSX shows a V9938's VRAM through the addressing of
# register 8's bit 3, VR, which a game can clear (FORMATS.md, Snapshot files),
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
