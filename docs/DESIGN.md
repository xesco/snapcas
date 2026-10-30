# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX1 or MSX2. `openMSX` loads
the game from its CAS file, in its own cassette player, on a copy of the user's
machine, and `snapcas` saves the machine's state when the game is ready. On the real
machine, the restorer, `SNAPCAS.COM`, restores that state and transfers control to
the game. A game that loads further data during play also receives a tape service,
which supplies the rest of the tape from memory. The build steps and their tests are
in [PLAN.md](PLAN.md).

## Terms

| Term | Meaning |
|---|---|
| Page | One of the four 16 KB parts of the Z80's 64 KB address space: page 0 is 0000h to 3FFFh, page 3 is C000h to FFFFh |
| Slot, subslot | Where the memory in a page comes from: one of four primary slots, and in an expanded slot one of four subslots |
| Slot ID | A slot in one byte: bit 7 set when expanded, bits 3 and 2 the subslot, bits 1 and 0 the primary slot |
| Segment | A 16 KB block of a memory mapper, selected into a page by the mapper registers at ports FCh to FFh |
| DOS's mapper | The mapper that holds DOS's four pages on the real machine |
| DOS's segments | The segments in pages 0 to 3 when the restorer starts |
| Image | `<GAME>.SNP`, the snapshot in the restorer's format ([Formats](#formats)) |
| Worker | The part of the restorer that runs in page 1 or 2 while it changes the other pages |
| Tail | The restore's last code: 26 bytes written below the game's stack pointer |
| T0 | A RAM copy of the BIOS's page 0 whose tape routines call the tape service's ([Tape service](#tape-service)) |
| Code segment | The segment that holds the tape service's routines, then the start of the tape |
| Service segment | A segment that holds T0, the code segment, or the rest of the tape |
| Replay | `<GAME>.RPL`, a recording of the load's screen and sound that the restorer can play before the restore ([Replay](#replay)) |

## Files and commands

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` |
| `games/<game>/game.txt` | A person or an LLM | The game's settings that hold on every machine |
| `games/<game>/<machine>.txt` | A person or an LLM, for a game that needs it | The game's settings that hold only on one machine, named after the machine file with `-` for `/` ([Game file](#game-file)) |
| `out/<machine>/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/<machine>/<game>/<GAME>.SNP` | `tools/build.py` | The image |
| `out/<machine>/<game>/<GAME>.RPL` | `tools/build.py` | The replay |
| `out/<machine>/<game>/scan.txt` | `tools/build.py` | The scan's findings and patches |
| `out/<machine>/<game>/check/` | `tools/check.py` | The check's report and savestates |
| `bin/SNAPCAS.COM` | The developers | The restorer, from `src/snapcas.asm` |
| `bin/SERVICE.BIN` | The developers | The code that `build.py` writes into images: the tape service's routines, entries, entry code and reader, and the tail, from `src/service.asm` ([SERVICE.BIN](#servicebin)) |

The `bin/` files are built with sjasmplus 1.24.0 and shipped. `<machine>` is a path
below `machines/` without `.txt`, such as `basic/vg8020`. Each game is processed by
four commands, in this order:

1. `tools/capture.py <game> <machine> --cas <dir>` loads the game in `openMSX` and
   saves the snapshot ([Capture](#capture)). `<dir>` holds the user's CAS files.
2. `tools/build.py <game> <machine> --cas <dir>` writes the image and `scan.txt`
   ([Build](#build)), and prints `<GAME>`.
3. `tools/check.py <game> <machine> --dos <dir>` runs the restorer in `openMSX` and
   verifies the restore ([Check](#check)). `<dir>` holds the user's DOS system
   files.
4. The user copies `SNAPCAS.COM` and `<GAME>.SNP` to a disk of the real machine and
   runs `SNAPCAS <GAME>`. With `<GAME>.RPL` beside them, `SNAPCAS <GAME> /R` first
   shows the load as it happened in the capture. With `/T1200` or `/T2400`, a game
   with the tape service loads at that speed, with the sound of the tape
   ([Tape speed and sound](#tape-speed-and-sound)).

`tools/snapcas.py <game> <machine> --cas <dir> [--dos <dir>]` makes the image in one
command: it runs steps 1 and 2, and step 3 when `--dos` is given. When the build or
the check fails, and the game file names no `capture` machine, it runs these steps
again on each capture variant of the machine, in the order of their names
([Machine file](#machine-file)). It keeps the first image that passes, and prints
the `capture` line that made it, for the machine's game file. Otherwise it stops at
the first step that fails, with that step's exit status. `capture.py`'s
`--capture <variant>` names the variant, in place of the game file's `capture` line.

The tools are Python 3 programs that require only Python 3 and `openMSX` 22.0, so
they run on macOS, Linux and Windows. They print errors on standard error, naming
the file and the problem, and exit with 0 on success, 1 for an error in the input
files, 2 when `openMSX` fails or a wait times out, and 3 when a check fails.

## Machine file

A machine file holds one `openmsx` line, one `disk` line, any number of `boot` lines
and at most one `dos` line, as in this example for a Sanyo PHC-28S with a RAM
cartridge and a Carnivore2:

```
openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2
disk hda
boot "DefConfig" space
```

| Line | Meaning |
|---|---|
| `openmsx` | The `openMSX` arguments that reproduce the machine |
| `disk` | The `openMSX` command that inserts `check.py`'s disk image, such as `hda` for an IDE interface or `diska` for a floppy drive |
| `boot` | A text on the screen during boot and the key to press when it appears. Each key has its own line, matched in order. A menu can show its text before it reads the keyboard, so the key is pressed again each second while the text stays, up to 10 times |
| `dos` | For a machine that boots MSX-DOS from a disk of its own, as the MegaFlashROM SCC+ SD boots from the ROM disk in its flash: DOS's prompt, such as `A:\>`, and the drive letter of `check.py`'s disk. When the prompt appears, the capture types `BASIC`, because it loads the game from BASIC, and the check types that drive and `AUTOEXEC` |

`openMSX` puts each `-ext` cartridge in the next free external slot, so the order of
the `-ext` options sets the slots, and it must match the real machine's. `boot`
lines pass a cartridge's boot menu, such as the Carnivore2's. The tools read the
screen with `get_screen`, so such a menu must be in a text mode. A line that starts
with `#` is a comment.

Machine files are of three kinds, each in its own place:

| Kind | Where | What it is |
|---|---|---|
| A user's machine | `machines/basic/` and `machines/advanced/` | A real machine that the images are made for, given as the command's `<machine>` |
| A capture variant | Beside its machine, named after it and the cartridge it leaves out, such as `advanced/phc28s-nodisk` | The same machine with one cartridge fewer, for a game whose loader trips over that cartridge. A game's `capture` line names it |
| A test machine | `machines/test/` | A machine that only the tests use |

A capture variant only takes a cartridge away: it keeps the machine's ROMs and every
other cartridge in its slot. The image built from its snapshot is still for the
user's machine and is checked there, so the restorer finds the RAM pages in the
slots that the snapshot names. Its first line, a comment, says which cartridge it
leaves out and why. The capture variants of a machine are the machine files beside
it whose names start with the machine's name and `-`, so `tools/snapcas.py` finds
them without a list.

## Game file

A game file holds one setting per line: a key, a space and a value. A line that
starts with `#` is a comment, and blank lines are ignored. Times are decimal
emulated seconds from the moment the load command is typed. Addresses and bytes are
hexadecimal. Only `cas` is required. This example is for Gauntlet, which loads its
levels from the tape's second side:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
```

| Key | Value | Default | File |
|---|---|---|---|
| `cas` | The CAS file of side 1, in the `--cas` folder | | `game.txt` |
| `side2` | The CAS file of side 2 | None | `game.txt` |
| `sha1` | The SHA-1 of `cas`, then that of `side2` | None | `game.txt` |
| `name` | `<GAME>`, up to 8 letters and digits | The folder name in upper case, cut to 8 letters and digits | `game.txt` |
| `keys` | A time, then a key name ([Key names](#key-names)) held for 0.1 seconds, or a text in quotes that `openMSX` types. Each press has its own line | None | `game.txt` |
| `continue` | A key name that the capture tries before space and Return, to continue a load that waits for a key | None | `game.txt` |
| `snapshot` | `at` and a time, at which the capture takes the snapshot: for a game that asks the player to stop the tape, the moment it asks, because `openMSX`'s tape runs on and the tape service serves every later load | Found by the capture | `game.txt` |
| `capture` | A capture variant of the machine, on which the capture loads the game ([Machine file](#machine-file)) | The command's machine file | The machine's game file |
| `service` | `no` for a game that never reads the rest of its tape, though blocks of it stay unread. A game can read them only at its end, so `no` is for a game that someone has played to its end. Or `at` and an address xxE1h in page 3, where the tape service's part of page 3 goes ([Build](#build)). Or `t0`, for the tape service without a part in page 3 ([Without a part in page 3](#without-a-part-in-page-3)) | Found by the capture, and by `build.py` | `game.txt` |
| `patch` | A place, the old bytes, `>`, the new bytes: `patch page3:215F CD E1 00 > CD E1 FC` | None | `game.txt`, and a patch of a slot register's value the machine's game file |
| `rom` | `keep` for a game that must find the ROM in page 0 at the snapshot's slot: T0 does not replace the ROM, and the game reaches the tape service only through calls patched to the entries in page 3 | T0 replaces the ROM when the restorer's rule allows it | `game.txt` |

A place is a RAM page as `page<n>:<offset>`, which names the RAM page that the
snapshot selects in page n, 0 to 3, and the offset from that page's start. A place
can also be on the tape, as `side1:<offset>` or `side2:<offset>`, an offset in the
CAS file. A patch on the tape changes the tape that the capture loads and that the
tape service serves, so it also reaches the code that the capture runs. Neither form
names a slot, so a patch line holds on every machine that the game runs on, unless
its new bytes are a slot register's value. A patch fits only the dump that it was
made for, so `capture.py` and `build.py` stop with an error when the old bytes
differ, or when the game file has `patch` lines and `sha1` is missing or differs
from a CAS file's SHA-1.

`game.txt` describes the game and its tape, and holds on every machine. A game's
folder can also hold a machine's game file: a game file for one machine, named after
that machine file with `-` in place of `/`, such as `advanced-phc28s.txt` for
`advanced/phc28s`. The tools read it after `game.txt` when they capture, build or
check for that machine. Its lines add to those of `game.txt`, and a value that both
give is the machine's game file's. It holds the lines that depend on where the
machine's RAM and cartridges are:

| Line | Why it depends on the machine |
|---|---|
| `capture` | It names one of the machine's capture variants ([Machine file](#machine-file)) |
| A patch of a slot register's value | The value names slots. Sootland writes FCh to the slot register, for RAM in slot 3, and crashes on the Sanyo PHC-28S. Without Nextor, that machine's BASIC keeps page 3 in the internal RAM, slot 0, and the RAM cartridge in slot 1 holds pages 0 to 2, so a patch to 14h keeps page 3 there and selects slot 1 for pages 1 and 2. The capture makes such a patch itself for a fixed value ([Slot patches](#slot-patches)), so a game file needs one only for a value that the game computes |
| A `snapshot` that a real machine needs | Tokyo Nampa Street's snapshot comes after its music only because of the real PHC-28S ([Limits](#limits)) |

## Shipped files

The repository ships a game file for each game of File-Hunter's MSX CAS collection
in `games/`, in a folder named after the short name of its side 1 CAS file, such as
`games/ABADIA/` for `ABADIA.CAS`. The folder name then also names the image. Each
game file starts with two comments: the game's File-Hunter name, and the link to its
zip in File-Hunter's MSX1 CAS folder, which a few games lack because the folder does
not list them. The game file then has the `sha1` of its dumps, which finds a dump
whatever its file name. A side B, a later tape of a set or an expansion, which the
collection's `SIDES.TXT` lists, needs a tape before it, so it has no game file of
its own. A dump that File-Hunter marks `[b]`, a bad dump, has no game file either,
and a game with a better dump uses that one. Its `side2` lines pair the Side A and
Side B files of a game, its `continue` lines come from the key that the capture
reports, its `service no` lines from games played to their end, and its `patch`
lines from `check.py` and from traces of failed loads. The lines that hold only on
one machine are in the game's machine's game file ([Game file](#game-file)): 43
games have one for the Sanyo PHC-28S, `advanced-phc28s.txt`, and 69 for the Philips
VG-8020, `basic-vg8020.txt`. The other game files hold on any machine. It also ships
these machine files, each checked with `check.py` and a single-load game:

| File | Configuration |
|---|---|
| `basic/vg8020` | Philips VG-8020: an MSX1 with 64 KB and a Carnivore2 |
| `basic/nms8250` | Philips NMS 8250: an MSX2 with its own 128 KB and a floppy drive, and a Carnivore2 under Nextor, for the cartridge with a mapper and a disk interface that most MSX2 owners use |
| `basic/msx2ide` | Philips NMS 8245: an MSX2 with a 512 KB RAM cartridge and a Sunrise IDE interface, under Nextor. Its own 128 KB leave Nextor too few free segments |
| `basic/picoverse` | Philips VG-8020 with a Sunrise IDE interface under Nextor and a 192 KB memory mapper, as the PicoVerse cartridge has them. `openMSX` has no PicoVerse, so these two cartridges stand in for it, and the Makefile makes the 192 KB mapper from `openMSX`'s 512 KB one |
| `advanced/phc28s` | Sanyo PHC-28S: an MSX1 with 16 KB, a RAM cartridge in slot 1 and a Carnivore2 in slot 2 |
| `advanced/mfrsd` | Sony HB-75P: an MSX1 with 64 KB and a MegaFlashROM SCC+ SD in `openMSX`'s stock setup, which boots MSX-DOS from the ROM disk in its flash, with the check's disk in SD card slot 1 as drive B: |
| `advanced/hbf700p` | Sony HB-F700P: an MSX2 whose slot 0 is expanded, with a 512 KB RAM cartridge, under MSX-DOS 2. Its own mapper holds 256 KB |

It also ships these capture variants ([Machine file](#machine-file)), which the
games' `capture` lines name:

| File | Leaves out | Used by |
|---|---|---|
| `advanced/phc28s-nodisk` | The Carnivore2, and so Nextor | 20 games that crash when a disk system is present, or that select RAM by fixed slot values |
| `advanced/phc28s-noslot1` | The RAM cartridge in slot 1 | 10 games whose loader trips over it |
| `basic/vg8020-nodisk` | The Carnivore2, and so Nextor | 67 games that fail in a capture with the Carnivore2 in slot 1. 6 of them also select RAM in slot 2 by fixed slot values |
| `advanced/hbf700p-noram` | The RAM cartridge in slot 1 | La Abadia del Crimen in the tests, which crashes with the cartridge in either slot |

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
   BASIC's `Ok`, then 10 seconds more, as a person would. A disk system can still be
   busy just after `Ok`: on the Sanyo PHC-28S with a Carnivore2, Moonrider loads
   when the load starts 9 seconds after the boot menu, and stops when it starts
   after 5.
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
3. Inserts the CAS file of side 1, with the game file's `side1` patches written into
   a copy in `snap/`, into the cassette player, notes the slots selected in each
   page, and types the load command for the first header's type
   ([CAS data](#cas-data)): `BLOAD"CAS:",R`, `CLOAD`, or `RUN"CAS:"`. After `CLOAD`,
   it types `RUN` when the motor has stopped for 1 second. When the game file has
   `side2` and the game reads past side 1's end, by a `TAPION` call at its end or
   with the motor on there, the capture inserts side 2 at its start, as a player
   turns the tape over, and the tape position goes on in side 2. The replay's
   recording starts just before the command is typed ([Replay](#replay)).
4. Presses the `keys`, and logs these events with their times:
   - The tape position, kept as the tape service would keep it, from breakpoints at
     the addresses that the jump table entries 00E1h and 00E4h jump to, `TAPION` and
     `TAPIN`, while page 0 selects the main ROM.
   - Each slot and subslot selected in a page, from write watchpoints on port A8h
     and on FFFFh, and each write to port A8h that selects a slot that holds nothing
     ([Slot patches](#slot-patches)).
   - Each start and stop of the cassette motor.
5. Polls bit 4 of PPI port C, the cassette motor (0 = on), every 0.1 seconds. When
   the motor has been off, or the player has been at the tape's end
   (`cassetteplayer getpos` at least `getlength` minus 0.01), for 1 second, it saves
   the machine with `savestate`. The wait ends when that has lasted 30 seconds and
   the last `keys` time has passed, because a game can pause its own load: Moonrider
   pauses for 16 seconds. With `snapshot at`, the capture instead waits for that
   time and goes to step 6. Otherwise it goes back to the saved moment with
   `loadstate`, and proceeds:
   - If side 1 is read, it goes to step 6. Side 1 is read when the `TAPION` and
     `TAPIN` breakpoints fired and every block after the tape position is under 16
     bytes or equal to a block before it. A CAS file pads each block to a multiple
     of 8 bytes, so a block counts as read when at most 7 bytes of it are left.
   - Otherwise it tries the game file's `continue` key, then space, then Return,
     each from the saved moment and held for 0.5 seconds, because a loader can read
     the keyboard rarely. If the motor starts within 10 seconds of a key, and the
     tape is not at its end, the load was waiting for that key: the capture logs the
     key and restarts step 5. If no key starts it, the rest is loaded during play,
     and it goes to step 6 from the saved moment.

   `loadstate` restores the machine but neither the script's variables nor its
   timers, so each time the capture also restores its logged state from the saved
   moment and schedules again its polling and the `keys` that come after that
   moment.
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
   there, so the restored game makes it to the tape service. Saint Dragon reads its
   tape with interrupts off, and Thunder Blade waits in `TAPION` for side 2, so
   their snapshots come this way. The CPU is in the tape code when the main ROM is
   in page 0 and the program counter is in 19DDh to 1B44h, or is below 4000h with
   one of the 8 words on top of the stack in that range, as in `BREAKX`, which the
   tape code calls. The capture saves the machine at each `TAPION` call's entry for
   this, and a rewind of step 5 puts back the entry saved with its moment.

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

1. At step 2, after BASIC's `Ok`, the capture tests each page of each primary slot,
   and of each subslot of an expanded slot, and writes the slot map,
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
   bytes before them occur once in a CAS file, the capture stops. `capture.py` then
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

Sootland's FCh names slot 0 for page 0, which holds the ROM, and slot 3 for pages 1
to 3. On the PHC-28S without Nextor, BASIC selects slot 1 in page 2 and slot 0 in
page 3, and slot 1 also holds RAM in page 1, so the patch writes 14h. The patches in
`snap/patches.txt` change the tape after the game file's `patch` lines, and
`build.py` applies them as well, so the tape service serves the tape that the
capture loaded.

The watch and the scan know two forms of the code that sets a fixed value:

| Code | Bytes | Where the watch finds it |
|---|---|---|
| `LD A,n / OUT (0A8h),A` | `3E n D3 A8` | Its last byte is the last byte of the write's `OUT` |
| `LD A,n / CALL 013Bh`, a call of the BIOS's `WSLREG`, which writes A to the slot register | `3E n CD 3B 01` | When the write's `OUT` is in the main ROM, its last byte is the byte before the return address on top of the stack. The capture reads that address in the slot that page 3 selected before the write, because the write can change page 3. Finders Keepers selects RAM in slot 2 this way |

### Snapshot files

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>-<seg>.bin` | 16 KB for each RAM page kept, by primary slot, subslot (`x` when not expanded), page and segment (`x` when not in a mapper) |
| `rom.bin` | 32 KB: pages 0 and 1 of the main ROM, from the slot that `EXPTBL` names |
| `subrom.bin` | 16 KB on an MSX2: the sub-ROM, from the slot that `EXBRSA` names |
| `vram.bin` | The `physical VRAM` debuggable: 16 KB with an MSX1 VDP, 64 or 128 KB with a V9938 |
| `state.txt` | One `name value` per line, values in hexadecimal, as below |
| `replay.log` | The VDP, PSG and cassette writes of the load, for the replay ([Replay](#replay)) |
| `side1.cas` | Side 1 with the game file's `side1` patches and those of `patches.txt`, when there are any: the tape that the capture loads |
| `slots.txt` | The slot map: for each page of each slot and subslot, whether it holds RAM, ROM or nothing ([Slot patches](#slot-patches)) |
| `patches.txt` | The slot patches on the tape that the capture found, as `patch` lines |
| `log.txt` | The logged events and the capture's decisions, in time order: each stop of the load with the screen's text, the key that continued it, each mapper's size, and how the snapshot was taken. Its last line names the `continue` key that worked |

| `state.txt` names | Source in `openMSX` |
|---|---|
| `af`, `bc`, `de`, `hl`, `af2`, `bc2`, `de2`, `hl2`, `ix`, `iy`, `sp`, `pc`, `i`, `im` | `reg` |
| `iff` | Bit 0 of `reg IFF`: 1 when interrupts are on |
| `a8`, `ppic` | `debug read` on ports A8h and AAh |
| `sub0` to `sub3`, `-` when not expanded | For a slot that `EXPTBL` marks expanded, the byte at FFFFh, inverted, read while page 3 selects that slot |
| `fc` to `ff`, `-` without a mapper | `MSX Memory Mapper I/O`: the values written, which each mapper masks to its size |
| `vdp0` to `vdp23`, `vdp32` to `vdp45` | `VDP regs`, which holds only 0 to 7 with an MSX1 VDP |
| `pal0` to `pal15` | `VDP palette` |
| `vramptr` | `VRAM pointer`, 14 bits, with bits 14 to 16 from register 14 |
| `vramwrite` | `VRAM access status`: 1 after a write setup, 0 after a read setup |
| `psg0` to `psg15`, `psgsel` | `PSG regs`, and the port A0h watchpoint |
| `tapepos`, `service` | The tape position in side 1, and 1 when the game gets the tape service |

## Build

`tools/build.py` writes the image ([Formats](#formats)). It:

- Stores each 16 KB block of `vram.bin`, as a block of zeros when it holds only
  zeros, and each RAM page, once for a segment that two pages select.
- Turns the PSG, PPI and VDP state into a list of port writes, in the order that the
  restorer performs them ([Port writes](#port-writes)).
- Writes the tail, from `SERVICE.BIN`, into the 26 bytes below the stack pointer. At
  an interrupt's entry these bytes are free, because the handler that runs next
  pushes onto them. It stops with an error when they cross a page boundary, include
  FFFFh, or are not in a RAM page that the snapshot keeps.
- Applies the patches of `snap/patches.txt` to the tape, and runs the scan's search
  for slot values on every image ([Slot patches](#slot-patches)).
- With the tape service, builds T0, the code segment and the other tape segments
  from `rom.bin`, the CAS files and `SERVICE.BIN`, writes the service's part of page
  3 into the game's page 3, with the snapshot's value of mapper register FCh at
  FCF9h, runs the scan, and applies the scan's patches and the `patch` lines
  ([Tape service](#tape-service)). When no part of page 3 has room for the service's
  part, it uses the mode without a part in page 3, as `service t0` does
  ([Without a part in page 3](#without-a-part-in-page-3)). It stops with an error
  when the service's part of page 3 holds the tail, or when the code segment and the
  tape need more than 64 segments.
- Puts the service's part of page 3 at FCE1h when FCC9h to FD88h are zero at the
  snapshot, as the capture leaves them. A game can use that area itself, as
  Moonwalker does for its code. The part then goes to xxE1h of the highest page xx
  below the BIOS's work area at F380h whose 168 bytes from there are zero, or to the
  game file's `service at`. Zeros at the snapshot can still be a buffer that the
  game fills later, so a moved part is checked by playing to the game's next load.
  The part moves by its page alone: the entries keep their low bytes, E1h to F3h,
  and the scan's patches write xxh instead of FCh. `build.py` adds xx minus FCh to
  each byte that `SERVICE.BIN`'s last part lists, and writes xx in the image's
  header ([SERVICE.BIN](#servicebin)).
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
     `SNAPCAS.COM` ([Image](#image)). An image with another number gets a message
     that it was made for another version of `SNAPCAS.COM`.
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

      It stops when there are too few, naming the segments needed and free. Then,
      with `/R`, it plays the replay ([Replay](#replay)).
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
     register ([Tail](#tail)).
   - With the tape service, in the code segment at 001Ah: the code segment, then the
     other tape segments, and at 0062h: 1 for `/T1200`, 2 for `/T2400`, with `/R`
     alone the replay's speed, or otherwise 0.
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
| Entry code | `SLTWRK`, after its data at FCF6h to FCFAh | Selects T0 in page 0, calls the routine, and selects the game's page 0 again |
| Trampoline | `SLTWRK` | Selects the code segment in page 0, calls a routine there, and selects T0 again |
| Reader | `SLTWRK` | `OUT (C),D / LD E,(HL) / OUT (C),B / RET`: reads a tape byte |

`build.py` builds T0 from `rom.bin`, so it first checks that each jump table entry
below jumps to its address, as in the standard MSX BIOS. The restorer's ROM check
ensures that the real ROM equals `rom.bin`.

| Entry | Routine | Address it must jump to |
|---|---|---|
| 00E1h | `TAPION` | 1A63h |
| 00E4h | `TAPIN` | 1ABCh |
| 00E7h | `TAPIOF` | 19E9h |
| 00EAh | `TAPOON` | 19F1h |
| 00EDh | `TAPOUT` | 1A19h |
| 00F0h | `TAPOOF` | 19DDh, the start of the tape code |
| 0018h | `OUTDO` | 1B45h, the first byte after the tape code |

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
| `TAPIOF`, `TAPOOF` | Enable interrupts and return |
| `TAPOON`, `TAPOUT` | Return with carry set: the tape cannot be written |
| `STMOTR` | Returns |

The code segment holds the service's data, its routines and then the tape, which
starts at a multiple of 8 bytes. The tape position and the sides' starts and ends
count bytes from the code segment's start, across the code segment and the tape
segments after it. The code segment's fields are these:

| Offset | Size | Field |
|---|---|---|
| 0000h | 6 | Jumps to `TAPION` and `TAPIN` |
| 0006h | 3 | The tape position |
| 0009h | 3 | Side 1's end, which is side 2's start |
| 000Ch | 3 | Side 2's end, equal to side 1's end without a side 2 |
| 000Fh | 3 | Side 1's start |
| 0012h | 8 | The CAS header |
| 001Ah | 64 | The code segment, then the other tape segments, filled in by the restorer |
| 005Ah | 2 | The address of the game's value of VDP register 7: `RG7SAV`, F3E6h, when it equals the snapshot's register 7, otherwise 005Dh |
| 005Ch | 1 | The frames in 0.1 second: 5 when bit 7 of the ROM's byte 002Bh is set, for 50 Hz, otherwise 6 |
| 005Dh | 1 | The snapshot's VDP register 7 |
| 005Eh | 1 | The side that the tape position is on: 0 for side 1, 1 for side 2, set by `build.py` from the position at the snapshot |
| 005Fh | 2 | The address of the game's value of VDP register 1: `RG1SAV`, F3E0h, when it equals the snapshot's register 1, otherwise 0061h |
| 0061h | 1 | The snapshot's VDP register 1 |
| 0062h | 1 | The tape speed, filled in by the restorer: 0 for the fast load, 1 for 1200 baud, 2 for 2400 baud |
| 0063h | 1 | 1 when the tape has a side 2, set by `build.py` |
| 0064h | 3 | The tape position while `TAPIN` looks for a header |
| 0067h | 3 | Side 1's end before its padding, set by `build.py` when the tape has a side 2, otherwise side 1's end |
| 006Ah | | The routines, then the tape |

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
keeps its data before its code:

| Address | Value |
|---|---|
| FCF6h | DOS's mapper's slot ID, filled in by the restorer |
| FCF7h | T0's segment, filled in by the restorer |
| FCF8h | The code segment, filled in by the restorer |
| FCF9h | The game's mapper register FCh, from `build.py`, or T0's segment when T0 replaces the ROM |
| FCFAh | 1 while the entry code runs, so that T0's `TAPIOF` and `TAPOOF` leave interrupts off |

The tape position starts where the game stopped reading at the snapshot, and moves
on these events. The routines read the keyboard matrix through the PPI.

| Event | New position |
|---|---|
| `TAPION` or `TAPIN` reads past side 1's end | Side 2's start, as when the player turns the tape over, or side 1's start when there is no side 2 |
| `TAPIN` reads in side 1's padding before side 2 | Side 2's start, and `TAPIN` returns FFh: the padding is not on the tape, and the read that waits while the player turns the tape over returns FFh in `openMSX`, which Saint Dragon's loader expects |
| `TAPIN` reads at a multiple of 8 where a CAS header is | The byte after the header, because a header is a tone on the tape, which `TAPIN` waits through, as when a game reads on into the next block or side |
| `TAPION` or `TAPIN` reads past side 2's end | Side 2's start, as after a rewind |
| `TAPION` is called while GRAPH is held | Side 1's start |
| `TAPION` is called while CODE is held | Side 2's start, or side 1's start when there is no side 2 |

The service shows the side that the position moves to with one flash of the side's
colour over the whole screen for 0.1 second, after GRAPH or CODE, and when a read
reaches side 2 or goes back to a side's start. It sets the border colour and blanks
the display, which then shows only the border, because the border alone is thin and
many screens crop it. Side 2 starts at side 1's end, so a read that reaches side 2
changes only the side at 005Eh, and that change shows the flash. The service counts
the frames by the frame flag in the VDP's status register 0, then writes the game's
VDP registers 7 and 1 back and goes on. The VDP's registers cannot be read, so the
service takes the game's values from the addresses at 005Ah and 005Fh in the code
segment. The colours are these:

| Outcome | Border |
|---|---|
| Side 1's start | Light green, 3 |
| Side 2's start | Light red, 9 |

### Without a part in page 3

A game can use all of its page 3 over time, as Moonwalker does: its main game loads
its code into FCC9h to FD88h, and no 168 bytes of its page 3 stay free from one load
to the next. For such a game, the game file's `service t0` puts the whole tape
service into T0, and nothing of it stays in page 3. `build.py` also takes this mode
itself when no part of page 3 has room at the snapshot, so a game file needs
`service t0` only for a game whose page 3 is free at the snapshot but not in a later
load, as Moonwalker's is. Such a game needs the line on every machine, in
`game.txt`. The service's part of page 3 exists only because the service switches
page 0 while it runs, so this mode removes the three switches:

| Switch | Without a part in page 3 |
|---|---|
| The entry code selects T0 in page 0 | The game reaches T0 by slot. T0 stays in mapper register FCh for good, so page 0 shows T0 whenever the game selects DOS's mapper there, and T0's jump table, from 00E1h to 00F3h, is the only set of entries. When the snapshot has the ROM in page 0, the restorer selects T0 there instead, by the default mode's rule ([Restorer](#restorer)), so that BASIC's own `BLOAD`, which Tokyo Nampa Street uses for each scene, reaches T0 |
| The trampoline selects the code segment | The routines run in T0: they, the tape position, the table of the tape's segments and the flash's data take the 360 bytes from 19DDh to 1B44h, which an assertion in `src/service.asm` checks. `src/tape.inc` holds the routines, which `service.asm` assembles in the code segment and in T0, and `build.py` points T0's jump table at T0's copy |
| The reader selects the tape's segments in page 0 | `TAPIN` reads through page 2 or page 1, which `build.py` chooses: the first that is a page of a mapper at the snapshot, or else page 2. With interrupts off, it keeps the slot register's value in T0, selects DOS's mapper's slot in that page through the slot register and the byte's segment through FEh or FDh, reads the byte, and writes back the slot register and the snapshot's segment. It uses no stack meanwhile, so the page can hold the game's stack, as Tokyo Nampa Street's page 2 does. A game whose RAM is in a slot without a mapper, as Bronx's is on the Sanyo PHC-28S, can also lend its page. When the capture has no mapper at all, as a capture variant without the Carnivore2 has none, the game lends page 2, and `TAPIN` writes back segment 0, which only DOS's mapper sees |

The tape takes at most 16 segments, 256 KB, and starts at the first tape segment.
`TAPIOF` and `TAPOOF` enable interrupts, as the BIOS's do. The keys and the flash
work as in the default mode.

A game can use the mode only when these hold at the snapshot. Otherwise `build.py`
stops with an error, or the restorer with a message for the last condition:

| Condition | Why |
|---|---|
| No RAM page kept for page 0 is in DOS's mapper | T0 takes the game's mapper register FCh for good |
| When the borrowed page is in DOS's mapper, the game keeps its segment there from then on | `TAPIN` writes back the snapshot's segment |
| When DOS's mapper's slot is expanded, the snapshot's subslot register of that slot selects the mapper in the borrowed page | The slot register alone then selects the mapper there. The restorer checks this, because only it knows DOS's mapper's slot. When the capture did not have that slot expanded, as a capture variant without the Carnivore2 does not, the game never wrote its subslot register, so the restorer sets the borrowed page's bits there to the mapper's subslot instead |

Code that selects the ROM in page 0 itself and then calls the tape reaches the ROM,
not T0, so the scan only lists its findings in this mode, and the game file sends
that code to T0 with `patch` lines that make it select DOS's mapper in page 0.
Moonwalker's loader computes the value that its stub writes to the slot register as
`AND H / LD L,A`, the slot register with page 0's bits cleared, for slot 0. On the
Sanyo PHC-28S the game keeps the slot register at A5h, so `LD L,0A6h` in their place
selects slot 2, DOS's mapper. A game that writes FCh itself loses T0, and a game
whose own page 0 RAM is in DOS's mapper, as Moonwalker's is on an NMS 8250, cannot
use the mode.

The restorer allocates T0 and the tape's segments as in the default mode, writes the
table of the tape's segments and DOS's mapper's slot for the borrowed page into T0,
and sets mapper register FCh to T0's segment, with DOS's mapper's subslot in the
page 0 bits of its slot's subslot register and of `SLTTBL`. It writes nothing into
the game's page 3. Bit 1 of the image's flags marks the mode ([Image](#image)).

### Tape speed and sound

By default the tape service returns each byte as soon as the game asks for it, so a
load takes a moment. For the experience of a real tape, `SNAPCAS <GAME> /T1200` or
`/T2400` makes a game load at that speed, with the tape's sound. The restorer writes
the speed at 0062h in the code segment, and the service then works as a tape at that
speed:

- `TAPIN` plays each byte that it returns as the tape holds it, on the keyclick bit,
  PPI port C bit 7, which the MSX sends to its sound output: a start bit 0, the 8
  data bits from bit 0 up, and 2 stop bits 1 (MSX Red Book, chapter 4).
- `TAPION` plays the leader tone before each header that it finds, as long as the
  BIOS's `TAPOON` writes it: the long one before a block that starts with a file
  type's 10 bytes ([CAS data](#cas-data)), the short one before the others.
- `TAPION` starts the motor and `TAPIOF` stops it, and `STMOTR` switches it, as the
  BIOS's routines do, through the motor relay, PPI port C bit 4. So the relay clicks
  when the tape starts and stops.

Each bit is one or two cycles of a square wave:

| Speed | Bit 0 | Bit 1 | A byte's 11 bits |
|---|---|---|---|
| 1200 baud | One cycle of 1200 Hz | Two cycles of 2400 Hz | 9.2ms |
| 2400 baud | One cycle of 2400 Hz | Two cycles of 4800 Hz | 4.6ms |

The sound is the wait, so a byte takes as long as on the tape, plus the game's own
code between two bytes. The service writes the keyclick bit back to its value before
the byte. The keys and the flash work as at the fast speed.

`/T1200` and `/T2400` act only through the tape service, so they change nothing for
a game without it, and the restorer then says so before the restore. Such a game
loaded completely before the snapshot, and the experience of its load comes from the
replay, which plays the load at the capture's speed with the sound of a tape
([Replay](#replay)). The two combine: with `/R /T1200`, the replay shows the first
load, and the game's later loads come from the tape service at 1200 baud.

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
| A call of a tape routine: `CALL 00E1h`, `CALL 00E4h` or `CALL 00E7h` | `CD E1 00`, `CD E4 00` or `CD E7 00` | The call's `00` becomes `FC` |
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

## Replay

The replay shows the load on the real machine as it happened in the capture: BASIC's
screen with the load command being typed, the loading screens being drawn, their
music, the game's own pauses and its waits for a key, and the cassette motor's
relay. Nothing of the loader runs again: the replay is a recording, played before
the restore, so it works for every game whose capture works. It is optional, in its
own file, `<GAME>.RPL`, and runs only with `/R`.

The capture records it from just before it types the load command to the snapshot,
in `snap/replay.log`. The log starts with the VDP's state at that moment: VRAM, the
registers and, on a V9938, the palette. Then it holds one line per write: the frame,
the port and the value. A frame is one VDP interrupt period of the machine, 1/50 or
1/60 of a second. It logs:

- Each write to the VDP's ports 98h to 9Bh and the PSG's ports A0h and A1h, from
  write watchpoints.
- Each change of the cassette motor and keyclick bits of PPI port C, bits 4 and 7,
  as a bit set or reset on port ABh, so that the replay does not touch the keyboard
  row bits.
- Each wait that a key continued ([Capture](#capture), step 5), as the frames of the
  wait's first 30 seconds, kept aside before the rewind, and the key.
- The frame of the load command's RETURN.

A rewind truncates the log to its length at the saved moment, as it puts back the
rest of the logged state.

`build.py` turns the log into a stream of commands ([Replay stream](#replay-stream))
and compresses it in chunks with the LZ4 block format. The restorer, after step 2,
plays the stream with interrupts off while it writes and on while it waits for the
next frame:

- It writes the first state with the display blanked, so the screen shows BASIC as
  it was in the capture. It then types the command as the capture did, and at the
  command's RETURN it waits until the player presses RETURN, as on a cassette
  machine.
- Before it plays, it reads `<GAME>.RPL` with its own FCB into the segments of DOS's
  mapper that step 2 leaves free, 16 KB each, and then plays from RAM. A DOS read
  during the replay would stop the frames and the sound, longest on a floppy disk.
  When the file needs more segments than are free, it fills them, and as it plays it
  reads the next chunks ahead into the segments that it has played, at frames in
  which the motor bit is off, when a tape is silent too.
- It writes VRAM no faster than one byte every 29 cycles, 8 µs, which an MSX1 VDP
  needs during the display.
- At a wait, it plays the wait's frames in a loop until a key is pressed.
- `/R2` to `/R9` play 2 to 9 frames for each frame that it waits.
- While the motor runs at `/R` speed, it toggles the keyclick bit in each frame's
  spare time at 1200 Hz for a 0 bit and 2400 Hz for a 1 bit, from the stream's own
  bytes, so that the load sounds like a tape.

When the replay ends, VRAM, the VDP's registers and the PSG's registers hold their
values at the snapshot, and the restore goes on with step 3.

A game with the tape service then loads the rest of its tape during play. So that
the whole session loads at one speed, `/R` alone also sets the tape service to the
capture's speed ([Tape speed and sound](#tape-speed-and-sound)). `build.py` finds
that speed, 1200 or 2400 baud, from the times of the `TAPIN` calls in the capture's
log and writes it in the replay's header. `/T1200` or `/T2400` with `/R` sets the
speed instead.

## Check

`tools/check.py` makes a disk image with `openMSX`'s `diskmanipulator`: a 720 KB
image without a partition table, which Nextor reads from its first sector and
MSX-DOS reads as a floppy disk. It holds the `--dos` folder's files, `SNAPCAS.COM`,
the image and an `AUTOEXEC.BAT` that runs `SNAPCAS <GAME>`. The folder holds
`NEXTOR.SYS` and `COMMAND2.COM`, `MSXDOS2.SYS` and `COMMAND2.COM`, or `MSXDOS.SYS`
and `COMMAND.COM`, which `snapcas` cannot ship. `check.py` boots the machine with
that disk and the `boot` keys, and writes its report to `check/report.txt`:

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
   `check/10s.oms` to `check/60s.oms`, and a breakpoint on each scan finding in a
   kept RAM page reports which findings the game executes. `openMSX` loads such a
   savestate to show the screen, because it takes screenshots only with a renderer.
   This point only reports.

Code that a game builds only when the player reaches a level is not visible to the
scan or to the check. It appears as a hang during play, and a trace of that load in
`openMSX` provides the `patch` line.

## Decisions

| Decision | Reason |
|---|---|
| Restore a snapshot | The game's loader runs once, in `openMSX`, so its slot code, stubs and checks need no changes on the real machine |
| Capture on a copy of the user's machine, with the disk system's hooks and work area removed | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Snapshot at an interrupt's entry | The CPU's state is complete, interrupts are off, and the bytes below the stack pointer are free for the tail |
| Mapper pages restored to their own segments, over DOS's at the end | The game finds the segment numbers that it wrote, and DOS's memory is overwritten only when DOS is no longer needed |
| ROM checksums checked by the restorer | A snapshot runs only on the ROMs it was taken with, and `build.py` can build T0 from `rom.bin` |
| Port writes, T0 and the tail made by `build.py` | The restorer copies records and fills in only the values that depend on the real machine |
| One restorer for every image | The user updates one program, and DOS passes it the image's name |
| A game file can name the machine for the capture | On the Sanyo PHC-28S, La Abadia del Crimen's loader takes the RAM cartridge in slot 1 for an expanded slot and crashes, but loads without it. Its image then runs with the cartridge in place, because the game never selects slot 1 again |
| Replay a recording of the load, not the load | Loading again on the real machine, through the tape service from the start, brings back what the snapshot avoids: loaders that go around T0 through their own slot code, loaders that use the page 0 RAM where T0 is, and loaders that trip over the machine's slots |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| T0 kept out of page 0 when the game's page 0 RAM is in DOS's mapper | On a single-mapper MSX2, T0 and that RAM need the same mapper register. Of the 59 multi-load files tested on an NMS 8250, two games use page 0 RAM and leave the ROM there at the snapshot: Moonwalker and Time Out |
| `rom keep` in the game file, not a rule of the restorer | T0 in page 0 serves a BASIC program, whose tape calls are in the ROM and cannot be patched, but it changes the slot register's page 0 bits. Gauntlet's RAM search adds the slot that it finds to those bits, expecting the ROM's slot 0, and selects an empty slot |
| Find the slot patches of the load by watching it, and not by a search of the whole tape | A search also changes bytes that are data or code that never runs, and a loader that checks a block's sum then fails to load it. A write that the watch sees runs, and selects a slot that holds nothing, so its patch is needed |
| Scan the snapshot and the unread blocks | A search of the 1,653 files of File-Hunter's MSX CAS collection for files that leave over 10% and 2 KB unread in a test load and hold a rewind or play prompt found 62 files of 51 games. Of those games, 20 build stubs that T0 alone does not intercept |
| The replay read into RAM before it plays | A disk read stops the frames and the tape's sound, and a compressed replay holds a few tens of KB, which fit in a few free segments |
| The replay starts at BASIC's screen, before the load command | The player sees the command typed and presses RETURN, as on a cassette machine, and the screen is the capture's, so it fits the machine |
| The tape speed as an option of `SNAPCAS`, fast by default | The player chooses at each run between a quick load and the experience of the tape, and the image stays the same |
| Rewind the capture with `savestate` and `loadstate` | `openMSX`'s `reverse goto` replays the input recorded after its target, while each key try must start from the saved moment with no other input |
| A tape with both sides, a wrap, and fixed keys for each side's start | In 41 of those 51 games the unread blocks have no names, so only the tape's position decides which block a game reads, as with a real tape |
| GRAPH for side 1's start and CODE for side 2's | GRAPH and CODE alone type no character, BASIC ignores them, and games rarely read them, while STOP pauses a BASIC program, the function keys type text, and many games use SELECT in their menus. On a Japanese MSX, CODE's key is KANA, which also switches the kana lock |

## Limits

- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- DOS's four pages must be in one memory mapper, with enough free segments for the
  image's holding and service segments and the worker. A game with a long tape needs
  a large mapper: Moonwalker's 236 KB tape does not fit in an NMS 8250's 128 KB.
- A game with the tape service needs one of two things. Either its page 3 keeps 168
  bytes from an address xxE1h free for the service's part of page 3, at the snapshot
  and in every later load ([Build](#build)). Or the game meets the conditions of the
  mode without a part in page 3, which `build.py` takes when page 3 has no room, or
  the game file's `service t0` asks for
  ([Without a part in page 3](#without-a-part-in-page-3)).
- A game that reads the tape with its own code gets no tape service, so it runs only
  if it loads in a single pass.
- Without a part in page 3, T0 has no room for `TAPIN`'s skip of a header and of
  side 1's padding, so a game that reads on with `TAPIN` into the next block or side
  gets the header's bytes in that mode.
- The shipped machine's game files, `advanced-phc28s.txt` and `basic-vg8020.txt`,
  hold only on their machine. On another machine, the games that have one may need a
  machine's game file of their own for that machine.
- A slot value that the code of neither form in [Slot patches](#slot-patches) sets
  gets no slot patch. The capture only logs its write, for a `patch` line by hand.
- The replay is a recording: a loader that lets the player act while it loads shows
  only what happened in the capture.
- A snapshot taken without an interrupt overwrites the 26 bytes below the stack
  pointer with the tail.
- Music that BASIC's `PLAY` statement is still playing at the snapshot does not
  resume on a real Sanyo PHC-28S, though it does in `openMSX`, and the cause is not
  known. Tokyo Nampa Street then waits for its music to end and never does. Its game
  file's `snapshot at` comes after the music, and with it the game runs on the real
  machine.

## Formats

### Image

All numbers are little-endian, and the CRC-16 is CRC-16/CCITT-FALSE: polynomial
1021h, initial value FFFFh, not reflected, no final XOR. The image holds 4,096 bytes
of header and tables, padded with zeros, then the data of each record in table
order, 16,384 bytes each, except a block of zeros, which holds none.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | `SNAPCAS3`, which changes when the image's format changes |
| 8 | 2 | CRC-16 of the main ROM's 32 KB |
| 10 | 2 | CRC-16 of the sub-ROM's 16 KB, or 0 on an MSX1 |
| 12 | 1 | Number of records |
| 13 | 1 | Number of port writes |
| 14 | 1 | Flags: bit 0 set for `rom keep`, bit 1 for `service t0` ([Game file](#game-file)) |
| 15 | 1 | The page of the tape service's part of page 3, whose entries start at E1h of it: FCh unless it moved, or 0 without the tape service |
| 16 | 24 | AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC |
| 40 | 1 | I |
| 41 | 1 | Interrupt mode |
| 42 | 1 | IFF1: 1 when interrupts are on |
| 43 | 1 | Slot register |
| 44 | 4 | Subslot registers of slots 0 to 3, 0 when not expanded |
| 48 | 4 | Mapper registers FCh to FFh |
| 52 | 2 | Tail address |
| 54 | 1 | The snapshot's VDP register 1 |
| 55 | 1 | Without a part in page 3, the page that `TAPIN` borrows, 1 or 2, otherwise 0 |
| 56 | 1 | Bit n set when slot n is not expanded in the capture |
| 57 | 7 | Zero |
| 64 | 4 per record | Record table |
| 64 + 4 × records | 2 per port write | Port writes: port, value |

| Record byte | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| RAM page in a mapper | 1 | Slot ID | Page | Segment |
| RAM page not in a mapper | 2 | Slot ID | Page | 0 |
| Service segment: T0 first, then the tape in order | 3 | 0 | 0 | 0 |
| VRAM block | 4 | Block number, 0 to 7 | 0 | 0 |
| VRAM block of zeros | 5 | Block number, 0 to 7 | 0 | 0 |

### Tail

| Offset | Bytes | Instruction |
|---|---|---|
| 0 | `3E nn` | `LD A,nn`: the snapshot's value of the worker's page's mapper register, filled in by the restorer |
| 2 | `D3 nn` | `OUT (nn),A`: FDh or FEh, filled in by the restorer |
| 4 | `3E nn` | `LD A,nn`: the slot register, filled in by the restorer |
| 6 | `D3 A8` | `OUT (0A8h),A` |
| 8 | `3E nn` | `LD A,nn`: the subslot register of DOS's mapper's slot, filled in by the restorer when the tail writes it |
| 10 | `32 FF FF` or `00 00 00` | `LD (0FFFFh),A` when the tail writes that register, otherwise three `NOP`s |
| 13 | `31 nn nn` | `LD SP,nnnn`: the tail's address plus 24 |
| 16 | `F1` | `POP AF` |
| 17 | `31 nn nn` | `LD SP,nnnn`: the snapshot's SP |
| 20 | `FB` or `00` | `EI` when IFF1 is set, otherwise `NOP` |
| 21 | `C3 nn nn` | `JP nnnn`: the snapshot's PC |
| 24 | 2 bytes | AF |

### Port writes

`build.py` lists the writes in this order:

1. For each PSG register from 0 to 15, its number to port A0h and its value to port
   A1h, with register 7's bits 7 and 6 forced to 1 and 0, then `psgsel` to port A0h.
2. PPI port C to port AAh.
3. On a V9938: 0 to register 16, the 16 palette entries to port 9Ah, 2 bytes each in
   the order that the `VDP palette` debuggable holds them, red and blue first, then
   32 to register 17, for auto-increment, and registers 32 to 45 to port 9Bh.
4. VDP registers 0 to 7, or 0 to 23, to port 99h, as a value and 80h plus the
   register's number.
5. The VRAM pointer to port 99h: its low byte, then its high bits with 40h for a
   write setup. A read setup writes the pointer minus 1, because the VDP reads ahead
   and advances the pointer. When the pointer's low 14 bits are 0, register 14 is
   written again first, with its value minus 1.

### SERVICE.BIN

`SERVICE.BIN` starts with a table of its parts, and `build.py` reads only the parts
that it names:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | Version: 5. `build.py` stops with an error on any other |
| 1 | 1 | Number of parts |
| 2 | 4 per part | Each part's offset and length in the file, 2 bytes each |

The parts hold the code that `build.py` places, with the operands and the data that
`build.py` and the restorer fill in set to 0:

| Part | What it holds |
|---|---|
| 0 | The tail ([Tail](#tail)) |
| 1 | T0's stubs, for 19DDh to 1B44h ([Tape service](#tape-service)) |
| 2 | The service's part of page 3, for FCE1h to FD88h |
| 3 | The code segment's data and routines, from 0000h, up to the tape's start |
| 4 | The addresses of `STMOTR`'s stub, of the tape position in the code segment, of the byte at FCF9h and of the marker's data in the code segment, with the most segments that the code segment and the tape can use, 2 bytes each |
| 5 | T0's routines and data without a part in page 3, for 19DDh to 1B44h ([Without a part in page 3](#without-a-part-in-page-3)) |
| 6 | The addresses of T0's routines for the jump table's entries from 00E1h to 00F3h, in their order, then of T0's tape position, borrowed page and flash's data, and the most segments of the tape, 2 bytes each |
| 7 | The offsets in the file of the bytes that move with the part of page 3, 2 bytes each: the high bytes of the addresses in that part |

The Makefile assembles `src/service.asm` twice, with the part of page 3 at FCE1h and
at FBE1h, one page lower, and `tools/relocs.py` lists the bytes that differ as the
last part. They differ by exactly 1, and the assembly at FCE1h is the file.

### Replay stream

`<GAME>.RPL` starts with `SNAPRPL1`, a byte with the frame rate, 50 or 60, a byte
with the capture's tape speed, 1 for 1200 baud and 2 for 2400 baud, and a 2-byte
count of chunks. Each chunk is a 2-byte compressed length and an LZ4 block that
decompresses to at most 16,384 bytes. The decompressed stream is a sequence of
commands:

| Command | Bytes | Meaning |
|---|---|---|
| End of frame | `00` | Wait for the next frame |
| Wait | `01 n` | Wait n more frames, 1 to 255 |
| Port write | `02 port value` | Write the value to the port: 99h, 9Ah, 9Bh, A0h, A1h or ABh |
| VRAM bytes | `03 n` and n bytes | Write n bytes, 1 to 255, to port 98h |
| Wait's start | `04` | The frames of a wait for a key start here |
| Wait's end | `05` | Play the frames since `04` again until a key is pressed |
| RETURN | `06` | Wait until the player presses RETURN, at the load command's RETURN |
| End | `FF` | The replay ends |

The stream starts with the first state, as port writes and VRAM bytes. A `02 A0h`
write and the `02 A1h` write after it are written together, with interrupts off, so
that the BIOS's interrupt handler, which selects PSG registers 14 and 15 for the
joysticks, cannot come between them.

### CAS data

A CAS file is a sequence of blocks, each starting with the 8-byte header
`1F A6 DE BA CC 13 7D 74` at an offset that is a multiple of 8. A file's first block
holds 10 bytes of its type and a 6-byte name: D0h for a binary file loaded with
`BLOAD"CAS:",R`, D3h for a BASIC program loaded with `CLOAD`, and EAh for an ASCII
program loaded with `RUN"CAS:"`. The capture stops with an error when the first
block has none of these types. The tape position is an offset in this data.

### Key names

The key names are the MSX keyboard matrix's special keys, which have the same place
on every keyboard layout.

| Row | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 6 | `shift` | `ctrl` | `graph` | `caps` | `code` | `f1` | `f2` | `f3` |
| 7 | `f4` | `f5` | `esc` | `tab` | `stop` | `bs` | `select` | `return` |
| 8 | `space` | `home` | `ins` | `del` | `left` | `up` | `down` | `right` |
