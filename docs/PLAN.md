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
| `CAS_DIR` | Make variable: the folder of the user's CAS files, by default `tapes/`, which git ignores |
| Nextor | `NEXTOR.SYS` 2.11 and `COMMAND2.COM` 2.44 from Nextor 2.1.0's `tools.zip`, downloaded by the Makefile into `out/dl/nextor/`, checked by SHA-256 |
| `DOS_DIR` | Make variable: a folder with `msxdos2/` (`MSXDOS2.SYS`, `COMMAND2.COM`) and `msxdos1/` (`MSXDOS.SYS`, `COMMAND.COM`), by default `dos/`, which git ignores |

The test machines are the six shipped machines and two machine files that only the
tests use, in `machines/test/`. Each one boots the DOS of its row:

| Machine file | DOS | Why |
|---|---|---|
| `advanced/phc28s`, `basic/vg8020`, `basic/msx2ide` | Nextor | Shipped |
| `advanced/mfrsd` | Nextor 2.10, from the ROM disk in the cartridge's flash | Shipped |
| `basic/nms8250`, `advanced/hbf700p` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | Shipped |
| `test/nms8250-dos1` | `DOS_DIR/msxdos1/`, from the NMS 8250's own disk ROM | No shipped machine runs MSX-DOS 1 |
| `test/nms8250-512k` | `DOS_DIR/msxdos2/` | An NMS 8250 whose single mapper holds 512 KB, because 128 KB cannot hold Moonwalker's 236 KB tape |

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
on `advanced/phc28s`, then on `basic/vg8020`, `basic/nms8250`, `advanced/hbf700p`
and `test/nms8250-dos1`. Check point 1 must pass on each machine, except where the
restorer stops because DOS leaves too few free segments: the test then checks that
the restorer's message names the segments needed and free. The savestates stay in
`check/` for the user to look at.

The results of the step:

| Machine | Passes point 1 | Other results |
|---|---|---|
| `advanced/phc28s`, `basic/vg8020` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | La Abadia crashes during its load when a Carnivore2 is present |
| `basic/nms8250` | El Caldero Magico | MSX-DOS 2 leaves 2 free segments of the 8 in 128 KB, so the restorer stops for the other games, naming the segments needed and free |
| `advanced/hbf700p` | Moonrider, El Caldero Magico, La Abadia | `FREDDY.CAS` and `FERNANDO.CAS` do not load to their end in `openMSX` |
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
| `SOOTLAND.CAS` | `advanced/phc28s`, captured on `advanced/phc28s-nodisk` | With a `side1` patch of the slot register's value that its loader writes: that the capture loads the patched tape, and that the game reads side 2 through the tape service ([Game file](DESIGN.md#game-file)) |
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
each of the six shipped machines, then capture, build and check every game file on
`advanced/phc28s` and `basic/vg8020`, and write a report of passes and failures.

## Step 10: real hardware

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
