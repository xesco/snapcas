# The capture's watch for a slot register write that cuts off the code that
# made it (docs/INTERNALS.md, The RAM search patch). tools/patches/ramsearch.py
# puts its settings before this file, which follows slots.tcl:
#   ::ramsearch      the bytes of the loader's RAM search
#   ::ramsearch_at   the offset of the patch in them
#   ::ramsearch_old, ::ramsearch_new  the bytes there before and after the patch

# Step 4's watch on the slot register, for each value written, with the value
# before it. A write from code in page 3 that selects another primary slot
# there, where the 4 bytes after its OUT differ, is logged. When the loader's
# RAM search occurs in the tape files, the capture stops with a patch of each
# copy, and capture.py runs it again. Each copy cuts off its code on this
# machine, and a copy on side 2, or in a compilation's later game, runs after
# the snapshot. Otherwise, when the write's code is one of the slot patches'
# forms, its value gets page 3's slot from before the write.
proc ramsearch_watch {value before} {
    set pc [reg pc]
    if {$pc < 0xC000 || (($value ^ $before) & 0xC0) == 0} return
    set next [expr {$pc + 2}]
    if {[read_with $value $next 4] eq [read_with $before $next 4]} return
    set cut "the slot register write of [hex 2 $value] at PC [hex 4 $pc] cuts off its code"
    set lines [lmap place [tape_find $::ramsearch] {
        lassign $place side offset
        patch_line $side [expr {$offset + $::ramsearch_at}] $::ramsearch_old $::ramsearch_new
    }]
    if {[llength $lines]} { stop_with_patch $lines "$cut: the RAM search patched" }
    # Else the write's own code, when it is one of the forms, gets a patch that
    # keeps page 3's slot.
    set new [expr {($value & 0x3F) | ($before & 0xC0)}]
    set lines [patch_lines [slot_code $value $before] $before $new]
    if {[llength $lines]} { stop_with_patch $lines "$cut: patched to [hex 2 $new], which keeps page 3" }
    if {[incr ::run(cutoff_logs)] <= 4} { decide "$cut in page 3, for a patch line" }
}
set ::run(cutoff_logs) 0
hook slot_write ramsearch_watch
