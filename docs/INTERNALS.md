# Internals

This page describes each part of `snapcas` step by step: the games run, the tools'
code, the tape files, the capture, the build, the restorer, the tape service and the
check. [DESIGN.md](DESIGN.md) says what each part does and why, in short. The
formats that the parts share are in [FORMATS.md](FORMATS.md), and the games behind
the rules are in [NOTES.md](NOTES.md).

## The games run

`make games MACHINE=<machine>` runs `tools/games.py`, which checks that every
shipped game file makes a working image on the machine. The games run is not part of
`make test`, because it takes hours, and it reads none of the tests' tapes. The run
has these steps:

1. It looks for each game file's tapes in `downloads/`, where `snap` puts them. It
   downloads nothing, because a download of the whole collection would load
   File-Hunter, one person's site. A game file whose tape is missing gets a result
   that says so.
2. It captures, builds and checks each game file, 11 at once by default, because
   `openMSX` keeps about one core busy. The check always runs, with the DOS files of
   the machine's folder below `dos/`, as `snap --check` does, unless `DOS=` names
   others. The `dosfiles` line of the machine file names that folder.
3. It moves the image of each game file that passes to `images/<machine>/`, as
   `snap` does, so that `sync` copies the image to a card. A game file that fails
   keeps the image of its last pass in `images/`.
4. It writes one line per game file to `out/games/<machine>.txt`. The line holds the
   folder, a tab and one of three texts: the first line of the check's report, the
   failed point with its first line, or the failed step's error.
5. It compares the failures with two lists. `tests/openmsx-failures.txt` holds the
   game files that fail in `openMSX` itself, and `tests/snapcas-failures.txt` holds
   the known failures of `snapcas`. It prints the failures in three groups: the
   failures of each list, and the new failures, which neither list holds. It exits
   with 3 only when there is a new failure. It also names each listed game file that
   passes now, so that its line can be removed.

Before it starts, the run reads both lists and stops at a line that it cannot read,
at a machine without its firmware or at a folder without DOS files. The run checks
these things first, so that none of these faults stops the run hours later.

A game file keeps its last result, and its image in `images/`, while its inputs are
unchanged. The inputs are its folder, its tapes, the machine files that it runs on,
`bin/`, `tools/`, the DOS files that the check boots and `openMSX`'s version, as
`openmsx -v` prints it. A cache beside the results, `<machine>.txt.cache`, holds the
hash of each game file's inputs. `FULL=1` gives every game file a new result. Two
results run again whatever the hash:

| Result | Why it runs again |
|---|---|
| A pass whose image is no longer in `images/` | The run makes the image again |
| A result of a run that broke. A run broke when `openMSX` failed, stopped before its result or timed out, or when a tool ended in a Python traceback or by a signal | The result says nothing of the game. The run prints the result, with `(not kept)`, and writes it to `out/games/<machine>.txt`, but not to the cache |

Ctrl-C stops the run. The run then starts no other game, stops the process of each
game that is running, with that process's `openMSX`, and exits with 130. The cache
keeps the results so far, so the next run goes on from them.

## The tools' code

The commands share their code through modules, and the Tcl that runs inside
`openMSX` is in files of its own:

| File | Holds |
|---|---|
| `tools/gamefile.py` | Reads game files, and lists the game files' folders and their titles. Finds a game's folder from a name below `games/`, such as `ABADIA` or `SUPERMSX/GOLF`, or from a path. Finds the game's work folder and the place of its image in `images/`. Applies a `patch` line to the bytes of its place, and stops when they are not the line's old bytes |
| `tools/msx.py` | Reads machine files, finds one from its name, and lists the user machines with what each is. Gives the folder of the DOS files that a machine boots, and checks the machine's firmware. Starts `openMSX`, the program that `OPENMSX` names or `openmsx` on the path, with a Tcl script, and stops with an error when `openMSX` ends with an exit status other than 0. Returns what `openMSX` printed on standard error. A tool adds the last lines of that text to its own error when the tool finds no result. Gives `openMSX`'s home folder, where `openMSX` writes savestates, deletes a run's savestates, and makes disk images. Holds the tools' argument parser, which exits with 1 for an error in the command line. Holds the failure that a step of an image raises, as below |
| `tools/cas.py`, `tools/tsx.py`, `tools/tape.py` | The readers of CAS and TSX files, the tape model and the tape service's tape, which the rest of the code uses, and a game's tape files as the capture plays them ([Tape files](#tape-files)) |
| `tools/snapshot.py` | Reads a snapshot's folder ([FORMATS.md, Snapshot files](FORMATS.md#snapshot-files)), so that no other code knows the folder's layout. It reads these things from the folder: the state's values as text and as numbers, the RAM pages and the names of their files, the slot and the RAM page that the snapshot selects in a page, a mapper's size, the slot map, and the capture's error and patches |
| `tools/patches/` | The automatic patches, one file for each kind, as below |
| `tools/tcl/prelude.tcl` | The procedures that every `openMSX` run gets: running a callback, ending the run, reading the screen, waiting for a text on it, passing the boot menu, and typing at DOS's prompt, as below |
| `tools/tcl/memory.tcl` | The procedures that the capture and the check share: EXPTBL, a slot ID's primary slot and subslot, whether page 0 selects a slot, a 16-bit word in memory, the CPU's view of memory with a slot selected, the tests of RAM and of a mapper, the read of VRAM, and the machine's state under the names of `state.txt` |
| `tools/tcl/capture.tcl` | The capture's steps ([Capture](#capture)) |
| `tools/tcl/check.tcl` | The check ([Check](#check)) |
| `tools/relocs.py` | The last two parts of `SERVICE.BIN`, which `tools/relocs.py` appends when `make all` assembles the service. The two parts are the symbols that `build.py` reads by name, and the offsets that `build.py` changes to move the page 3 part ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)) |
| `tools/download.py` | The download of a game's tape files from its `url` line, for `snapcas.py snap` ([CLI.md](CLI.md)) |
| `tools/pipeline.py` | The steps of one game's image on one machine, and their result, as below |
| `tools/games.py` | The games run of `make games` ([The games run](#the-games-run)) |
| `tools/fetch.py` | The download of the test setup's files |
| `tools/try.py` | The `openMSX` run of `snapcas.py try`, with its window. The run types the restorer's command ([CLI.md, Try an image](CLI.md#try-an-image)) |
| `tools/plain.py` | A load of a game's tape in plain `openMSX`, without the capture's code. The tool prints the screen 60 seconds after the tape's end. A game that fails there fails in `openMSX` itself |

`tools/pipeline.py` holds the sequence of an image's steps once, for
`snapcas.py snap` and for the games run. The sequence is the capture, the build and
the check, the trials of the capture variants
([DESIGN.md, Files and commands](DESIGN.md#files-and-commands)), and the move to
`images/` of an image that passes. The pipeline calls each step as a function of
`capture.py`, `build.py` or `check.py`. A step that fails raises a failure. The
failure holds three things: the exit status that the tool gives as a program, its
error, and whether the run broke. A run broke when `openMSX` failed, stopped before
its result or timed out. So the pipeline reads none of a step's printed text. The
pipeline's result holds these fields:

| Field | What it holds |
|---|---|
| step | The step that failed: capture, build or check, or none |
| status | That step's exit status, or 0 |
| message | One line: the failed step's error, the failed point of the check with its first line, or `point 1: pass` for a check that passes |
| transient | Whether the run broke, so that the result says nothing of the game |
| variant | The capture variant whose trial passed, or none |
| image | The image's path in `images/`, or none. It is none for a result that fails, and for a game folder outside `games/` and `custom/` |

A result passes when its status is 0. With the check, the status is 0 by
`check.py`'s rule, which is that all four points pass. `snap` prints each step when
the step ends, and then prints the image and the variant from the result. The games
run starts `pipeline.py` as a program for each game file, and the program prints the
result as one line of JSON. So each game has a process of its own, for three
reasons:

- The names of a run's savestates hold the process ID.
- Ctrl-C stops the process with its `openMSX`.
- A step that ends in a Python error ends only its own game.

A program that prints no result gives a transient result.

A callback is Tcl that `openMSX` runs later, at an emulated time, at a breakpoint or
at a watchpoint. `openMSX` only prints the error of a callback that fails, and goes
on without the callback, so a script would wait for a callback that never comes. The
prelude's procedures prevent such a wait:

| Procedure | What it does |
|---|---|
| `safe` | Runs a callback's body. It gives the error of a body that fails to `script_failed`, and runs nothing once the run is stopping. Every timer, breakpoint and watchpoint of the tools runs its body under `safe` |
| `later` | Runs a body under `safe` after emulated seconds |
| `script_failed` | Gets the error. The prelude's `script_failed` prints the error and ends `openMSX` with status 1. The capture's `script_failed` writes the error to `snap/error.txt`, and the check's `script_failed` writes it into the check's report |
| `stop` | Ends the run. `openMSX`'s `exit` takes effect only when the callback that calls it returns, and the other callbacks of the same instruction still run. So `stop` marks the run as stopping and leaves its callback with an error, which `safe` drops |
| `wait_screen` | Looks for a text on the screen every 0.5 seconds. Runs one body when the text shows, and another body when a number of seconds has passed without the text. The waits for a boot text, for DOS's prompt and for BASIC's `Ok` all use `wait_screen`, so each wait has a deadline |

`tools/msx.py` writes the script to a file of its own, which the prelude reads
under a catch. So an error while `openMSX` reads the script, such as an unknown
command, also ends `openMSX` with status 1.

An automatic patch is a change that the tools make to a game without a line in its
game file. Each kind of automatic patch is one file in `tools/patches/`:

| File | Kind |
|---|---|
| `tapecode.py` | The calls, stubs and entries of the tape routines, sent to the entries in page 3, and the readers of the cassette signal, which are only listed ([Scan](#scan)) |
| `t0stub.py` | The stub of `TAPION` that selects the ROM in page 0 itself, sent to T0 in the mode without a part in page 3 ([Without a part in page 3](#without-a-part-in-page-3)) |
| `slots.py` | The fixed slot values that name a slot that holds nothing, and the bytes of their code for the capture's watch ([Slot patches](#slot-patches)) |
| `slots.tcl` | The capture's watch on the slot register ([Slot patches](#slot-patches)) |
| `ramsearch.py` | The bytes of the loader's RAM search and its patch ([The RAM search patch](#the-ram-search-patch)) |
| `ramsearch.tcl` | The capture's watch for a slot register write that cuts off the code that made it, and its patch that keeps page 3's slot ([The RAM search patch](#the-ram-search-patch)) |
| `pagecopy.py` | The forms of the loaders' code that copies page 3's slot to the other pages, and their places in the tape files ([The page copy patch](#the-page-copy-patch)) |
| `pagecopy.tcl` | The capture's decision, by the slot map, of which forms to patch ([The page copy patch](#the-page-copy-patch)) |

The Python file of each kind has the same two functions. `find(data, context)`
returns the kind's findings in data, for the scan. `tcl(side1, side2)` returns the
kind's Tcl for the capture, for the tape files' bytes. A kind that works only in the
capture finds nothing, because the loader that it patches has finished by the
snapshot. A kind that works only in the scan returns no Tcl. A finding is the code
found, its offset, what it is, and its patched bytes, or none for code that is only
listed. A finding can also name the place of one patched byte whose value the
restorer writes, because that value depends on the machine that restores the image
([FORMATS.md, Image](FORMATS.md#image)). `tools/patches/finding.py` defines a
finding. The context holds what a search depends on, in four fields. The first field
is the entry page, the high byte xx of the addresses of the entries in page 3, xxE1h
to xxF3h, or none for an image without them. The other fields are the slot map,
whether the image has the tape service, and whether the data is a RAM page or a
block of the tape. `tools/patches/__init__.py` lists the kinds once, in the order
that the scan runs them and that the capture loads their Tcl. It also holds the two
things that all kinds share: the patch of the bytes and the text of `scan.txt`. So a
new kind is a new file and a name in that list.

A kind that works in the capture has a Tcl file of the same name, and its
`tcl(side1, side2)` returns the kind's settings and then that file. Data that both
files of a kind need, such as the bytes of the forms of
[Slot patches](#slot-patches), is in the Python file only, and reaches the Tcl file
as settings. `capture.py` loads the kinds' Tcl after `capture.tcl`, in the list's
order. `slots.py` is before `ramsearch.py` and `pagecopy.py` there, because its Tcl
makes the slot map and holds the procedures that the other two use. A kind's Tcl
file adds its procedures to the capture's two hooks. The `start` hook runs in step 3
before the load command, and the `slot_write` hook runs in step 4 for each write to
the slot register. A kind that finds a patch gives the patch's lines to
`stop_with_patch`, which stops the capture ([Slot patches](#slot-patches)). A game
file's `patch` lines are not automatic patches, and the build applies them
([FILES.md, Game file](FILES.md#game-file)).

## Tape files

`snapcas` reads two formats of tape file, CAS and TSX. A CAS file holds only blocks
in the format that the BIOS's tape routines read. So a tape whose loader reads its
own format, as a turbo loader does, has no CAS file. A TSX file holds any MSX tape,
the turbo loaders' blocks included ([FORMATS.md, TSX data](FORMATS.md#tsx-data)).

Each format has its own reader, and no other code reads a tape file. A reader turns
a file into the tape model, which the capture, the build, the patches and the check
use:

| File | Holds |
|---|---|
| `tools/cas.py` | The reader of CAS files ([FORMATS.md, CAS data](FORMATS.md#cas-data)) |
| `tools/tsx.py` | The reader of TSX files ([FORMATS.md, TSX data](FORMATS.md#tsx-data)) |
| `tools/tape.py` | The tape model, the choice of the reader by the file's extension, and a game's tape files as the capture plays them, with the `patch` lines applied |

The tape model is the file's blocks in tape order, and each block has these fields:

| Field | What it is |
|---|---|
| Kind | Standard, for a block that the BIOS's `TAPION` and `TAPIN` read, or non-standard, for a block in any other format, such as a turbo loader's |
| Data | The block's bytes |
| Offset | The offset of the data's first byte in the file |
| Time | The seconds at which `openMSX`'s cassette player reaches the block and leaves it, from a TSX file's pulses. A CAS file holds only standard blocks, which the capture follows by `TAPIN`, so its blocks have no time |

`openMSX` plays the file itself, in either format, so the game loads as from its
real tape. The rest works on the model:

1. The load command comes from the type in the first block's 10 bytes: D0h, D3h or
   EAh ([FORMATS.md, CAS data](FORMATS.md#cas-data)). A tape whose first block is
   not standard needs the game file's `load` line.
2. The tape position is an offset in the tape service's tape. That tape is the
   standard blocks, each after the 8-byte header `1F A6 DE BA CC 13 7D 74` at an
   offset that is a multiple of 8. A CAS file whose headers are at multiples of 8
   has that layout, so its positions stay its offsets. The capture follows standard
   blocks by the `TAPION` and `TAPIN` breakpoints, as for a CAS file, and
   non-standard blocks by the player's time. By the player's time, a block is read
   when `cassetteplayer getpos` passes the block's end.
3. A patch's place, `side1:` or `side2:` and an offset, is an offset in the tape
   file, of either format, because both formats keep a block's bytes as they are.
   The capture's watches search the files' bytes in the same way
   ([Slot patches](#slot-patches)). A patch in a block whose loader checks a sum
   must fix the sum, as it must in a CAS file.
4. The build writes the standard blocks after the snapshot's position into the tape
   service's tape. A non-standard block after that position is one that the game
   reads with its own loader during play. The tape service cannot serve such a
   block, so the build stops with an error that names the block, unless the game
   file has `service no`.

### A game later on the tape

A compilation holds several programs on one side, each with its own loader. A player
reaches a later program by letting the tape run on and typing its load command
again. Engesoft's MSXF-07 has Circus Charlie and then Sky Jaguar on side B. The game
file's `start` line names the later program's first file, and the load starts there:

1. The capture plays a copy of side 1 that begins at the first file with that name.
   The capture applies the game file's patch lines to the original first, so that
   the lines' offsets and the SHA-1 lines stay those of the downloaded file. The
   capture's own patches ([Slot patches](#slot-patches)) have offsets in the copy,
   which is the file that the capture plays. The build makes the same copy, so the
   tape service's tape and its positions begin there too.
2. A CAS file's copy is the tape service's tape of the blocks from the named file's
   own block on. So the copy's headers are at multiples of 8 even where the
   original's are not, as on the tape with Sky Jaguar. The capture stops with an
   error when the name is not a file's own block, but bytes inside one.
3. A TSX file's copy keeps the file's first 10 bytes and begins at the block that
   holds the file's header. The capture stops with an error when the header is not
   at that block's start.
4. The load command comes from the named file's type, unless the game file has
   `load`. The capture stops with an error when side 1 has no file with that name.

## Capture

`tools/capture.py` runs `openmsx` with the machine file's arguments, or those of the
game file's `capture` machine, and with a Tcl script made from the game file. The
throttle, the renderer and the sound are off. All times are emulated seconds,
counted across the rewinds of step 5. The script writes the snapshot to `snap/`,
with its log in `snap/log.txt`. It writes the log and `snap/error.txt` instead in
these cases: a `boot` text or BASIC's `Ok` does not appear within 120 seconds, the
load runs for more than 3,600 seconds, step 5 restarts more than 20 times, or one of
the script's callbacks fails. The capture then stops at once, and the log's last
line holds the error and the screen's text. `capture.py` deletes the capture's
savestates from `openMSX`'s home folder when `openMSX` ends, also when `openMSX` was
stopped. The script takes the following steps, which are the procedures `step1` to
`step6` of `tools/tcl/capture.tcl`:

1. Starts a write watchpoint on port A0h, which keeps the PSG register selected
   last, and one on port A1h, which keeps the last value written to register 15. It
   then boots the machine with no disk, presses the `boot` keys, and waits for
   BASIC's `Ok`. After `Ok`, it waits 10 seconds more, as a person would, because a
   disk system can still be busy just after `Ok`.
2. Stops with an error unless the ROM's byte at 002Dh is 0 (MSX1) or 1 (MSX2). It
   reads `EXPTBL` at FCC1h and `EXBRSA` at FAF8h, the slot IDs of the ROMs, once,
   because a game can overwrite page 3. It then removes the disk system from page 3
   with `debug write`. It writes RET (C9h) in every hook from FD9Ah to FFC9h and at
   `EXTBIO`, `DISINT` and `ENAINT`, so that nothing calls the disk system. It writes
   00h at F37Dh, which some loaders read to refuse to run with a disk system. It
   writes zeros from FCC9h to FD88h, `SLTATR` and `SLTWRK`, so that no extension ROM
   claims them and the tape service can use them. It then types `CLEAR200,&HF380`,
   which sets `HIMEM` to a cassette machine's F380h.
3. Notes the slots selected in each page, and runs the `start` hook of the patch
   kinds, which writes the slot map ([Slot patches](#slot-patches)) and decides on
   the page copy patch ([The page copy patch](#the-page-copy-patch)). It then
   inserts the tape file of side 1, with the game file's `side1` patches written
   into a copy in `snap/`, into the cassette player. It types the load command for
   the first header's type ([FORMATS.md, CAS data](FORMATS.md#cas-data)):
   `BLOAD"CAS:",R`, `CLOAD`, or `RUN"CAS:"`. After `CLOAD`, it types `RUN` when the
   motor has stopped for 1 second. When the game file has `side2` and the game reads
   past side 1's end, the capture inserts side 2 at its start, as a player turns the
   tape over. A read past side 1's end is a `TAPION` call at that end, or a read
   with the motor on there. After the turn, the tape position goes on in side 2,
   after side 2's first header, or at side 2's start when side 2 holds no standard
   block.
4. Presses the `keys`, and logs these events with their times:
   - The tape position, kept as the tape service would keep it. The position comes
     from breakpoints at the addresses that the jump table entries 00E1h and 00E4h
     jump to, `TAPION` and `TAPIN`, while page 0 selects the main ROM.
   - Each slot and subslot selected in a page, from write watchpoints on port A8h
     and on FFFFh, and each write to port A8h that selects a slot that holds nothing
     ([Slot patches](#slot-patches)). The watchpoint on port A8h runs the
     `slot_write` hook of the patch kinds.
   - Each start and stop of the cassette motor.
   - The start of the BIOS's reset routine, where 0000h's `DI / JP` jumps, while
     page 0 selects the main ROM. A loader can also jump there itself. The capture
     logs the reset and goes on, because a loader can reset the machine on purpose.
     A loader that copies a ROM game into RAM resets the machine, and the BIOS's
     search for cartridges at the reset finds the copy and starts it. A loader that
     crashes into a reset makes an image of a reboot, which the check's point 2 or
     point 3 fails ([Check](#check)).
5. Polls bit 4 of PPI port C, the cassette motor (0 means on), every 0.1 seconds.
   When the motor has been off, or the player has been at the tape's end
   (`cassetteplayer getpos` is at least `getlength` minus 0.01), for 1 second, it
   saves the machine with `savestate`. The wait ends when that condition has lasted
   30 seconds and the last `keys` time has passed, because a game can pause its own
   load. With `snapshot at`, the capture instead waits for that time and goes to
   step 6. Otherwise it goes back to the saved moment with `loadstate`, and goes on
   as follows:
   - If side 1 is read, it goes to step 6. Side 1 is read when the `TAPION` and
     `TAPIN` breakpoints fired and every block after the tape position is under 16
     bytes or equal to a block before it. The tape service's tape pads each block to
     a multiple of 8 bytes, so a block counts as read when at most 7 bytes of it are
     left.
   - Otherwise it tries the game file's `continue` key, then space, then Return,
     each from the saved moment and held for 0.5 seconds, because a loader can read
     the keyboard rarely. If the motor starts within 10 seconds of a key, and the
     tape is not at its end, the load was waiting for that key. The capture then
     logs the key and restarts step 5. If no key starts the motor, the game loads
     the rest during play, and the capture goes to step 6 from the saved moment.

   `loadstate` restores the machine but neither the script's variables nor its
   timers. So each time, the capture also restores its logged state from the saved
   moment, and schedules again its polling and the `keys` that come after that
   moment. `loadstate` also removes the watchpoints, though it keeps the
   breakpoints. The capture sets the watchpoints of step 1 on ports A0h and A1h
   again each time, so that the snapshot holds the PSG register selected last. It
   does not set the watchpoints on port A8h and on FFFFh again, so after the first
   `loadstate` it no longer logs those writes. Every game file passes without them,
   and setting them again made two game files fail.

   The capture goes on for 29 seconds after the saved moment before it goes back to
   that moment. So its log holds each reset of those seconds. The check's point 3
   looks for these resets ([Check](#check)). A reset during a key try is not in the
   log when the try's key does not continue the load, because the restored game gets
   no such key.
6. Takes the snapshot when the CPU next accepts an interrupt while no VDP command is
   running (status register 2, bit 0, is 0) and both VDP latches are empty. A probe
   breakpoint on `z80.acceptIRQ` marks the acceptance. A breakpoint at the handler's
   address takes the snapshot there, where the CPU has pushed the return address and
   interrupts are off. The handler's address is 0038h in interrupt modes 0 and 1, or
   the word at I × 256 + FFh in mode 2. When no such interrupt comes within 1
   second, it takes the snapshot where the CPU is. It stops with an error when the
   CPU is then halted. `openMSX` shows a halted CPU as a program counter just after
   a HALT (76h) that does not move. This snapshot needs the same quiet VDP, because
   a game that keeps its interrupts off can be between the two writes that set a VDP
   register. So the capture looks again every 3 milliseconds, up to 100 times, and
   then takes the snapshot as it is. The log says how long the capture waited, or
   that the VDP is not quiet. When the game gets the tape service and the CPU is in
   the BIOS's tape code, the snapshot goes back to the last `TAPION` call's entry,
   because T0 replaces that code. The program counter is then at `TAPION`'s jump
   table entry, 00E1h. The call has not run there, so the restored game makes the
   call to the tape service. The CPU is in the tape code when the main ROM is in
   page 0 and the program counter is either in 19DDh to 1B44h, or below 4000h with
   one of the 8 words on top of the stack in that range. `BREAKX`, which the tape
   code calls, is an example of the second case. So that the snapshot can go back,
   the capture saves the machine at each `TAPION` call's entry, and a rewind of step
   5 puts back the entry saved with its moment. While it reads the machine, the
   capture selects slots itself, with `debug write`. A capture without a rewind, as
   with `snapshot at`, still has its watchpoints on port A8h and on FFFFh then, and
   the watchpoints leave out these writes, which are not the game's.

The game gets the tape service when the `TAPION` and `TAPIN` breakpoints fired and
either side 1 is not read or the game file has `side2`, unless the game file has
`service no`. A load that waits for a choice that no key makes, such as Gauntlet's
joystick choice of players, gets its snapshot at that screen after the key tries of
step 5. The player chooses on the real machine, and the tape service supplies the
rest.

### RAM

The capture reads memory through the CPU's view, the `memory` debuggable. Before the
read, the capture selects a slot in a page with `debug write` on port A8h and, in a
slot that `EXPTBL` marks expanded, on FFFFh while page 3 selects that slot. It
writes both back afterwards. This method works for every device, including those
that expand their slot themselves, such as the Carnivore2. The snapshot keeps each
page that holds RAM and was selected at step 3, during the load or at the snapshot.
The capture reads these pages first and tests them afterwards, so a write that
switches a ROM's bank or overwrites a segment changes nothing it keeps:

- A page holds RAM when the byte at its first address takes a written value and its
  complement.
- A RAM page is in a mapper when two different marker bytes, written at its first
  address under two values of its mapper register, each read back under their own
  value after both are written.
- The mapper's size comes from the count that the restorer uses under MSX-DOS 1
  ([Restorer](#restorer)), made once for each mapper. A page's segment is its mapper
  register's value modulo that size. `state.txt` keeps the register's value as the
  game wrote it, for the image's header. It also keeps each mapper's size, with
  which the build finds the page that a register selects
  ([FORMATS.md, Snapshot files](FORMATS.md#snapshot-files)).

### Slot patches

A game that writes a fixed value to the slot register expects its RAM in the slots
of the machine that it was written for. Sootland writes FCh, for RAM in slot 3, and
crashes on the Sanyo PHC-28S, whose slot 3 holds nothing. The capture finds such
writes itself and patches each value to the slots that hold the machine's RAM, so
that no game file needs a line for them. It does this in four parts:

1. At step 3, before it types the load command, the capture tests each page of each
   primary slot, and writes the slot map, `snap/slots.txt`. In an expanded slot it
   tests only the subslot that the slot's subslot register selects in that page. A
   page holds RAM by the test of [RAM](#ram). A page holds nothing when it does not
   hold RAM and its first 256 bytes all read FFh.
2. A value's field for a page names a slot. When that slot holds nothing in the
   page, the patch replaces the field with the slot that the table below gives. A
   field that names a slot that holds RAM or ROM stays. An expanded slot never
   counts as holding nothing, because its subslot register belongs to the game. An
   expanded slot counts as RAM in a page when the subslot that its register selects
   there at step 3 holds RAM. A field with no RAM slot for its page stays, and the
   capture only logs the write.
3. At step 4, the write watchpoint on port A8h tests each value against the slot
   map. A value whose field names a slot that holds nothing makes the capture log
   the write, the address of its `OUT` and the new value. When the code that set the
   value is one of the forms in the third table below, the capture looks for the
   code in the tape files, in the order of the second table below. When it finds the
   code, the capture stops. `capture.py` then adds a patch of n at each place to
   `snap/patches.txt` and runs the capture again from step 1, up to 16 times.
   Otherwise the capture goes on, and the logged write is for a `patch` line by
   hand. The log holds each pair of an address and a value once, up to 16 pairs. It
   leaves out a write whose `OUT` is in the main ROM, because the BIOS's slot
   routines make one for each slot that a loader's search tries. The capture logs a
   call of `WSLREG` with a fixed value, with the address of the call's code.
4. The build's scan ([Scan](#scan)) looks for the same code with such a value in the
   snapshot's RAM pages and in the tape's unread blocks, for code that runs only
   while the game is played.

| Page | The slot that replaces one that holds nothing |
|---|---|
| 2 or 3 | The slot that BASIC selects in that page at step 3 |
| 0 or 1 | The slot that holds RAM in that page. Of several, the slot of page 2 at step 3 when it holds RAM there, or else the lowest |

The patches in `snap/patches.txt` change the tape after the game file's `patch`
lines. `build.py` applies them as well, so the tape service serves the tape that the
capture loaded.

The capture looks for the code in three ways, and takes the first that finds it:

| Bytes looked for | Places patched | For |
|---|---|---|
| The code and the 8 bytes before it | Each place | Most loaders. Rocky's and Time Out's tapes hold their routine more than once, and a copy can run after the snapshot |
| The code and the 8 bytes after it | Each place | A loader that copies a routine to RAM without the bytes before it, as Sootland's does |
| The code alone | The one place, when it occurs once | A routine that writes into the bytes around the code, as Uchi Mata's writes the slot register's value into the operand of the `LD A,n` after it |

The watch and the scan know two forms of the code that sets a fixed value:

| Code | Bytes | Where the watch finds it |
|---|---|---|
| `LD A,n / OUT (0A8h),A` | `3E n D3 A8` | Its last byte is the last byte of the write's `OUT` |
| `LD A,n / CALL 013Bh`, a call of the BIOS's `WSLREG`, which writes A to the slot register | `3E n CD 3B 01` | When the write's `OUT` is in the main ROM, its last byte is the byte before the return address on top of the stack. The capture reads that address in the slot that page 3 selected before the write, because the write can change page 3 |

The bytes of a form can also be the end of a longer instruction, whose operand a
patch of n would change. The watch knows that A holds n, and only `LD A,(nn)`, `3A`,
loads A with the byte after a `3E` in its operand, as Knight Orc's does
([NOTES.md, Slot patches](NOTES.md#slot-patches)). So the watch skips code whose
`3E` follows a `3A`. The scan does not know A, so it skips code whose `3E` can be
any operand:

| Byte | Opcodes |
|---|---|
| The byte before `3E` | Those of an instruction with a one-byte operand: `06 0E 16 1E 26 2E 36 3E C6 CE D6 DE E6 EE F6 FE D3 DB 10 18 20 28 30 38`, or with a two-byte operand, as below |
| The second byte before `3E` | Those of an instruction with a two-byte operand: `01 11 21 31 22 2A 32 3A C2 C3 C4 CA CC CD D2 D4 DA DC E2 E4 EA EC F2 F4 FA FC` |

The scan also skips a real `LD A,n` after an operand that has the value of such an
opcode, and the watch patches that `LD A,n` when it runs before the snapshot.

### The RAM search patch

Some loaders search for RAM in pages 0 and 1 themselves, from code in page 3. Mot's
loader tries each slot ID from 15 down to 0 through the BIOS's `WRSLT` and `RDSLT`,
and marks each ID from 4 up as the ID of an expanded slot. To select the slot that
it finds, the loader writes the slot's subslot register at FFFFh, so the loader
selects that primary slot in page 3, where its own code runs. That write works when
the RAM of page 3 is in the same primary slot, as on the VG-8020, whose RAM is all
in slot 3. On the Sanyo PHC-28S, the RAM of page 3 is in slot 0 and the HBM-64's RAM
is in slot 1, so the loader's code is gone after the write. The capture finds such a
write itself, in three parts:

1. At step 4, the write watchpoint on port A8h tests each write from code in page 3
   that selects another primary slot in page 3. When the 4 bytes after the write's
   `OUT` differ in that slot, the write cuts off the code that made it, and the
   capture logs the write.
2. When the loader's search, below, occurs in the tape files, the capture stops.
   `capture.py` then adds a patch of each copy to `snap/patches.txt` and runs the
   capture again, as for a slot patch. Each copy cuts off its code on this machine,
   and a copy on side 2 or in a compilation's later game runs after the snapshot.
   The patched loader selects the slot that it finds through the slot register only.
3. Otherwise, when the write's code is one of the slot patches' forms
   ([Slot patches](#slot-patches)), the capture patches the code's value, in the
   same way as a slot patch. The patched value keeps page 3 in the slot that page 3
   selected before the write. Doki Doki Penguin Land's and Eggerland's loaders
   select slot 1 in pages 1 to 3 on the PHC-28S, whose page 3 is in slot 0, from
   code in page 3. Otherwise the logged write is for a `patch` line by hand.

| Code | Bytes | Patch |
|---|---|---|
| `LD A,B / DEC A / CP 4 / JR C,+2 / SET 7,A`: the slot ID from the search's count, with the expanded slot's mark from 4 up | `78 3D FE 04 38 02 CB FF` | `SET 7,A` to two `NOP`s, `00 00` |

A machine whose RAM for page 3 is in the same primary slot never gets the patch,
because the write keeps the loader's code.

### Page 3's slot for the other pages

Many loaders assume that the slot of page 3's RAM also holds RAM in pages 0 to 2.
The slot does so on a machine with 64 KB in one slot, such as the Philips VG-8020.
On a machine whose RAM is in several slots, such a loader copies the game into the
ROM or into a subslot that the other pages do not select. The game then crashes into
a reset, or starts in BASIC's ROM, which stops at an error ([Check](#check), point
4).

The loaders take many forms. The capture's own patches cover the forms that set a
fixed value or copy a slot with known code ([Slot patches](#slot-patches),
[The RAM search patch](#the-ram-search-patch),
[The page copy patch](#the-page-copy-patch)). The other forms' fixes are lines in
the game files, most often a capture without the Carnivore2. The forms seen so far,
and their games, are in [NOTES.md](NOTES.md#page-3s-slot-for-the-other-pages).

### The page copy patch

Some loaders give pages 0 and 1 the slots of pages 2 and 3, or page 1 the slot of
page 3, by shifting the slot register's value. On the PHC-28S without the
Carnivore2, page 3 is the internal RAM in slot 0, which has the ROM in pages 0
and 1. So the copy selects the ROM where the loader writes the game. The capture
patches this code itself, in three parts:

1. Before each capture, `capture.py` looks for the forms below in the tape files.
   For each place, it also tests whether the last byte of the CAS block that holds
   the place is the 8-bit sum of the block's other bytes. The blocks that Level 9's
   loader checks have such a last byte.
2. At step 3, before the load command, the capture tests each slot that a form
   copies, as the slot register selects it then, against the slot map. A slot
   is fit for a page when it holds RAM there. For CasLink3's form, an expanded slot
   is fit as well, because CasLink3 also copies the subslot register's fields.
3. When a slot is not fit, the capture patches the form at each place, and adds the
   patch's difference to the block's sum byte. It writes the patches to
   `snap/patches.txt` and runs the capture again, as for a slot patch.

| Form | Bytes | Copies | Patch |
|---|---|---|---|
| Level 9's: `IN A,(0A8h)`, four `SRA A`s, `AND 0Fh`, `OR C` | `DB A8 CB 2F CB 2F CB 2F CB 2F E6 0F B1` | Pages 2 and 3 to pages 0 and 1 | `LD A,n` and `NOP`s |
| CasLink3's: `AND 0F0h`, `LD B,A`, four `RRCA`s, `AND 0Fh`, `OR B` | `E6 F0 47 0F 0F 0F 0F E6 0F B0` | Pages 2 and 3 to pages 0 and 1 | `LD A,n` and `NOP`s |
| The Wall's: `AND 0F0h`, `LD B,A`, four `RLCA`s, `OR B` | `E6 F0 47 07 07 07 07 B0` | Pages 2 and 3 to pages 0 and 1 | `LD A,n` and `NOP`s |
| Engesoft's: `BIT 7,A / JR Z,+2 / SET 3,A / BIT 6,A / JR Z,+2 / SET 2,A` | `CB 7F 28 02 CB DF CB 77 28 02 CB D7` | Page 3 to page 1 | `AND 0F3h / OR n` and `NOP`s |
| M-Droid's: the same with `JP Z` | `CB 7F CA nn nn CB DF CB 77 CA nn nn CB D7` | Page 3 to page 1 | `AND 0F3h / OR n` and `NOP`s |

In `LD A,n`, n holds BASIC's slots in pages 2 and 3. In pages 0 and 1, n holds the
copied slot when it is fit, and otherwise the slot map's replacement for the page.
In `OR n`, n holds the slot map's replacement for page 1. On the PHC-28S without the
Carnivore2, n is 15h for the first three forms, and 04h, the RAM cartridge in page
1, for the last two. A machine whose RAM for page 3 holds RAM in pages 0 and 1, as
the VG-8020's slot 3 does, never gets the patch.

## Build

`tools/build.py` writes the image ([DESIGN.md, Formats](DESIGN.md#formats)). It:

- Stores each 16 KB block of `vram.bin`, as a block of zeros when it holds only
  zeros, and each RAM page, once for a segment that two pages select. Such a
  segment's record has the lower page, so the header names the records that hold
  the tail and the game's page 3 by their numbers
  ([FORMATS.md, Image](FORMATS.md#image)).
- Turns the PSG, PPI and VDP state into a list of port writes, in the order that the
  restorer makes them ([FORMATS.md, Port writes](FORMATS.md#port-writes)).
- Writes the tail, from `SERVICE.BIN`, into the 26 bytes below the stack pointer. At
  an interrupt's entry these bytes are free, because the handler that runs next
  pushes onto them. When they cross a page boundary, the tail goes into the 26 bytes
  below that boundary instead. Those bytes are further below the stack pointer and
  as free. `build.py` stops with an error when the bytes go below 0000h, include
  FFFFh, or are not in a RAM page that the snapshot keeps. The last case is mostly a
  load that failed on that machine, with the stack in the ROM, so the error names
  `snap/log.txt`.
- Finds the RAM page that the snapshot selects in a page by its slot. In a memory
  mapper, it also finds the RAM page by the segment that the page's mapper register
  selects, because a game can select one segment in two pages.
- Applies the patches of `snap/patches.txt` to the tape, and runs the scan's search
  for slot values on every image ([Slot patches](#slot-patches)).
- With the tape service, builds T0, the code segment and the other tape segments
  from `rom.bin`, the tape files and `SERVICE.BIN`. For such an image, it also
  writes the service's part of page 3 into the game's page 3, with the snapshot's
  value of mapper register FCh at FCF9h. With the tape service, it also runs the
  scan, and applies the scan's patches and the `patch` lines
  ([Tape service](#tape-service)). When no part of page 3 has room for the service's
  part, it uses the mode without a part in page 3, as `service t0` does
  ([Without a part in page 3](#without-a-part-in-page-3)). It stops with an error
  when the code segment and the tape need more than 64 segments.
- Puts the service's part of page 3 at FCE1h when FCC9h to FD88h are zero at the
  snapshot, as the capture leaves them. A game can use that area itself. The part
  then goes to xxE1h of the highest page xx below the BIOS's work area at F380h
  whose 143 bytes from there are zero, or to the game file's `service at`. The
  tail's 26 bytes are zero at the snapshot too, when the stack is empty there. So
  `build.py` finds the tail's address first and takes no place that holds one of the
  tail's bytes. It stops with an error when the game file's `service at` holds one,
  or would put the part past FFFEh. Zeros at the snapshot can still be a buffer that
  the game fills later, so a moved part is checked by playing to the game's next
  load. The part moves by its page alone. The entries keep their low bytes, E1h to
  F3h, and the scan's patches write xxh instead of FCh. `build.py` adds xx minus FCh
  to each byte that `SERVICE.BIN`'s last part lists, and writes xx in the image's
  header ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)).
- Prints the most mapper segments that the image can require.

`build.py` holds no address of the service's code. It reads each address by its name
from the symbols in `SERVICE.BIN`, which `src/service.asm` exports. The symbols give
the fields that `build.py` fills in, the stubs' addresses that the ROM's jump table
must hold, the part's length and the area FCC9h to FD88h. `build.py` holds no offset
of the image's header or of the tail either. `src/service.inc` defines the image's
layout, its flags, its record types and the tail's fields once. The restorer is
assembled with these names, and `SERVICE.BIN`'s symbols give them to `build.py`. Of
the image's mark, `build.py` holds `SNAPCAS`, and it takes the format's number from
the symbols. `build.py` stops with an error in four cases:

- The version byte of `SERVICE.BIN` is not the one that `build.py` expects.
- The file has another number of parts.
- The file's tail is not 26 bytes.
- The file lacks a symbol.

## Restorer

`SNAPCAS.COM` runs under MSX-DOS 1, MSX-DOS 2 or Nextor. Its code and data stay
below 4000h, and it holds the worker twice, assembled to run in pages 1 and 2. The
restorer keeps DOS's stack, in page 3, because MSX-DOS 2's mapper routines page the
DOS kernel into page 0. It uses a stack in page 0 only while it selects another slot
in page 3, and the worker keeps its own stack in its own page. The restorer reads
the image with the FCB functions `_FOPEN`, `_SETDTA` and `_RDBLK`, which MSX-DOS 1
has and which MSX-DOS 2 and Nextor keep. For DOS's mapper, it takes these from each
DOS:

| | MSX-DOS 2 and Nextor | MSX-DOS 1 |
|---|---|---|
| DOS's segments in pages 0 to 3 | `GET_P0` to `GET_P3` | 3, 2, 1 and 0, as the MSX2 BIOS and Nextor set them. The restorer checks these segments |
| A segment selected in page 2, while DOS runs | `PUT_P2` | A write to mapper register FEh |
| The mapper's size in segments | The mapper support's answer, from `EXTBIO` | A count |
| The free segments | Each segment that `ALL_SEG` gives, until it fails | Segments 4 and up |

MSX-DOS 1 has no mapper calls, and a mapper register cannot be read back on every
machine. So under MSX-DOS 1 the restorer looks through page 2, with interrupts off.
To check page 2 itself, the restorer writes a mark at 8000h and selects segment 1 in
page 2. The mark must still be at 8000h. To check each other page, the restorer
selects the page's segment in page 2 and changes a byte there. The byte at the
page's first address must change too. The restorer counts the mapper's segments in
four steps:

1. It saves the first byte of segments 0 to 3.
2. It writes each segment's number into the segment's first byte, from segment 255
   down to segment 0.
3. It reads the first bytes back from segment 4 up, to the first mismatch.
4. It restores the saved bytes.

The restorer performs the steps below. Steps 1 and 2 are the restorer's plan. In the
plan, the restorer decides everything that the restore depends on, and writes
nothing of the game. Every stop for an image that the machine cannot restore comes
in the plan, so the stop's message shows on DOS's screen
([The restorer's stops](#the-restorers-stops)).

1. Opens `<GAME>.SNP`, whose name DOS has placed in the FCB at 005Ch, with the
   extension set to SNP. Without a name, it prints its usage. It reads the image's
   first 4,096 bytes, and checks, in this order:
   - That the image starts with `SNAPCAS` and the format's number of this
     `SNAPCAS.COM` ([FORMATS.md, Image](FORMATS.md#image)). For an image with
     another number, the restorer's message says that the image was made for another
     version of `SNAPCAS.COM`.
   - That `RAMAD0` to `RAMAD3` name one slot, DOS's mapper. Under MSX-DOS 2 and
     Nextor, that slot must be the primary mapper's. Under MSX-DOS 1, the pages must
     show segments 3, 2, 1 and 0, as above.
   - That the CRC-16 of the main ROM and of the sub-ROM equal the image's. The
     worker runs in page 2 and reads the ROMs while pages 0 and 1 select the ROM.
   - That the file holds the header and tables and 16,384 bytes for each record
     that has data, by the size that `_FOPEN` leaves in the FCB.
   - The records. The slot of each RAM page must be expanded on this machine when
     the slot was expanded at the capture, and only then. A RAM page outside a
     mapper must not be in DOS's mapper's slot, where the page's copy would write
     over DOS's own memory. Each segment of DOS's mapper must be within the mapper's
     size.
   - With the tape service, that no RAM page kept for page 0 is in another subslot
     of the primary slot of DOS's mapper. In the mode without a part in page 3, the
     restorer also checks that mode's conditions
     ([Without a part in page 3](#without-a-part-in-page-3)).
   - With the tape service, whether T0 replaces the ROM. T0 replaces the ROM when
     the snapshot's page 0 selects the main ROM, no RAM page kept for page 0 is in
     DOS's mapper, and the game file has no `rom keep` line. The restorer then
     changes the snapshot's values that step 6 writes. Page 0's slot becomes DOS's
     mapper, and step 2 sets mapper register FCh to T0's segment.
   - With the tape service, when DOS's mapper is in an expanded slot, the snapshot's
     page 0. The entry code selects DOS's mapper in page 0 by the slot register
     alone. So the restorer sets page 0's bits of that slot's subslot register to
     the mapper's subslot. When T0 does not replace the ROM and the snapshot's page
     0 is in another subslot of that slot, page 0 would become the mapper's RAM, so
     the restorer stops. The main ROM of a game file with `rom keep` is such a page
     0 on a machine that has its ROM and DOS's mapper in one slot. The Victor HC-90A
     has them in slots 0-0 and 0-2.
   - That page 1 or page 2, other than the tail's page, can hold the worker at the
     end. When DOS's mapper is in an expanded slot, the worker must keep the
     mapper's subslot in its page while it writes that slot's subslot register. The
     restorer takes the first of these:
     - A page whose bits in the snapshot's subslot register of the slot already
       select the mapper's subslot.
     - When the snapshot's page 3 selects the slot, either page. The tail then
       writes the slot's true subslot register at FFFFh.
     - A page that does not select the slot at the snapshot. That page's bits of the
       register then differ until the BIOS writes them again from `SLTTBL`.
2. Takes every free segment of DOS's mapper, and counts the segments that the image
   needs. The image needs one for each RAM page of DOS's mapper whose segment is not
   DOS's own in page 1 or 2, one for each service segment, and one for the worker.
   The restorer stops when DOS has fewer free segments, and its message names the
   number needed and the number free. It then gives each record of DOS's mapper the
   segment that step 3 reads the record into:
   - A RAM page of DOS's mapper whose own segment is free, or is DOS's segment in
     page 1 or 2, goes straight into that segment.
   - Each other RAM page of DOS's mapper gets a holding segment, which the worker
     copies into the page's own segment in step 6. The worker's list holds 64
     holding segments.
   - T0 takes mapper register FCh permanently in two cases: in the mode without a
     part in page 3, and when T0 replaces the ROM. Every mapper follows FCh. So when
     a RAM page for page 0 is in another mapper, T0 must be that page's segment of
     DOS's mapper. The restorer reads T0 straight into that segment when the segment
     is free. Otherwise T0 gets a holding segment, which the worker copies into that
     segment in step 6.
   - Each other service segment gets one of the segments left, and so does the
     worker.
3. Reads the records in this order, through the FCB's random record field: the RAM
   pages of slots other than DOS's mapper, the service segments, the RAM pages of
   DOS's mapper, and the VRAM blocks. The VRAM blocks come last, because the first
   one blanks the display and writes over DOS's text. It places each record:
   - The restorer reads a RAM page of another slot into page 2, or into page 1 for a
     target in page 2. The copy selects the target slot in the target page, and
     changes only that page's bits of the subslot register. It sets the page's
     mapper register to the record's segment when the record has one. It then copies
     the page, reads the page back, and selects DOS's slot and segment again.
     Interrupts are off for all of these actions. The restorer itself copies to
     pages 1 to 3, on a stack in page 0. For a target in page 0, the worker copies,
     in page 1 with its stack there. In an expanded slot, the copy of page 3 stops
     at FFFEh, because FFFFh is the subslot register. A mismatch stops the restorer,
     because the machine file then does not describe this machine.
   - The restorer reads a service segment or a RAM page of DOS's mapper into that
     record's segment, selected in page 2.
   - The restorer reads a VRAM block into the worker's segment, selected in page 2.
     That segment is free until step 6, and DOS's own segment in page 2 can hold a
     page of the game by now. The restorer writes the block to the VDP through ports
     98h and 99h and register 14, with interrupts off and the display blanked. To
     blank the display, the restorer writes register 1 with `RG1SAV`'s value, with
     bit 6 clear and with bit 7 from the snapshot's value. That bit makes the VDP
     map VRAM as the game does, because bit 7 of a TMS9918's register 1 chooses its
     4 KB or 16 KB mapping (TMS9918A data book, register 1). The other bits stay
     DOS's, because a game's bit 5 of 0 turns off the VDP's interrupt, and DOS needs
     that interrupt between the blocks. The restorer writes a block of zeros without
     a read. DOS's text mode has no planar layout, so the bytes go to VRAM as
     stored.

   As the records arrive, the restorer fills in the values that depend on the real
   machine. The header names the records of the tail and of the game's page 3 by
   their numbers ([FORMATS.md, Image](FORMATS.md#image)):
   - In the tail: the worker's page's mapper register and its value, the slot
     register and, when step 1 chose it, the write of the subslot register of DOS's
     mapper's slot ([FORMATS.md, Tail](FORMATS.md#tail)).
   - With the tape service, in the code segment at 0014h: the code segment, then the
     other tape segments, and at 0054h: 1 for `/M`, or otherwise 0.
   - With the tape service, in the game's page 3 at FCF6h: DOS's mapper's slot ID,
     T0's segment and the code segment, and at FCF9h T0's segment when T0 replaces
     the ROM.
   - With the tape service, when DOS's mapper is in an expanded slot, DOS's mapper's
     subslot in the page 0 bits of `SLTTBL` in the game's page 3, as step 1 set them
     in that slot's subslot register.
   - In each place that the header lists, the slot register value that selects
     DOS's mapper in page 0.
4. Waits until `JIFFY` has advanced by 180, so that a floppy drive's motor stops,
   then disables interrupts. From this point on, it calls neither DOS nor the BIOS.
5. Performs the port writes.
6. Copies the worker into the worker's segment through page 2, with the snapshot's
   values that the worker writes, and selects that segment in the page that step 1
   found. The worker, with its stack in its own segment, copies each holding segment
   into its own segment through the two other pages below page 3. It then writes the
   subslot register of each expanded slot while page 3 selects that slot, and ends
   with the snapshot's page 3 slot. Then it writes the mapper registers of the three
   other pages, and the slot register with its own page still selecting DOS's
   mapper. It loads every register except AF and SP, sets I and the interrupt mode,
   and jumps to the tail.
7. The tail writes the worker's page's mapper register, the slot register and, when
   step 1 chose it, the subslot register of DOS's mapper's slot. It then loads AF
   and SP, enables interrupts when IFF1 is set, and jumps to the program counter.
   The restorer does not restore the R register.

### The restorer's stops

When the restorer stops, it prints the image's name and one of these messages, and
returns to DOS:

| Message | Step | The restorer stops when |
|---|---|---|
| `not found` | 1 | DOS finds no `<GAME>.SNP` |
| `is not a snapcas image` | 1 | The file holds fewer than 4,096 bytes, or does not start with `SNAPCAS` |
| `made for another version of SNAPCAS.COM` | 1 | The mark's format number is not this `SNAPCAS.COM`'s |
| `DOS's pages are not in one memory mapper` | 1 | `RAMAD0` to `RAMAD3` name more than one slot, or a slot other than MSX-DOS 2's primary mapper |
| `MSX-DOS 1 needs a memory mapper with DOS in segments 3, 2, 1 and 0` | 1 | Under MSX-DOS 1, a page does not show its segment of a mapper |
| `made for another machine: its ROMs differ from this one's` | 1 | A ROM's CRC-16 is not the image's |
| `the file is cut short: it lacks data of its records` | 1 | The file holds fewer bytes than its header and its records' data |
| `slot N is not expanded as at the capture: the machine file does not describe this machine` | 1 | A RAM page's slot is expanded on this machine and was not at the capture, or the reverse |
| `slot N is DOS's mapper, and the image has RAM without a mapper there` | 1 | A RAM page outside a mapper is in DOS's mapper's slot |
| `a page's segment is beyond this machine's mapper` | 1 | A RAM page of DOS's mapper has a segment that the mapper lacks |
| `a page 0 is in another subslot of DOS's mapper's slot` | 1 | With the tape service, a RAM page kept for page 0, or the snapshot's page 0 when T0 does not replace the ROM, is in DOS's mapper's primary slot with another subslot |
| `rom keep needs the main ROM outside DOS's mapper's slot` | 1 | The game file has `rom keep`, and the snapshot's page 0 selects the main ROM in another subslot of DOS's mapper's primary slot |
| `service t0 needs page 0 outside DOS's mapper` | 1 | Without a part in page 3, a RAM page kept for page 0 is in DOS's mapper |
| `service t0 needs DOS's mapper's subslot in the borrowed page` | 1 | Without a part in page 3, the snapshot's subslot register of DOS's mapper's slot selects another subslot in the page that `TAPIN` borrows |
| `no page 1 or 2 can hold the restorer's worker at the end` | 1 | None of step 1's three rules gives the worker a page |
| `needs N free mapper segments, and DOS has M` | 2 | DOS has fewer free segments than the image needs |
| `T0 cannot take the segment of page 0's RAM, which shares mapper register FCh with it` | 2 | T0 must be the segment of a page 0 in another mapper, and one of these is true: two such pages differ in that segment, DOS's mapper lacks the segment, or a RAM page of DOS's mapper has the segment |
| `more than 64 pages need a segment that DOS uses` | 2 | The worker's list of holding segments is full |
| `DOS has too few free mapper segments` | 2 | A segment is missing after the count, because the image needs 256 |
| `slot N page P is not RAM: the machine file does not describe this machine` | 3 | A RAM page of another slot reads back with another byte than its copy |
| `cannot be read` | 3 | DOS reads fewer bytes than a record's data, as at a disk error |

The two stops of step 3 come after the restorer has written memory of the game, but
before the VRAM blocks, so their messages show too. Only a VRAM block after the
first can stop the restore with a blanked display, at `cannot be read`. The restorer
then sets up DOS's text screen again before it prints. It calls the BIOS's `INITXT`,
or `INIT32` when `SCRMOD` is 1, through DOS's inter-slot call at 001Ch. On an MSX2
it first selects VRAM's first 16 KB again in register 14. DOS itself prints a
message for a disk error during the VRAM blocks, such as its question to abort or
retry. That message gets no such screen, and stays invisible.

## Tape service

The tape service keeps the tape in service segments, and has these parts:

| Part | Location | Function |
|---|---|---|
| T0 | A service segment | The BIOS's page 0 with the service's stubs from 19DDh to 1B44h |
| Code segment | A service segment | The routines, the tape position and the table of the tape's segments, then the start of the tape |
| Tape data | The code segment, then the other service segments | Side 1, padded with zeros to a multiple of 8 bytes, by at least 1 byte when side 2 follows, then side 2 |
| Entries | FCE1h to FCF5h, in `SLTATR`, unless the part moved ([Build](#build)) | One for each entry of the BIOS's tape jump table, from 00E1h to 00F5h, for code that goes around T0 |
| `TAPIOF` and `STMOTR` | Page 3, after the entries' data at FCF6h to FCFAh | The two routines that only stop the manual tape. The entries and T0's stubs jump to them |
| Entry code | Page 3, after `TAPIOF` and `STMOTR` | For the entries of `TAPION` and `TAPIN`, selects DOS's mapper in page 0, calls the routine through the trampoline, and selects the game's page 0 again |
| Trampoline | Page 3, after the entry code | Selects the code segment in page 0, calls a routine there, and selects T0 again |
| Reader | Page 3, after the trampoline | Reads a tape byte. Its code is `OUT (C),D / LD E,(HL) / OUT (C),B / RET` |
| Stack | Page 3, after the reader, to FD6Fh | The entry code's scratch bytes, 3 for the game's stack pointer and slot register, then its stack, 22 bytes |

These parts in page 3, from the entries to the stack, are the service's part of
page 3. The part is 143 bytes long, and goes from FCE1h to FD6Fh by default.

`build.py` builds T0 from `rom.bin`, so it first checks that each jump table entry
below jumps to its address, as in the standard MSX BIOS. The restorer's ROM check
ensures that the real ROM equals `rom.bin`.

The addresses are in [FORMATS.md, T0's jump table](FORMATS.md#t0s-jump-table).

T0's stubs keep these addresses and leave the rest of the 360 bytes from 19DDh to
1B44h free. `build.py` also points the jump table entry 00F3h, `STMOTR`, at its
stub, because the BIOS's code is outside that range. That code is at 1384h on an
MSX1 and at 1387h on an MSX2. The stubs of `TAPION` and `TAPIN` call the code
segment's routines through the trampoline, which is in page 3 because it changes
page 0. The stubs of `TAPIOF` and `STMOTR` jump to their routines in page 3, and the
entries share those routines.

Each routine returns as the BIOS's routine does, by the BIOS's code in the ROM. It
gives the same result, keeps the same registers and leaves the same interrupt state,
except for the three differences below the table. The routines return in this way
through T0's jump table, through the entries in page 3, and in the mode without a
part in page 3. So a game can keep a counter in B across `STMOTR`, and can call
`STMOTR` with interrupts on and then wait for an interrupt. A game can also test
after `TAPIOF` the carry that its last `TAPIN` returned.

| Routine | What it does | What it returns and keeps |
|---|---|---|
| `TAPION` | Moves the tape position past the next CAS header at a multiple of 8 bytes | Carry clear, or set when CTRL+STOP is held. Interrupts off. It changes AF, BC, DE and HL |
| `TAPIN` | Returns the byte at the tape position, and advances the position | The byte in A. Carry clear, or set when CTRL+STOP is held. B = 0 with a byte, as the BIOS's `TAPIN` leaves B, because Gauntlet's level loader adds BC to a sum with the byte in C. Interrupts off. It changes AF, BC, DE and HL |
| `TAPIOF` | Stops the manual tape ([The manual tape](#the-manual-tape)) | Every register and flag kept. Interrupts on |
| `TAPOOF` | Nothing | Every register and flag kept. Interrupts on |
| `TAPOON` | Nothing, because the tape cannot be written | Carry set, with interrupts off, as the BIOS's `TAPOON` returns when CTRL+STOP ends it. It changes only flags |
| `TAPOUT` | Nothing, because the tape cannot be written | Carry set, with the interrupts as they were, as the BIOS's `TAPOUT` returns when CTRL+STOP ends it. It changes only flags |
| `STMOTR` | Stops the manual tape when A is not 1 | It changes only AF. The interrupts stay as they were |

Three details differ from the BIOS's code:

- The BIOS's `TAPIN` changes AF, BC, DE and L, so it keeps H, and the service's
  `TAPIN` does not keep H. A caller must save L, so the caller saves HL. T0 has no
  room for the code that would keep H in the mode without a part in page 3.
- The BIOS's `TAPIN` leaves the interrupts as they are, because it expects them off
  after `TAPION`. The service's `TAPIN` disables them, because it changes page 0.
- The BIOS's `STMOTR` stops the motor for A = 0, starts it for A from 1 to 7Fh, and
  changes its state for A from 80h to FFh. The service's `STMOTR` stops the manual
  tape for every A except 1. A tape that is stopped once more only waits for the
  player's key.

The code segment holds the service's data, its routines and then the tape, which
starts at a multiple of 8 bytes
([FORMATS.md, The code segment](FORMATS.md#the-code-segment)).

`TAPIN` reads a byte through the reader in page 3. The reader runs with C = FCh,
with the byte's segment in D and with the code segment in B. It selects the byte's
segment in page 0, reads the byte at HL into E, and selects the code segment again.

Each entry is 3 bytes long, so the entries have the low bytes of the jump table's
entries, E1h to F3h. So a game that changes the low byte of a call, from `TAPION` to
`TAPIN` and then `STMOTR`, reaches the matching entry. Each entry has its own code,
so that each returns as its routine must:

| Entry | Code |
|---|---|
| `TAPION`, `TAPIN` | A jump to the entry code, with the routine's address in the code segment |
| `TAPIOF`, `STMOTR` | A jump to the routine in page 3. The routine only writes the byte at FCFAh, so it runs with the game's page 0, stack, registers and interrupt state |
| `TAPOON` | `DI / SCF / RET` |
| `TAPOUT` | `SCF / RET` |
| `TAPOOF` | `EI / RET` |

The entry code disables interrupts, switches to its own stack, selects DOS's mapper
in page 0, and calls the routine through the trampoline. Then it selects the game's
page 0 and stack again, with mapper register FCh set to the value at FCF9h, and
returns with interrupts off. It returns the registers as the trampoline does, so an
entry and T0's stub of the same routine leave the same registers. The entry code's
deepest path takes 20 of the stack's 22 bytes. That path is a read under the header
compare of `TAPION` or `TAPIN` that moves the tape to another side and flashes. The
data of the part is before its code
([FORMATS.md, The entry code's data](FORMATS.md#the-entry-codes-data)).

The tape position starts where the game stopped reading at the snapshot, and moves
on these events. The routines read the keyboard matrix through the PPI.

| Event | Automatic tape, the default | Manual tape, with `/M` |
|---|---|---|
| `TAPION` or `TAPIN` reads past side 1's end | Side 2's start, as when the player turns the tape over, or side 1's start when there is no side 2 | The tape stops at that end and waits for the player's key ([The manual tape](#the-manual-tape)) |
| `TAPIN` reads in side 1's padding before side 2 | Side 2's start, and `TAPIN` returns FFh. The padding is not on the tape. In `openMSX`, the read that waits while the player turns the tape over returns FFh, and loaders expect that value | The tape stops at side 1's end. After RETURN, the position is side 2's start and `TAPIN` returns FFh |
| `TAPIN` reads at a multiple of 8 where a CAS header is | The byte after the header, because a header is a tone on the tape. `TAPIN` waits through that tone, as when a game reads on into the next block or side | The same |
| `TAPION` or `TAPIN` reads past side 2's end | Side 2's start, as after a rewind | The tape stops at that end and waits for the player's key |
| `TAPION` or `TAPIN` is called while the tape is stopped | The automatic tape never stops | The tape waits for the player's key |
| `TAPION` is called while GRAPH is held | Side 1's start | Side 1's start, at any read that waits |
| `TAPION` is called while CODE is held | Side 2's start, or side 1's start when there is no side 2 | The same, at any read that waits |

The service shows a move of the tape with one flash of a colour over the whole
screen for 0.1 second. GRAPH and CODE flash the colour of the side that the position
moves to. So does the automatic tape when it reaches side 2 or goes back to a side's
start. RETURN on the manual tape flashes its own colour when the tape plays on, and
also when RETURN turns the tape over to side 2. The flash sets the border colour and
blanks the display, and the display then shows only the border. The flash blanks the
display because the border alone is thin and many screens crop it. Side 2 starts at
side 1's end, so a read that reaches side 2 changes only the side at 0059h, and that
change shows the flash. The service counts the frames by the frame flag in the VDP's
status register 0. It then writes the game's VDP registers 7 and 1 back and goes on.
The VDP's registers cannot be read, so the service takes the game's values from the
addresses at 0055h and 005Ah in the code segment. The colours are these:

| Outcome | Border |
|---|---|
| Side 1's start | Light green, 3 |
| Side 2's start | Light red, 9 |
| RETURN plays on | Light yellow, 11 |

### The manual tape

By default the tape is automatic. It turns over and rewinds by itself, and the
player needs no key. With `/M`, the tape service moves the tape only when the player
asks, as a real tape moves only after the player presses PLAY. So the player follows
what the game says on the screen. The manual tape stops in these cases, and the byte
at FCFAh records the stop:

- The game stops the motor, with `TAPIOF`, or with `STMOTR` and A other than 1.
- `TAPION` finds the motor off in PPI port C bit 4, because the game stopped the
  motor without the service. The game did so through the BIOS in ROM, or with its
  own write to the port. `TAPION` then starts the motor, as the BIOS's `TAPION`
  does.
- A read reaches side 1's end or side 2's end.
- The motor is off at the snapshot. `build.py` reads the motor's state from PPI port
  C bit 4.

While the motor runs, between the blocks of one load, the tape plays on and no read
waits. A read that finds the tape stopped reads the keyboard matrix through the PPI,
and waits for one of these keys:

| Key | The tape |
|---|---|
| RETURN | Plays on from where it stopped. At side 1's end with a side 2, it goes on at side 2's start, as when the player turns the tape over. At side 2's end, or at side 1's end without a side 2, it waits on, because the tape holds nothing more |
| GRAPH | Goes to side 1's start, as after a rewind |
| CODE | Goes to side 2's start, or to side 1's start when there is no side 2 |
| CTRL+STOP | The routine returns with carry set, as the BIOS's routine does, and the tape stays stopped where it was. So does a `TAPION` that waits while it reads on to a multiple of 8 bytes |

After GRAPH or CODE, the read that waited starts again at the new place, as a read
does after a real rewind. So `TAPION` looks for a header from there, and `TAPIN`
skips the header there and returns the byte after it.

A key that is held when the read starts acts at once. So one press can answer both a
game's own prompt and the tape. For "rewind the tape and press a key", the player
presses CODE as the game's key and holds it until the game reads. The read goes on
only when the player releases the key, so the game does not read the key.

The manual tape's code and data take 198 bytes, and the service without them fills
359 of T0's 360 bytes. So in the mode without a part in page 3 the tape stays
automatic. With `/M`, `SNAPCAS` then says before the restore that the tape stays
automatic, as it does for a game without the tape service, and goes on.

### Without a part in page 3

A game can use all of its page 3 over time, as Moonwalker does. Moonwalker's main
game loads its code into FCC9h to FD88h, and no 143 bytes of Moonwalker's page 3
stay free from one load to the next. For such a game, the game file's `service t0`
puts the whole tape service into T0, and nothing of the service stays in page 3.
`build.py` also takes this mode itself when no part of page 3 has room at the
snapshot. So a game file needs `service t0` only for a game whose page 3 is free at
the snapshot but not in a later load, as Moonwalker's is. The line goes in the game
file of each machine that needs it. Moonwalker's is in
`phc28s-ram64k-carnivore2.txt`. The service's part of page 3 exists only because the
service switches page 0 while it runs, so this mode removes the three switches:

| Switch | Without a part in page 3 |
|---|---|
| The entry code selects DOS's mapper in page 0 | The game reaches T0 by slot. T0 stays in mapper register FCh permanently, so page 0 shows T0 whenever the game selects DOS's mapper there. T0's jump table, from 00E1h to 00F3h, is the only set of entries. When the snapshot has the ROM in page 0, the restorer selects T0 there instead, by the default mode's rule ([Restorer](#restorer)), so that BASIC's own `BLOAD` reaches T0 |
| The trampoline selects the code segment | The routines run in T0. They, the tape position, the table of the tape's segments and the flash's data take the 360 bytes from 19DDh to 1B44h, and an assertion in `src/service.asm` checks that they do. `src/tape.inc` holds the data and the routines, and `service.asm` assembles them in the code segment and in T0. `build.py` points T0's jump table at T0's copy |
| The reader selects the tape's segments in page 0 | `TAPIN` reads through page 2 or page 1. `build.py` chooses the first of these pages that is a page of a mapper at the snapshot, or else page 2. `TAPIN` keeps the slot register's value in T0. It selects DOS's mapper's slot in that page through the slot register, and the byte's segment through FEh or FDh. It then reads the byte, and writes back the slot register and the snapshot's segment. Interrupts are off for all of these actions. It uses no stack meanwhile, so the page can hold the game's stack. A game whose RAM is in a slot without a mapper can also lend its page. When the capture has no mapper at all, as a capture variant without the Carnivore2 has none, the game lends page 2. `TAPIN` then writes back segment 0, which only DOS's mapper sees |

The tape takes at most 16 segments, 256 KB, and starts at the first tape segment.
Each routine returns as in the default mode ([Tape service](#tape-service)).
`TAPIOF` and `TAPOOF` only enable interrupts, and `STMOTR` only returns, because
this mode has no manual tape to stop. The keys and the flash work as in the default
mode.

A game can use the mode only when the conditions below hold at the snapshot. The
last column says what stops when a condition does not hold. The game file's reader
or `build.py` stops with an error, or the restorer stops with a message.

| Condition | Why | What checks it |
|---|---|---|
| No RAM page kept for page 0 is in DOS's mapper | T0 takes the game's mapper register FCh permanently | The restorer, which knows DOS's mapper: `service t0 needs page 0 outside DOS's mapper`. `build.py` checks the condition only when it can tell DOS's mapper. It can tell DOS's mapper when the capture ran on the machine itself, without a capture variant, and the snapshot's mapper pages are all in one slot, which is then DOS's. `build.py` then stops and says that the game needs a capture variant or `service at`. With a capture variant, or with mapper pages in two slots, as on the HB-F700P with a RAM cartridge, `build.py` leaves the condition to the restorer |
| The game file has no `rom keep` | With `rom keep` the ROM stays in page 0, and this mode has no entries in page 3. So the game's tape calls reach the BIOS's own routines and not T0 | The game file's reader, for a game file with `service t0`, and `build.py`, when it takes the mode itself |
| When the borrowed page is in DOS's mapper, the game keeps its segment there from then on | `TAPIN` writes back the snapshot's segment | Nothing, because the condition is about what the game does after the snapshot |
| When DOS's mapper's slot is expanded, the snapshot's subslot register of that slot selects the mapper in the borrowed page | The slot register alone then selects the mapper there. The restorer checks the condition, because only the restorer knows DOS's mapper's slot. When the capture did not have that slot expanded, as a capture variant without the Carnivore2 does not, the game never wrote the slot's subslot register. So the restorer sets the borrowed page's bits there to the mapper's subslot instead | The restorer: `service t0 needs DOS's mapper's subslot in the borrowed page` |
| When a RAM page for page 0 is in another mapper, no RAM page of DOS's mapper has that page's segment | Every mapper follows FCh, so T0 takes that segment of DOS's mapper ([Restorer](#restorer), step 2). Afterburner on the HB-F700P keeps page 0 in the machine's own mapper, and DOS takes the RAM cartridge's | The restorer |

Code that selects the ROM in page 0 itself and then calls the tape reaches the ROM,
not T0. This mode has no entries in page 3 to send that code to. So the scan only
lists the code that reaches the tape in this mode, without a patch. One form of that
code does get a patch. That form is a stub of `TAPION` that also pushes `OUT (C),L`,
reads the slot register into H, and computes the value with page 0's field cleared,
for slot 0, as `AND H / LD L,A`. The scan makes `AND H / LD L,A` into `LD L,nn`,
where `nn` is the snapshot's slot register value with the primary slot of DOS's
mapper in page 0's field. Only the restorer knows DOS's mapper, so `build.py` writes
0 for `nn` and lists the byte's place in the image's header. The restorer writes the
value there ([FORMATS.md, Image](FORMATS.md#image)). `scan.txt` shows that byte as
`nn`. The restorer writes no byte of the tape, so the scan only lists a stub in an
unread block. Other such code needs `patch` lines in the game file that make the
code select DOS's mapper in page 0. A game that writes FCh itself loses T0.

The restorer allocates T0 and the tape's segments as in the default mode. It writes
the table of the tape's segments and DOS's mapper's slot for the borrowed page into
T0. It sets mapper register FCh to T0's segment, with DOS's mapper's subslot in the
page 0 bits of its slot's subslot register and of `SLTTBL`. `SLTTBL` is all that the
restorer writes of the game's page 3 for the service. It also writes the value of
each patched stub, at the places that the header lists. Bit 1 of the image's flags
marks the mode ([FORMATS.md, Image](FORMATS.md#image)).

### Scan

With the tape service, `build.py` scans the snapshot's RAM pages and the unread
blocks of both sides for code that reaches the tape without going through T0. It
lists each finding in `scan.txt`, in a `patch` line's form, so that a finding in an
unread block can be copied into the game file. Such a finding's offset is an offset
in the downloaded tape file, where a `patch` line is applied. The offset is in the
downloaded tape file also when the game file's `start` line makes the capture play a
copy that starts at a later file
([A game later on the tape](#a-game-later-on-the-tape)). The scan names a RAM page
that the snapshot does not select in its page by the RAM page's file in `ram/`. The
scan runs after the game file's `patch` lines, and it patches the findings in the
RAM pages. In an unread block the scan only lists the findings, for `patch` lines,
because a loader usually checks a block against a sum stored at the block's end, and
each loader computes that sum in its own way. A line of `scan.txt` holds new bytes
after `>` only for a finding that the scan patches, or in an unread block for one
that a `patch` line can patch. So in the mode without a part in page 3, where the
entries in page 3 do not exist, the calls, stubs and entries show without new bytes.
The scan looks for this code:

| Code | Bytes | Patch |
|---|---|---|
| A stub built with `TAPION`'s entry: `LD DE,00E1h / PUSH DE / LD DE,CDD9h / PUSH DE`, or the same with HL | `11 E1 00 D5 11 D9 CD D5`, or `21 E1 00 E5 21 D9 CD E5` | `E1 00` becomes `E1 FC` |
| A call of a tape routine: `CALL 00E1h`, `CALL 00E4h`, `CALL 00E7h` or `CALL 00F3h`. The last call is `STMOTR`, which the manual tape needs for Gauntlet's stops ([The manual tape](#the-manual-tape)) | `CD E1 00`, `CD E4 00`, `CD E7 00` or `CD F3 00` | The call's `00` becomes `FC` |
| An entry in HL before a call: `LD HL,00E1h` or `LD HL,00E4h`, then `CALL`, to a routine of the game's that selects the ROM in page 0 and jumps to HL | `21 E1 00 CD` or `21 E4 00 CD` | The `00` becomes `FC` |
| A reader of the cassette signal: `IN A,(0A2h)`, then within 4 bytes `RLA`, `RLCA`, `BIT 7,A` or `AND 80h` | `DB A2`, then `17`, `07`, `CB 7F` or `E6 80` | None. The scan lists the reader, for a `patch` line that sends the reader's callers to the service |
| A reader of PSG register 14, whose bit 7 is the cassette signal and whose other bits are a joystick: `LD A,0Eh / OUT (0A0h),A / IN A,(0A2h)` | `3E 0E D3 A0 DB A2` | None. The scan lists the reader, as above, and also finds this code in joystick code |
| In the mode without a part in page 3, a stub of `TAPION` that selects the ROM in page 0 as `AND H / LD L,A` ([Without a part in page 3](#without-a-part-in-page-3)) | `11 E1 00 D5 11 D9 CD D5 11 ED 69 D5 E5 D9 0E A8 ED 60 A4 6F` | In a RAM page, `A4 6F` becomes `2E nn`, `LD L,nn`. `nn` is the value that selects DOS's mapper in page 0, and the restorer writes that value |
| A fixed slot value: `LD A,n / OUT (0A8h),A` or `LD A,n / CALL 013Bh` ([Slot patches](#slot-patches)), with a field of n that names a slot that holds nothing | `3E n D3 A8` or `3E n CD 3B 01` | n becomes the value that [Slot patches](#slot-patches) gives |

The stub stores `TAPION`'s address in RAM, and the game later changes the address's
low byte to E4h for `TAPIN` and F3h for `STMOTR`. So the entries keep the BIOS's low
bytes. A patched call goes to an entry in page 3, and the entry selects DOS's mapper
in page 0 whatever page 0 holds. So the patch also serves a loader that selects the
ROM in page 0 itself, from its own copy of the slot register. A stub that pushes
00EAh, `TAPOON`, writes the tape, and the scan leaves it alone. A patch in code that
ran only during the load is harmless. But a call's 3 bytes can also be data, and
there the patch changes one byte. The search for fixed slot values runs on every
image, with or without the tape service, because a game can select its slots at any
time while it is played.

## Check

`tools/check.py` makes a disk image with `openMSX`'s `diskmanipulator`. The disk
image is a 720 KB image without a partition table, which Nextor reads from its first
sector and MSX-DOS reads as a floppy disk. The disk image holds the `--dos` folder's
files, `SNAPCAS.COM`, the image and an `AUTOEXEC.BAT` that runs `SNAPCAS <GAME>`.
The folder holds `NEXTOR.SYS` and `COMMAND2.COM`, `MSXDOS2.SYS` and `COMMAND2.COM`,
or `MSXDOS.SYS` and `COMMAND.COM`. `snapcas` cannot ship these files.

The check takes these values from `build.txt`, which `build.py` writes beside the
image:

- The tail's address, and the offsets of the tail's bytes that the check reads.
- The area FCC9h to FD88h.
- The bytes that the build patched.
- The tape service's part of page 3.
- The addresses of the tape position and of the tape's end.
- The addresses of the service's two jumps at the tape's end.

So the check judges the image by the build's own decisions and by the `SERVICE.BIN`
that the build used. `tools/tcl/check.tcl` holds none of these numbers. The check
takes the snapshot's registers from `state.txt`. `check.py` boots the machine with
the disk and the `boot` keys, and writes its report to `check/report.txt`:

1. A breakpoint at the tail's last instruction, while the slot register and the
   jump's target are the snapshot's, compares the machine with the snapshot. The
   kept RAM pages, the stored VRAM blocks and the registers must be equal. The
   registers are those of `state.txt`, and the check reads them from the machine
   with the capture's own procedure. The exceptions are the tail's bytes, FCC9h to
   FD88h, the tape service's part of page 3 when the part moved, FFFFh in an
   expanded slot, the patched bytes, R, and PSG register 7's bits 7 and 6. PSG
   register 14, an input whose value is the joystick lines and the cassette signal,
   is an exception too. So are the bits of the worker's page in the subslot register
   of DOS's mapper's slot when that page does not select the slot, and the values
   that the restorer changes for the tape service ([Restorer](#restorer), steps 1
   and 3). The check must find every RAM page of `snap/ram/`, and fails the point
   when it finds fewer. A difference or a timeout fails the check.

   The breakpoint must fire within 120 seconds, or the point fails with the
   screen's text. When the restorer refuses the image, it prints a message and
   returns to DOS, and the point need not wait. A breakpoint at the start of that
   code, `stop_message` in `src/snapcas.asm`, fails the point 2 seconds later, with
   `the restorer stopped:` and the message from the screen. The address comes from
   `out/snapcas.sym`, which `make all` writes, and the breakpoint fires only while
   `SNAPCAS.COM` is the program at 0100h. Without that file, or with the file of
   another assembly than `bin/SNAPCAS.COM`, the check sets no such breakpoint, and
   the point fails after the 120 seconds.
2. The game runs for 60 seconds, and the check saves it with `savestate` every 10
   seconds as `check/10s.oms` to `check/60s.oms`. `openMSX` loads such a savestate
   to show the screen, because it takes screenshots only with a renderer. Meanwhile
   the game must not write the tape service's part of page 3, when the image has
   one. An image without a part in page 3 has nothing to watch, so it passes the
   point. The part's last bytes, from `e_sp` to the stack's top, do not count,
   because the service sets them on each call before it reads them. A watchpoint on
   the part's other addresses notes each write that the game makes there. A write is
   the game's when its code is outside the part, and when the slot register and
   mapper register FFh select the snapshot's page 3. The service's own writes come
   from the part's code, and from the code segment for the manual tape. So a write
   from page 0 does not count while page 0 selects DOS's mapper with the code
   segment or with another segment than the snapshot's. The byte at FCF8h, `E_CODE`,
   names the code segment.

   A write after the service has read the tape to its end does not count either,
   because the game has no more to load then. The check learns that end in two
   ways:

   | The tape's end | How the check learns it |
   |---|---|
   | The tape is at its end at the write, as when the snapshot's tape is there | The check reads the service's tape position and the tape's end from the code segment. The tape counts as read when at most 7 bytes are left, a block's padding |
   | The service reads the tape's last byte after the restore | The automatic tape then goes back to a side's start at once ([Tape service](#tape-service)), so its position no longer shows the end. The check sets a breakpoint at each of the service's two jumps that leave the last side's end, in `wrap` of `src/tape.inc`. One jump is for a tape of one side, and one is for side 2. `build.txt` holds their addresses. From the first such jump on, no write counts |

   Side 1's end of a tape with a side 2 is not the tape's end, so a write after it
   counts. The check restores the image without `/M`, so its tape is the automatic
   tape. The manual tape stops at its last side's end and stays there
   ([The manual tape](#the-manual-tape)), where the first way would find it.

   The report then adds `point 2: fail` and the writes, or else `point 2: pass`, and
   a failed point 2 fails the check. A game that writes the part needs the mode
   without a part in page 3 ([Without a part in page 3](#without-a-part-in-page-3)).
   The point sees only the writes of its 60 seconds, not those that come after a
   key, a level or another side.
3. During the same 60 seconds the restored machine must not reboot. Points 1 and 2
   do not see a reboot. Any of three signs fails the point:

   | Sign | What it shows |
   |---|---|
   | `SNAPCAS.COM` starts again, and the breakpoint at 0100h that reads RAMAD3 fires after the restore | A reset has booted DOS from the check's disk, and its `AUTOEXEC.BAT` runs the restorer again |
   | The screen's text holds `MSX  system` at two or more of the six savestates | The machine stays on the MSX1 BIOS's boot screen, or comes back to it in a loop of resets. `MSX  system` is that screen's first line. A reset on purpose shows the boot screen for a few seconds before the game starts, so a single savestate can catch it. BASIC's banner holds `MSX BASIC` instead, so a BASIC game whose restored screen still holds the banner does not count. The MSX2 BIOS draws its boot screen as graphics, so this sign holds only on an MSX1 |
   | The capture's log holds a reset after the snapshot, less than 60 seconds after it, and the check notes none | The restored game does not do what the loaded one did. The capture goes on for 29 seconds after the moment that it saves for the snapshot ([Capture](#capture), step 5), so its log holds the resets of those seconds. A snapshot at a `TAPION` call's entry is earlier than that moment, so a reset can come later after it |

   The point judges where the machine ends, not the reset, because a loader can
   reset the machine on purpose after the restore and then start the game. A
   breakpoint at the start of the BIOS's reset routine, as in the capture's log
   ([Capture](#capture)), notes each reset in the report with its time. But a reset
   alone does not fail the point. The check reads EXPTBL, for the main ROM's slot,
   when `SNAPCAS.COM` starts, because the BIOS of some machines has not set it when
   the boot steps end. The report adds `point 3: fail` and the sign, or else
   `point 3: pass`, and a failed point 3 fails the check. A hang is not a reboot,
   and point 3 does not see it.
4. During the same 60 seconds the game must not stop at a BASIC error. A BASIC
   program, or a loader written in BASIC, that meets an error prints one of BASIC's
   error messages, such as `Syntax error in 100`. It then waits at `Ok`, in a text
   mode, where `openMSX`'s `screen` reads the message. Points 1 to 3 do not see such
   a stop. So the point fails when the screen's text holds one of those messages at
   one of the savestates. A loader that stops at `Ok` on purpose, and tells the
   player to press F5 or type `RUN`, shows no error message, so it passes. The
   report adds `point 4: fail` and the message, or else `point 4: pass`, and a
   failed point 4 fails the check.

The check passes only when the report holds all four points as passed. `check.tcl`
writes point 1 at the restore and points 2 to 4 together, after the 60 seconds. So a
report that stops after a passed point 1 is one that `openMSX` left. `check.py` then
exits with 2, as it does when `openMSX` ends with another exit status than 0 or by a
signal.

An error of one of `check.tcl`'s callbacks fails the point that the check is at, and
ends the check. The report gets that point as failed, with a line that starts with
`check:` and holds the error. The point is point 1 until `check.tcl` writes that
point's lines, and then point 2, or point 3 or 4 when the error comes from their
code. The check also ends, in the same way, when it has not ended 600 emulated
seconds after its start. It also ends in the same way when a `boot` text or DOS's
prompt does not appear within 120 seconds. `check.py` moves the savestates from
`openMSX`'s home folder to `check/`, and deletes those that a stopped `openMSX`
leaves there.

Neither the scan nor the check sees code that a game builds only when the player
reaches a level. Such code appears as a hang during play, and a trace of that load
in `openMSX` gives the `patch` line.
