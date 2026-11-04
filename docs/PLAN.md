# `snapcas` plan

This page lists the steps that build the first version of `snapcas`, in order, and
the tests that each step adds. It is for the developers, and it follows the design
([DESIGN.md](DESIGN.md)). Each step ends with a review by the user before the next
one starts, and the whole test suite runs with one command, `make test`.

## Test setup

The build pins its tools. The tests read their tape files from `tests/tapes/`, in
git, and the MSX-DOS system files from a folder that the user names, because
`snapcas` cannot ship MSX-DOS.

| Item | Value |
|---|---|
| Assembler | sjasmplus 1.24.0, downloaded and built by the Makefile, checked by SHA-256 |
| Emulator | `openMSX` 22.0, on the path, with the system ROMs of the test machines and of the `msxdos2` cartridge |
| Python | Python 3, standard library only |
| Tapes | `tests/tapes/`: the corpus, the TSX files of step 15, and the collection's tapes that the other steps name |
| Nextor | `NEXTOR.SYS` 2.11 and `COMMAND2.COM` 2.44 from Nextor 2.1.0's `tools.zip`, downloaded by the Makefile into `dos/nextor/`, checked by SHA-256 |
| `DOS_DIR` | Make variable: a folder with `msxdos2/` (`MSXDOS2.SYS`, `COMMAND2.COM`) and `msxdos1/` (`MSXDOS.SYS`, `COMMAND.COM`), by default `dos/`, which git ignores |

The test machines are the seven shipped machines and three machine files that only
the tests use, in `machines/test/`. The shipped machines have a mapper of at least
512 KB, apart from `vg8020-picoverse`, so that the tests show the games and not a
shortage of free segments. Each one boots the DOS of its row:

| Machine file | DOS | Why |
|---|---|---|
| `phc28s-ram64k-carnivore2`, `vg8020-carnivore2`, `nms8250-carnivore2`, `nms8245-ram512k-sunriseide`, `vg8020-picoverse` | Nextor | Shipped |
| `hb75p-mfrsd` | Nextor 2.10, from the ROM disk in the cartridge's flash | Shipped |
| `hbf700p-ram512k-msxdos2` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | Shipped |
| `test/nms8250-dos1` | `DOS_DIR/msxdos1/`, from the NMS 8250's own disk ROM | No shipped machine runs MSX-DOS 1 |
| `test/nms8250-512k` | `DOS_DIR/msxdos2/` | An NMS 8250 whose single mapper holds 512 KB, because 128 KB cannot hold Moonwalker's 236 KB tape |
| `test/nms8250-128k` | `DOS_DIR/msxdos2/` | The NMS 8250 with only its own 128 KB, for the restorer's message when DOS has too few free segments |

`test/nms8250-512k` uses a machine configuration that the Makefile makes from
`openMSX`'s own NMS 8250, with its mapper at 512 KB, in a private `openMSX` home,
named by `OPENMSX_HOME`, with links to the user's system ROMs.

The corpus is a fixed set of CAS files from File-Hunter's collection, one or more
for each case that the design lists:

| Case | File | Load command |
|---|---|---|
| Single load, the first game that failed on the PHC-28S | `FREDDY.CAS` (Freddy Hardest) | `RUN"CAS:"` |
| Single load, slot search from slot 0 up | `FERNANDO.CAS` (Fernando Martin Basket Master) | `RUN"CAS:"` |
| Single load that pauses on its own for 16 seconds | `022-MOON.CAS` (Moonrider) | `RUN"CAS:"` |
| Single load that waits for a key, on an NMS 8250: on the PHC-28S its loader puts slot 1 in page 3 and crashes | `ABADIA.CAS` (La Abadia del Crimen) | `BLOAD"CAS:",R` |
| Single load, BASIC program | `CALDERO.CAS` (El Caldero Magico) | `CLOAD` |
| BASIC program that loads during play, T0 in place of the ROM | `COMPUTAD.CAS` (Computadora Adivina) | `CLOAD` |
| Load during play, side 2 | `TOUR-91.CAS` and `TOUR-91B.CAS` (Tour 91) | `RUN"CAS:"` |
| Load during play, side 2, joystick choice | `GAUNTLET.CAS` and `GAUNTLEB.CAS` (Gauntlet) | `RUN"CAS:"` |
| Load during play, page 0 RAM in DOS's mapper | `MOONWALK.CAS` (Moonwalker) | `RUN"CAS:"` |

## Step 1: build and harness

This step sets up the build and the code that every tool uses to run `openMSX`. It
adds:

- A Makefile that builds sjasmplus and `bin/SNAPCAS.COM`, and runs the tests.
- The machine file `phc28s-ram64k-carnivore2`.
- `tools/msx.py`, which reads a machine file, starts `openMSX` with a Tcl script,
  presses the `boot` keys, and makes, with `diskmanipulator`, a disk image of the
  kind that the machine file's `disk` command takes.
- A first `SNAPCAS.COM` that opens `<GAME>.SNP`, prints its usage without a name,
  and prints an error when the file is missing or is not an image.

The test boots `phc28s-ram64k-carnivore2` with a disk of Nextor's files,
`SNAPCAS.COM` and two bad images: `SHORT.SNP` of 3 bytes and `BAD.SNP`, which starts
with `SNAPCAS9`. It runs `SNAPCAS`, then `SNAPCAS` with `NONE`, `SHORT` and `BAD`,
and reads the usage and the three errors from the screen with `get_screen`. It
proves the assembler, the disk image, the boot keys and the screen reading.

## Step 2: capture

This step writes `tools/capture.py`: capture steps 1 to 6, the RAM rules and the
snapshot files ([Capture](INTERNALS.md#capture)), and the machine file
`nms8250-carnivore2`. The tests capture the single-load files of the corpus, all on
`phc28s-ram64k-carnivore2` except `ABADIA.CAS` on `nms8250-carnivore2`, and check:

- That `state.txt` holds every name of the register table, and that `service` is 0
  for the files on `phc28s-ram64k-carnivore2`.
- That every kept page holds RAM and is in slot 0's page 3, in slot 1 or in the
  Carnivore2's subslot 2-2, and that the Carnivore2's mapper has 64 segments.
- That `ABADIA.CAS` continues after a key, and `log.txt` names it, and that its game
  file's `service no` leaves out the tape service, because its last 16 KB stay
  unread.
- That a second capture of the same file gives the same snapshot.

## Step 3: build

This step writes `tools/build.py` for games without the tape service, and
`src/service.asm` with the tail only. Python unit tests check the image header, the
record table, the port-write order and the tail's bytes against the design's tables
([Formats](DESIGN.md#formats)), on the snapshots of step 2 and on one of
`FREDDY.CAS` captured on `nms8250-carnivore2`, for the V9938's port writes. They
also check that `build.py` stops with an error when `SERVICE.BIN`'s version byte is
wrong.

## Step 4: restorer and check

This step writes `SNAPCAS.COM` without the tape service, restorer steps 1 to 7
([Restorer](INTERNALS.md#restorer)), `tools/check.py`, and the machine files of its
tests. The tests capture, build and check each single-load file of the corpus, first
on `phc28s-ram64k-carnivore2`, then on `vg8020-carnivore2`, `nms8250-carnivore2`,
`hbf700p-ram512k-msxdos2`, `test/nms8250-128k` and `test/nms8250-dos1`. Check point
1 must pass on each machine, except where the restorer stops because DOS leaves too
few free segments: the test then checks that the restorer's message names the
segments needed and free. The savestates stay in `check/` for the user to look at.

The results of the step:

| Machine | Passes point 1 | Other results |
|---|---|---|
| `phc28s-ram64k-carnivore2`, `vg8020-carnivore2` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | La Abadia crashes during its load when a Carnivore2 is present, until the RAM search patch ([Step 14](#step-14-the-ram-search-patch)) |
| `nms8250-carnivore2` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | The Carnivore2's mapper under Nextor has room for every game |
| `hbf700p-ram512k-msxdos2` | Moonrider, El Caldero Magico, La Abadia | `FREDDY.CAS` and `FERNANDO.CAS` do not load to their end in `openMSX` |
| `test/nms8250-128k` | El Caldero Magico | MSX-DOS 2 leaves 2 free segments of the 8 in 128 KB, so the restorer stops for the other games, naming the segments needed and free |
| `test/nms8250-dos1` | All five | |

The test leaves out the games that fail in `openMSX` itself.

## Step 5: tape service

This step adds the tape service to `src/service.asm`, `build.py` and `SNAPCAS.COM`
([Tape service](INTERNALS.md#tape-service)), and the game file's `patch` lines to
`build.py` ([Game file](FILES.md#game-file)), which the scan of step 6 builds on.
The tests capture, build and check two files on `phc28s-ram64k-carnivore2`:
`COMPUTAD.CAS`, and `GAUNTLET.CAS` with `GAUNTLEB.CAS` as side 2. Each test checks
that `service` is 1 in `state.txt`. For Computad, the Tcl script then presses space,
space, 1, RETURN and space, which load the first theme, and checks that the tape
position in the code segment moves to the theme's end. Gauntlet's loaders select the
ROM in page 0 from their own copy of the slot register, so its game file has `patch`
lines for their tape calls and for the sum at the end of the main game's block. Its
menus read the joystick, which `openMSX` cannot press from a script, so the Tcl
script clears the button's bit in register A after the game reads PSG register 14.
The script then plays through the intro and the menus to the side 2 prompt, and
checks that the main game loads to side 1's end and that a level loads from side 2.

## Step 6: scan

This step adds the scan and its patches ([Scan](INTERNALS.md#scan)). Python unit
tests check each of the scan's patterns on bytes made for it. The corpus test
captures each file of `CAS_DIR` on `phc28s-ram64k-carnivore2`, with a side 2 file as
the side 2 of its game, builds the files that need the tape service, and writes
every `scan.txt` into one report. It checks the findings that have been confirmed by
hand: for Gauntlet, the calls of `TAPION` and `TAPIN` at E15Fh and E1ABh in page 3,
patched, and at AE88h and AED4h of side 1, listed. A game's findings join the check
when they are confirmed.

The step also takes the tests that need the scan:

| File | Machine | What the test checks |
|---|---|---|
| `TOUR-91.CAS` | `phc28s-ram64k-carnivore2` | That the game's stub reaches the tape service at its next load |
| `MAD-MIDE.CAS` | `phc28s-ram64k-carnivore2` | The same |
| `DESPERAD.CAS` | `phc28s-ram64k-carnivore2` | The same, for a loader that selects the ROM in page 0 itself, with `IN A,(0A8h) / AND 0FCh / OR 00h / OUT (0A8h),A` |
| `MOONWALK.CAS` | `phc28s-ram64k-carnivore2` | With `service t0`, its snapshot in the intro and a `patch` line that makes its loader select DOS's mapper: that the main game loads through T0, to the end of its 22 KB block ([Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)) |
| `SOOTLAND.CAS` | `phc28s-ram64k-carnivore2`, captured on `phc28s-ram64k` | With a `side1` patch of the slot register's value that its loader writes: that the capture loads the patched tape, and turns the tape over to side 2 when the game reads past side 1's end ([Game file](FILES.md#game-file), [Capture](INTERNALS.md#capture)) |
| `tests/borrow.asm`, which the test writes to a CAS file with a block of the bytes 0 to 255 | `phc28s-ram64k-carnivore2` | With `service t0` and a `patch` line that makes it select DOS's mapper in page 0: that `TAPIN` borrows page 2, which holds the RAM cartridge in slot 1 and the stack, through the slot register, and reads the block right |

## Step 7: replay (dropped)

This step was to play a recording of the first load, its screen and its tape's sound,
before the restore. It was dropped, and the steps after it keep their numbers.

## Step 8: tape speed and sound

This step adds `/T1200` and `/T2400` to `SNAPCAS.COM` and the tape's speed and sound
to the service
([INTERNALS.md, Tape speed and sound](INTERNALS.md#tape-speed-and-sound)). The tests
restore Gauntlet on `phc28s-ram64k-carnivore2` through the check, with check.py's
`--options`, play it to the main game's load as in step 5, and measure:

| Test | What it proves |
|---|---|
| The time between two `TAPIN`s of one block | The main game's 34,341 bytes take their 11 bits each at the chosen speed, within 1%: 9.22 ms at 1200 baud and 4.57 ms at 2400 |
| The same without an option | The load stays as fast as in step 5, 0.62 ms a byte |
| The keyclick bit's edges for each byte, from a write watchpoint on port AAh | Each 0 bit toggles it twice and each 1 bit four times, but for the stop bits' quarter cycles that the gap between two bytes takes, for all 34,341 bytes, and it ends as it started |
| The motor bit of port AAh | It is on at each byte and off after the load |
| The time from `TAPION` to the block's first `TAPIN` | The short leader tone, about 1.6 seconds at either speed, before the main game's block |

## Step 9: shipped files

This step writes the last two machine files, `nms8245-ram512k-sunriseide` and
`hb75p-mfrsd`, with the machine file's `dos` line that the second needs, and the
game files for the collection, by running the capture over `CAS_DIR` on
`phc28s-ram64k-carnivore2` ([Shipped files](FILES.md#shipped-files)). The tests
check a single-load game on each of the seven shipped machines, then capture, build
and check every game file on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2`, and
write a report of passes and failures.

That run, `make games MACHINE=<machine>` since step 24, takes hours, so it keeps a
cache beside each machine's report: each game file's result, with a hash of its
inputs. The inputs are the game's folder, its tape files, the machine files that it
runs on, and `bin/` and `tools/`. A game file whose hash is unchanged keeps its
result, so a run after a fix to game files reruns only those, and a change to the
code reruns all. `FULL=1` reruns every game file. The run does 11 at once, because
the efficiency cores of the Mac where it runs count as well.

Some game files fail on a machine in `openMSX` itself, without `snapcas`: a plain
load of the tape, with the same machine and no capture code, fails there too. Those
are not failures of `snapcas`, so `tests/openmsx-failures.txt` lists them, with the
machine, the game file's folder and what fails, to try again at the end. The run
passes when every game file that fails is in that list, and it names the others. A
listed game file that passes is only noted, for its line to go, because an `openMSX`
failure can come and go. A patch line can still make such a game work later. The
game files that load in a plain `openMSX` but fail with `snapcas` are its own
failures, to fix, and `tests/snapcas-failures.txt` lists them in the same form. The
run does not pass them, so they show until they are fixed.

From 1 November 2026 the work focuses on two machines: `phc28s-ram64k-carnivore2`,
the user's own, and `vg8020-carnivore2`, the plain MSX1. On the other five the
collection's failures go into the two lists only, and no more is done there until
later.

## Step 10: automatic fixes

This step makes the fixes that the game files hold by hand automatic, so that a new
machine needs as few game files of its own as possible. It adds the slot patches of
the capture and of the scan ([Slot patches](INTERNALS.md#slot-patches)), the mode
without a part in page 3 when page 3 has no room
([Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)), and the tries
of `snapcas.py make` on the capture variants
([Files and commands](DESIGN.md#files-and-commands)). The tests check each fix on a
game that needed it by hand, without its line: Sootland and Finders Keepers for the
slot patches, Chase H.Q. for the mode, and Sootland on the HB-F700P for the
variants. La Abadia del Crimen was the variants' test until the RAM search patch
fixed its load ([The RAM search patch](INTERNALS.md#the-ram-search-patch)). The
collection then runs on all seven shipped machines, and the report lists the game
files that a machine still needs.

## Step 11: real hardware

The user runs the corpus on the Sanyo PHC-28S with the Sony HBM-64 in slot 1 and the
Carnivore2 in slot 2, and the results go in this page, with the machine and
cartridges named. A failure that `openMSX` does not show goes in the design's limits
until it is understood. `./snapcas.py try <game> <machine>` starts `openMSX` with
the same machine and the image, to compare.

| Date | Machine | Images | Result |
|---|---|---|---|
| 2026-10-29 | Sanyo PHC-28S, Sony HBM-64 in slot 1, Carnivore2 in slot 2, Nextor 2.1 | `FREDDY.SNP`, `FERNANDO.SNP`, `MOONRIDE.SNP`, `CALDERO.SNP`, from step 4 | All four games run |
| 2026-10-29 | The same | `ABADIA.SNP`, captured with `capture phc28s-empty-carnivore2` | La Abadia del Crimen runs, with the RAM cartridge in slot 1 |
| 2026-10-29 | The same | `KNIGHTMA.SNP`, with `snapshot at 130`, and the 31 images of the step 4 batch | All run |
| 2026-10-29 | The same | `GAUNTLET.SNP`, with `GAUNTLEB.CAS` as side 2, from step 5 | The main game and its levels load from the tape service, side 2 included, and the side's colour shows at the turn-over |
| 2026-10-29 | The same | `MOONWALK.SNP`, with `service t0`, from step 6 | The game loads through T0 and plays. The loading messages show a few wrong pixels, likely VRAM writes that come faster than the VDP accepts, because the tape service returns a byte much sooner than a tape; step 8's `/T1200` is to confirm it |
| 2026-10-31 | The same | `KNIGHT1.SNP`, from step 10 | Knight Orc hung after its first letter, because the scan had patched the `3E EF` of the address in `LD A,(EF3Eh)`. It plays since the scan skips a `3E` that can be an operand ([Slot patches](INTERNALS.md#slot-patches)) |
| 2026-10-31 | The same | `GHOSTBUS.SNP`, from step 10 | Ghostbusters II loads, and its menu starts with SPACE, or with the fire button of a joystick in port 2. The menu reads PSG register 14 without selecting a port, and the BIOS's interrupt routine leaves port 2 selected on this machine, so a load from tape behaves the same |
| 2026-10-31 | The same | `NAVYMOV.SNP`, from step 10 | Navy Moves plays with the keyboard. With 2-JOYSTICK, the jet-ski jumped by itself and did not obey, as with the plain tape in `openMSX`. Two `patch` lines in `games/NAVY-MOV/game.txt` fix the game: its joystick controls now point at the joystick's row, and a sound effect no longer clears bit 7 of PSG register 7. The joystick then works in port 1, the only port that the game reads |
| 2026-10-31 | The same | `ALTERED.SNP`, from step 10 | Altered Beast hung with a yellow screen after side B's load: the game keeps its variables at FCE1h to FCE4h, where the service's entries are. With `service t0` and five `patch` lines in `games/ALTERED/phc28s-ram64k-carnivore2.txt`, which send its loader's stub to T0, side B loads and the game plays. The wait of about 25 seconds before the prompt to turn the tape over is the game's own, as with the plain tape in `openMSX` |
| 2026-10-31 | The same | `OUTRUN.SNP`, `OPERATIO.SNP` and `DONKECAS.SNP`, from step 10, with the scan's slot patches | Out Run, Operation Wolf and Donkey Kong run |
| 2026-11-02 | The same | `ENGESOFT\ATHLETIC.SNP`, `SUPERMSX\VERTIGO.SNP` and `SUPERMSX\ALIENS.SNP`, `D\DAMBUST.SNP`, `ENGESOFT\HYPERSP3.SNP` and `K\KONAMI.SNP`, from step 16's collection run | Athletic Land and Vertigo run. Aliens and Dam Busters reboot to the boot screen and Hyper Sports 3 into DOS, as point 3 reports. Konami's Soccer reboots into DOS, though `openMSX`'s check passed it, which led to point 3's third sign ([Check](INTERNALS.md#check)) |
| 2026-11-02 | The same | `K\KONAMI.SNP`, `B\BUDOKAN.SNP`, `B\BEACHHE.SNP`, `M\MDROID.SNP` and `SUPERMSX\ALIENS.SNP`, with the fixes for loaders that take page 3's slot for the other pages ([Page 3's slot for the other pages](INTERNALS.md#page-3s-slot-for-the-other-pages)) | All five run. Konami's Soccer flashes its title until a key, and Budokan is silent at its menu, as they are in `openMSX` |
| 2026-11-03 | The same | The 1,545 images of `phc28s-ram64k-carnivore2`, copied to the card with `sync`, and `G\GAUNTLET.SNP` played | `CD \SNAPCAS\G` and `\BIN\SNAPCAS GAUNTLET` start the game from the card's layout. After a game over, CODE held at the side B prompt loads level 1 at once. Without it, the automatic tape reads on through the rest of side B, about 10 seconds, before it wraps to side B's start |
| 2026-11-04 | The same | `G\GAUNTLET.SNP` with `/T1200` and `/T2400`, from step 8 | The main game loads at the tape's speed, with the leader tone and the tape's sound through the MSX, and the game plays |

## Step 12: the tools' code

This step moves the tools' code into the files of
[The tools' code](INTERNALS.md#the-tools-code), and does not change what the tools
do. It splits `build()` and `service_segments()` into the build's steps. The proof
is that the outputs stay the same, byte for byte:

| Test | What it proves |
|---|---|
| Every snapshot of `out/` on the seven shipped machines, built again | The images and `scan.txt` files are the same as before the step |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The snapshots are the same as before the step, and every check passes |
| `make test` | The steps' tests pass |

## Step 13: the check's guard of page 3

This step adds to the check's point 2 the watch on the tape service's part of page 3
([Check](INTERNALS.md#check)), after Altered Beast wrote its variables over the
service's entries on the real machine. The collection reports point 2's failure in
place of point 1's line:

| Test | What it proves |
|---|---|
| Gauntlet's check on `phc28s-ram64k-carnivore2` | The service's own writes to the part, during the game's tape calls, do not count |
| 7 Card Stud's check on `phc28s-ram64k-carnivore2` | The game's writes after the service has read the tape to its end do not count |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The games whose first 60 seconds write the part are listed, for a game file's `service t0` |

On those two machines, the guard listed 53 game files. Most of them were not games
that write the part. On the PHC-28S, 30 were captures whose loader had reset the
machine, so the image replayed a reboot, and the reboot wrote the part. Most of
those loaders cut off their own code ([Step 14](#step-14-the-ram-search-patch)).

## Step 14: the RAM search patch

This step adds the capture's watch for a slot register write that cuts off the code
that made it, and the patch of the RAM search that Mot's loader and many Opera Soft
loaders share ([The RAM search patch](INTERNALS.md#the-ram-search-patch)). Mot and
Satan's game files took the tape of their part 2 for a side 2. Each part now has a
game file of its own, and Mot's demo has its own as well.

| Test | What it proves |
|---|---|
| Mot, its demo and the 20 other tapes with the search that reset the PHC-28S, on `phc28s-ram64k-carnivore2` | The capture patches the search, and each check passes |
| Mot on `vg8020-carnivore2` | A machine whose RAM for page 3 is in the slot that the loader finds gets no patch |
| Made in Spain on `phc28s-ram64k-carnivore2` | Each copy of the search on a tape is patched |
| Sootland's variant test on `hbf700p-ram512k-msxdos2` | Replaces La Abadia del Crimen's, whose load the patch fixes there |

## Step 15: TSX tape files

This step adds the reader of TSX files and the tape model, and moves the code that
reads CAS files behind the model ([Tape files](INTERNALS.md#tape-files)). The tools'
`--cas` folder becomes `--tapes`, because it holds both formats, and the game file
gets the keys `tsx` and `load`. The tests use TSX files from the collection that the
TSX experiment loaded, each chosen for a case of the design, from the `tsx/` folder
of `CAS_DIR`. Part 2, the reader, checks the times of the blocks against `openMSX`'s
length of the tape:

| Test | What it proves |
|---|---|
| A TSX file with only standard blocks, whose CAS file is in the collection | The two files load the same game: its RAM page is the same, though the TSX file keeps the original tape's timing |
| A TSX file of standard blocks recorded at about 1660 baud | TAPION reads a tape recorded between 1200 and 2400 baud |
| Two single-load TSX files with turbo blocks | A turbo loader loads its whole tape in the capture, and the image passes the check |
| A tape of TSX bytes whose first block is a turbo block, with and without `load` | The load command comes from the game file, and without it the capture stops |
| A tape of TSX bytes with a turbo block after the snapshot's time | The build stops with an error that names the block, unless the game file has `service no` |
| A patch line at an offset in a TSX file | The capture loads the patched file |
| A CAS file whose block headers are off the grid of 8 bytes | The reader finds each block, as `openMSX` does |
| Sky Jaguar with `start SKY`, from the Engesoft tape after Circus Charlie | The load starts at a later file, from a copy whose blocks are back on the grid, and the image passes the check ([A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The CAS game files keep their results behind the model |

## Step 16: the check's reboot point

This step adds point 3 to the check: a reboot of the machine during the 60 seconds
after the restore fails it, shown by `SNAPCAS.COM` starting again or by
`MSX system`, the MSX1 BIOS's boot screen, on the screen at two or more savestates,
or by no reset in the check where the capture's log shows one after the snapshot
([Check](INTERNALS.md#check)). The breakpoint at the start of the BIOS's reset
routine while page 0 selects the main ROM notes each reset in the report, and it is
set after point 1, because the check's own boot passes there.

| Test | What it proves |
|---|---|
| Aliens, from Super MSX n.9, on `phc28s-ram64k-carnivore2`, without its machine's game file | An image that reboots to the boot screen fails point 3, though it passes points 1 and 2 |
| Konami's Soccer on `vg8020-carnivore2`, without its machine's game file | An image that reboots into DOS fails point 3, because `SNAPCAS.COM` starts again |
| Enchanted on `phc28s-ram64k-carnivore2` | A game whose code passes the tail's jump address again passes point 3 |
| Roberto Mate, from Philips's Turbo Pack A, on `phc28s-ram64k-carnivore2` | A game whose restored screen holds BASIC's banner passes point 3 |
| Konami's Soccer on `phc28s-ram64k-carnivore2`, without its machine's game file | An image whose restored game never reaches the reset that its capture shows fails point 3 |
| Bumper Ship Racing on `phc28s-ram64k-carnivore2` | The reset breakpoint notes a reset on the PHC-28S, where the BIOS sets EXPTBL after the boot steps |
| Japan, from Super MSX n.20, on `vg8020-carnivore2` | A loader that resets on purpose after the restore and then starts its ROM copy passes point 3, and the report notes the reset |
| Raider, from Super MSX n.18, on `vg8020-carnivore2` | A reset on purpose whose boot screen a single savestate catches passes point 3 |
| A single-load game on each shipped machine | The check's own boot, before the restore, is not a reboot |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The game files that fail point 3 are sorted into the failure lists |

## Step 17: one service setting

This step makes the game file's `service` line one value, `no`, `at xxE1` or `t0`,
which a machine's game file replaces, and makes `rom keep` with the mode without a
part in page 3 an error ([Game file](FILES.md#game-file),
[Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)). `build.py` takes
the game file's settings as one value instead of a parameter for each.

| Test | What it proves |
|---|---|
| A game file with two different `service` lines | The game file is refused with an error that names the second line |
| A game file with `rom keep` and `service t0` | The game file is refused with an error |
| A game file with `service no` and a machine's game file with `service t0` | The machine's line replaces `game.txt`'s on that machine, and only there |
| A game file with `service at` an address whose page has room at the snapshot | `build.py` places the tape service's part there, and the image passes the check |
| A game file with `rom keep` whose page 3 has no room for the part | `build.py` stops with an error instead of taking the mode without a part in page 3 |
| Every shipped game file | It reads to the same settings as before, and the sample of game files keeps byte-identical images, scans, states and reports |

## Step 18: the check's BASIC error point

This step adds point 4 to the check: a BASIC error message on the screen at one of
the savestates fails it ([Check](INTERNALS.md#check)). The messages are BASIC's, and
the check reads the screen's text at each savestate, as point 3 reads it for the
boot screen.

| Test | What it proves |
|---|---|
| Field Master without its patch line, on `phc28s-ram64k-carnivore2` | A BASIC game that stops at `Overflow in 130` after the restore fails point 4, though it passes points 1 to 3 |
| Aritmo, from Philips's Turbo Pack A, on `phc28s-ram64k-carnivore2` | A loader that stops at `Ok` on purpose, for the player to press F5, passes point 4 |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The game files that fail point 4 are the 17 runs of the scan, and they are fixed or sorted into the failure lists |

## Step 19: machine names

This step names each machine file after its model and its cartridges, in slot order,
and moves the capture variants to `machines/capture/` under names of the same form
([Machine file](FILES.md#machine-file)). Each machine file lists its variants with
`variant` lines, which `snapcas.py make` reads instead of finding the variants by
their names. The machine's game files take the machines' new names, and their
`capture` lines the variants' new names. The `openmsx` lines stay as they were, so
the images do not change.

| Test | What it proves |
|---|---|
| Every shipped machine's game file | Its name is a machine file's name |
| Every shipped `capture` line | It names a variant that its machine file lists |
| Sootland on `hbf700p-ram512k-msxdos2`, without a `capture` line | `snapcas.py make` tries the variants that the machine file lists, and prints `capture hbf700p-msxdos2` |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | Every game file passes, as before the rename |

## Step 20: the release machines

This step adds five machine files for the setups that users most probably own, from
the 2026 MSX survey on msx.org and owners' threads there
([Shipped files](FILES.md#shipped-files)): `vg8020-sdmapper`, `xp800-sdmapper`,
`fsa1-mfrsd`, `hbf1xd-mfrsd` and `vg8235`. The machine file gets two lines for them:

| Line | Why |
|---|---|
| `hold` | The Panasonic FS-A1 starts its Desk Pac menu in a graphics mode unless DEL is held from power-on |
| A size on the `disk` line | The Philips VG-8235's single-sided drive reads only a 360 KB disk |

The Makefile downloads the SD Mapper's firmware and Nextor's ROM for the
MegaFlashROM SCC+ SD, each pinned by SHA-256, and makes the cartridge's flash with
Nextor only, because the stock flash's ROM disk starts a file manager on an MSX2.

| Test | What it proves |
|---|---|
| Caldero on each of the five machines | A single-load game restores on each, under Nextor or, on the VG-8235, MSX-DOS 1 |
| The collection on each of the five machines | Each game file passes, or is fixed, or is in a failure list |

## Step 21: the url line

This step is the first of the `snapcas` command's ([CLI.md](CLI.md)). It adds the
game file's `url` line, the links to the zips that hold a game's sides
([Game file](FILES.md#game-file)), which the command downloads. A one-off script
filled the lines from File-Hunter's listing of its MSX1 CAS folder and the
collection's lists of its files, and removed the link comments, which had no side
2's link. An apostrophe in a link is written `%27`, because the game file's lines
are split as a shell splits words, which would take it for a quote. The 8 game files
without a link, in the `SM-` folders, were copies of Spectravideo's Swing Man,
Cryptic Cube and Roulette under their catalogue numbers, so they went, with 13 other
copies of a release under several names ([Shipped files](FILES.md#shipped-files)).

| Test | What it proves |
|---|---|
| A game file with a link for each side | The game file reads, with both links |
| A game file with side 2 and one link, or with a link that is not https to a zip | The game file is refused with an error |
| Every shipped game file | Each links its zips on File-Hunter |
| Side 2 of Gauntlet, Meganova and Strip Poker II+, downloaded once | Each side 2's zip holds the file with the game file's SHA-1 |

## Step 22: the command

This step adds the `snapcas` command, `snapcas.py` at the repository's top, with its
three verbs ([CLI.md](CLI.md)). The file is executable, so macOS and Linux run it as
`./snapcas.py`, and without arguments it prints its help.

| Verb | What this step gives it |
|---|---|
| `list` | It lists the games whose folder or title holds a text. A game's title names the File-Hunter file that it comes from: a game's File-Hunter name, its zip's name or the zip's name, `/` and the CAS file in it, and a compilation's program's zip's name, `/` and the program's name, the text before its first comment's first comma |
| `machines` | It lists the user machines, each with the first sentence of its machine file's first comment |
| `make` | It takes over `tools/snapcas.py`, which goes: capture, build, `--check`, and the tries of the capture variants. It finds the game by its folder or by a text, and the machine by a start of its name. The download and `--to` come in later steps |

| Test | What it proves |
|---|---|
| `list wall` | It lists the three games whose folder or title holds "wall", and their number |
| `list` with a text in mixed case | A text matches in any case |
| `list` on Gauntlet, Aritmo, Africa Film and Athletic Land | Each game's title names its File-Hunter file: a zip, a CAS file in a zip, or a compilation's zip and the program |
| `list "super msx n.23"` | A compilation's name finds its programs |
| `list` without a text | It lists every game file |
| `machines` | It lists the user machines and no capture variant or test machine, each with its first sentence |
| `make wall phc28s` and `make gauntlet vg8020` | A text that several games match, or a start that several machines' names have, lists them and stops with status 1 |
| `make` with a game or a machine that nothing matches, or `--dos` without `--check` | The command stops with status 1 |
| No arguments, or `make` alone | The command prints its help |
| An unknown verb | The command stops with status 1, as the tools do for an error in their input |
| `snapcas.py`'s mode | The file is executable |
| Step 9's single-load game and step 10's runs, through `make` | `make` makes and checks images, and finds a capture variant, as `tools/snapcas.py` did |

## Step 23: the download

This step makes `snapcas.py make` download the game's tape files that are not in the
tapes folder ([CLI.md, Download](CLI.md#download)), with `tools/download.py`. For
each side, it downloads the zip that the `url` line links, finds the file whose
SHA-1 the `sha1` line gives, and saves it under the name that the `cas` or `side2`
line gives. A file of that name with another SHA-1 stops the command and stays.

| Test | What it proves |
|---|---|
| A game with two sides, each in a zip of its own, one of them with another file | Each side is found by its SHA-1 and saved under the game file's name |
| The same game again | A tape already in the folder is not downloaded again |
| A file in the folder with another SHA-1 | The command stops, and the file stays |
| A zip without the side's SHA-1 | The command stops and writes nothing |
| A game file without a `url` line | The command names the file to put in the folder, with its SHA-1 |
| Gauntlet on `phc28s-ram64k-carnivore2`, by hand, into an empty folder | Both sides come from File-Hunter with the game file's SHA-1s, and the image builds |

The tests replace the network with zips that they make, so they run offline.

## Step 24: the folders

This step gives each kind of file a folder of its own, so that the tests, the games
run and the user's images share no folder:

| Folder | Holds |
|---|---|
| `tests/tapes/` | The tests' 61 tape files, in git, in place of `CAS_DIR` and its `tsx/` and `collection/` folders |
| `downloads/` | The tapes that `snapcas.py snap` downloads, which the games run reads without downloading, in place of `--tapes` and `tapes/` |
| `images/<machine>/<game>/` | The image of a shipped game, which `snap` moves there when every step passes, in place of `out/<machine>/<game>/` |
| `out/work/<machine>/<game>/` | The snapshot, the image until `snap` moves it, the check and the build's reports. A game folder of the tests holds its own, `<folder>/<machine>/`, below `out/test/` |
| `out/cache/` | The tools that the Makefile downloads and builds, and the test home of `openMSX` |
| `dos/nextor/` | Nextor's files, in place of `out/dl/nextor/` |

The run over every game file moves from the tests to `tools/games.py`, and
`make games MACHINE=<machine>` replaces `make collection`
([INTERNALS.md, The games run](INTERNALS.md#the-games-run)). The step moved the
1,850 tapes of `tapes/collection/` into `downloads/`, after checking that each of
the 1,601 tapes that the game files name has its game file's SHA-1.

The command's verb `make` becomes `snap`, as in `./snapcas.py snap gauntlet phc28s`,
so that it no longer shares its name with the Makefile's `make test` and
`make games`. `make try`, which put every image of `out/try/` on one disk, becomes
`./snapcas.py try <game> <machine>`, which starts one game's image and types its
command, and `tools/run.py` goes. A game and a machine are given by their names, as
`list` and `machines` show them. A name that is not a game's or a machine's stops
the command, where step 22 chose the one game or machine that the text matched.

| Test | What it proves |
|---|---|
| `make test` | The tests find every tape in `tests/tapes/`, and `make` finds them there through `SNAPCAS_DOWNLOADS` |
| Corpus | The scan reads the 38 tapes of its list, and not the other tapes of `tests/tapes/` |
| Temptations on `phc28s-ram64k-carnivore2` with `--check`, by hand | The image goes to `images/`, the work files to `out/work/`, and each point of the check passes |

## Step 25: custom games

This step adds `custom/`, the user's own games, for games that `snapcas` does not
ship and for the user's own dumps of a tape
([CLI.md, Your own games](CLI.md#your-own-games)). A custom game's folder holds its
`game.txt` and its tape files, and its name is `custom/<game>`. `snap` reads its
tapes from the folder and never downloads them, and its image and work files go
below `custom/` in `images/<machine>/` and `out/work/<machine>/`. Git keeps only
`custom/README.md`.

| Test | What it proves |
|---|---|
| A folder of the tests' own `custom/` with a game file, and one without | Only the folder with a `game.txt` is a custom game |
| `CUSTOM/mygame` | The name finds the game's folder in any case |
| `list custom` | The game shows with its title |
| The tapes, the work folder and the image | The tapes are the game's folder, and the work folder and image are below `custom/` |
| Gauntlet | A shipped game is no custom game: its tapes come from `downloads/` |
| A custom game made from `FREDDY.CAS` on `phc28s-ram64k-carnivore2` with `--check`, by hand | `snap` passes, and the image goes to `images/phc28s-ram64k-carnivore2/custom/ZZFREDDY/` |

## Step 26: sync a card

This step adds `snapcas.py sync <machine> <destination>`, which copies the
machine's images and `SNAPCAS.COM` to a card, in place of `snap`'s `--to` option
([CLI.md, Sync a card](CLI.md#sync-a-card)). It copies only the new and changed
files, reads each copy back, and deletes nothing on the card.

| Test | What it proves |
|---|---|
| A game, a compilation's program, a custom game and a name that starts with a digit | Each file goes to its letter's folder, and `SNAPCAS.COM` to `BIN/` |
| A second sync after one image changed, with a file of the user's own on the card | Only the changed image is copied, and the user's file stays |
| The card's `SNAPCAS` or `BIN` folder as the destination | The command stops and asks for the card's top folder |
| Two images for one place on the card | The command stops |
| `phc28s-ram64k-carnivore2` into an empty folder, twice, by hand | The first sync copies 1,546 files and the second none |
