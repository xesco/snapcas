# Procedures that every openMSX run gets (docs/INTERNALS.md, The tools' code).
# tools/msx.py puts them before each script. screen returns the text screen
# without its null characters, or nothing in a graphics mode, which get_screen
# cannot read. boot waits for each boot text in turn and presses its key, then
# runs the command done. A menu can show its text before it reads the keyboard,
# so boot presses the key again each second while the text is still on the
# screen, up to 10 times.
proc screen {} {
  if {[catch {get_screen} text]} { return "" }
  string map [list \0 ""] $text
}
proc boot {steps done {tries 0}} {
  if {[llength $steps] == 0} { eval $done; return }
  lassign [lindex $steps 0] text key
  if {[string first $text [screen]] < 0} {
    if {$tries > 0} {
      after time 0.5 [list boot [lrange $steps 1 end] $done]
    } else {
      after time 0.5 [list boot $steps $done]
    }
  } elseif {$tries < 10} {
    eval $key
    after time 1 [list boot $steps $done [expr {$tries + 1}]]
  } else {
    error "boot: the key for '$text' did not take effect"
  }
}
# at_prompt waits for DOS's prompt, then types a text once, because the prompt
# stays on the screen, and runs the command done. The prompt and the text come
# as hex, so that they need no quoting.
proc at_prompt {prompt hex done {tries 0}} {
  set text [binary format H* $prompt]
  if {[string first $text [screen]] >= 0} {
    type [binary format H* $hex]
    eval $done
  } elseif {$tries < 240} {
    after time 0.5 [list at_prompt $prompt $hex $done [expr {$tries + 1}]]
  } else {
    error "at_prompt: '$text' did not appear within 120 seconds"
  }
}
