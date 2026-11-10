# Notes

This page keeps the evidence behind the design: the games, the counts and the
findings that taught each rule, under the name of the section that holds the rule,
in [INTERNALS.md](INTERNALS.md) or, for the decisions and the limits, in
[DESIGN.md](DESIGN.md). A rule stays on its page, and its examples come here, so the
pages read short and the evidence is not lost. The last two sections hold the rules
that changed, and the questions that are still open.

## Tape files

In a collection of 2354 TSX files, 327 hold blocks that a CAS file cannot hold. Of
the first 125 of them, 123 played to their end in `openMSX` on the Sanyo PHC-28S, 3
of them with a reset.

## Capture

Step 1's 10 seconds after `Ok`: on the Sanyo PHC-28S with a Carnivore2, Moonrider
loads when the load starts 9 seconds after the boot menu, and stops when it starts
after 5.

Resets in the capture's step 4: Alien 8's loader jumps to the reset routine itself.
The Goonies's snapshot is taken during the start that its loader's reset begins, and
the restored machine finishes it. A loader that crashes into a reset writes the tape
service's part of page 3: 30 collection tapes on the PHC-28S did, most of them
through the loader that the RAM search patch now fixes.

Moonrider pauses its own load for 16 seconds, which is why step 5's wait lasts 30.

Saint Dragon reads its tape with interrupts off, and Thunder Blade waits in `TAPION`
for side 2, so their snapshots go back to the last `TAPION` call's entry (step 6).

## Slot patches

Sootland's FCh names slot 0 for page 0, which holds the ROM, and slot 3 for pages 1
to 3. On the PHC-28S without Nextor, BASIC selects slot 1 in page 2 and slot 0 in
page 3, and slot 1 also holds RAM in page 1, so the patch writes 14h.

Knight Orc reads its slot values from RAM with `LD A,(EF3Eh) / OUT (0A8h),A`,
`3A 3E EF D3 A8`, whose last four bytes are the first form with n = EFh. A patch of
that n changed the address, so the game read a wrong value and hung, which is why
the watch skips a `3E` after a `3A`, and the scan a `3E` that can be any operand.
When the watch used the wide rule too, it skipped Rocky's `01 F3 3E FF`, a `DI`
after data, Time Out's `LD SP,EAA8h` before its `LD A,0FCh`, and Uchi Mata's
`LD (DE0Bh),A` before its `LD A,0F0h`. Finders Keepers selects
RAM in slot 2 through `WSLREG`, the second form.

## The RAM search patch

In the test collection, 70 tapes have this search, many of them from Opera Soft. The
second copy on Made in Spain's tape runs after the snapshot.

## Page 3's slot for the other pages

The Sanyo PHC-28S keeps its own 16 KB in slot 0, in page 3 only, beside the ROM in
pages 0 and 1, and its RAM cartridge in slot 1. With the Carnivore2, BASIC takes
pages 2 and 3 from the Carnivore2's mapper in slot 2-2 instead. The loaders seen so
far take these forms:

| Form | Games | Fix in the PHC-28S's game file |
|---|---|---|
| `BIT 7,A` / `SET 3,A` / `BIT 6,A` / `SET 2,A`: page 1's bits of the slot register from page 3's | Circus Charlie and Hyper Sports 3 from Engesoft, and M-Droid's `core` | The page copy patch, which makes the routine select slot 1, the RAM cartridge, in page 1 |
| The same routine as text, in a BASIC loader's `DATA` lines | M-Droid | A patch of the text |
| A fixed value for pages 1 to 3, chosen by page 3's slot | Beach-Head: 54h for page 3 in slot 0 or 1, from code in page 2, so the capture's patch that keeps page 3 does not see it | A patch to 14h, and the capture without the Carnivore2 |
| Page 2's slot copied into page 1's bits | Budokan, Michel Futbol Master's side B, Professional Tennis Simulator and Arquimedes XXI, whose program is `slots`, with two dumps each of Michel Futbol Master and Professional Tennis Simulator. Night Shade from Engesoft, whose NIGHT and SHADE end with the copy. Konami's Soccer, whose MUNDIA parts OR the slot register with itself shifted right by two bits | The capture without the Carnivore2, where pages 1 to 3 are the RAM cartridge |
| A search for RAM in page 1 only, and a ROM image read into page 1 there and into BASIC's page 2, after which the game selects page 1's slot in page 2 | From Super MSX: Aliens, Star and Worm, whose loader is LOADER, and American Football, Japan, Xerider, The Karate Kid, Alexis, Guardic and Mad Driver, whose loader is two parts. Also Dam Busters, and the second half of Hyper Sports 3 | The capture without the Carnivore2, where pages 1 and 2 are the RAM cartridge |
| A shorter variant of `slots` that keeps the slots it finds | Underground | The capture without the Carnivore2. Which value leads the game to its reset is not known |
| Pages 2 and 3's slots copied into pages 0 and 1: `AND F0h`, then four `RLCA`s, `RRCA`s or `SRA A`s of the slot register's value, then `OR` with the first, with `AND 0Fh` before it after `RRCA`s or `SRA A`s | The Wall from Super MSX 7, whose LOADER is at DD00h. Each part of a tape made by CasLink3: Hang-On, Lunar Ball and Quartet. Level 9's adventures, which read their A-code in pages 0 and 1: Emerald Isle, Red Moon, Time and Magik II, Return to Eden, Silicon Dreams II, The Worm in Paradise, and the four parts of The Secret Diary of Adrian Mole | The page copy patch, to `LD A,15h`, and the capture without the Carnivore2 |

The forms with fixed code, the bit tests and the copies of pages 2 and 3, are the
page copy patch's ([INTERNALS.md, The page copy patch](INTERNALS.md#the-page-copy-patch)),
and the others are lines in the game files. CasLink3's form is in 60 tapes, but its
parts also copy the subslot register's fields of pages 2 and 3 to pages 0 and 1.
With the Carnivore2, pages 2 and 3 are its mapper, so pages 0 and 1 get the mapper
too, and the patch leaves the form alone. Only the games that need the capture
without the Carnivore2 for another reason get it. Level 9's code copies the slot
register only, so its games need the capture without the Carnivore2, and the patch
on the PHC-28S, though Erik the Viking, which has the same code, works with the
Carnivore2. The blocks that Level 9's loader checks end with an 8-bit sum, which the
patch keeps. M-Droid's BASIC loader holds the routine as text, which stays a line in
its game file.

## Build

Double Dragon selects one segment in two pages, so the build finds a page's RAM by
its segment as well as its slot.

Moonwalker keeps its code in FCC9h to FD88h, the area where the service's part of
page 3 goes by default.

## Tape service

Saint Dragon's loader expects the FFh that `TAPIN` returns in side 1's padding, as
`openMSX` returns it while the player turns the tape over.

Gauntlet stops the motor through the BIOS in ROM: it calls `STMOTR` there, with
`rom keep`, so the manual tape's `TAPION` finds the motor off.

4x4 Off-Road Racing asks the player to stop the tape and press space: on the manual
tape, the tape has stopped by itself, because the game stops the motor, as openMSX
shows, and at its next load the player presses RETURN to play on, or GRAPH or CODE
to rewind.

Tokyo Nampa Street loads each scene with BASIC's own `BLOAD`, and its page 2 holds
the game's stack, which is why the mode without a part in page 3 serves `BLOAD` and
its `TAPIN` uses no stack. Bronx's RAM is in a slot without a mapper on the Sanyo
PHC-28S, and it lends its page too.

Bronx's page 3 has one area of zeros at the snapshot that the service's part fits,
F1E1h to F26Fh. Bronx's code names two addresses in that area, F1F3h and F207h, so
Bronx's game file has `service t0`. `build.py` took that mode by itself while the
part was 168 bytes, because the part did not fit in the area then.

Gauntlet's level loader reads a byte with `TAPIN`, puts the byte in C, and adds BC
to a sum. The loader counts on the B = 0 that the BIOS's `TAPIN` leaves. So the
service's `TAPIN` leaves B = 0 too, through the entries in page 3 and through T0.

Moonwalker's loader computes the value that its stub writes to the slot register as
`AND H / LD L,A`, the slot register with page 0's bits cleared, for slot 0. On the
Sanyo PHC-28S the game keeps the slot register at A5h, so the scan puts `LD L,0A6h`
in their place, which selects slot 2, DOS's mapper. Altered Beast and Bronx have the
same stub. On an NMS 8250 its own page 0 RAM is in DOS's mapper,
so it cannot use the mode there.

Desperado's phase loader writes 0 to FD68h before it looks for a phase, and that
byte is in the tape service's reader in page 3. The write turns the reader's `OUT
(C),D` into a 2-byte NOP, so every read comes from the code segment, where side 1
starts, and the loader never finds a phase on side 2. The check does not start a
phase, so it passes. The write happens on every machine, so the game's `game.txt`
has `service t0`, and the scan patches its two stubs of `TAPION`. Gunsmoke, Go!'s
release of the same game, has the same loader and the same line. Far West, Super
MSX's copy, holds only the first phase and reads no more of the tape.

The three versions' joystick routine writes PSG register 7 as the sound's value OR
C0h before it reads register 14. Bit 6 makes I/O port A an output, and a discrete
PSG, as the PHC-28S, VG-8020 and HB-75P have, then returns register 14's own latch
and not the joystick. Their `game.txt` patches OR C0h to OR 80h. The game never
writes register 15, so it reads the port that the BIOS selected last, port 2.
Its sound driver writes register 7 with bit 7 clear, so I/O port B is an input
at the snapshot, and register 15 then reads FFh, its pins. The restore wrote that
FFh with port B an output, which drives pin 8 of both joystick ports high, and a
joystick whose switches share pin 8 then reads nothing. The capture now keeps the
last value written to register 15, the BIOS's CFh.

## Check

7 Card Stud reads its last block through the service and then keeps its variables at
FD00h, which is why point 2 ignores writes after the tape is read to its end.

Altered Beast, after loading its side B, writes its variables over the service's
entries at FCE1h, and its next call of the tape hangs, so it needs the mode without
a part in page 3. Point 2 does not see those writes, because they come after its 60
seconds.

Points 1 and 2 do not see a reboot: seven Super MSX images on the PHC-28S, and
American Football on the VG-8020, passed them and showed the boot screen or Nextor's
60 seconds after the restore, as their loads do in plain `openMSX`.

Raider, from Super MSX n.18, resets the VG-8020 6.2 seconds after the restore and
shows its game at 60 seconds, which is why point 3 needs the boot screen at two
savestates.

Konami's Soccer and Budokan on the PHC-28S, captured with the Carnivore2, stay on a
title or an empty screen for the 60 seconds, though their captures reset 8.7 and 7.8
seconds after the snapshot, and on a real PHC-28S Konami's Soccer's restored game
does reset, into DOS.

   The point judges where the machine ends, not the reset, because a loader can
   reset the machine on purpose after the restore: Japan, from Super MSX n.20,
   resets the VG-8020 0.8 seconds after it, and the BIOS's search for cartridges
   finds the ROM copy in RAM and starts it. A breakpoint at the start of the BIOS's
   reset routine, where 0000h's `DI / JP` jumps, while page 0 selects the main ROM,
   as in the capture's log ([Capture](#capture)), notes each reset in the report
   with its time, but a reset alone does not fail the point. The check reads EXPTBL,
   for the main ROM's slot, when `SNAPCAS.COM` starts. It read it when the boot
   steps ended at first, and on the PHC-28S the BIOS has not set it then, so the
   breakpoint took the main ROM for slot 3-3 and missed every reset there, Aliens's
   among them. The report adds `point 3: fail` and the sign, or else
   `point 3: pass`, and a failed point 3 fails the check. A hang is not a reboot,
   and point 3 does not see it: American Football, captured with the Carnivore2,
   stops in the BIOS on the VG-8020 with its interrupts off. Its game file now
   captures it without the Carnivore2
   ([Page 3's slot for the other pages](#page-3s-slot-for-the-other-pages)).
4. During the same 60 seconds the game must not stop at a BASIC error. A BASIC
   program, or a loader written in BASIC, that meets an error prints one of BASIC's
   error messages, such as `Syntax error in 100`, and waits at `Ok`, in a text mode,
   where `openMSX`'s `screen` reads it. The point fails when the screen's text holds
   one of those messages at one of the savestates. Points 1 to 3 do not see such a
   stop: a scan of the 60-second savestates of the collection's passing game files
   found 17 runs on the PHC-28S and the VG-8020 that end at an error, among them
   Field Master's `Overflow in 130` and three tapes of the CasLink3 loader, whose
   `BLOAD` of the next part ends in `Syntax error`. A loader that stops at `Ok` on
   purpose, and tells the player to press F5 or type `RUN`, as 12 tapes do, shows no
   error message, so it passes. The report adds `point 4: fail` and the message, or
   else `point 4: pass`, and a failed point 4 fails the check.

## Decisions

Of 112 programs on the Engesoft and Super MSX tapes that File-Hunter also has as
dumps of their own, none had game blocks that equal the dump's.

On the Sanyo PHC-28S, La Abadia del Crimen's loader took the RAM cartridge in slot 1
for an expanded slot and crashed, but loaded without it, until the RAM search patch
fixed its load. Its image ran with the cartridge in place, because the game never
selects slot 1 again.

Of the 59 multi-load files tested on an NMS 8250, two games use page 0 RAM and leave
the ROM there at the snapshot: Moonwalker and Time Out.

A search of the 1,653 files of File-Hunter's MSX CAS collection for files that leave
over 10% and 2 KB unread in a test load and hold a rewind or play prompt found 62
files of 51 games. Of those games, 20 build stubs that T0 alone does not intercept,
and in 41 the unread blocks have no names.

## Limits

Moonwalker's 236 KB tape does not fit in an NMS 8250's 128 KB. The PicoVerse's 192
KB mapper leaves Nextor 5 free segments, and 191 games need 6 to 32 for their tapes.

Doki Doki Penguinland selects the RAM cartridge, slot 1, in page 3, where the Sanyo
PHC-28S without Nextor keeps its internal RAM, so its slot patch is a line by hand.
On the NMS 8250, BASIC's subslot register of slot 3 does not select RAM in pages 0
and 1 at step 3, so the slot map has no slot for those pages, and Checkmate! and
Finders Keepers keep their lines there.

Breakout's stack pointer is 0004h at the snapshot on the MFRSD machine, too low for
the tail.

Super MSX n.17's side B sets its stack pointer to 0000h, so its game file captures
without the Carnivore2, where FFFFh is RAM, and takes its snapshot at 125 seconds,
when the stack pointer leaves room for the tail.

Tokyo Nampa Street waits for its `PLAY` music to end, which never happens on a real
PHC-28S. Its game file's `snapshot at` comes after the music, and with it the game
runs on the real machine.

Konami's Soccer, in its hacked dump `KONAMI.CAS`, resets the machine 8.7 seconds
after the snapshot in its capture on the Sanyo PHC-28S, with no key pressed. On a
real PHC-28S with the RAM cartridge in slot 1 and the Carnivore2 in slot 2, the
restored game resets too, and the BIOS boots Nextor into DOS, as it does in
`openMSX` on the VG-8020, and as the plain load does in `openMSX` on the PHC-28S. In
`openMSX`'s check on the PHC-28S, the restored game stays on its title screen for
the 60 seconds and never resets. Point 3's third sign fails the check for that
([Check](#check)), and Budokan does the same, but why the restored machine does not
reset there is not known. Both captures reset because the loaders crash: they copy
page 2's slot into page 1's bits, and with the Carnivore2 page 2 is its mapper's
subslot ([Page 3's slot for the other pages](#page-3s-slot-for-the-other-pages)).
Their game files now capture them without the Carnivore2, where neither resets, and
both games run.

## History

The capture stopped at every reset for a time, which failed 37 game files on the
PHC-28S, among them The Goonies, KONAMI and KNIGHTMA, whose images pass the check
and show the game. It now only logs a reset.

The first signs were the tail's jump running a second time and
`Copyright 1983 by Microsoft` on the screen ([Decisions](#decisions)). The first
also fired when a game's own code passed the tail's jump address, within 0.4
seconds of the restore, as the code of Ci-U-Than Trilogy III and of Enchanted
does on the PHC-28S. The second also fired for games whose restored screen still
holds BASIC's banner with that line, such as Roberto Mate from Philips's Turbo
Pack A and Trick Boy.

The first machine names, such as `advanced/phc28s`, named only the model, and
folders split the machines by how hard they are to set up.

The first capture variants were named after their machine and the cartridge that
they leave out, such as `advanced/phc28s-nodisk`, and the tools found them by that
prefix. With the new machine names, that rule gives names such as
`phc28s-ram64k-carnivore2-nocarnivore2`.

A compilation's program that File-Hunter also has as a dump of its own first got no
game file. It now gets one in the collection's folder.

Eight Super MSX images crashed into a reboot after the restore and passed points 1
and 2. A first rule then failed every reset after the restore, on the view that a
loader resets on purpose only before the snapshot, as The Goonies's does. Japan,
from Super MSX n.20, resets the VG-8020 after the restore and then starts, so point
3 now judges where the machine ends. Its first signs, the tail's jump running again
and `Copyright 1983 by Microsoft` on the screen, failed games that do not reboot:
three whose code passes the tail's jump address, and games whose restored screen
holds BASIC's banner.

## Open questions

The RAM search patch on a machine where the RAM that the loader finds is in an
expanded slot other than the slot of page 3. The patched loader then selects the
subslot that the slot's register already selects.
