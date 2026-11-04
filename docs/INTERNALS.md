# Internals

This page describes each part of `snapcas` step by step: the games run, the tools'
code, the tape files, the capture, the build, the restorer, the tape service and the
check. [DESIGN.md](DESIGN.md) says what each part does and why, in short. The
formats that the parts share are in [FORMATS.md](FORMATS.md), and the games behind
the rules in [NOTES.md](NOTES.md).

## The games run

`make games MACHINE=<machine>` runs `tools/games.py`, which checks that every
shipped game file makes a working image on the machine. It is not part of
`make test`, because it takes hours, and it reads none of the tests' tapes:

1. It looks for each game file's tapes in `downloads/`, where `snap` puts them. It
   downloads nothing, because a download of the whole collection would load
   File-Hunter, one person's site. A game file whose tape is missing gets that as
   its result.
2. It captures, builds and checks each game file, 11 at once by default, because
   `openMSX` keeps about one core busy. The check always runs, with Nextor's files
   unless `DOS=` names others.
3. It writes one line per game file to `out/games/<machine>.txt`: the folder, a tab
   and the first line of the check's report, the failed point with its first line,
   or the failed step's error.
4. It compares the failures with `tests/openmsx-failures.txt`, which lists the game
   files that fail in `openMSX` itself, and exits with 3 when another game file
   fails.

A game file keeps its last result while its inputs are unchanged: its folder, its
tapes, the machine files that it runs on, `bin/` and `tools/`. A cache beside the
results, `<machine>.txt.cache`, holds the inputs' hash of each, and `FULL=1` gives
every game file a new result.

## The tools' code

The commands share their code through modules, and the Tcl that runs inside
`openMSX` is in files of its own:

| File | Holds |
|---|---|
| `tools/gamefile.py` | Reads game files, and lists the game files' folders and their titles. Finds a game's folder from a name below `games/`, such as `ABADIA` or `SUPERMSX/GOLF`, or from a path, and the game's work folder and the place of its image in `images/` |
| `tools/msx.py` | Reads machine files, finds one from its name, and lists the user machines with what each is. Starts `openMSX` with a Tcl script, gives its home folder, where it writes savestates, and makes disk images |
| `tools/cas.py`, `tools/tsx.py`, `tools/tape.py` | The readers of CAS and TSX files, and the tape model and the tape service's tape, which the rest of the code uses ([Tape files](#tape-files)) |
| `tools/patches/` | The automatic patches, one file for each kind, as below |
| `tools/tcl/prelude.tcl` | The procedures that every `openMSX` run gets: reading the screen, passing the boot menu, and typing at DOS's prompt |
| `tools/tcl/memory.tcl` | The procedures that the capture and the check share: EXPTBL, a slot ID's primary slot and subslot, whether page 0 selects a slot, a 16-bit word in memory, the CPU's view of memory with a slot selected, the tests of RAM and of a mapper, and the read of VRAM |
| `tools/tcl/capture.tcl` | The capture's steps ([Capture](#capture)) |
| `tools/tcl/check.tcl` | The check ([Check](#check)) |
| `tools/relocs.py` | The offsets that `build.py` changes to move `SERVICE.BIN`'s page 3 part ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)) |
| `tools/download.py` | The download of a game's tape files from its `url` line, for `snapcas.py snap` ([CLI.md](CLI.md)) |
| `tools/games.py` | The games run of `make games` ([The games run](#the-games-run)) |
| `tools/fetch.py` | The download of the test setup's files |
| `tools/try.py` | The `openMSX` run of `snapcas.py try`, with its window, which types the restorer's command ([CLI.md, Try an image](CLI.md#try-an-image)) |

An automatic patch is a change that the tools make to a game without a line in its
game file. Each kind of automatic patch is one file in `tools/patches/`:

| File | Kind |
|---|---|
| `tape.py` | The calls, stubs and entries of the tape routines, sent to the entries in page 3, and the readers of the cassette signal, which are only listed ([Scan](#scan)) |
| `slots.py` | The fixed slot values that name a slot that holds nothing, the slot map, and the capture's patches of the tape ([Slot patches](#slot-patches)) |
| `slots.tcl` | The capture's watch on the slot register ([Slot patches](#slot-patches)) |
| `ramsearch.py` | The bytes of the loader's RAM search and its patch ([The RAM search patch](#the-ram-search-patch)) |
| `ramsearch.tcl` | The capture's watch for a slot register write that cuts off the code that made it ([The RAM search patch](#the-ram-search-patch)) |

The Python file of each kind has a function, `find(data, context)`, that returns the
kind's findings in data. A finding is the code found, its offset, what it is, and
its patched bytes, and `tools/patches/finding.py` defines it. The context holds the
page of the entries, the slot map, and whether the image has the tape service.
`tools/patches/__init__.py` lists the kinds in the order that the scan runs them,
and holds the two things that all kinds share: the patch of the bytes and the text
of `scan.txt`. So a new kind is a new file and a line in that list. A kind that also
works in the capture has a Tcl file of the same name, which `capture.py` loads after
`capture.tcl`. A kind that works only in the capture has no `find` and is not in the
list, because the loader that it patches has finished by the snapshot. Data that
both files of a kind need, such as the opcodes of [Slot patches](#slot-patches), is
in the Python file only, and `capture.py` writes it into the Tcl settings. A game
file's `patch` lines are not automatic patches, and the build applies them
([FILES.md, Game file](FILES.md#game-file)).

## Tape files

`snapcas` reads two formats of tape file, CAS and TSX. A CAS file holds only blocks
in the format that the BIOS's tape routines read, so a tape whose loader reads its
own format, as a turbo loader does, has no CAS file. A TSX file holds any MSX tape,
the turbo loaders' blocks included ([FORMATS.md, TSX data](FORMATS.md#tsx-data)).

Each format has its own reader, and no other code reads a tape file. A reader turns
a file into the tape model, which the capture, the build, the patches and the check
use:

| File | Holds |
|---|---|
| `tools/cas.py` | The reader of CAS files ([FORMATS.md, CAS data](FORMATS.md#cas-data)) |
| `tools/tsx.py` | The reader of TSX files ([FORMATS.md, TSX data](FORMATS.md#tsx-data)) |
| `tools/tape.py` | The tape model, and the choice of the reader by the file's extension |

The tape model is the file's blocks in tape order, and each block has these fields:

| Field | What it is |
|---|---|
| Kind | Standard: a block that the BIOS's `TAPION` and `TAPIN` read. Non-standard: a block in any other format, such as a turbo loader's |
| Data | The block's bytes |
| Offset | The offset of the data's first byte in the file |
| Time | The seconds at which `openMSX`'s cassette player reaches the block and leaves it, from a TSX file's pulses. A CAS file holds only standard blocks, which the capture follows by `TAPIN`, so its blocks have no time |

`openMSX` plays the file itself, in either format, so the game loads as from its
real tape. The rest works on the model:

1. The load command comes from the type in the first block's 10 bytes: D0h, D3h or
   EAh ([FORMATS.md, CAS data](FORMATS.md#cas-data)). A tape whose first block is
   not standard needs the game file's `load` line.
2. The tape position is an offset in the tape service's tape: the standard blocks,
   each after the 8-byte header `1F A6 DE BA CC 13 7D 74` at an offset that is a
   multiple of 8. A CAS file whose headers are at multiples of 8 has that layout, so
   its positions stay its offsets. The capture follows standard blocks by the
   `TAPION` and `TAPIN` breakpoints, as for a CAS file, and non-standard blocks by
   the player's time: a block is read when `cassetteplayer getpos` passes its end.
3. A patch's place, `side1:` or `side2:` and an offset, is an offset in the tape
   file, of either format, because both formats keep a block's bytes as they are.
   The capture's watches search the files' bytes in the same way
   ([Slot patches](#slot-patches)). A patch in a block whose loader checks a sum
   must fix the sum, as it must in a CAS file.
4. The build writes the standard blocks after the snapshot's position into the tape
   service's tape. A non-standard block after that position is one that the game
   reads with its own loader during play, which the tape service cannot serve, so
   the build stops with an error that names the block, unless the game file has
   `service no`.

### A game later on the tape

A compilation holds several programs on one side, each with its own loader, and a
player reaches a later one by letting the tape run on and typing its load command
again. Engesoft's MSXF-07 has Circus Charlie and then Sky Jaguar on side B. The game
file's `start` line names the later program's first file, and the load starts there:

1. The capture plays a copy of side 1 that begins at the first file with that name,
   with the game file's patch lines applied to the original first, so that their
   offsets and the SHA-1 lines stay those of the downloaded file. The capture's own
   patches ([Slot patches](#slot-patches)) have offsets in the copy, which is the
   file it plays. The build makes the same copy, so the tape service's tape and its
   positions begin there too.
2. A CAS file's copy is the tape service's tape of the blocks from the named file's
   own block on, so its headers are at multiples of 8 even where the original's are
   not, as on the tape with Sky Jaguar. The capture stops with an error when the
   name is not a file's own block, but bytes inside one.
3. A TSX file's copy keeps the file's first 10 bytes and begins at the block that
   holds the file's header. The capture stops with an error when the header is not
   at that block's start.
4. The load command comes from the named file's type, unless the game file has
   `load`. The capture stops with an error when side 1 has no file with that name.

## Capture

`tools/capture.py` runs `openmsx` with the machine file's arguments, or those of the
game file's `capture` machine, and a Tcl script made from the game file, with the
throttle, the renderer and the sound off. All times are emulated seconds, counted
across the rewinds of step 5. The script writes the snapshot to `snap/`, with its
log in `snap/log.txt`, or the log and `snap/error.txt` when a `boot` text or BASIC's
`Ok` does not appear within 120 seconds, the load runs for more than 3,600 seconds,
or step 5 restarts more than 20 times. It performs the following steps:

1. Starts a write watchpoint on port A0h, which keeps the PSG register selected
   last, boots the machine with no disk, presses the `boot` keys, and waits for
   BASIC's `Ok`, then 10 seconds more, as a person would, because a disk system can
   still be busy just after `Ok`.
2. Stops with an error unless the ROM's byte at 002Dh is 0 (MSX1) or 1 (MSX2), and
   reads `EXPTBL` at FCC1h and `EXBRSA` at FAF8h, the slot IDs of the ROMs, once,
   because a game can overwrite page 3. It then removes the disk system from page 3
   with `debug write`. It writes RET (C9h) in every hook from FD9Ah to FFC9h and at
   `EXTBIO`, `DISINT` and `ENAINT`, so that nothing calls the disk system. It writes
   00h at F37Dh, which some loaders read to refuse to run with a disk system. It
   writes zeros from FCC9h to FD88h, `SLTATR` and `SLTWRK`, so that no extension ROM
   claims them and the tape service can use them. It then types `CLEAR200,&HF380`,
   which sets `HIMEM` to a cassette machine's F380h, and writes the slot map
   ([Slot patches](#slot-patches)).
3. Inserts the tape file of side 1, with the game file's `side1` patches written
   into a copy in `snap/`, into the cassette player, notes the slots selected in
   each page, and types the load command for the first header's type
   ([FORMATS.md, CAS data](FORMATS.md#cas-data)): `BLOAD"CAS:",R`, `CLOAD`, or
   `RUN"CAS:"`. After `CLOAD`, it types `RUN` when the motor has stopped for 1
   second. When the game file has `side2` and the game reads past side 1's end, by a
   `TAPION` call at its end or with the motor on there, the capture inserts side 2
   at its start, as a player turns the tape over, and the tape position goes on in
   side 2.
4. Presses the `keys`, and logs these events with their times:
   - The tape position, kept as the tape service would keep it, from breakpoints at
     the addresses that the jump table entries 00E1h and 00E4h jump to, `TAPION` and
     `TAPIN`, while page 0 selects the main ROM.
   - Each slot and subslot selected in a page, from write watchpoints on port A8h
     and on FFFFh, and each write to port A8h that selects a slot that holds nothing
     ([Slot patches](#slot-patches)).
   - Each start and stop of the cassette motor.
   - The start of the BIOS's reset routine, where 0000h's `DI / JP` jumps, while
     page 0 selects the main ROM. A loader can also jump there itself. The capture
     logs the reset and goes on, because a loader can reset the machine on purpose:
     a loader that copies a ROM game into RAM resets it, and the BIOS's search for
     cartridges at the reset finds the copy and starts it. A loader that crashes
     into a reset makes an image of a reboot, which the check's point 2 or point 3
     fails ([Check](#check)).
5. Polls bit 4 of PPI port C, the cassette motor (0 = on), every 0.1 seconds. When
   the motor has been off, or the player has been at the tape's end
   (`cassetteplayer getpos` at least `getlength` minus 0.01), for 1 second, it saves
   the machine with `savestate`. The wait ends when that has lasted 30 seconds and
   the last `keys` time has passed, because a game can pause its own load. With
   `snapshot at`, the capture instead waits for that time and goes to step 6.
   Otherwise it goes back to the saved moment with `loadstate`, and proceeds:
   - If side 1 is read, it goes to step 6. Side 1 is read when the `TAPION` and
     `TAPIN` breakpoints fired and every block after the tape position is under 16
     bytes or equal to a block before it. The tape service's tape pads each block to
     a multiple of 8 bytes, so a block counts as read when at most 7 bytes of it are
     left.
   - Otherwise it tries the game file's `continue` key, then space, then Return,
     each from the saved moment and held for 0.5 seconds, because a loader can read
     the keyboard rarely. If the motor starts within 10 seconds of a key, and the
     tape is not at its end, the load was waiting for that key: the capture logs the
     key and restarts step 5. If no key starts it, the rest is loaded during play,
     and it goes to step 6 from the saved moment.

   `loadstate` restores the machine but neither the script's variables nor its
   timers, so each time the capture also restores its logged state from the saved
   moment and schedules again its polling and the `keys` that come after that
   moment. `loadstate` also removes the watchpoints, though it keeps the
   breakpoints. The capture does not set its watchpoints again, so after the first
   `loadstate` it no longer logs writes to ports A0h and A8h or to FFFFh. Every game
   file passes without them, and setting them again made two game files fail.
6. Takes the snapshot when the CPU next accepts an interrupt while no VDP command is
   running (status register 2, bit 0, is 0) and both VDP latches are empty. A probe
   breakpoint on `z80.acceptIRQ` marks the acceptance, and a breakpoint at the
   handler's address, 0038h in interrupt modes 0 and 1 or the word at I × 256 + FFh
   in mode 2, takes the snapshot there: the return address is pushed and interrupts
   are off. When no such interrupt comes within 1 second, it takes the snapshot
   where the CPU is. It stops with an error when the CPU is then halted, which
   `openMSX` shows as a program counter just after a HALT (76h) that does not move.
   When the game gets the tape service and the CPU is in the BIOS's tape code, T0
   replaces that code, so the snapshot goes back to the last `TAPION` call's entry,
   with the program counter at its jump table entry, 00E1h. The call has not run
   there, so the restored game makes it to the tape service. The CPU is in the tape
   code when the main ROM is in page 0 and the program counter is in 19DDh to 1B44h,
   or is below 4000h with one of the 8 words on top of the stack in that range, as
   in `BREAKX`, which the tape code calls. The capture saves the machine at each
   `TAPION` call's entry for this, and a rewind of step 5 puts back the entry saved
   with its moment.

The game gets the tape service when the `TAPION` and `TAPIN` breakpoints fired and
either side 1 is not read or the game file has `side2`, unless the game file has
`service no`. A load that waits for a choice that no key makes, such as Gauntlet's
joystick choice of players, gets its snapshot at that screen after the key tries of
step 5. The player chooses on the real machine, and the tape service supplies the
rest.

### RAM

The capture reads memory through the CPU's view, the `memory` debuggable, after it
selects a slot in a page with `debug write` on port A8h and, in a slot that `EXPTBL`
marks expanded, on FFFFh while page 3 selects that slot, and writes both back
afterwards. This works for every device, including those that expand their slot
themselves, such as the Carnivore2. The snapshot keeps each page that holds RAM and
was selected at step 3, during the load or at the snapshot. The capture reads these
pages first and tests them afterwards, so a write that switches a ROM's bank or
overwrites a segment changes nothing it keeps:

- A page holds RAM when the byte at its first address takes a written value and its
  complement.
- A RAM page is in a mapper when two different marker bytes, written at its first
  address under two values of its mapper register, each read back under their own
  value after both are written.
- The mapper's size comes from the count that the restorer uses under MSX-DOS 1
  ([Restorer](#restorer), step 2). A page's segment is its mapper register's value
  modulo that size.

### Slot patches

A game that writes a fixed value to the slot register expects its RAM in the slots
of the machine that it was written for. Sootland writes FCh, for RAM in slot 3, and
crashes on the Sanyo PHC-28S, whose slot 3 holds nothing. The capture finds such
writes itself and patches each value to the slots that hold the machine's RAM, so
that no game file needs a line for them. It does this in four parts:

1. At step 3, before it types the load command, the capture tests each page of each
   primary slot, and of each subslot of an expanded slot, and writes the slot map,
   `snap/slots.txt`. A page holds RAM by the test of [RAM](#ram). A page holds
   nothing when it does not hold RAM and its first 256 bytes all read FFh.
2. A value's field for a page names a slot. When that slot holds nothing in the
   page, the patch replaces the field with the slot that the table below gives. A
   field that names a slot that holds RAM or ROM stays. An expanded slot never
   counts as holding nothing, because its subslot register belongs to the game, and
   it counts as RAM in a page when the subslot that its register selects there at
   step 3 holds RAM. A field with no RAM slot for its page stays, and the write is
   only logged.
3. At step 4, the write watchpoint on port A8h tests each value against the slot
   map. A value whose field names a slot that holds nothing makes the capture log
   the write, the address of its `OUT` and the new value. When the code that set the
   value is one of the forms in the second table below, and its bytes with the 8
   bytes before them, or else with the 8 bytes after them, occur once in a tape
   file, the capture stops. The bytes after them serve a loader that copies a
   routine to RAM without the bytes before it, as Sootland's does. `capture.py` then
   adds a patch of n on the tape to `snap/patches.txt` and runs the capture again
   from step 1, up to 16 times. Otherwise the capture goes on, and the logged write
   is for a `patch` line by hand.
4. The build's scan ([Scan](#scan)) looks for the same code with such a value in the
   snapshot's RAM pages and in the tape's unread blocks, for code that runs only
   while the game is played.

| Page | The slot that replaces one that holds nothing |
|---|---|
| 2 or 3 | The slot that BASIC selects in that page at step 3 |
| 0 or 1 | The slot that holds RAM in that page. Of several, the slot of page 2 at step 3 when it holds RAM there, or else the lowest |

The patches in `snap/patches.txt` change the tape after the game file's `patch`
lines, and `build.py` applies them as well, so the tape service serves the tape that
the capture loaded.

The watch and the scan know two forms of the code that sets a fixed value:

| Code | Bytes | Where the watch finds it |
|---|---|---|
| `LD A,n / OUT (0A8h),A` | `3E n D3 A8` | Its last byte is the last byte of the write's `OUT` |
| `LD A,n / CALL 013Bh`, a call of the BIOS's `WSLREG`, which writes A to the slot register | `3E n CD 3B 01` | When the write's `OUT` is in the main ROM, its last byte is the byte before the return address on top of the stack. The capture reads that address in the slot that page 3 selected before the write, because the write can change page 3 |

The bytes of a form can also be the end of a longer instruction, whose operand a
patch of n would change. So the watch and the scan skip code whose `3E` can be an
operand:

| Byte | Opcodes |
|---|---|
| The byte before `3E` | Those of an instruction with a one-byte operand: `06 0E 16 1E 26 2E 36 3E C6 CE D6 DE E6 EE F6 FE D3 DB 10 18 20 28 30 38`, or with a two-byte operand, as below |
| The second byte before `3E` | Those of an instruction with a two-byte operand: `01 11 21 31 22 2A 32 3A C2 C3 C4 CA CC CD D2 D4 DA DC E2 E4 EA EC F2 F4 FA FC` |

A real `LD A,n` after an operand that has the value of such an opcode is skipped as
well, and needs a `patch` line by hand.

### The RAM search patch

Some loaders search for RAM in pages 0 and 1 themselves, from code in page 3. Mot's
loader tries each slot ID from 15 down to 0 through the BIOS's `WRSLT` and `RDSLT`,
and marks each ID from 4 up as the ID of an expanded slot. To select the slot that
it finds, the loader writes the slot's subslot register at FFFFh, so it selects that
primary slot in page 3, where its own code runs. That works when the RAM of page 3
is in the same primary slot, as on the VG-8020, whose RAM is all in slot 3. On the
Sanyo PHC-28S, the RAM of page 3 is in slot 0 and the HBM-64's RAM is in slot 1, so
the loader's code is gone after the write. The capture finds this itself, in two
parts:

1. At step 4, the write watchpoint on port A8h tests each write from code in page 3
   that selects another primary slot in page 3. When the 4 bytes after the write's
   `OUT` differ in that slot, the write cuts off the code that made it, and the
   capture logs it.
2. When the loader's search, below, occurs in the tape files, the capture stops.
   `capture.py` then adds a patch of each copy to `snap/patches.txt` and runs the
   capture again, as for a slot patch. Each copy cuts off its code on this machine,
   and a copy on side 2 or in a compilation's later game runs after the snapshot.
   The patched loader selects the slot that it finds through the slot register only.
   Otherwise the logged write is for a `patch` line by hand.

| Code | Bytes | Patch |
|---|---|---|
| `LD A,B / DEC A / CP 4 / JR C,+2 / SET 7,A`: the slot ID from the search's count, with the expanded slot's mark from 4 up | `78 3D FE 04 38 02 CB FF` | `SET 7,A` to two `NOP`s, `00 00` |

A machine whose RAM for page 3 is in the same primary slot never gets the patch,
because the write keeps the loader's code.

### Page 3's slot for the other pages

Many loaders take for granted that the slot of page 3's RAM also holds RAM in pages
0 to 2, as it does on a machine with 64 KB in one slot, such as the Philips VG-8020.
On a machine whose RAM is in several slots, such a loader copies the game into the
ROM or into a subslot that the other pages do not select, and the game crashes into
a reset, or starts in BASIC's ROM, which stops at an error ([Check](#check), point
4).

The loaders take many forms, so their fixes are lines in the game files: most often
a capture without the Carnivore2, or a patch of the slot value. The capture's own
patches cover the forms that repeat over many tapes ([Slot patches](#slot-patches),
[The RAM search patch](#the-ram-search-patch)). The forms seen so far, and their
games, are in [NOTES.md](NOTES.md#page-3s-slot-for-the-other-pages).

## Build

`tools/build.py` writes the image ([DESIGN.md, Formats](DESIGN.md#formats)). It:

- Stores each 16 KB block of `vram.bin`, as a block of zeros when it holds only
  zeros, and each RAM page, once for a segment that two pages select.
- Turns the PSG, PPI and VDP state into a list of port writes, in the order that the
  restorer performs them ([FORMATS.md, Port writes](FORMATS.md#port-writes)).
- Writes the tail, from `SERVICE.BIN`, into the 26 bytes below the stack pointer. At
  an interrupt's entry these bytes are free, because the handler that runs next
  pushes onto them. When they cross a page boundary, the tail goes into the 26 bytes
  below that boundary instead, which are further below the stack pointer and as
  free. It stops with an error when the bytes go below 0000h, include FFFFh, or are
  not in a RAM page that the snapshot keeps.
- Finds the RAM page that the snapshot selects in a page by its slot, and in a
  memory mapper also by the segment that the page's mapper register selects, because
  a game can select one segment in two pages.
- Applies the patches of `snap/patches.txt` to the tape, and runs the scan's search
  for slot values on every image ([Slot patches](#slot-patches)).
- With the tape service, builds T0, the code segment and the other tape segments
  from `rom.bin`, the tape files and `SERVICE.BIN`, writes the service's part of
  page 3 into the game's page 3, with the snapshot's value of mapper register FCh at
  FCF9h, runs the scan, and applies the scan's patches and the `patch` lines
  ([Tape service](#tape-service)). When no part of page 3 has room for the service's
  part, it uses the mode without a part in page 3, as `service t0` does
  ([Without a part in page 3](#without-a-part-in-page-3)). It stops with an error
  when the service's part of page 3 holds the tail, or when the code segment and the
  tape need more than 64 segments.
- Puts the service's part of page 3 at FCE1h when FCC9h to FD88h are zero at the
  snapshot, as the capture leaves them. A game can use that area itself. The part
  then goes to xxE1h of the highest page xx below the BIOS's work area at F380h
  whose 168 bytes from there are zero, or to the game file's `service at`. Zeros at
  the snapshot can still be a buffer that the game fills later, so a moved part is
  checked by playing to the game's next load. The part moves by its page alone: the
  entries keep their low bytes, E1h to F3h, and the scan's patches write xxh instead
  of FCh. `build.py` adds xx minus FCh to each byte that `SERVICE.BIN`'s last part
  lists, and writes xx in the image's header
  ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)).
- Prints the most mapper segments that the image can require.

It stops with an error when the version byte of `SERVICE.BIN` is not the one it
expects.

## Restorer

`SNAPCAS.COM` runs under MSX-DOS 1, MSX-DOS 2 or Nextor. Its code and data stay
below 4000h, and it holds the worker twice, assembled to run in pages 1 and 2. It
keeps DOS's stack, in page 3, because MSX-DOS 2's mapper routines page the DOS
kernel into page 0. It uses a stack in page 0 only while it selects another slot in
page 3, and the worker keeps its own stack in its own page. Under MSX-DOS 2 and
Nextor, it selects segments in pages 1 and 2 with `PUT_P1` and `PUT_P2`, and learns
DOS's segments with `GET_P0` to `GET_P3`. Under MSX-DOS 1, it writes the mapper
registers, and DOS's segments are 3, 2, 1 and 0. It performs the following steps,
and until step 4 it can stop with a message and return to DOS:

1. Opens `<GAME>.SNP`, whose name DOS has placed in the FCB at 005Ch, with the
   extension set to SNP. Without a name, it prints its usage. It reads the image's
   first 4,096 bytes with the FCB functions `_FOPEN`, `_SETDTA` and `_RDBLK`, and
   checks:
   - That the image starts with `SNAPCAS` and the format's number of this
     `SNAPCAS.COM` ([FORMATS.md, Image](FORMATS.md#image)). An image with another
     number gets a message that it was made for another version of `SNAPCAS.COM`.
   - That `RAMAD0` to `RAMAD3` name one slot, DOS's mapper.
   - That the CRC-16 of the main ROM and of the sub-ROM equal the image's. The
     worker reads them in page 2, with pages 0 and 1 selecting the ROM.
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
   - With the tape service, that no RAM page kept for page 0 is in DOS's mapper's
     primary slot with another subslot.
   - That each record's segment is within DOS's mapper's size.
2. Allocates every free segment of DOS's mapper: under MSX-DOS 2 and Nextor with
   `ALL_SEG` until it fails, and under MSX-DOS 1, segments 4 and up. MSX-DOS 1 gives
   no count, so, with interrupts off and through page 2, the restorer saves the
   first byte of segments 0 to 3, writes each segment's number into its first byte
   from 255 down to 0, reads them back from 4 up to the first mismatch, and restores
   the saved bytes. It then assigns the segments:
   - A RAM page of DOS's mapper whose own segment is free, or is DOS's segment in
     page 1 or 2, goes straight into it.
   - Each other RAM page of DOS's mapper gets a holding segment, copied into its own
     segment in step 6.
   - Each service segment gets one of the segments left, and so does the worker,
     which the restorer copies into its segment.

      It stops when there are too few, naming the segments needed and free.
3. Reads the records in this order, through the FCB's random record field: the RAM
   pages of slots other than DOS's mapper, the VRAM blocks, the service segments,
   and the RAM pages of DOS's mapper. It places each one:
   - A RAM page of another slot is read into page 2, or into page 1 for a target in
     page 2. The worker selects the target slot in the target page, with only that
     page's bits of the subslot register changed, sets the page's mapper register to
     the record's segment when it has one, copies the page, reads it back, and
     selects DOS's pages again, all with interrupts off. The worker runs in page 1,
     with its stack there, for a target in page 0. The restorer itself copies to
     pages 1 to 3. In an expanded slot, the copy of page 3 stops at FFFEh, because
     FFFFh is the subslot register. A mismatch stops the restorer: the machine file
     does not describe this machine.
   - A VRAM block is read into page 2 and written to the VDP through ports 98h and
     99h and register 14, with interrupts off and the display blanked by writing
     register 1 with `RG1SAV`'s value, bit 6 clear and bit 7 from the snapshot's
     value. That bit makes the VDP map VRAM as the game does: bit 7 of a TMS9918's
     register 1 chooses its 4 KB or 16 KB mapping (TMS9918A data book, register 1).
     The other bits stay DOS's, because a game's bit 5 of 0 turns off the VDP's
     interrupt, and DOS needs that interrupt between the blocks. A block of zeros is
     written without a read. DOS's text mode has no planar layout, so the bytes go
     to VRAM as stored.
   - A service segment or a RAM page of DOS's mapper is read into its segment
     through page 1 or 2.

   As the records arrive, it fills in the values that depend on the real machine, in
   the records and in the registers that step 6 writes:
   - In the tail: the worker's page's mapper register and its value, and the slot
     register ([FORMATS.md, Tail](FORMATS.md#tail)).
   - With the tape service, in the code segment at 001Ah: the code segment, then the
     other tape segments, and at 006Ah: 1 for `/M`, or otherwise 0.
   - With the tape service, in the game's page 3 at FCF6h: DOS's mapper's slot ID,
     T0's segment and the code segment.
   - With the tape service, when DOS's mapper is in an expanded slot, DOS's mapper's
     subslot in the page 0 bits of that slot's subslot register, and in `SLTTBL` in
     the game's page 3, so that the entry code can select T0.
   - With the tape service, T0 replaces the ROM when the snapshot's page 0 selects
     the main ROM, no RAM page kept for page 0 is in DOS's mapper, and the game file
     has no `rom keep` line. Page 0's slot then becomes DOS's mapper, and mapper
     register FCh and the byte at FCF9h become T0's segment.
4. Waits until `JIFFY` has advanced by 180, so that a floppy drive's motor stops,
   then disables interrupts. From this point on, it calls neither DOS nor the BIOS.
5. Performs the port writes.
6. The worker, in the page that step 1 found, with its stack in its own segment,
   copies each holding segment into its own segment through the two other pages
   below page 3. It then writes the subslot register of each expanded slot while
   page 3 selects that slot, ending with the snapshot's page 3 slot, the mapper
   registers of the three other pages, and the slot register with its own page still
   selecting DOS's mapper. It loads every register except AF and SP, sets I and the
   interrupt mode, and jumps to the tail.
7. The tail writes the worker's page's mapper register, the slot register and, when
   step 1 chose it, the subslot register of DOS's mapper's slot, loads AF and SP,
   enables interrupts when IFF1 is set, and jumps to the program counter. The R
   register is not restored.

## Tape service

The tape service keeps the tape in service segments, and has these parts:

| Part | Location | Function |
|---|---|---|
| T0 | A service segment | The BIOS's page 0 with the service's stubs from 19DDh to 1B44h |
| Code segment | A service segment | The routines, the tape position and the table of the tape's segments, then the start of the tape |
| Tape data | The code segment, then the other service segments | Side 1, padded with zeros to a multiple of 8 bytes, by at least 1 byte when side 2 follows, then side 2 |
| Entries | FCE1h to FCF5h, in `SLTATR`, unless the part moved ([Build](#build)) | One for each entry of the BIOS's tape jump table, from 00E1h to 00F5h, for code that goes around T0 |
| Entry code | `SLTWRK`, after its data at FCF6h to FCFBh | Selects T0 in page 0, calls the routine, and selects the game's page 0 again |
| Trampoline | `SLTWRK` | Selects the code segment in page 0, calls a routine there, and selects T0 again |
| Reader | `SLTWRK` | `OUT (C),D / LD E,(HL) / OUT (C),B / RET`: reads a tape byte |

`build.py` builds T0 from `rom.bin`, so it first checks that each jump table entry
below jumps to its address, as in the standard MSX BIOS. The restorer's ROM check
ensures that the real ROM equals `rom.bin`.

The addresses are in [FORMATS.md, T0's jump table](FORMATS.md#t0s-jump-table).

T0's stubs keep these addresses and leave the rest of the 360 bytes from 19DDh to
1B44h free. `build.py` also points the jump table entry 00F3h, `STMOTR`, at its
stub, because the BIOS's code, at 1384h on an MSX1 and 1387h on an MSX2, is outside
that range. The stubs of `TAPION` and `TAPIN` call the code segment's routines
through the trampoline, which is in page 3 because it changes page 0. The routines
behave as the BIOS's: carry is clear on success and set when CTRL+STOP is held.

| Routine | What it does |
|---|---|
| `TAPION` | Disables interrupts and moves the tape position past the next CAS header at a multiple of 8 bytes |
| `TAPIN` | Disables interrupts, returns the byte at the tape position in A, and advances the position |
| `TAPIOF` | Stops the manual tape ([The manual tape](#the-manual-tape)), enables interrupts and returns |
| `TAPOOF` | Enables interrupts and returns |
| `TAPOON`, `TAPOUT` | Return with carry set: the tape cannot be written |
| `STMOTR` | Stops the manual tape when A is not 1, and returns |

The code segment holds the service's data, its routines and then the tape, which
starts at a multiple of 8 bytes
([FORMATS.md, The code segment](FORMATS.md#the-code-segment)).

`TAPIN` reads a byte through the reader in page 3: with C = FCh, D the byte's
segment and B the code segment, the reader selects the byte's segment in page 0,
reads the byte at HL into E, and selects the code segment again. The entry code
disables interrupts, switches to its own stack in `SLTWRK`, selects DOS's mapper and
T0 in page 0, calls the routine, and selects the game's page 0 and stack again, with
mapper register FCh set to the value at FCF9h. It returns with interrupts off,
except after `TAPIOF` and `TAPOOF`.

Each entry is a `CALL` to the entry code, 3 bytes long, so the entries have the low
bytes of the jump table's entries, E1h to F3h. The entry code finds the routine from
its return address's low byte, and a game that changes the low byte of a call, from
`TAPION` to `TAPIN` and then `STMOTR`, reaches the matching entry. The entry code
keeps its data before its code
([FORMATS.md, The entry code's data](FORMATS.md#the-entry-codes-data)).

The tape position starts where the game stopped reading at the snapshot, and moves
on these events. The routines read the keyboard matrix through the PPI.

| Event | Automatic tape, the default | Manual tape, with `/M` |
|---|---|---|
| `TAPION` or `TAPIN` reads past side 1's end | Side 2's start, as when the player turns the tape over, or side 1's start when there is no side 2 | The tape stops at that end and waits for the player's key ([The manual tape](#the-manual-tape)) |
| `TAPIN` reads in side 1's padding before side 2 | Side 2's start, and `TAPIN` returns FFh: the padding is not on the tape, and the read that waits while the player turns the tape over returns FFh in `openMSX`, which loaders expect | The tape stops at side 1's end. After RETURN, the position is side 2's start and `TAPIN` returns FFh |
| `TAPIN` reads at a multiple of 8 where a CAS header is | The byte after the header, because a header is a tone on the tape, which `TAPIN` waits through, as when a game reads on into the next block or side | The same |
| `TAPION` or `TAPIN` reads past side 2's end | Side 2's start, as after a rewind | The tape stops at that end and waits for the player's key |
| `TAPION` or `TAPIN` is called while the tape is stopped | The automatic tape never stops | The tape waits for the player's key |
| `TAPION` is called while GRAPH is held | Side 1's start | Side 1's start, at any read that waits |
| `TAPION` is called while CODE is held | Side 2's start, or side 1's start when there is no side 2 | The same, at any read that waits |

The service shows a move of the tape with one flash of a colour over the whole
screen for 0.1 second. GRAPH and CODE, and the automatic tape when it reaches side 2
or goes back to a side's start, flash the colour of the side that the position moves
to. RETURN on the manual tape flashes its own colour when the tape plays on, also
when RETURN turns the tape over to side 2. The flash sets the border colour and
blanks the display, which then shows only the border, because the border alone is
thin and many screens crop it. Side 2 starts at side 1's end, so a read that reaches
side 2 changes only the side at 005Eh, and that change shows the flash. The service
counts the frames by the frame flag in the VDP's status register 0, then writes the
game's VDP registers 7 and 1 back and goes on. The VDP's registers cannot be read,
so the service takes the game's values from the addresses at 005Ah and 005Fh in the
code segment. The colours are these:

| Outcome | Border |
|---|---|
| Side 1's start | Light green, 3 |
| Side 2's start | Light red, 9 |
| RETURN plays on | Light yellow, 11 |

### The manual tape

By default the tape is automatic: it turns over and rewinds by itself, and the
player needs no key. With `/M`, the tape service moves the tape only when the player
asks, as a real tape moves only after the player presses PLAY, so the player follows
what the game says on the screen. The manual tape stops in these cases, and the byte
at FCFBh records it:

- The game stops the motor, with `TAPIOF`, or with `STMOTR` and A other than 1.
- `TAPION` finds the motor off in PPI port C bit 4, because the game stopped it
  without the service: through the BIOS in ROM, or with its own write to the port.
  `TAPION` then starts the motor, as the BIOS's does.
- A read reaches side 1's end or side 2's end.
- The motor is off at the snapshot, which `build.py` reads from PPI port C bit 4.

While the motor runs, between the blocks of one load, the tape plays on and no read
waits. A read that finds the tape stopped waits for one of these keys, which it
reads in the keyboard matrix through the PPI:

| Key | The tape |
|---|---|
| RETURN | Plays on from where it stopped. At side 1's end with a side 2, it goes on at side 2's start, as when the player turns the tape over. At side 2's end, or at side 1's end without a side 2, it waits on, because the tape holds nothing more |
| GRAPH | Goes to side 1's start, as after a rewind |
| CODE | Goes to side 2's start, or to side 1's start when there is no side 2 |
| CTRL+STOP | The routine returns with carry set, as the BIOS's does, and the tape stays stopped |

After GRAPH or CODE, the read that waited starts again at the new place, as a read
does after a real rewind. So `TAPION` looks for a header from there, and `TAPIN`
skips the header there and returns the byte after it.

A key that is held when the read starts acts at once. So one press can answer both a
game's own prompt and the tape: for "rewind the tape and press a key", the player
presses CODE as the game's key and holds it until the game reads. The read goes on
only when the key is released, so the game does not read it.

The manual tape's code takes 141 bytes more than T0's 360, so in the mode without a
part in page 3 the tape stays automatic. With `/M`, `SNAPCAS` then says so before
the restore, as it does for a game without the tape service, and goes on.

### Without a part in page 3

A game can use all of its page 3 over time, as Moonwalker does: its main game loads
its code into FCC9h to FD88h, and no 168 bytes of its page 3 stay free from one load
to the next. For such a game, the game file's `service t0` puts the whole tape
service into T0, and nothing of it stays in page 3. `build.py` also takes this mode
itself when no part of page 3 has room at the snapshot, so a game file needs
`service t0` only for a game whose page 3 is free at the snapshot but not in a later
load, as Moonwalker's is. The line goes in the game file of each machine that needs
it: Moonwalker's is in `phc28s-ram64k-carnivore2.txt`. The service's part of page 3
exists only because the service switches page 0 while it runs, so this mode removes
the three switches:

| Switch | Without a part in page 3 |
|---|---|
| The entry code selects T0 in page 0 | The game reaches T0 by slot. T0 stays in mapper register FCh for good, so page 0 shows T0 whenever the game selects DOS's mapper there, and T0's jump table, from 00E1h to 00F3h, is the only set of entries. When the snapshot has the ROM in page 0, the restorer selects T0 there instead, by the default mode's rule ([Restorer](#restorer)), so that BASIC's own `BLOAD` reaches T0 |
| The trampoline selects the code segment | The routines run in T0: they, the tape position, the table of the tape's segments and the flash's data take the 360 bytes from 19DDh to 1B44h, which an assertion in `src/service.asm` checks. `src/tape.inc` holds the routines, which `service.asm` assembles in the code segment and in T0, and `build.py` points T0's jump table at T0's copy |
| The reader selects the tape's segments in page 0 | `TAPIN` reads through page 2 or page 1, which `build.py` chooses: the first that is a page of a mapper at the snapshot, or else page 2. With interrupts off, it keeps the slot register's value in T0, selects DOS's mapper's slot in that page through the slot register and the byte's segment through FEh or FDh, reads the byte, and writes back the slot register and the snapshot's segment. It uses no stack meanwhile, so the page can hold the game's stack. A game whose RAM is in a slot without a mapper can also lend its page. When the capture has no mapper at all, as a capture variant without the Carnivore2 has none, the game lends page 2, and `TAPIN` writes back segment 0, which only DOS's mapper sees |

The tape takes at most 16 segments, 256 KB, and starts at the first tape segment.
`TAPIOF` and `TAPOOF` enable interrupts, as the BIOS's do. The keys and the flash
work as in the default mode.

A game can use the mode only when these hold at the snapshot. Otherwise `build.py`
stops with an error, or the restorer with a message for the last condition:

| Condition | Why |
|---|---|
| No RAM page kept for page 0 is in DOS's mapper | T0 takes the game's mapper register FCh for good |
| The game file has no `rom keep` | With `rom keep` the ROM stays in page 0, and this mode has no entries in page 3, so the game's tape calls reach the BIOS's own routines and not T0 |
| When the borrowed page is in DOS's mapper, the game keeps its segment there from then on | `TAPIN` writes back the snapshot's segment |
| When DOS's mapper's slot is expanded, the snapshot's subslot register of that slot selects the mapper in the borrowed page | The slot register alone then selects the mapper there. The restorer checks this, because only it knows DOS's mapper's slot. When the capture did not have that slot expanded, as a capture variant without the Carnivore2 does not, the game never wrote its subslot register, so the restorer sets the borrowed page's bits there to the mapper's subslot instead |

Code that selects the ROM in page 0 itself and then calls the tape reaches the ROM,
not T0, so the scan only lists its findings in this mode, and the game file sends
that code to T0 with `patch` lines that make it select DOS's mapper in page 0. A
game that writes FCh itself loses T0.

The restorer allocates T0 and the tape's segments as in the default mode, writes the
table of the tape's segments and DOS's mapper's slot for the borrowed page into T0,
and sets mapper register FCh to T0's segment, with DOS's mapper's subslot in the
page 0 bits of its slot's subslot register and of `SLTTBL`. It writes nothing into
the game's page 3. Bit 1 of the image's flags marks the mode
([FORMATS.md, Image](FORMATS.md#image)).

### Scan

With the tape service, `build.py` scans the snapshot's RAM pages and the unread
blocks of both sides for code that reaches the tape without going through T0, and
lists each finding in `scan.txt`, in a `patch` line's form, so that a finding in an
unread block can be copied into the game file. A RAM page that the snapshot does not
select in its page is named by its file in `ram/`. The scan runs after the game
file's `patch` lines, and it patches the findings in the RAM pages. In an unread
block it only lists them, for `patch` lines, because a loader usually checks a block
against a sum stored at the block's end, and each loader computes that sum in its
own way. The scan looks for this code:

| Code | Bytes | Patch |
|---|---|---|
| A stub built with `TAPION`'s entry: `LD DE,00E1h / PUSH DE / LD DE,CDD9h / PUSH DE`, or the same with HL | `11 E1 00 D5 11 D9 CD D5`, or `21 E1 00 E5 21 D9 CD E5` | `E1 00` becomes `E1 FC` |
| A call of a tape routine: `CALL 00E1h`, `CALL 00E4h`, `CALL 00E7h` or `CALL 00F3h`, `STMOTR`, which the manual tape needs for Gauntlet's stops ([The manual tape](#the-manual-tape)) | `CD E1 00`, `CD E4 00`, `CD E7 00` or `CD F3 00` | The call's `00` becomes `FC` |
| An entry in HL before a call: `LD HL,00E1h` or `LD HL,00E4h`, then `CALL`, to a routine of the game's that selects the ROM in page 0 and jumps to HL | `21 E1 00 CD` or `21 E4 00 CD` | The `00` becomes `FC` |
| A reader of the cassette signal: `IN A,(0A2h)`, then within 4 bytes `RLA`, `RLCA`, `BIT 7,A` or `AND 80h` | `DB A2`, then `17`, `07`, `CB 7F` or `E6 80` | None: listed, for a `patch` line that sends its callers to the service |
| A reader of PSG register 14, whose bit 7 is the cassette signal and whose other bits are a joystick: `LD A,0Eh / OUT (0A0h),A / IN A,(0A2h)` | `3E 0E D3 A0 DB A2` | None: listed, as above, and also found in joystick code |
| A fixed slot value: `LD A,n / OUT (0A8h),A` or `LD A,n / CALL 013Bh` ([Slot patches](#slot-patches)), with a field of n that names a slot that holds nothing | `3E n D3 A8` or `3E n CD 3B 01` | n becomes the value that [Slot patches](#slot-patches) gives |

The stub stores `TAPION`'s address in RAM, and the game later changes its low byte
to E4h for `TAPIN` and F3h for `STMOTR`, so the entries keep the BIOS's low bytes. A
patched call goes to an entry in page 3, which selects T0 in page 0 whatever page 0
holds. So the patch also serves a loader that selects the ROM in page 0 itself, from
its own copy of the slot register. A stub that pushes 00EAh, `TAPOON`, writes the
tape, and the scan leaves it alone. A patch in code that ran only during the load is
harmless, but a call's 3 bytes can also be data, where the patch changes one byte.
The search for fixed slot values runs on every image, with or without the tape
service, because a game can select its slots at any time while it is played.

## Check

`tools/check.py` makes a disk image with `openMSX`'s `diskmanipulator`: a 720 KB
image without a partition table, which Nextor reads from its first sector and
MSX-DOS reads as a floppy disk. It holds the `--dos` folder's files, `SNAPCAS.COM`,
the image and an `AUTOEXEC.BAT` that runs `SNAPCAS <GAME>`. The folder holds
`NEXTOR.SYS` and `COMMAND2.COM`, `MSXDOS2.SYS` and `COMMAND2.COM`, or `MSXDOS.SYS`
and `COMMAND.COM`, which `snapcas` cannot ship. The check takes the bytes that the
build patched, the tape service's part of page 3 and `C_POS`'s address from
`build.txt`, which `build.py` writes beside the image, so that it judges the image
by the build's own decisions and by the `SERVICE.BIN` that the build used.
`check.py` boots the machine with that disk and the `boot` keys, and writes its
report to `check/report.txt`:

1. A breakpoint at the tail's last instruction, while the slot register and the
   jump's target are the snapshot's, compares the machine with the snapshot. It must
   fire within 120 seconds, and the report then holds the screen's text, which shows
   a message of the restorer: the kept RAM pages, the stored VRAM blocks and the
   registers must be equal. The exceptions are the tail's bytes, FCC9h to FD88h, the
   tape service's part of page 3 when it moved, FFFFh in an expanded slot, the
   patched bytes, R, PSG register 7's bits 7 and 6, PSG register 14, an input whose
   value is the joystick lines and the cassette signal, the bits of the worker's
   page in the subslot register of DOS's mapper's slot when that page does not
   select the slot, and the values that restorer step 3 changes for the tape
   service. A difference or a timeout fails the check.
2. The game runs for 60 seconds, saved with `savestate` every 10 seconds as
   `check/10s.oms` to `check/60s.oms`. `openMSX` loads such a savestate to show the
   screen, because it takes screenshots only with a renderer. Meanwhile the game
   must leave the tape service's part of page 3 alone, when the image has one. The
   part's last bytes, from `e_sp` to the stack's top, do not count, because the
   service sets them on each call before it reads them. A watchpoint on the part's
   other addresses notes each write that the game makes there: from code outside the
   part, while `E_INSIDE` is 0, so outside a call of the service, and while the slot
   register and mapper register FFh select the snapshot's page 3. A write after the
   service has read the tape to its end does not count either, because nothing calls
   the service then: the check reads the service's tape position, `C_POS`, and the
   tape's end, `C_TOTAL`, from the code segment that `E_CODE` names, and the tape is
   read when at most 7 bytes are left, a block's padding. The report then adds
   `point 2: fail` and the writes, or else `point 2: pass`, and a failed point 2
   fails the check. A game that writes the part needs the mode without a part in
   page 3 ([Without a part in page 3](#without-a-part-in-page-3)). The point sees
   only the writes of its 60 seconds, not those that come after a key, a level or
   another side.
3. During the same 60 seconds the restored machine must not reboot. Points 1 and 2
   do not see a reboot. Any of three signs fails the point:

   | Sign | What it shows |
   |---|---|
   | `SNAPCAS.COM` starts again: the breakpoint at 0100h that reads RAMAD3 fires after the restore | A reset has booted DOS from the check's disk, and its `AUTOEXEC.BAT` runs the restorer again |
   | The screen's text holds `MSX  system` at two or more of the six savestates | The machine stays on the MSX1 BIOS's boot screen, whose first line that is, or comes back to it in a loop of resets. A reset on purpose shows the boot screen for a few seconds before the game starts, so a single savestate can catch it. BASIC's banner holds `MSX BASIC` instead, so a BASIC game whose restored screen still holds the banner does not count. The MSX2 BIOS draws its boot screen as graphics, so this sign holds only on an MSX1 |
   | The capture's log holds a reset in the 60 seconds after the snapshot, and the check notes none | The restored game does not do what the loaded one did |

   The point judges where the machine ends, not the reset, because a loader can
   reset the machine on purpose after the restore and then start the game. A
   breakpoint at the start of the BIOS's reset routine, as in the capture's log
   ([Capture](#capture)), notes each reset in the report with its time, but a reset
   alone does not fail the point. The check reads EXPTBL, for the main ROM's slot,
   when `SNAPCAS.COM` starts, because the BIOS of some machines has not set it when
   the boot steps end. The report adds `point 3: fail` and the sign, or else
   `point 3: pass`, and a failed point 3 fails the check. A hang is not a reboot,
   and point 3 does not see it.
4. During the same 60 seconds the game must not stop at a BASIC error. A BASIC
   program, or a loader written in BASIC, that meets an error prints one of BASIC's
   error messages, such as `Syntax error in 100`, and waits at `Ok`, in a text mode,
   where `openMSX`'s `screen` reads it. Points 1 to 3 do not see such a stop, so the
   point fails when the screen's text holds one of those messages at one of the
   savestates. A loader that stops at `Ok` on purpose, and tells the player to press
   F5 or type `RUN`, shows no error message, so it passes. The report adds
   `point 4: fail` and the message, or else `point 4: pass`, and a failed point 4
   fails the check.

Code that a game builds only when the player reaches a level is not visible to the
scan or to the check. It appears as a hang during play, and a trace of that load in
`openMSX` provides the `patch` line.
