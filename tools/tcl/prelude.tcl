# Procedures that every openMSX run gets (docs/INTERNALS.md, The tools' code).
# tools/msx.py puts them before each script.

# ::run holds a run's state. ::run(phase) names what the script does now: boot
# at first, then the values that a script gives it, and stopping once stop has
# ended the run.
set ::run(phase) boot

# stop ends the run. openMSX's exit takes effect only when the callback that
# calls it has returned, and the other breakpoints and watchpoints of the same
# instruction still run. So stop sets the phase, which makes safe skip every
# callback after it, and leaves its own callback with an error, which safe
# drops.
proc stop {{status 0}} {
  set ::run(phase) stopping
  exit $status
  error "the run has stopped"
}

# script_failed gets the error of a callback that failed. This one prints it
# and ends openMSX with status 1, which tools/msx.py reports with the text. The
# capture and the check have their own, which write the error to their result.
proc script_failed {msg} {
  puts stderr "script error: $msg"
  stop 1
}

# safe runs the body of a callback: of a timer, a breakpoint or a watchpoint.
# It runs nothing once the run is stopping, and it gives the error of a body
# that fails to script_failed. When that fails too, it prints both errors and
# ends openMSX with status 1. later runs a body under safe after emulated
# seconds.
proc safe {body} {
  if {$::run(phase) eq "stopping"} return
  if {![catch {uplevel #0 $body} e] || $::run(phase) eq "stopping"} return
  if {[catch {script_failed $e} e2] && $::run(phase) ne "stopping"} {
    puts stderr "script error: $e, and then: $e2"
    catch {stop 1}
  }
}
proc later {secs body} { after time $secs [list safe $body] }

# screen returns the text screen without its null characters, or nothing in a
# graphics mode, which get_screen cannot read.
proc screen {} {
  if {[catch {get_screen} text]} { return "" }
  string map [list \0 ""] $text
}

# wait_screen looks for a text on the screen now and then each 0.5 seconds. It
# runs then when the screen shows the text, or else when seconds have passed
# without it.
proc wait_screen {text seconds then else} {
  if {[string first $text [screen]] >= 0} { uplevel #0 $then; return }
  if {$seconds <= 0} { uplevel #0 $else; return }
  later 0.5 [list wait_screen $text [expr {$seconds - 0.5}] $then $else]
}

# boot waits for each boot text in turn, up to seconds for each, and presses
# its key, then runs the command done. A menu can show its text before it reads
# the keyboard, so boot presses the key again each second while the text is
# still on the screen, up to 10 times.
proc boot {steps done {seconds 120}} {
  if {[llength $steps] == 0} { uplevel #0 $done; return }
  set text [lindex $steps 0 0]
  wait_screen $text $seconds [list boot_key $steps $done $seconds 0] \
    [list error "the boot text '$text' did not appear within $seconds seconds"]
}
proc boot_key {steps done seconds tries} {
  lassign [lindex $steps 0] text key
  if {[string first $text [screen]] < 0} {
    later 0.5 [list boot [lrange $steps 1 end] $done $seconds]
  } elseif {$tries < 10} {
    eval $key
    later 1 [list boot_key $steps $done $seconds [expr {$tries + 1}]]
  } else {
    error "the boot key for '$text' did not take effect"
  }
}

# at_prompt waits for DOS's prompt, up to seconds, then types a text once,
# because the prompt stays on the screen, and runs the command done. The prompt
# and the text come as hex, so that they need no quoting.
proc at_prompt {prompt hex done {seconds 120}} {
  set text [binary format H* $prompt]
  wait_screen $text $seconds [list typed_at_prompt $hex $done] \
    [list error "DOS's prompt '$text' did not appear within $seconds seconds"]
}
proc typed_at_prompt {hex done} {
  type [binary format H* $hex]
  uplevel #0 $done
}
