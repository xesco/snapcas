# `snapcas` plan

This page lists the steps that build the first version of `snapcas`, in order, and
the tests that each step adds. It is for the developers, and it follows the design
([DESIGN.md](DESIGN.md)). Each step ends with a review by the user before the next
one starts, and the whole test suite runs with one command, `make test`.

## Test setup

The build pins its tools, and the tests read the CAS files and the MSX-DOS system
files from two folders that the user names, because `snapcas` cannot ship them.

| Item | Value |
|---|---|
| Assembler | sjasmplus 1.24.0, downloaded and built by the Makefile, checked by SHA-256 |
| Emulator | `openMSX` 22.0, on the path, with the system ROMs of the test machines and of the `msxdos2` cartridge |
| Python | Python 3, standard library only |
| `CAS_DIR` | Make variable: the folder of the user's tape files, by default `tapes/`, which git ignores. Its `tsx/` folder holds the TSX files of step 15 |
| Nextor | `NEXTOR.SYS` 2.11 and `COMMAND2.COM` 2.44 from Nextor 2.1.0's `tools.zip`, downloaded by the Makefile into `out/dl/nextor/`, checked by SHA-256 |
| `DOS_DIR` | Make variable: a folder with `msxdos2/` (`MSXDOS2.SYS`, `COMMAND2.COM`) and `msxdos1/` (`MSXDOS.SYS`, `COMMAND.COM`), by default `dos/`, which git ignores |

The test machines are the seven shipped machines and three machine files that only
the tests use, in `machines/test/`. The shipped machines have a mapper of at least
512 KB, apart from `basic/picoverse`, so that the tests show the games and not a
shortage of free segments. Each one boots the DOS of its row:

| Machine file | DOS | Why |
|---|---|---|
| `advanced/phc28s`, `basic/vg8020`, `basic/nms8250`, `basic/msx2ide`, `basic/picoverse` | Nextor | Shipped |
| `advanced/mfrsd` | Nextor 2.10, from the ROM disk in the cartridge's flash | Shipped |
| `advanced/hbf700p` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | Shipped |
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
- The machine file `advanced/phc28s`.
- `tools/msx.py`, which reads a machine file, starts `openMSX` with a Tcl script,
  presses the `boot` keys, and makes, with `diskmanipulator`, a disk image of the
  kind that the machine file's `disk` command takes.
- A first `SNAPCAS.COM` that opens `<GAME>.SNP`, prints its usage without a name,
  and prints an error when the file is missing or is not an image.

The test boots `advanced/phc28s` with a disk of Nextor's files, `SNAPCAS.COM` and
two bad images: `SHORT.SNP` of 3 bytes and `BAD.SNP`, which starts with `SNAPCAS9`.
It runs `SNAPCAS`, then `SNAPCAS` with `NONE`, `SHORT` and `BAD`, and reads the
usage and the three errors from the screen with `get_screen`. It proves the
assembler, the disk image, the boot keys and the screen reading.

## Step 2: capture

This step writes `tools/capture.py`: capture steps 1 to 6, the RAM rules and the
snapshot files ([Capture](DESIGN.md#capture)), and the machine file `basic/nms8250`.
The tests capture the single-load files of the corpus, all on `advanced/phc28s`
except `ABADIA.CAS` on `basic/nms8250`, and check:

- That `state.txt` holds every name of the register table, and that `service` is 0
  for the files on `advanced/phc28s`.
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
`FREDDY.CAS` captured on `basic/nms8250`, for the V9938's port writes. They also
check that `build.py` stops with an error when `SERVICE.BIN`'s version byte is
wrong.

## Step 4: restorer and check

This step writes `SNAPCAS.COM` without the tape service, restorer steps 1 to 7
([Restorer](DESIGN.md#restorer)), `tools/check.py`, and the machine files of its
tests. The tests capture, build and check each single-load file of the corpus, first
on `advanced/phc28s`, then on `basic/vg8020`, `basic/nms8250`, `advanced/hbf700p`,
`test/nms8250-128k` and `test/nms8250-dos1`. Check point 1 must pass on each
machine, except where the restorer stops because DOS leaves too few free segments:
the test then checks that the restorer's message names the segments needed and free.
The savestates stay in `check/` for the user to look at.

The results of the step:

| Machine | Passes point 1 | Other results |
|---|---|---|
| `advanced/phc28s`, `basic/vg8020` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | La Abadia crashes during its load when a Carnivore2 is present, until the RAM search patch ([Step 14](#step-14-the-ram-search-patch)) |
| `basic/nms8250` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | The Carnivore2's mapper under Nextor has room for every game |
| `advanced/hbf700p` | Moonrider, El Caldero Magico, La Abadia | `FREDDY.CAS` and `FERNANDO.CAS` do not load to their end in `openMSX` |
| `test/nms8250-128k` | El Caldero Magico | MSX-DOS 2 leaves 2 free segments of the 8 in 128 KB, so the restorer stops for the other games, naming the segments needed and free |
| `test/nms8250-dos1` | All five | |

The test leaves out the games that fail in `openMSX` itself.

## Step 5: tape service

This step adds the tape service to `src/service.asm`, `build.py` and `SNAPCAS.COM`
([Tape service](DESIGN.md#tape-service)), and the game file's `patch` lines to
`build.py` ([Game file](DESIGN.md#game-file)), which the scan of step 6 builds on.
The tests capture, build and check two files on `advanced/phc28s`: `COMPUTAD.CAS`,
and `GAUNTLET.CAS` with `GAUNTLEB.CAS` as side 2. Each test checks that `service` is
1 in `state.txt`. For Computad, the Tcl script then presses space, space, 1, RETURN
and space, which load the first theme, and checks that the tape position in the code
segment moves to the theme's end. Gauntlet's loaders select the ROM in page 0 from
their own copy of the slot register, so its game file has `patch` lines for their
tape calls and for the sum at the end of the main game's block. Its menus read the
joystick, which `openMSX` cannot press from a script, so the Tcl script clears the
button's bit in register A after the game reads PSG register 14. The script then
plays through the intro and the menus to the side 2 prompt, and checks that the main
game loads to side 1's end and that a level loads from side 2.

## Step 6: scan

This step adds the scan and its patches ([Scan](DESIGN.md#scan)). Python unit tests
check each of the scan's patterns on bytes made for it. The corpus test captures
each file of `CAS_DIR` on `advanced/phc28s`, with a side 2 file as the side 2 of its
game, builds the files that need the tape service, and writes every `scan.txt` into
one report. It checks the findings that have been confirmed by hand: for Gauntlet,
the calls of `TAPION` and `TAPIN` at E15Fh and E1ABh in page 3, patched, and at
AE88h and AED4h of side 1, listed. A game's findings join the check when they are
confirmed.

The step also takes the tests that need the scan:

| File | Machine | What the test checks |
|---|---|---|
| `TOUR-91.CAS` | `advanced/phc28s` | That the game's stub reaches the tape service at its next load |
| `MAD-MIDE.CAS` | `advanced/phc28s` | The same |
| `DESPERAD.CAS` | `advanced/phc28s` | The same, for a loader that selects the ROM in page 0 itself, with `IN A,(0A8h) / AND 0FCh / OR 00h / OUT (0A8h),A` |
| `MOONWALK.CAS` | `advanced/phc28s` | With `service t0`, its snapshot in the intro and a `patch` line that makes its loader select DOS's mapper: that the main game loads through T0, to the end of its 22 KB block ([Without a part in page 3](DESIGN.md#without-a-part-in-page-3)) |
| `SOOTLAND.CAS` | `advanced/phc28s`, captured on `advanced/phc28s-nodisk` | With a `side1` patch of the slot register's value that its loader writes: that the capture loads the patched tape, and turns the tape over to side 2 when the game reads past side 1's end ([Game file](DESIGN.md#game-file), [Capture](DESIGN.md#capture)) |
| `tests/borrow.asm`, which the test writes to a CAS file with a block of the bytes 0 to 255 | `advanced/phc28s` | With `service t0` and a `patch` line that makes it select DOS's mapper in page 0: that `TAPIN` borrows page 2, which holds the RAM cartridge in slot 1 and the stack, through the slot register, and reads the block right |

## Step 7: replay

This step adds the replay ([Replay](DESIGN.md#replay)): the recording in
`capture.py`, the stream and its compression in `build.py`, and the playing with
`/R` in `SNAPCAS.COM`. The tests check:

- With Python unit tests, that the stream's commands and the LZ4 compression read
  back what they wrote, and that a rewind truncates `replay.log`.
- That after `SNAPCAS MOONRIDE /R` plays Moonrider's replay in `openMSX`, VRAM, the
  VDP's registers and the PSG's registers equal the snapshot's, before the restore
  goes on, and the same for the other single-load files of the corpus on
  `advanced/phc28s`.
- That a wait for a key holds the replay until a key is pressed, with `ABADIA.CAS`
  on `basic/nms8250`.
- That Moonrider's replay at `/R` takes the capture's time within 5%, and at `/R2`
  half of it, and that it makes no DOS call while it plays, from a breakpoint at
  0005h, when the file fits in the free segments.
- That with fewer free segments than the file needs, the replay reads its other
  chunks only at frames in which the motor bit is off.
- That the replay toggles the keyclick bit only while the motor bit is on, at 1200
  Hz for a 0 bit and 2400 Hz for a 1 bit, from write watchpoints on ports AAh and
  ABh.
- That Moonrider's replay starts with VRAM and the VDP's registers as they were just
  before the capture typed the load command, types the command, and waits at its
  RETURN until RETURN is pressed.

The step also reports the size of each `.RPL` file of the corpus, compressed and
not, to judge the compression.

## Step 8: tape speed and sound

This step adds `/T1200` and `/T2400` to `SNAPCAS.COM` and the tape's speed and sound
to the service ([Tape speed and sound](DESIGN.md#tape-speed-and-sound)). The tests
restore Gauntlet on `advanced/phc28s` with each option, play it to the main game's
load as in step 5, and check:

- That the main game's 34,341 bytes take 11 bits each at the chosen speed, within
  5%, and that the load without an option stays as fast as in step 5.
- That the keyclick bit toggles twice for each 0 bit and four times for each 1 bit
  of a block, from a write watchpoint on port AAh, and has its value before the load
  at the end.
- That the motor bit of port AAh is on during the load and off after it.
- That with `/R` alone the tape service runs at the speed in Gauntlet's replay
  header, and with `/R /T2400` at 2400 baud.

## Step 9: shipped files

This step writes the last two machine files, `basic/msx2ide` and `advanced/mfrsd`,
with the machine file's `dos` line that the second needs, and the game files for the
collection, by running the capture over `CAS_DIR` on `advanced/phc28s`
([Shipped files](DESIGN.md#shipped-files)). The tests check a single-load game on
each of the seven shipped machines, then capture, build and check every game file on
`advanced/phc28s` and `basic/vg8020`, and write a report of passes and failures.

That run, `make collection`, takes hours, so it keeps a cache beside each machine's
report: each game file's result, with a hash of its inputs. The inputs are the
game's folder, its CAS files, the machine files that it runs on, and `bin/` and
`tools/`. A game file whose hash is unchanged keeps its result, so a run after a fix
to game files reruns only those, and a change to the code reruns all.
`COLLECTION_FULL=1` reruns every game file. The run does 11 at once, because the
efficiency cores of the Mac where it runs count as well.

## Step 10: automatic fixes

This step makes the fixes that the game files hold by hand automatic, so that a new
machine needs as few game files of its own as possible. It adds the slot patches of
the capture and of the scan ([Slot patches](DESIGN.md#slot-patches)), the mode
without a part in page 3 when page 3 has no room
([Without a part in page 3](DESIGN.md#without-a-part-in-page-3)), and the tries of
`tools/snapcas.py` on the capture variants
([Files and commands](DESIGN.md#files-and-commands)). The tests check each fix on a
game that needed it by hand, without its line: Sootland and Finders Keepers for the
slot patches, Chase H.Q. for the mode, and Sootland on the HB-F700P for the
variants. La Abadia del Crimen was the variants' test until the RAM search patch
fixed its load ([The RAM search patch](DESIGN.md#the-ram-search-patch)). The
collection then runs on all seven shipped machines, and the report lists the game
files that a machine still needs.

## Step 11: real hardware

The user runs the corpus on the Sanyo PHC-28S with the Sony HBM-64 in slot 1 and the
Carnivore2 in slot 2, and the results go in this page, with the machine and
cartridges named. A failure that `openMSX` does not show goes in the design's limits
until it is understood. `make try` starts `openMSX` with the same machine and the
same files, to compare.

| Date | Machine | Images | Result |
|---|---|---|---|
| 2026-10-29 | Sanyo PHC-28S, Sony HBM-64 in slot 1, Carnivore2 in slot 2, Nextor 2.1 | `FREDDY.SNP`, `FERNANDO.SNP`, `MOONRIDE.SNP`, `CALDERO.SNP`, from step 4 | All four games run |
| 2026-10-29 | The same | `ABADIA.SNP`, captured with `capture advanced/phc28s-noslot1` | La Abadia del Crimen runs, with the RAM cartridge in slot 1 |
| 2026-10-29 | The same | `KNIGHTMA.SNP`, with `snapshot at 130`, and the 31 images of the step 4 batch | All run |
| 2026-10-29 | The same | `GAUNTLET.SNP`, with `GAUNTLEB.CAS` as side 2, from step 5 | The main game and its levels load from the tape service, side 2 included, and the side's colour shows at the turn-over |
| 2026-10-29 | The same | `MOONWALK.SNP`, with `service t0`, from step 6 | The game loads through T0 and plays. The loading messages show a few wrong pixels, likely VRAM writes that come faster than the VDP accepts, because the tape service returns a byte much sooner than a tape; step 8's `/T1200` is to confirm it |
| 2026-10-31 | The same | `KNIGHT1.SNP`, from step 10 | Knight Orc hung after its first letter, because the scan had patched the `3E EF` of the address in `LD A,(EF3Eh)`. It plays since the scan skips a `3E` that can be an operand ([Slot patches](DESIGN.md#slot-patches)) |
| 2026-10-31 | The same | `GHOSTBUS.SNP`, from step 10 | Ghostbusters II loads, and its menu starts with SPACE, or with the fire button of a joystick in port 2. The menu reads PSG register 14 without selecting a port, and the BIOS's interrupt routine leaves port 2 selected on this machine, so a load from tape behaves the same |
| 2026-10-31 | The same | `NAVYMOV.SNP`, from step 10 | Navy Moves plays with the keyboard. With 2-JOYSTICK, the jet-ski jumped by itself and did not obey, as with the plain tape in `openMSX`. Two `patch` lines in `games/NAVY-MOV/game.txt` fix the game: its joystick controls now point at the joystick's row, and a sound effect no longer clears bit 7 of PSG register 7. The joystick then works in port 1, the only port that the game reads |
| 2026-10-31 | The same | `ALTERED.SNP`, from step 10 | Altered Beast hung with a yellow screen after side B's load: the game keeps its variables at FCE1h to FCE4h, where the service's entries are. With `service t0` and five `patch` lines in `games/ALTERED/advanced-phc28s.txt`, which send its loader's stub to T0, side B loads and the game plays. The wait of about 25 seconds before the prompt to turn the tape over is the game's own, as with the plain tape in `openMSX` |
| 2026-10-31 | The same | `OUTRUN.SNP`, `OPERATIO.SNP` and `DONKECAS.SNP`, from step 10, with the scan's slot patches | Out Run, Operation Wolf and Donkey Kong run |

## Step 12: the tools' code

This step moves the tools' code into the files of
[The tools' code](DESIGN.md#the-tools-code), and does not change what the tools do.
It splits `build()` and `service_segments()` into the build's steps. The proof is
that the outputs stay the same, byte for byte:

| Test | What it proves |
|---|---|
| Every snapshot of `out/` on the seven shipped machines, built again | The images and `scan.txt` files are the same as before the step |
| The collection on `advanced/phc28s` and `basic/vg8020` | The snapshots are the same as before the step, and every check passes |
| `make test` | The steps' tests pass |

## Step 13: the check's guard of page 3

This step adds to the check's point 2 the watch on the tape service's part of page 3
([Check](DESIGN.md#check)), after Altered Beast wrote its variables over the
service's entries on the real machine. The collection reports point 2's failure in
place of point 1's line:

| Test | What it proves |
|---|---|
| Gauntlet's check on `advanced/phc28s` | The service's own writes to the part, during the game's tape calls, do not count |
| 7 Card Stud's check on `advanced/phc28s` | The game's writes after the service has read the tape to its end do not count |
| The collection on `advanced/phc28s` and `basic/vg8020` | The games whose first 60 seconds write the part are listed, for a game file's `service t0` |

On those two machines, the guard listed 53 game files. Most of them were not games
that write the part. On the PHC-28S, 30 were captures whose loader had reset the
machine, so the image replayed a reboot, and the reboot wrote the part. Most of
those loaders cut off their own code ([Step 14](#step-14-the-ram-search-patch)).

## Step 14: the RAM search patch

This step adds the capture's watch for a slot register write that cuts off the code
that made it, and the patch of the RAM search that Mot's loader and many Opera Soft
loaders share ([The RAM search patch](DESIGN.md#the-ram-search-patch)). Mot and
Satan's game files took the tape of their part 2 for a side 2. Each part now has a
game file of its own, and Mot's demo has its own as well.

| Test | What it proves |
|---|---|
| Mot, its demo and the 20 other tapes with the search that reset the PHC-28S, on `advanced/phc28s` | The capture patches the search, and each check passes |
| Mot on `basic/vg8020` | A machine whose RAM for page 3 is in the slot that the loader finds gets no patch |
| Made in Spain on `advanced/phc28s` | Each copy of the search on a tape is patched |
| Sootland's variant test on `advanced/hbf700p` | Replaces La Abadia del Crimen's, whose load the patch fixes there |

## Step 15: TSX tape files

This step adds the reader of TSX files and the tape model, and moves the code that
reads CAS files behind the model ([Tape files](DESIGN.md#tape-files)). The tools'
`--cas` folder becomes `--tapes`, because it holds both formats, and the game file
gets the keys `tsx` and `load`. The tests use TSX files from the collection that the
TSX experiment loaded, each chosen for a case of the design, from the `tsx/` folder
of `CAS_DIR`. Part 2, the reader, checks the times of the blocks against `openMSX`'s
length of the tape:

| Test | What it proves |
|---|---|
| A TSX file with only standard blocks, whose CAS file is in the collection | The two files load the same game: its RAM page is the same, though the TSX file keeps the original tape's timing |
| Two single-load TSX files with turbo blocks | A turbo loader loads its whole tape in the capture, and the image passes the check |
| A tape of TSX bytes whose first block is a turbo block, with and without `load` | The load command comes from the game file, and without it the capture stops |
| A tape of TSX bytes with a turbo block after the snapshot's time | The build stops with an error that names the block, unless the game file has `service no` |
| A patch line at an offset in a TSX file | The capture loads the patched file |
| The collection on `advanced/phc28s` and `basic/vg8020` | The CAS game files keep their results behind the model |
