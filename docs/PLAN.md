# `snapcas` plan

This page lists the steps that build the first version of `snapcas`, in order, and
the tests that each step adds. It is for the developers, and it follows the design
([DESIGN.md](DESIGN.md)). Each step ends with a review by the user before the next
one starts. One command, `make test`, runs the whole test suite.

## Test setup

The build pins its tools. The tests read their tape files from `tests/tapes/`, in
git. They read the MSX-DOS system files from a folder that the user names, because
`snapcas` cannot ship MSX-DOS. Two commands run the tests:

| Command | What it runs | Time |
|---|---|---|
| `make unit` | The pure tier, whose tests start no `openMSX` and read no tape of `tests/tapes/` | About 3 seconds |
| `make test` | Both tiers, the pure tier and the emulator tier. The emulator tier's tests run `openMSX`, muted and without a window | About 2 minutes |

The setup holds these items:

| Item | Value |
|---|---|
| Assembler | sjasmplus 1.24.0, downloaded and built by the Makefile, checked by SHA-256 |
| Emulator | `openMSX` 22.0, on the path, with the system ROMs of the test machines and of the `msxdos2` cartridge |
| Python | Python 3, standard library only |
| Tapes | `tests/tapes/`: the corpus, the TSX files of step 15, and the collection's tapes that the other steps name. The Makefile's `TEST_TAPES` lists them, so `make test` stops when the folder lacks one |
| Nextor | `NEXTOR.SYS` 2.11 and `COMMAND2.COM` 2.44 from Nextor 2.1.0's `tools.zip`, downloaded by the Makefile into `dos/nextor/`, checked by SHA-256 |
| `DOS_DIR` | A Make variable. Its value is a folder with `msxdos2/` (`MSXDOS2.SYS`, `COMMAND2.COM`) and `msxdos1/` (`MSXDOS.SYS`, `COMMAND.COM`). The default is `dos/`, which git ignores |

A tier is a property of a test module. `tests/support.py` lists the modules of the
pure tier, and every other test module is in the emulator tier. `tests/support.py`
also holds what two test modules share, so no test module imports another. Each
module is named after what it tests:

| Module | Tier | What it tests |
|---|---|---|
| `test_gamefile.py` | Pure | Game files: each kind of line, each error, a machine's game file, and the shipped game files |
| `test_tape.py` | Pure | The readers of CAS and TSX files, the tape model, and a load that starts at a later file, on tapes that the test writes |
| `test_snapshot.py` | Pure | A snapshot's folder |
| `test_build.py` | Pure | The image: the build's helpers, the layout's one source, and `build.py` on a snapshot that the test writes |
| `test_patches.py` | Pure | The patterns of the automatic patches, and the settings that the capture's Tcl gets |
| `test_gate.py` | Pure | `check.py`'s reading of a report, its exit status and its failures. The test gives `openMSX`'s end |
| `test_pipeline.py` | Pure | The steps of an image, the trials of the capture variants, and their result |
| `test_gamesrun.py` | Pure | The games run: its lists, its three groups, its exit status and its cache, on results that the test gives |
| `test_cli.py` | Pure | The `snapcas` command's verbs, and the tools' command lines |
| `test_msx.py` | Pure | Machine files, the Tcl that `tools/msx.py` writes, and how `tools/msx.py` treats `openMSX`'s end |
| `test_download.py`, `test_custom.py`, `test_card.py` | Pure | The download of a tape, custom games, and the sync of a card |
| `test_harness.py` | Emulator | Runs of `openMSX` and the prelude's procedures, in the C-BIOS machine, and the tests' own setup |
| `test_capture.py` | Emulator | The capture of single-load games, its Tcl procedures in the C-BIOS machine, the images of captured snapshots, and a patched tape with two sides |
| `test_corpus.py` | Emulator | The scan over the corpus |
| `test_restore.py` | Emulator | The restorer on images that the test writes: its messages, its stops, its plan, and a restore to the tail's jump |
| `test_machines.py` | Emulator | The single-load games of the corpus on the test machines, one game on every shipped machine, and the games of the RAM search patch |
| `test_service.py` | Emulator | The tape service in restored games: loads during play, the contracts of its entries, the manual tape, and the check's guard of its part of page 3 |
| `test_check.py` | Emulator | The check's points 3 and 4 on games, and `check.tcl`'s own errors in the C-BIOS machine |
| `test_snap.py` | Emulator | `snapcas.py snap` on games, and the automatic fixes |
| `test_tsx.py` | Emulator | The TSX files of the collection |

`tests/run.py` runs the tests for both commands. It runs each test class in a
process of its own, 8 at once. When a module has one setup for all its classes, it
runs the whole module at once. It prints each class's time, its result and its
number of tests, and then the output of each class that fails. It exits with 1 when
a test fails or ends in an error, when it cannot import a test module, and when its
arguments select no test. It takes these arguments:

| Argument | What it does |
|---|---|
| `--pure` | Runs the pure tier only. `OPENMSX` then names no program, so a test of that tier that starts `openMSX` fails |
| A text, such as `restore` or `Stops.test_a_cut` | Runs only the tests whose ID holds the text. A test's ID is `<module>.<class>.<test>`. With several texts, it runs the tests of each |
| `--list` | Prints the IDs of the tests that it would run, and runs none |
| `--workers <n>` | Runs n classes at once, in place of 8 |

A test is skipped only when it needs the files of MSX-DOS 1 or MSX-DOS 2 and
`DOS_DIR` does not hold them. `tests/run.py` prints each skipped test under its
reason, and the number of skipped tests in its last line. A tape or a built file
that is missing is an error of the setup, so it fails the test. `make test` stops
before the tests when `tests/tapes/` lacks a tape.

Most tests use three pieces of `tests/support.py`:

| Piece | What it gives |
|---|---|
| `snapshot` | A small snapshot folder that the test writes, in place of a capture's: `state.txt`, `ram/`, `vram.bin`, `rom.bin`, `slots.txt` and `log.txt`. Its parameters choose RAM in a mapper or outside one, the tape service, one segment in two pages, and an MSX2's state. The pure tier builds its images from it |
| `restore`, `assert_passes` and `assert_fails` | A game's capture, build and check as programs, and the gate. A game passes only when `check.py` exits with 0 and its report holds all four points as passed. A check that fails must exit with 3 and fail at the one point that the test names |
| `synthetic_image`, `restorer_screen`, `restorer_plans` and `restorer_memory` | An image that the test writes, and a run of `SNAPCAS.COM` on it. The run gives the messages on the screen, or the restorer's plan. The plan is the segment of each record, the holding segments and T0's segment, read from the restorer's memory before the restorer reads a record. Or the run gives the restored machine's memory at the tail's jump |

The test machines are the 13 shipped machines and six machine files that only the
tests use, in `machines/test/`. With its `dosfiles` line, each machine file names
the DOS that it boots. A machine file without that line boots Nextor. The tests take
each machine's DOS files from that line, so a new shipped machine needs no line in
the tests:

| Machine file | DOS | Why |
|---|---|---|
| `fsa1-mfrsd`, `hb75p-carnivore2`, `hbf1xd-mfrsd`, `nms8245-ram512k-sunriseide`, `nms8250-carnivore2`, `phc28s-ram64k-carnivore2`, `vg8020-carnivore2`, `vg8020-picoverse`, `vg8020-sdmapper`, `xp800-sdmapper` | Nextor | Shipped |
| `hb75p-mfrsd` | Nextor 2.10, from the ROM disk in the cartridge's flash | Shipped |
| `hbf700p-ram512k-msxdos2` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | Shipped |
| `vg8235` | `DOS_DIR/msxdos1/`, from the VG-8235's own disk ROM | Shipped |
| `test/nms8250-dos1` | `DOS_DIR/msxdos1/`, from the NMS 8250's own disk ROM | No shipped machine runs MSX-DOS 1 |
| `test/nms8250-512k` | `DOS_DIR/msxdos2/` | An NMS 8250 whose single mapper holds 512 KB, because 128 KB cannot hold Moonwalker's 236 KB tape |
| `test/nms8250-128k` | `DOS_DIR/msxdos2/` | The NMS 8250 with only its own 128 KB, for the restorer's message when DOS has too few free segments |
| `test/nms8250-4m-dos1` | `DOS_DIR/msxdos1/` | An NMS 8250 whose single mapper holds 4 MB. MSX-DOS 1 leaves the mapper's last segment, 255, free |
| `test/nms8250-4m-ram4mb-dos1` | `DOS_DIR/msxdos1/` | The same NMS 8250 with a RAM cartridge of 4 MB in slot 1. The cartridge's mapper, which is DOS's, and the machine's own mapper both have a segment 255. The test puts a page in segment 255 of the machine's own mapper |
| `test/hc90a-msxdos2` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | The Victor HC-90A has its main ROM and its mapper in one slot, 0-0 and 0-2. The tests use this machine for the restorer's stop for `rom keep` there |

`test/nms8250-512k`, `test/nms8250-4m-dos1` and `test/nms8250-4m-ram4mb-dos1` each
use a machine configuration that the Makefile makes from `openMSX`'s own NMS 8250,
with its mapper at 512 KB or at 4 MB. The Makefile puts these configurations in a
private `openMSX` home, which `OPENMSX_HOME` names, with links to the user's system
ROMs.

The corpus is a fixed set of CAS files from File-Hunter's collection, one or more
for each case that the design lists:

| Case | File | Load command |
|---|---|---|
| Single load, the first game that failed on the PHC-28S | `FREDDY.CAS` (Freddy Hardest) | `RUN"CAS:"` |
| Single load, slot search from slot 0 up | `FERNANDO.CAS` (Fernando Martin Basket Master) | `RUN"CAS:"` |
| Single load that pauses on its own for 16 seconds | `022-MOON.CAS` (Moonrider) | `RUN"CAS:"` |
| Single load that waits for a key, on an NMS 8250. On the PHC-28S its loader puts slot 1 in page 3 and crashes | `ABADIA.CAS` (La Abadia del Crimen) | `BLOAD"CAS:",R` |
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
  and presses the `boot` keys. With `diskmanipulator`, it makes a disk image of the
  kind that the machine file's `disk` command takes.
- A first `SNAPCAS.COM` that opens `<GAME>.SNP`, prints its usage without a name,
  and prints an error when the file is missing or is not an image.

The test, `Usage` in `tests/test_restore.py`, boots `phc28s-ram64k-carnivore2` with
a disk of Nextor's files, `SNAPCAS.COM` and three bad images. The bad images are
`SHORT.SNP` of 3 bytes, `BAD.SNP`, which starts with `SNAPDISK`, and `OLD.SNP`,
which starts with `SNAPCAS2`. The test runs `SNAPCAS`, then `SNAPCAS` with `NONE`,
`SHORT`, `BAD` and `OLD`, and reads the usage and the four errors from the screen
with `get_screen`. It proves the assembler, the disk image, the boot keys and the
screen reading. `Run` in `tests/test_harness.py` runs scripts in `openMSX`'s C-BIOS
machine. It checks that `stop` ends a run immediately, and that an error of a script
ends `openMSX` and reaches the caller.

## Step 2: capture

This step writes `tools/capture.py`, with capture steps 1 to 6, the RAM rules and
the snapshot files ([Capture](INTERNALS.md#capture)). It also writes the machine
file `nms8250-carnivore2`. The tests, `SingleLoads` in `tests/test_capture.py`,
capture the single-load files of the corpus. They capture `ABADIA.CAS` on
`test/nms8250-128k` and all the other files on `phc28s-ram64k-carnivore2`. The tests
check:

- That `state.txt` holds every name of the register table, and that `service` is 0
  for the files on `phc28s-ram64k-carnivore2`.
- That every kept page holds RAM and is in slot 0's page 3, in slot 1 or in the
  Carnivore2's subslot 2-2, and that the Carnivore2's mapper has 64 segments.
- That `ABADIA.CAS` continues after a key, and that `log.txt` names it. Also that
  its game file's `service no` leaves out the tape service, because its last 16 KB
  stay unread.
- That a second capture of the same file gives the same snapshot.
- That `state.txt` holds the slot and mapper registers with two digits, and the size
  of the Carnivore2's mapper.

A second group of tests, `Procedures` in the same module, runs the capture's Tcl
procedures in `openMSX`'s C-BIOS machine, which needs no system ROMs. The procedures
run at 1 emulated second, when the BIOS has set the slot register. At time 0 the
register reads back as 0 whatever a script writes to it. The tests check:

- That a read of memory selects the slots that it is given, wraps at FFFFh, and
  puts the slot register back after the read and after an error.
- That the tape position after a turn to a side 2 without a standard block is side
  2's start.
- That the watchpoints on the slot register leave out the snapshot's own writes.
- That a reset during a key try follows the machine, so that the try's rewind drops
  it.
- That the log holds once each write that names a slot that holds nothing, and holds
  no write from the main ROM.
- That an error stops the capture immediately, and that a later error does not
  replace that error in `error.txt`.
- That a boot without BASIC's `Ok` leaves the error and the screen's text in
  `log.txt`.

## Step 3: build

This step writes `tools/build.py` for games without the tape service, and
`src/service.asm` with the tail only. The tests check the image against the design's
tables ([Formats](DESIGN.md#formats)). Most of the tests build the image of a
snapshot that the test writes, so they need no capture:

| Module and classes | What they check |
|---|---|
| `tests/test_build.py`: `Crc`, `PortWrites`, `Tail`, `ServicePart`, `Service`, `Synthetic` | The CRC-16. The port-write order of an MSX1 and of a V9938. The tail's place below the stack pointer, its bytes, and the stops for a stack that leaves it no place. The place of the service's part of page 3, and the stop for a tail under it. The records and the service's segments, the stop for a tape that is too long, a segment in two pages, segment 255, and the limit of 255 records |
| `tests/test_build.py`: `ServiceFile`, `Layout` | `SERVICE.BIN`'s version, parts and symbols. The restorer, `SERVICE.BIN` and [FORMATS.md](FORMATS.md) have one layout |
| `tests/test_build.py`: `Program` | `build.py` as a program: the files that it writes, its exit status 1 for an error in its input, and its stop for a `SERVICE.BIN` of another version |
| `tests/test_snapshot.py`: `SelectedPage`, `SnapshotFolder` | A snapshot's folder as the build reads it. A mapper register selects the page of its value modulo the mapper's size, with a snapshot's sizes and without them |
| `tests/test_capture.py`: `Images` | The header, the records, the port writes and the tail of the images of captured snapshots. Three are of `phc28s-ram64k-carnivore2`, and one is of `FREDDY.CAS` on `nms8250-carnivore2`, for the V9938's port writes |

## Step 4: restorer and check

This step writes `SNAPCAS.COM` without the tape service, restorer steps 1 to 7
([Restorer](INTERNALS.md#restorer)), `tools/check.py`, and the machine files of its
tests. `Corpus` in `tests/test_machines.py` captures, builds and checks each
single-load file of the corpus on `phc28s-ram64k-carnivore2`, `vg8020-carnivore2`,
`nms8250-carnivore2`, `hbf700p-ram512k-msxdos2`, `test/nms8250-128k` and
`test/nms8250-dos1`. Each game must pass the gate on each machine. A game passes the
gate when `check.py` exits with 0 and its report holds all four points as passed.
The exception is a machine where the restorer stops because DOS leaves too few free
segments. There the test checks that the restorer's message names the segments
needed and free, and that the check ends at that message with exit status 3. The
savestates stay in `check/` for the user to look at.

Further tests check the check and the restorer themselves:

| Module and class | What it checks |
|---|---|
| `tests/test_machines.py`: `Corpus` | A game folder whose path holds `[`, `]` and `*` has its RAM pages compared. A changed byte in a page of its snapshot fails point 1 |
| `tests/test_gate.py`: `Report` | `check.py` gives each report its exit status, and only a report with all four points passes. The address of the restorer's `stop_message` comes only from the symbols of the same assembly as `SNAPCAS.COM` |
| `tests/test_gate.py`: `Gate` | `check.py` on a built image. The test gives `openMSX`'s end. A failed point gives exit status 3. These are runs that broke, with exit status 2: a report with only point 1, no report, an `openMSX` that ends with another status than 0 or by a signal, and a timeout. An error in the input files gives exit status 1 before `openMSX` starts. The savestates go to `check/`, and none stays in `openMSX`'s home |
| `tests/test_check.py`: `Script` | An error of a callback of `check.tcl` fails its point in the report, and a check that never ends stops at its deadline. Both run in `openMSX`'s C-BIOS machine |
| `tests/test_restore.py`: `Stops`, `RomKeep`, `Dos1` | The restorer's stops, on images that the test writes: a cut file, a record that cannot be read after a VRAM block, RAM without a mapper in DOS's mapper's slot, a slot that is not expanded as at the capture, `rom keep` with the ROM in DOS's mapper's slot, and MSX-DOS 1 outside segments 3 to 0 |
| `tests/test_restore.py`: `Plan` | The restorer's plan in a mapper of 4 MB under MSX-DOS 1. A page goes straight into segment 255, the list of holding segments holds 64, and a 65th stops the restorer |
| `tests/test_restore.py`: `OtherMapper` | A RAM page in segment 255 of a mapper that is not DOS's is copied into that segment, on `test/nms8250-4m-ram4mb-dos1`. It is not in DOS's mapper, and not in the segment that its page selected |
| `tests/test_restore.py`: `Manual` | The restorer reads `/M` in its command line in upper case or lower case, and an image without the part in page 3 gets the note that the tape stays automatic |
| `tests/test_restore.py`: `Fill` | The restorer fills in the record that the header names. The image is of a snapshot that the test writes. The snapshot's pages 2 and 3 select one mapper segment, so one record of page 2 holds the tail and the game's page 3. The restore runs to the tail's jump on `test/nms8250-512k`. The tail then holds the build's bytes and the restorer's values, and page 3 holds the service's part with the restorer's values and SLTTBL's |

The results of the step:

| Machine | Passes the check | Other results |
|---|---|---|
| `phc28s-ram64k-carnivore2` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico, La Abadia | La Abadia crashed during its load when a Carnivore2 is present, until the RAM search patch ([Step 14](#step-14-the-ram-search-patch)). The test also checks it with `capture phc28s-empty-carnivore2` |
| `vg8020-carnivore2` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | La Abadia is not in the test on this machine |
| `nms8250-carnivore2` | Freddy Hardest, Fernando, Moonrider, El Caldero Magico | The Carnivore2's mapper under Nextor has room for every game |
| `hbf700p-ram512k-msxdos2` | Moonrider, El Caldero Magico, La Abadia | `FREDDY.CAS` and `FERNANDO.CAS` do not load to their end in `openMSX` |
| `test/nms8250-128k` | El Caldero Magico | MSX-DOS 2 leaves 2 free segments of the 8 in 128 KB, so the restorer stops for the other games and names the segments needed and free |
| `test/nms8250-dos1` | All five | |

The test leaves out the games that fail in `openMSX` itself.

## Step 5: tape service

This step adds the tape service to `src/service.asm`, `build.py` and `SNAPCAS.COM`
([Tape service](INTERNALS.md#tape-service)). It also adds the game file's `patch`
lines to `build.py` ([Game file](FILES.md#game-file)), which the scan of step 6
builds on. The tests, `Loads` in `tests/test_service.py`, capture, build and check
two files on `phc28s-ram64k-carnivore2`: `COMPUTAD.CAS`, and `GAUNTLET.CAS` with
`GAUNTLEB.CAS` as side 2. Each game must pass the gate, with `service` at 1 in
`state.txt`. The plays then start from the check's savestate at 10 seconds. An error
of a play's Tcl ends `openMSX`, so the test fails. For Computad, the Tcl script
presses space, space, 1, RETURN and space, which load the first theme. The script
checks that the tape position in the code segment moves to the theme's end.
Gauntlet's loaders select the ROM in page 0 from their own copy of the slot
register. The game file of Gauntlet therefore has `patch` lines for their tape calls
and for the sum at the end of the main game's block. Gauntlet's menus read the
joystick, which `openMSX` cannot press from a script. The Tcl script therefore
clears the button's bit in register A after the game reads PSG register 14. The
script then plays through the intro and the menus to the side 2 prompt. It checks
that the main game loads to side 1's end and that a level loads from side 2.

## Step 6: scan

This step adds the scan and its patches ([Scan](INTERNALS.md#scan)). `Patterns` in
`tests/test_patches.py` checks each of the scan's patterns on bytes made for it.
`Corpus` in `tests/test_corpus.py` captures each file of the corpus's list on
`phc28s-ram64k-carnivore2`, with a side 2 file as the side 2 of its game. The test
builds each file, and writes every `scan.txt` into one report. Every file must
capture and build. The test checks the findings that have been confirmed by hand.
For Gauntlet, these findings are the calls of `TAPION` and `TAPIN` at E15Fh and
E1ABh in page 3, patched, and at AE88h and AED4h of side 1, listed. A game's
findings join the check when they are confirmed.

The step also takes the tests that need the scan, all on `phc28s-ram64k-carnivore2`.
Each game must pass the gate before its play:

| File | Class | What the test checks |
|---|---|---|
| `TOUR-91.CAS` | `Stubs` in `tests/test_service.py` | That the game's stub reaches the tape service at its next load |
| `MAD-MIDE.CAS` | `Stubs` | The same |
| `DESPERAD.CAS` | `Stubs` | The same, for a loader that selects the ROM in page 0 itself, with `IN A,(0A8h) / AND 0FCh / OR 00h / OUT (0A8h),A` |
| `MOONWALK.CAS` | `WithoutAPartInPage3` in `tests/test_service.py` | The test runs with `service t0`, with the game's snapshot in the intro, and with the scan's patch that makes the game's loader's stub select DOS's mapper. It checks that the main game loads through T0, to the end of its 22 KB block ([Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)) |
| `SOOTLAND.CAS`, captured on `phc28s-ram64k` | `PatchedTape` in `tests/test_capture.py` | The test runs with a `side1` patch of the slot register's value that the game's loader writes. It checks that the capture loads the patched tape, and turns the tape over to side 2 when the game reads past side 1's end ([Game file](FILES.md#game-file), [Capture](INTERNALS.md#capture)) |
| `tests/borrow.asm`, which the test writes to a CAS file with a block of the bytes 0 to 255 | `BorrowedBySlot` in `tests/test_service.py` | The test runs with `service t0` and a `patch` line that makes the game select DOS's mapper in page 0. It checks that `TAPIN` borrows page 2 through the slot register and reads the block correctly. Page 2 holds the RAM cartridge in slot 1 and the stack |
| `tests/contract.asm`, which the test writes to four CAS files, each with its cases and with blocks of known bytes | `Contracts` in `tests/test_service.py` | That each entry of the tape service returns as the BIOS's routine does. The game calls each entry with known registers and interrupts on or off, and keeps AF, BC, DE, HL and the interrupt state after the call ([Tape service](INTERNALS.md#tape-service)). The calls go through T0's jump table and through the entries in page 3, and with `service t0`. On the manual tape, which the test asks for with `/M` in the restorer's command line, the test checks that the restorer sets the code segment's mode. On the manual tape, the test also checks that CTRL+STOP ends a `TAPION` and a `TAPIN` that wait, with carry and the tape still stopped where it was. On a tape that ends with a header, the test checks that the entry code's deepest path takes 20 of its stack's 22 bytes |

## Step 7: replay (dropped)

This step was to play a recording of the first load, its screen and its tape's
sound, before the restore. It was dropped, and the steps after it keep their
numbers.

## Step 8: tape speed and sound (dropped)

This step added `/T1200` and `/T2400`, which made the tape service's loads take a
tape's time and play the tape's sound. It was dropped, and its code was removed.

## Step 9: shipped files

This step writes the last two machine files, `nms8245-ram512k-sunriseide` and
`hb75p-mfrsd`, with the machine file's `dos` line that the second needs. It also
writes the game files for the collection, by running the capture over `CAS_DIR` on
`phc28s-ram64k-carnivore2` ([Shipped files](FILES.md#shipped-files)). The tests
check a single-load game on each shipped machine. The games run then captures,
builds and checks every game file on `phc28s-ram64k-carnivore2` and
`vg8020-carnivore2`, and writes a report of passes and failures. These tests cover
the step without the games run itself:

| Module and class | What it checks |
|---|---|
| `tests/test_machines.py`: `Shipped` | El Caldero Magico passes the gate on every machine file of `machines/`, with the DOS files that the machine file names |
| `tests/test_gamefile.py`: `MachineFile`, `ShippedGameFiles` | A machine's game file adds its lines for its machine only. Every shipped game file reads, on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` |
| `tests/test_snap.py`: `OneCommand` | `snapcas.py snap` with `--check` makes and checks an image, and prints each step and each point |
| `tests/test_pipeline.py`: `Pipeline` | The result of the steps: the failed step, its status and its message, a run that broke, and the trials of the capture variants |
| `tests/test_gamesrun.py`: `Lists`, `Run` | The games run on four game files and results that the test gives. The two lists are read and checked before the run. The games run prints the failures in three groups, and the exit status is 3 only for a failure in neither list. A game file whose inputs are unchanged is not run again. A result of a run that broke is not kept, and a pass whose image is gone runs again |

The games run, `make games MACHINE=<machine>` since step 24, takes hours, so it
keeps a cache beside each machine's report. The cache holds each game file's result,
with a hash of the game file's inputs. The inputs are the game's folder, its tape
files, the machine files that it runs on, `bin/` and `tools/`, the DOS files that
the check boots, and `openMSX`'s version. A game file whose hash is unchanged keeps
its result. A run after a fix to game files therefore reruns only those game files,
and a change to the code reruns all. A result of a run that broke, such as an
`openMSX` that stopped, is not kept
([INTERNALS.md, The games run](INTERNALS.md#the-games-run)). `FULL=1` reruns every
game file. The run does 11 at once, because the efficiency cores of the Mac where it
runs count as well.

Some game files fail on a machine in `openMSX` itself, without `snapcas`. A plain
load of the tape, with the same machine and no capture code, fails there too. Those
are not failures of `snapcas`, so `tests/openmsx-failures.txt` lists them, with the
machine, the game file's folder and what fails, to try again at the end. A listed
game file that passes is only noted, so that its line can be removed, because an
`openMSX` failure can appear and disappear. A patch line can still make such a game
work later. The game files that load in a plain `openMSX` but fail with `snapcas`
are `snapcas`'s own failures, to fix. `tests/snapcas-failures.txt` lists them in the
same form. The run passes when every game file that fails is in one of the two
lists. It prints the failures of each list as a group of their own, so the known
failures of `snapcas` show until they are fixed, and a new failure, in neither
list, fails the run and shows apart from them.

From 1 November 2026 the work focuses on two machines: `phc28s-ram64k-carnivore2`,
the user's own, and `vg8020-carnivore2`, the plain MSX1. On the other five the
collection's failures go into the two lists only, and no more is done there until
later.

## Step 10: automatic fixes

This step makes automatic the fixes that the game files hold by hand, so that a new
machine needs as few game files of its own as possible. It adds the slot patches of
the capture and of the scan ([Slot patches](INTERNALS.md#slot-patches)), the mode
without a part in page 3 when page 3 has no room
([Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)), and the tries
of `snapcas.py snap` on the capture variants
([Files and commands](DESIGN.md#files-and-commands)). The tests of
`tests/test_snap.py` check each fix on a game that needed it by hand, without its
line, through `snapcas.py snap`. Each game must pass the gate. `SlotPatches` has
Sootland, Finders Keepers, Rocky, Uchi Mata and Doki Doki Penguin Land for the slot
patches, and `PageCopy` has Emerald Isle. `WithoutPage3` has Chase H.Q. for the
mode, and `Variants` has Digger Dungeon on the HB-F700P. La Abadia del Crimen was
the variants' test until the RAM search patch fixed its load
([The RAM search patch](INTERNALS.md#the-ram-search-patch)). Sootland was the
variants' test until the patch that keeps page 3 fixed it. The collection then runs
on all seven shipped machines, and the report lists the game files that a machine
still needs.

Two groups of tests need no game:

| Module and class | What it checks |
|---|---|
| `tests/test_patches.py`: `SlotPatches`, `Kinds`, `PageCopy`, `T0Stub` | The patterns of each kind on bytes made for it. The capture's Tcl gets the forms of the slot patches from `tools/patches/slots.py`, and each kind's hooks in the order of the kinds |
| `tests/test_restore.py`: `T0Segment` | T0 takes the segment of the game's page 0 in another mapper. The test writes the images for the HB-F700P, whose own mapper is not DOS's. The restorer reads T0 straight into that segment when the segment is free in DOS's mapper, and T0 goes through a holding segment when DOS uses the segment. The restorer stops when two pages for page 0 have different segments, when the segment is beyond DOS's mapper, and when a RAM page of DOS's mapper has that segment. Afterburner on the HB-F700P is the game with such a page 0, and its tape is not among the tests' tapes |

## Step 11: real hardware

The user runs the corpus on the Sanyo PHC-28S with the Sony HBM-64 in slot 1 and the
Carnivore2 in slot 2. The results go in this page, with the machine and the
cartridges named. A failure that `openMSX` does not show goes in the design's limits
until it is understood. `./snapcas.py try <game> <machine>` starts `openMSX` with
the same machine and the image, to compare.

| Date | Machine | Images | Result |
|---|---|---|---|
| 2026-10-29 | Sanyo PHC-28S, Sony HBM-64 in slot 1, Carnivore2 in slot 2, Nextor 2.1 | `FREDDY.SNP`, `FERNANDO.SNP`, `MOONRIDE.SNP`, `CALDERO.SNP`, from step 4 | All four games run |
| 2026-10-29 | The same | `ABADIA.SNP`, captured with `capture phc28s-empty-carnivore2` | La Abadia del Crimen runs, with the RAM cartridge in slot 1 |
| 2026-10-29 | The same | `KNIGHTMA.SNP`, with `snapshot at 130`, and the 31 images of the step 4 batch | All run |
| 2026-10-29 | The same | `GAUNTLET.SNP`, with `GAUNTLEB.CAS` as side 2, from step 5 | The main game and its levels load from the tape service, side 2 included, and the side's colour shows at the turn-over |
| 2026-10-29 | The same | `MOONWALK.SNP`, with `service t0`, from step 6 | The game loads through T0 and plays. The loading messages show a few wrong pixels. The likely cause is VRAM writes that come faster than the VDP accepts, because the tape service returns a byte much sooner than a tape. Step 8's `/T1200` is to confirm that cause |
| 2026-10-31 | The same | `KNIGHT1.SNP`, from step 10 | Knight Orc hung after its first letter, because the scan had patched the `3E EF` of the address in `LD A,(EF3Eh)`. It plays since the scan skips a `3E` that can be an operand ([Slot patches](INTERNALS.md#slot-patches)) |
| 2026-10-31 | The same | `GHOSTBUS.SNP`, from step 10 | Ghostbusters II loads, and its menu starts with SPACE, or with the fire button of a joystick in port 2. The menu reads PSG register 14 without selecting a port, and the BIOS's interrupt routine leaves port 2 selected on this machine. A load from tape therefore behaves the same |
| 2026-10-31 | The same | `NAVYMOV.SNP`, from step 10 | Navy Moves plays with the keyboard. With 2-JOYSTICK, the jet-ski jumped by itself and did not obey, as with the plain tape in `openMSX`. Two `patch` lines in `games/NAVY-MOV/game.txt` fix the game. Its joystick controls now point at the joystick's row, and a sound effect no longer clears bit 7 of PSG register 7. The joystick then works in port 1, the only port that the game reads |
| 2026-10-31 | The same | `ALTERED.SNP`, from step 10 | Altered Beast hung with a yellow screen after side B's load, because the game keeps its variables at FCE1h to FCE4h, where the service's entries are. With `service t0` and five `patch` lines in `games/ALTERED/phc28s-ram64k-carnivore2.txt`, which send its loader's stub to T0, side B loads and the game plays. The wait of about 25 seconds before the prompt to turn the tape over is the game's own, as with the plain tape in `openMSX` |
| 2026-10-31 | The same | `OUTRUN.SNP`, `OPERATIO.SNP` and `DONKECAS.SNP`, from step 10, with the scan's slot patches | Out Run, Operation Wolf and Donkey Kong run |
| 2026-11-02 | The same | `ENGESOFT\ATHLETIC.SNP`, `SUPERMSX\VERTIGO.SNP` and `SUPERMSX\ALIENS.SNP`, `D\DAMBUST.SNP`, `ENGESOFT\HYPERSP3.SNP` and `K\KONAMI.SNP`, from step 16's collection run | Athletic Land and Vertigo run. Aliens and Dam Busters reboot to the boot screen and Hyper Sports 3 reboots into DOS, as point 3 reports. Konami's Soccer reboots into DOS, though `openMSX`'s check passed it. That result led to point 3's third sign ([Check](INTERNALS.md#check)) |
| 2026-11-02 | The same | `K\KONAMI.SNP`, `B\BUDOKAN.SNP`, `B\BEACHHE.SNP`, `M\MDROID.SNP` and `SUPERMSX\ALIENS.SNP`, with the fixes for loaders that take page 3's slot for the other pages ([Page 3's slot for the other pages](INTERNALS.md#page-3s-slot-for-the-other-pages)) | All five run. Konami's Soccer flashes its title until a key, and Budokan is silent at its menu, as they are in `openMSX` |
| 2026-11-03 | The same | The 1,545 images of `phc28s-ram64k-carnivore2`, copied to the card with `sync`, and `G\GAUNTLET.SNP` played | `CD \SNAPCAS\G` and `\BIN\SNAPCAS GAUNTLET` start the game from the card's layout. After a game over, CODE held at the side B prompt loads level 1 immediately. Without CODE, the automatic tape reads on through the rest of side B, about 10 seconds, before it wraps to side B's start |
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
([Check](INTERNALS.md#check)). The step comes after Altered Beast wrote its
variables over the service's entries on the real machine. The collection reports
point 2's failure in place of point 1's line:

| Test | What it proves |
|---|---|
| `Guard` in `tests/test_service.py`: `tests/guard.asm`, a game that reads 8 bytes of its tape after the restore and then writes FCE1h | A game's write to the part fails point 2, with the address that it writes, and `check.py` exits with 3 |
| `Guard`: the same game without the write | The service's own writes to the part, during the game's tape calls, do not count |
| `Guard`: the same game with the write, whose own load ends side 2 before the snapshot | The game's writes after the service has read the tape to its end do not count |
| `TapeEnd` in `tests/test_service.py`: 7 Card Stud on `phc28s-ram64k-carnivore2`, as shipped | The game that the rule was made for passes the check. Its snapshot is in the middle of its load. The restored game reads its tape to its end through the service, where the position stays, 3 bytes of padding before the tape's end. The game then keeps its own values in the part, which no longer holds the service's bytes 60 seconds after the restore |
| `Guard`: the same game with the write, which reads its tape's last byte after the restore, on a tape of one side and on side 2 | The check notes the tape's end where the service leaves it, because the automatic tape is back at a side's start by the write |
| `Guard`: the same game with the write, which reads to side 1's end of a tape with a side 2, or 8 bytes of side 2 | Only the last side's end is the tape's end, so both writes fail point 2 |
| `Loads` in `tests/test_service.py`: Gauntlet's check | An image with the part passes point 2 |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The games whose first 60 seconds write the part are listed, for a game file's `service t0` |

On those two machines, the guard listed 53 game files. Most of them were not games
that write the part. On the PHC-28S, 30 were captures whose loader had reset the
machine, so the image replayed a reboot, and the reboot wrote the part. Most of
those loaders cut off their own code ([Step 14](#step-14-the-ram-search-patch)).

## Step 14: the RAM search patch

This step adds the capture's watch for a slot register write that cuts off the code
that made it. It also adds the patch of the RAM search that Mot's loader and many
Opera Soft loaders share
([The RAM search patch](INTERNALS.md#the-ram-search-patch)). Mot and Satan's game
files used the tape of their part 2 as a side 2. Each part now has a game file of
its own, and Mot's demo has its own as well.

| Test | What it proves |
|---|---|
| `Procedures` in `tests/test_capture.py`: the capture's watch in the C-BIOS machine, with the search twice on side 1 and once on side 2 | A slot register write that cuts off its code stops the capture with a patch of each copy of the search on the tape. A write that keeps page 3's slot does not |
| `Corpus` in `tests/test_machines.py`: La Abadia del Crimen on `phc28s-ram64k-carnivore2` and `hbf700p-ram512k-msxdos2`, without a `capture` line | The capture patches the search and loads the patched tape, and the image passes the gate |
| `SingleLoads` in `tests/test_capture.py` and `Corpus`: La Abadia del Crimen on `test/nms8250-128k` and `test/nms8250-dos1` | A machine whose RAM for page 3 is in the slot that the loader finds gets no patch |
| `RamSearch` in `tests/test_patches.py` | The patch's bytes, the settings that the capture's Tcl gets, and that the scan leaves the search alone |
| `Variants` in `tests/test_snap.py`: Digger Dungeon on `hbf700p-ram512k-msxdos2` | The test replaces the variant test of La Abadia del Crimen, whose load the patch fixes there, and then Sootland's |
| `RamSearch` in `tests/test_machines.py`: Mot on `phc28s-ram64k-carnivore2`, as shipped | The capture patches the search, and the image passes the gate |
| `RamSearch`: Mot on `vg8020-carnivore2`, as shipped, with its `capture vg8020` line | A machine whose RAM for page 3 is in the slot that the loader finds gets no patch |
| `RamSearch`: Made in Spain on `phc28s-ram64k-carnivore2`, as shipped | The capture patches each of the two copies of the search on the tape, and the image passes the gate |
| The collection: Mot's demo and the 20 other tapes with the search that reset the PHC-28S, on `phc28s-ram64k-carnivore2` | The capture patches the search, and each check passes |

## Step 15: TSX tape files

This step adds the reader of TSX files and the tape model, and moves the code that
reads CAS files behind the model ([Tape files](INTERNALS.md#tape-files)). The tools'
`--cas` folder becomes `--tapes`, because it holds both formats, and the game file
gets the keys `tsx` and `load`. The tests use TSX files from the collection that the
TSX experiment loaded, from the `tsx/` folder of `CAS_DIR`. Each file was chosen for
a case of the design. Part 2, the reader, checks the times of the blocks against
`openMSX`'s length of the tape:

| Test | What it proves |
|---|---|
| A TSX file with only standard blocks, whose CAS file is in the collection | The two files load the same game. Its RAM page is the same, though the TSX file keeps the original tape's timing |
| A TSX file of standard blocks recorded at about 1660 baud | TAPION reads a tape recorded between 1200 and 2400 baud |
| Two single-load TSX files with turbo blocks | A turbo loader loads its whole tape in the capture, and the image passes the check |
| A tape of TSX bytes whose first block is a turbo block, with and without `load` | The load command comes from the game file, and without it the capture stops |
| A tape of TSX bytes with a turbo block after the snapshot's time | The build stops with an error that names the block, unless the game file has `service no` |
| A patch line at an offset in a TSX file | The capture loads the patched file |
| A CAS file whose block headers are off the grid of 8 bytes | The reader finds each block, as `openMSX` does |
| Sky Jaguar with `start SKY`, from the Engesoft tape after Circus Charlie | The load starts at a later file, from a copy whose blocks are back on the grid, and the image passes the check ([A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The CAS game files keep their results behind the model |

The tests on bytes that the test writes are `Reader`, `Model` and `Start` in
`tests/test_tape.py`, and `Lines` in `tests/test_gamefile.py`. The tests on the
collection's files are `Files` and `Games` in `tests/test_tsx.py`.

## Step 16: the check's reboot point

This step adds point 3 to the check. A reboot of the machine during the 60 seconds
after the restore fails point 3. One of these signs shows the reboot: `SNAPCAS.COM`
starts again, `MSX system` is on the screen at two or more savestates, or the check
has no reset where the capture's log shows one after the snapshot
([Check](INTERNALS.md#check)). `MSX system` is the MSX1 BIOS's boot screen. The
breakpoint at the start of the BIOS's reset routine while page 0 selects the main
ROM notes each reset in the report. That breakpoint is set after point 1, because
the check's own boot passes there.

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

The games' tests are `Reboots` in `tests/test_check.py`. Each one checks
`check.py`'s exit status and all four points. A game that fails point 3 passes the
other three. The single-load game on each shipped machine is `Shipped` in
`tests/test_machines.py`.

## Step 17: one service setting

This step makes the game file's `service` line one value, `no`, `at xxE1` or `t0`,
which a machine's game file replaces. It also makes `rom keep` with the mode without
a part in page 3 an error ([Game file](FILES.md#game-file),
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

The game files' tests are `ServiceLine` in `tests/test_gamefile.py`, and the two
builds are `Parts` in `tests/test_service.py`. `ServicePart` and `Service` in
`tests/test_build.py` check the same places on a snapshot that the test writes.

## Step 18: the check's BASIC error point

This step adds point 4 to the check. A BASIC error message on the screen at one of
the savestates fails point 4 ([Check](INTERNALS.md#check)). The messages are
BASIC's, and the check reads the screen's text at each savestate, as point 3 reads
it for the boot screen. The two games' tests are `BasicErrors` in
`tests/test_check.py`.

| Test | What it proves |
|---|---|
| Field Master without its patch line, on `phc28s-ram64k-carnivore2` | A BASIC game that stops at `Overflow in 130` after the restore fails point 4, though it passes points 1 to 3 |
| Aritmo, from Philips's Turbo Pack A, on `phc28s-ram64k-carnivore2` | A loader that stops at `Ok` on purpose, for the player to press F5, passes point 4 |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | The game files that fail point 4 are the 17 runs of the scan, and they are fixed or sorted into the failure lists |

## Step 19: machine names

This step names each machine file after its model and its cartridges, in slot order.
It moves the capture variants to `machines/capture/` under names of the same form
([Machine file](FILES.md#machine-file)). Each machine file lists its variants with
`variant` lines, which `snapcas.py snap` reads instead of finding the variants by
their names. The machine's game files take the machines' new names, and their
`capture` lines take the variants' new names. The `openmsx` lines stay as they were,
so the images do not change. The tests are `ShippedGameFiles` in
`tests/test_gamefile.py` and `Variants` in `tests/test_snap.py`.

| Test | What it proves |
|---|---|
| Every shipped machine's game file | Its name is a machine file's name |
| Every shipped `capture` line | It names a variant that its machine file lists |
| Digger Dungeon on `hbf700p-ram512k-msxdos2`, without a `capture` line, Sootland before the patch that keeps page 3 | `snapcas.py snap` tries the variants that the machine file lists, and prints `capture hbf700p-msxdos2` |
| The collection on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` | Every game file passes, as before the rename |

## Step 20: the release machines

This step adds five machine files for the setups that users most probably own, from
the 2026 MSX survey on msx.org and owners' threads there
([Shipped files](FILES.md#shipped-files)). The five machine files are
`vg8020-sdmapper`, `xp800-sdmapper`, `fsa1-mfrsd`, `hbf1xd-mfrsd` and `vg8235`. The
machine file gets two lines for them:

| Line | Why |
|---|---|
| `hold` | The Panasonic FS-A1 starts its Desk Pac menu in a graphics mode unless DEL is held from power-on |
| A size on the `disk` line | The Philips VG-8235's single-sided drive reads only a 360 KB disk |

The Makefile downloads the SD Mapper's firmware and Nextor's ROM for the
MegaFlashROM SCC+ SD, each pinned by SHA-256. It makes the cartridge's flash with
Nextor only, because the stock flash's ROM disk starts a file manager on an MSX2.
Caldero's test is `Shipped` in `tests/test_machines.py`.

| Test | What it proves |
|---|---|
| Caldero on each of the five machines | A single-load game restores on each, under Nextor or, on the VG-8235, MSX-DOS 1 |
| The collection on each of the five machines | Each game file passes, or is fixed, or is in a failure list |

## Step 21: the url line

This step is the first of the `snapcas` command's steps ([CLI.md](CLI.md)). It adds
the game file's `url` line, the links to the zips that hold a game's sides
([Game file](FILES.md#game-file)). The command downloads those zips. A one-off
script filled the lines from File-Hunter's listing of its MSX1 CAS folder and the
collection's lists of its files. The script removed the link comments, which had no
side 2's link. An apostrophe in a link is written `%27`, because the game file's
lines are split as a shell splits words, and that split would treat the apostrophe
as a quote. The 8 game files without a link, in the `SM-` folders, were copies of
Spectravideo's Swing Man, Cryptic Cube and Roulette under their catalogue numbers.
They were therefore removed, with 13 other copies of a release under several names
([Shipped files](FILES.md#shipped-files)). The tests are `UrlLine` and
`ShippedGameFiles` in `tests/test_gamefile.py`.

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
| `snap` | It takes over the work of `tools/snapcas.py`: capture, build, `--check`, and the tries of the capture variants. `tools/snapcas.py` is removed. `snap` finds the game and the machine by their names, as `list` and `machines` show them. The download comes in step 23 |

| Test | What it proves |
|---|---|
| `list wall` | It lists the three games whose folder or title holds "wall", and their number |
| `list` with a text in mixed case | A text matches in any case |
| `list` on Gauntlet, Aritmo, Africa Film and Athletic Land | Each game's title names its File-Hunter file: a zip, a CAS file in a zip, or a compilation's zip and the program |
| `list "super msx n.23"` | A compilation's name finds its programs |
| `list` without a text | It lists every game file |
| `machines` | It lists the user machines and no capture variant or test machine, each with its first sentence |
| `snap gaunt phc28s-ram64k-carnivore2` and `snap gauntlet phc28s` | A text that is not a game's name, or not a machine's, stops the command with status 1, also when it is a part of one |
| `snap` with `--dos` and without `--check` | The command stops with status 1 |
| No arguments, or `snap` alone | The command prints its help |
| An unknown verb | The command stops with status 1, as the tools do for an error in their input |
| `snapcas.py`'s mode | The file is executable |
| Step 9's single-load game and step 10's runs, through `snap` | `snap` makes and checks images, and finds a capture variant, as `tools/snapcas.py` did |
| A script with an unknown command, while `openMSX` reads it and in a callback | `openMSX` ends with status 1, and the error reaches the caller |
| A wait for a text that never shows: `wait_screen`, `boot` and `at_prompt` | Each wait ends at its deadline with an error |
| A typed text with `$` and `[` | It reaches Tcl as hex |
| The savestates of two runs whose names start alike | Only the named run's savestates are removed |
| A capture whose own patch does not fit the tape | `capture.py` stops with status 1 and one line |
| `capture.py` and `check.py` without arguments | They stop with status 1, as the other tools do |

The command's tests are `Command`, `List`, `Machines` and `Snap` in
`tests/test_cli.py`. The tests of `openMSX`'s end and of the waits are `Run` in
`tests/test_harness.py` and `Msx` in `tests/test_msx.py`. `Run` runs `openMSX`.
`Msx` gives `tools/msx.py` the end of an `openMSX` that the test does not start.

## Step 23: the download

This step makes `snapcas.py snap` download the game's tape files that are not in the
tapes folder ([CLI.md, Download](CLI.md#download)), with `tools/download.py`. For
each side, the command downloads the zip that the `url` line links. It finds the
file whose SHA-1 the `sha1` line gives, and saves that file under the name that the
`cas` or `side2` line gives. A file of that name with another SHA-1 stops the
command and stays.

| Test | What it proves |
|---|---|
| A game with two sides, each in a zip of its own, one of them with another file | The command finds each side by its SHA-1 and saves it under the game file's name |
| The same game again | The command does not download again a tape that is already in the folder |
| A file in the folder with another SHA-1 | The command stops, and the file stays |
| A zip without the side's SHA-1 | The command stops and writes nothing |
| A game file without a `url` line | The command names the file to put in the folder, with its SHA-1 |
| Gauntlet on `phc28s-ram64k-carnivore2`, by hand, into an empty folder | Both sides come from File-Hunter with the game file's SHA-1s, and the image builds |

The tests are `Download` in `tests/test_download.py`. They replace the network with
zips that they make, so they run offline.

## Step 24: the folders

This step gives each kind of file a folder of its own, so that the tests, the games
run and the user's images share no folder:

| Folder | Holds |
|---|---|
| `tests/tapes/` | The tests' tape files, in git, in place of `CAS_DIR` and its `tsx/` and `collection/` folders |
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

The command's verb is `snap`, as in
`./snapcas.py snap gauntlet phc28s-ram64k-carnivore2`, so that it does not share its
name with the Makefile's `make test` and `make games`. `make try`, which put every
image of `out/try/` on one disk, becomes `./snapcas.py try <game> <machine>`, which
starts one game's image and types its command. `tools/run.py` is removed. A game and
a machine are given by their names, as `list` and `machines` show them. A name that
is not a game's or a machine's stops the command.

| Test | What it proves |
|---|---|
| `make test` | The tests find every tape in `tests/tapes/`, and `snap` finds them there through `SNAPCAS_DOWNLOADS` |
| Corpus | The scan reads the 38 tapes of its list, and not the other tapes of `tests/tapes/` |
| Temptations on `phc28s-ram64k-carnivore2` with `--check`, by hand | The image goes to `images/`, the work files to `out/work/`, and each point of the check passes |

`Setup` in `tests/test_harness.py` checks that the Makefile lists each tape of
`tests/tapes/`, and that a missing tape is an error and not a skipped test. The
corpus's test is `Corpus` in `tests/test_corpus.py`.

## Step 25: custom games

This step adds `custom/`, the user's own games, for games that `snapcas` does not
ship and for the user's own dumps of a tape
([CLI.md, Your own games](CLI.md#your-own-games)). A custom game's folder holds its
`game.txt` and its tape files, and its name is `custom/<game>`. `snap` reads the
game's tapes from the folder and never downloads them. The game's image and work
files go below `custom/` in `images/<machine>/` and `out/work/<machine>/`. Git keeps
only `custom/README.md`.

| Test | What it proves |
|---|---|
| A folder of the tests' own `custom/` with a game file, and one without | Only the folder with a `game.txt` is a custom game |
| `CUSTOM/mygame` | The name finds the game's folder in any case |
| `list custom` | The game shows with its title |
| The tapes, the work folder and the image | The tapes are the game's folder, and the work folder and image are below `custom/` |
| Gauntlet | A shipped game is no custom game. Its tapes come from `downloads/` |
| A custom game made from `FREDDY.CAS` on `phc28s-ram64k-carnivore2` with `--check`, by hand | `snap` passes, and the image goes to `images/phc28s-ram64k-carnivore2/custom/ZZFREDDY/` |

The tests are `Custom` in `tests/test_custom.py`. They give `tools/gamefile.py`'s
`CUSTOM` a folder of their own for the time of a test, so they leave `custom/`
alone.

## Step 26: sync a card

This step adds `snapcas.py sync <machine> <destination>`, which copies the machine's
images and `SNAPCAS.COM` to a card, in place of `snap`'s `--to` option
([CLI.md, Sync a card](CLI.md#sync-a-card)). It copies only the new and changed
files, reads each copy back, and deletes no image on the card. The tests are `Sync`
in `tests/test_card.py`.

| Test | What it proves |
|---|---|
| A game, a compilation's program, a custom game and a name that starts with a digit | Each file goes to its letter's folder, and `SNAPCAS.COM` to `BIN/` |
| A second sync after one image changed, with a file of the user's own on the card | The command copies only the changed image, and the user's file stays |
| The card's `SNAPCAS` or `BIN` folder as the destination | The command stops and asks for the card's top folder |
| Two images for one place on the card | The command stops |
| `phc28s-ram64k-carnivore2` into an empty folder, twice, by hand | The first sync copies 1,546 files and the second none |
