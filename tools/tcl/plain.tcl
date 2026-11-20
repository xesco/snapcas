# Plain openMSX tape run for tools/plain.py. Expects ::P(tape), ::P(load),
# ::P(run_after), ::P(after_boot), ::P(after_tape), and ::P(out).

proc plain {} {
  wait_screen Ok 120 { later $::P(after_boot) plain_load } \
    { error "BASIC's Ok did not appear within 120 seconds" }
}

proc plain_load {} {
  set ::autoruncassettes off
  cassetteplayer insert $::P(tape)
  set len [cassetteplayer getlength]
  type [binary format H* $::P(load)]
  if {$::P(run_after) ne ""} {
    later [expr {$len + 5}] { type [binary format H* $::P(run_after)] }
  }
  later [expr {$len + $::P(after_tape)}] plain_screen
}

proc plain_screen {} {
  write_text $::P(out) [screen]
  stop
}
