# The capture's watch for a slot register write that cuts off the code that
# made it (docs/DESIGN.md, The RAM search patch). tools/capture.py loads it
# after slots.tcl, and sets ::ramsearch, ::ramsearch_at, ::ramsearch_old and
# ::ramsearch_new from patches/ramsearch.py.

# Step 4's watch on the slot register, for each value written, with the value
# before it. A write from code in page 3 that selects another primary slot
# there, where the 4 bytes after its OUT differ, is logged. When the loader's
# RAM search occurs in the CAS files, the capture writes a patch of each copy to
# newpatch.txt and stops, and capture.py runs it again. Each copy cuts off its
# code on this machine, and a copy on side 2, or in a compilation's later game,
# runs after the snapshot.
proc ramsearch_watch {value before} {
    set pc [reg pc]
    if {$pc < 0xC000 || (($value ^ $before) & 0xC0) == 0} return
    set next [expr {($pc + 2) & 0xFFFF}]
    if {[read_with $value $next 4] eq [read_with $before $next 4]} return
    set found [cas_find $::ramsearch]
    if {[llength $found]} {
        set f [open [file join $::S(snap) newpatch.txt] w]
        foreach place $found {
            lassign $place side offset
            puts $f [format "patch side%d:%X %s > %s" $side [expr {$offset + $::ramsearch_at}] \
                $::ramsearch_old $::ramsearch_new]
        }
        close $f
        decide "the slot register write of [hex 2 $value] at PC [hex 4 $pc] cuts off its code: the RAM search patched"
        catch write_log
        quit
    }
    if {[incr ::cutoff_logs] <= 4} {
        decide "the slot register write of [hex 2 $value] at PC [hex 4 $pc] cuts off its code in page 3, for a patch line"
    }
}
set ::cutoff_logs 0
