# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX1 or MSX2. `openMSX` loads
the game from its CAS file, in its own cassette player, on a copy of the user's
machine, and `snapcas` saves the machine's state when the game is ready. A program
on the real machine, the restorer, restores that state and transfers control to the
game. A game that loads further data during play also receives a tape service, which
supplies the rest of the tape from memory.

## Terms

| Term | Meaning |
|---|---|
| Page | One of the four 16 KB parts of the Z80's 64 KB address space: page 0 is 0000h to 3FFFh, page 3 is C000h to FFFFh |
| Slot, subslot | Where the memory in a page comes from: one of four primary slots, and in an expanded slot one of four subslots[^slots] |
| Slot ID | A slot in one byte: bit 7 set when expanded, bits 3 and 2 the subslot, bits 1 and 0 the primary slot |
| Segment | A 16 KB block of a memory mapper, selected into a page by the mapper registers at ports FCh to FFh |
| DOS's mapper | The mapper that holds DOS's four pages on the real machine |
| Snapshot | The emulated machine's state at one moment ([Capture](#capture)) |
| Image | `<GAME>.IMG`, the snapshot in the restorer's format ([Formats](#formats)) |
| Restorer | `<GAME>.COM`, the program that restores the image on the real machine |
| Worker | The part of the restorer that runs in page 1 or 2 while it changes the other pages |
| Tail | The last 24 bytes of the restore, written below the game's stack pointer |
| T0 | A RAM copy of the BIOS's page 0 whose tape routines are the tape service's ([Tape service](#tape-service)) |
| Scan | The search of the game's code for tape access that goes around T0 ([Scan](#scan)) |

## Files and commands

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` |
| `games/<game>/game.txt` | A person or an LLM | The game's settings |
| `games/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/<game>/<GAME>.IMG` | `tools/build.py` | The image |
| `out/<game>/<GAME>.COM` | `tools/build.py` | The restorer, copied from `bin/RESTORE.COM` |
| `out/<game>/scan.txt` | `tools/build.py` | The scan's findings and patches |
| `out/<game>/check/` | `tools/check.py` | Screenshots and the check's report |
| `bin/RESTORE.COM`, `bin/SLOTS.COM` | The developers | Built from `src/` with sjasmplus 1.24.0, and shipped |

Each game is processed by four commands, in this order:

1. `tools/capture.py <game> <machine> --cas <dir>` loads the game in `openMSX` and
   saves the snapshot ([Capture](#capture)). `<dir>` holds the user's CAS files.
2. `tools/build.py <game> <machine> --cas <dir>` writes the image, the restorer and
   `scan.txt` ([Build](#build)).
3. `tools/check.py <game> <machine> --dos <dir>` runs the restorer in `openMSX` and
   verifies the restore ([Check](#check)). `<dir>` holds the user's DOS system
   files.
4. The user copies `<GAME>.COM` and `<GAME>.IMG` to a disk of the real machine and
   runs `<GAME>`.

`<GAME>` is the game's folder name in upper case, cut to its first 8 letters and
digits. The tools are Python 3 programs that require only Python 3 and `openMSX`
22.0, so they run on macOS, Linux and Windows. They print errors on standard error,
naming the file and the problem, and exit with 0 on success, 1 for an error in the
input files, 2 when `openMSX` fails or a wait times out, and 3 when a check fails.

## Machine file

A machine file holds one `openmsx` line, one `disk` line and any number of `boot`
lines, as in this example for a Sanyo PHC-28S with a RAM cartridge and a Carnivore2:

```
openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2
disk hda
boot "Carnivore 2 MFC" esc
boot "DefConfig" space
```

| Line | Meaning |
|---|---|
| `openmsx` | The `openMSX` arguments that reproduce the machine |
| `disk` | The command that inserts `check.py`'s disk image: `hda` for an IDE interface, `diska` for a floppy drive |
| `boot` | A text on the screen during boot and the key to press when it appears; one line per key, matched in order |

`openMSX` puts each `-ext` cartridge in the next free external slot, so the order of
the `-ext` options sets the slots, and it must match the real machine's. `boot`
lines pass a cartridge's boot menu, such as the Carnivore2's; the tools read the
screen with `get_screen`, so such a menu must be in a text mode.

## Game file

A game file holds one setting per line ([Formats](#formats)). Only `cas` is
required. This example is for Gauntlet, which loads its levels from the tape's
second side:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
```

| Key | Meaning | Default |
|---|---|---|
| `cas` | The CAS file of side 1 | |
| `side2` | The CAS file of side 2 | None |
| `sha1` | The SHA-1 of `cas`, and of `side2` | None |
| `keys` | A time and a key or text that the capture presses then | None |
| `continue` | A key that the capture tries before space and Return, to continue a load that waits for a key | None |
| `snapshot` | `at` and a time, at which the capture takes the snapshot | Found by the capture |
| `patch` | A change to the snapshot's RAM or tape | None |

A patch fits only the dump that it was made for, so `build.py` stops with an error
when the game file has `patch` lines and `sha1` is missing or differs from a CAS
file's SHA-1.

## Shipped files

The repository ships game files and machine files, so that a user needs to write
neither for a known game or a common machine.

`games/` holds a game file for each game of File-Hunter's MSX CAS collection, named
after its File-Hunter file name, with the `sha1` of its dumps. Its `side2` and
`continue` lines come from running the capture, and its `patch` lines from
`check.py` and from traces of failed loads.

`machines/basic/` holds common configurations:

- An MSX1 with 64 KB and a Carnivore2 (Philips VG-8020).
- An MSX2 with its own mapper and a floppy drive, under MSX-DOS 2 (Philips NMS
  8250).
- An MSX2 with a Sunrise IDE interface, under Nextor.

`machines/advanced/` holds less common layouts:

- An MSX1 with 16 KB, a RAM cartridge in slot 1 and a Carnivore2 in slot 2 (Sanyo
  PHC-28S).
- An MSX1 with a MegaFlashROM SCC+ SD.
- An MSX2 whose slot 0 is expanded (Sony HB-F700P).

`check.py` checks each shipped machine file with a reference game. `SLOTS.COM`
confirms that a machine file matches a real machine: it prints the slot register,
`EXPTBL`, for each slot whether it is expanded and which pages hold RAM, and the
CRC-16 of the main ROM and the sub-ROM. `check.py` runs it in `openMSX` and prints
its output, which must equal its output on the real machine.

## Capture

`tools/capture.py` writes a Tcl script with the game file's settings and runs
`openmsx`, with the machine file's arguments and that script, with the throttle off,
the renderer off and the sound off. All times are emulated seconds. The script
writes the snapshot to `snap/` and quits, or writes `snap/error.txt` and quits when
a `boot` text or BASIC's `Ok` does not appear within 120 seconds, or the load runs
for more than 3,600 seconds. It performs the following steps:

1. Starts `openMSX`'s reverse recording, boots the machine with no disk, presses the
   `boot` keys, and waits for BASIC's `Ok`.
2. Removes the disk system from page 3 with `debug write`: RET (C9h) in every hook
   from FD9Ah to FFC9h and at `EXTBIO`, `DISINT` and `ENAINT`, so that nothing calls
   the disk system; 00h at F37Dh, which some loaders read to refuse to run with a
   disk system; and zeros from FCC9h to FD88h, `SLTATR` and `SLTWRK`, so that no
   extension ROM claims them and the tape service can use them.[^sys] It types
   `CLEAR200,&HF380`, which sets `HIMEM` to a cassette machine's F380h.[^clear]
3. Reads every page of every slot and subslot ([RAM](#ram)), inserts the CAS file of
   side 1 into the cassette player, and types the load command for the first
   header's type ([Formats](#formats)): `BLOAD"CAS:",R`, `CLOAD` followed by `RUN`,
   or `RUN"CAS:"`. Times in `keys` and `snapshot` count from this moment. Side 2 is
   never inserted.
4. Presses the `keys`, and follows the load:
   - Breakpoints at the addresses that the jump table entries 00E1h and 00E4h jump
     to, `TAPION` and `TAPIN`, while page 0 selects the main ROM, keep the tape
     position as the tape service would ([Tape service](#tape-service)).
   - Write watchpoints on port A8h and on FFFFh record every slot and subslot that
     the game selects in each page.
   - A write watchpoint on port A0h keeps the PSG register that was selected last.
5. Polls bit 4 of PPI port C, the cassette motor (0 = on),[^ports] every 0.1
   seconds, and waits until the motor has been off for 10 seconds, or the player has
   been at the tape's end (`cassetteplayer getpos` equal to `getlength`) for 10
   seconds. With `snapshot at`, it instead waits for that time and goes to step 6.
   Otherwise it goes back with the reverse recording to 1 second after the wait
   began, and proceeds:
   - If side 1 is read, it goes to step 6. Side 1 is read when the `TAPION` and
     `TAPIN` breakpoints never fired, or when every block after the tape position is
     under 16 bytes or equal to a block before it.
   - Otherwise it tries the keys that continue a load that waits for a key: the game
     file's `continue` key, then space, then Return, each from that same moment. If
     the motor starts within 10 seconds of a key, the load was waiting for that key,
     and step 5 restarts. If no key starts it, the remaining blocks are loaded
     during play, and it goes to step 6 from that moment.
6. Takes the snapshot when the CPU next accepts an interrupt and no VDP command is
   running (status register 2, bit 0, is 0). A probe breakpoint on `z80.acceptIRQ`
   marks the acceptance, and a breakpoint at the handler's address, 0038h in
   interrupt mode 1 or the word at I × 256 + FFh in mode 2, takes the snapshot
   there: the return address is pushed and interrupts are off. When no interrupt
   comes within 1 second, it takes the snapshot where the CPU is; a halted CPU then
   stops the capture with an error.

A load that waits for a choice that none of these keys makes, such as Gauntlet's
choice of players and character with the joystick, therefore gets its snapshot at
that screen. The player makes the choice on the real machine, and the tape service
supplies the rest of the load.

### RAM

The capture reads memory through the CPU's view, the `memory` debuggable, after it
selects a slot and subslot in the page with `debug write` on port A8h and on FFFFh,
and writes both back afterwards. This works for every device, including those that
expand their slot themselves, such as the Carnivore2. At the snapshot, a page of a
slot and subslot is RAM when a byte written at its first address with `debug write`
reads back, and so does its complement. A RAM page is in a mapper when writing
another value to its mapper register changes what the page shows; its segment is the
value in `MSX Memory Mapper I/O`.

The snapshot keeps each RAM page that the game selected during the load and whose 16
KB differ from step 3's. A mapper page whose segment step 3 did not see counts as
changed.

### Snapshot files

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each RAM page kept, by primary slot, subslot (`x` when not expanded) and page |
| `rom.bin` | 32 KB: pages 0 and 1 of the main ROM, from the slot that `EXPTBL` names |
| `subrom.bin` | 16 KB: the MSX2 sub-ROM, from the slot that `EXBRSA` names[^grauw] |
| `vram.bin` | The `physical VRAM` debuggable: 16 KB with an MSX1 VDP, 64 or 128 KB with a V9938 |
| `state.txt` | The registers, the RAM pages' segments and the tape position ([Formats](#formats)) |

| Register | Source in `openMSX` |
|---|---|
| CPU registers, interrupt mode, IFF1 | `reg` |
| Slot register and PPI port C | `debug read` on ports A8h and AAh |
| Subslot register of each expanded slot | The byte at FFFFh, inverted, read while page 3 selects that slot |
| Mapper registers | `MSX Memory Mapper I/O` |
| VDP registers | `VDP regs`: 0 to 7, or 0 to 23 and 32 to 45 on a V9938 |
| Palette | `VDP palette` |
| VRAM pointer | `VRAM pointer`, 14 bits, with bits 14 to 16 from register 14 |
| VRAM access | `VRAM access status`: 1 after a write setup, 0 after a read setup |
| VDP latches | `VDP register latch status`, `VDP data latch value`, `VDP palette latch status` |
| PSG registers | `PSG regs`, and port A0h's watchpoint |

## Build

`tools/build.py` writes the image ([Formats](#formats)) and copies `bin/RESTORE.COM`
to `<GAME>.COM` with the image's name at 0103h, because MSX-DOS 1 does not tell a
program its own name. It also:

- Keeps the 16 KB blocks of `vram.bin` that are not all zeros.
- Turns the PSG, PPI and VDP state into a list of port writes, in the order that the
  restorer performs them ([Port writes](#port-writes)).
- Writes the tail into the 24 bytes below the stack pointer. At an interrupt's entry
  these bytes are free, because the handler that runs next pushes onto them. It
  stops with an error when they cross a page boundary, include FFFFh, or are not in
  a RAM page that the snapshot keeps.
- With the tape service, builds T0 and the tape segments from `rom.bin` and the CAS
  files, writes the entries into the game's page 3, runs the scan, applies the
  `patch` lines and the scan's patches, and writes the fix-ups that the restorer
  fills in with segment numbers ([Tape service](#tape-service)).
- Prints the number of mapper segments that the image requires.

## Restorer

`<GAME>.COM` runs under MSX-DOS 1, MSX-DOS 2 or Nextor. It holds the worker twice,
assembled to run in page 1 and in page 2. It performs the following steps, and until
step 4 it can stop with a message and return to DOS:

1. Reads the image's first 4,096 bytes, the header and its tables, with the FCB
   functions `_FOPEN`, `_SETDTA` and `_RDBLK`,[^fcb] and checks:
   - That `RAMAD0` to `RAMAD3` name one slot, DOS's mapper.[^grauw]
   - That the CRC-16 of the main ROM and of the sub-ROM equal the image's. The
     worker reads them in page 2, with pages 0 and 1 selecting the ROM.
   - That page 1 or page 2 can hold the worker at the end: a page other than the
     tail's whose bits, when DOS's mapper is in an expanded slot, select DOS's
     mapper's subslot in the snapshot's subslot register of that slot.
2. Allocates every free segment of DOS's mapper: under MSX-DOS 2 and Nextor with
   `ALL_SEG` until it fails;[^dos2] under MSX-DOS 1, segments 4 and up, because DOS
   runs in segments 3 to 0. MSX-DOS 1 gives no count, so, with interrupts off and
   through page 2, the restorer saves the first byte of segments 0 to 3, writes each
   segment's number into its first byte from 255 down to 0, reads them back from 4
   up to the first mismatch, and restores the saved bytes. It then assigns the
   segments:
   - A RAM page of DOS's mapper whose own segment is free goes straight into it.
   - Each other RAM page of DOS's mapper gets a holding segment, copied into its own
     segment in step 6.
   - Each service segment, the worker and a read buffer get one segment each.

   It stops when there are too few, naming the segments needed and free.
3. Reads the records, 16 KB each, in the image's order, and places each one:
   - A RAM page of DOS's mapper, or a service segment, is read into its segment
     through page 2.
   - A RAM page of another slot is read into the buffer. The worker selects the
     target slot and subslot in the target page, with only that page's bits of the
     subslot register changed, sets the page's mapper register to the record's
     segment when it has one, copies the page, reads it back, and selects DOS's
     pages again, all with interrupts off. In an expanded slot, the copy of page 3
     stops at FFFEh, because FFFFh is the subslot register. A mismatch stops the
     restorer: the machine file does not describe this machine.
   - A VRAM block is written to the VDP through ports 98h and 99h, and register 14,
     with interrupts off and the display blanked by writing register 1 with
     `RG1SAV`'s value and bit 6 clear.[^sys] DOS's text mode has no planar layout,
     so the bytes go to VRAM as they are stored.

   It applies the fix-ups to each record as it arrives. With the tape service, when
   the snapshot's page 0 selects the main ROM, it selects T0 there instead: page 0's
   slot becomes DOS's mapper, mapper register FCh T0's segment, and, in an expanded
   slot, the subslot register's page 0 bits DOS's mapper's subslot, also in `SLTTBL`
   in the game's page 3 record.
4. Waits until `JIFFY` has advanced by 180, so that a floppy drive's motor stops,
   then disables interrupts. From this point on, it calls neither DOS nor the BIOS.
5. Performs the port writes.
6. The worker, in the page that step 1 found, copies each holding segment into its
   own segment through the two other pages below page 3, then writes the subslot
   register of each expanded slot while page 3 selects that slot, ending with the
   snapshot's page 3 slot, the mapper registers of the three other pages, and the
   slot register with its own page still selecting DOS's mapper. It loads every
   register except AF and SP, sets I and the interrupt mode, and jumps to the tail.
7. The tail writes the worker's page's mapper register and the slot register, loads
   AF and SP, enables interrupts when IFF1 is set, and jumps to the program counter.
   The R register is not restored.

## Tape service

The tape service exists in the image of a game whose side 1 is not read
([Capture](#capture)) or that has a `side2` file. It keeps the tape in mapper
segments and has these parts:

| Part | Location | Function |
|---|---|---|
| T0 | A segment | The BIOS's page 0 with the service's routines from 19DDh to 1B44h |
| Tape data | Segments | Side 1, padded with zeros to a multiple of 8 bytes, then side 2 |
| Entries | FCE1h, FCE4h, FCE7h, in `SLTATR` | Jumps to `TAPION`, `TAPIN` and `TAPIOF` for code that goes around T0 |
| Entry code | `SLTWRK` | Selects T0 in page 0, calls the routine, and selects the game's page 0 again |
| Reader | `SLTWRK` | `OUT (C),D / LD E,(HL) / OUT (C),B / RET`: reads a tape byte |

`build.py` builds T0 from `rom.bin`, so it first checks that each jump table entry
below jumps to its address, as in the standard MSX BIOS. The restorer's ROM check
ensures that the real ROM equals `rom.bin`.[^tape]

| Entry | Routine | Address it must jump to |
|---|---|---|
| 00E1h | `TAPION` | 1A63h |
| 00E4h | `TAPIN` | 1ABCh |
| 00E7h | `TAPIOF` | 19E9h |
| 00EAh | `TAPOON` | 19F1h |
| 00EDh | `TAPOUT` | 1A19h |
| 00F0h | `TAPOOF` | 19DDh, the start of the tape code |
| 0018h | `OUTDO` | 1B45h, the first byte after the tape code |

`build.py` writes the service's routines, their data and a table of up to 64 tape
segments over the 360 bytes from 19DDh to 1B44h, and points the jump table entry
00F3h, `STMOTR`, at its routine, because the BIOS's code, at 1384h on an MSX1 and
1387h on an MSX2, is outside that range. The routines behave as the BIOS's: carry is
clear on success and set when CTRL+STOP is held.

| Routine | What it does |
|---|---|
| `TAPION` | Disables interrupts and moves the tape position past the next CAS header at a multiple of 8 bytes ([Formats](#formats)) |
| `TAPIN` | Returns the byte at the tape position in A, and advances the position |
| `TAPIOF`, `TAPOOF` | Enable interrupts and return |
| `TAPOON`, `TAPOUT` | Return with carry set: the tape cannot be written |
| `STMOTR` | Returns |

`TAPIN` reads a byte through the reader in page 3: with C = FCh, D the byte's tape
segment and B T0's segment, the reader selects the tape segment in page 0, reads the
byte at HL into E, and selects T0 again. The entry code disables interrupts,
switches to its own stack in `SLTWRK`, selects DOS's mapper and T0 in page 0, calls
the routine, and selects the game's page 0 and stack again. It returns with
interrupts off, except after `TAPIOF`. Because the restorer leaves DOS's mapper's
subslot in page 0 of an expanded slot, selecting T0 changes only the slot register
and mapper register FCh.

The tape position starts where the game stopped reading at the snapshot, and moves
on these events. The routines read the keyboard matrix through the PPI.

| Event | New position |
|---|---|
| `TAPION` or `TAPIN` reads past side 1's end | Side 2's start, as when the player turns the tape over; side 1's start when there is no side 2 |
| `TAPION` or `TAPIN` reads past side 2's end | Side 2's start, as after a rewind |
| `TAPION` is called while STOP is held without CTRL | The start of the current side |
| `TAPION` is called while SELECT is held | The start of the other side |

## Scan

With the tape service, `build.py` scans the snapshot's RAM pages and the unread
blocks for code that reaches the tape without going through T0, applies the patches,
and lists each finding and patch in `scan.txt`:

| Code | Instructions | Patch |
|---|---|---|
| A stub built with `TAPION`'s entry | `LD DE,00E1h / PUSH DE / LD DE,CDD9h / PUSH DE`, or the same with HL | The pushed address's high byte becomes FCh |
| A tape call after the ROM is selected in page 0 | `IN A,(0A8h) / AND 0F0h / OUT (0A8h),A`, which selects slot 0 in pages 0 and 1, then `CALL 00E1h` or `CALL 00E4h` | The call's high byte becomes FCh |
| A reader of the cassette signal | `IN A,(0A2h)`, then a test of bit 7, in a loop | None: listed, for a `patch` line that sends its callers to the service |

The stub stores `TAPION`'s address in RAM, and the game later changes its low byte
to E4h for `TAPIN`, so the entries keep the BIOS's low bytes. A stub that pushes
00EAh, `TAPOON`, writes the tape, and the scan leaves it alone. A patch in code that
ran only during the load is harmless.

## Check

`tools/check.py` makes a disk image with `openMSX`'s `diskmanipulator`, with the
`--dos` folder's files, the restorer, the image and an `AUTOEXEC.BAT` that runs
`<GAME>`. The folder holds `NEXTOR.SYS` and `COMMAND2.COM`, `MSXDOS2.SYS` and
`COMMAND2.COM`, or `MSXDOS.SYS` and `COMMAND.COM`, which `snapcas` cannot ship.
`check.py` boots the machine with that disk and the `boot` keys, and writes its
report to `check/report.txt`:

1. A breakpoint at the tail's last instruction compares the machine with the
   snapshot: the kept RAM pages, the stored VRAM blocks and the registers must be
   equal. The exceptions are the tail's bytes, FCC9h to FD88h, the patched bytes, R,
   and, when T0 replaces the ROM, page 0's slot, mapper register FCh, the subslot
   register's page 0 bits and `SLTTBL`. A difference fails the check.
2. The game runs for 60 seconds, with a screenshot every 10 seconds in `check/`, and
   a breakpoint on each scan finding reports which findings the game executes.

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
| Port writes and T0 made by `build.py` | The restorer only copies records, fills in segment numbers and performs writes in order |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| Scan the snapshot and the unread blocks | A search of the 1,653 files of File-Hunter's MSX CAS collection for files that leave over 10% and 2 KB unread in a test load and hold a rewind or play prompt found 62 files of 51 games; 20 of those games build stubs that T0 alone does not intercept |
| A tape with both sides, a wrap, and fixed rewind and flip keys | In 41 of those 51 games the unread blocks have no names, so only the tape's position decides which block a game reads, as with a real tape |

## Limits

- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- DOS's four pages must be in one memory mapper. Under MSX-DOS 1, that mapper must
  hold DOS in segments 3 to 0, as the MSX2 BIOS and Nextor set them.
- The restorer needs a page 1 or 2 that selects DOS's mapper at the end
  ([Restorer](#restorer), step 1).
- A game that needs the tape service runs only on a machine whose BIOS keeps its
  tape code where the standard MSX BIOS does, and only if it leaves FCC9h to FD88h
  unused. `build.py` stops with an error when those bytes are not zero at the
  snapshot.
- A game that reads the tape with its own code gets no tape service, so it runs only
  if it loads in a single pass. The scan lists such readers for a `patch` line.
- Code that selects the BIOS ROM in page 0 and calls the tape in a way that the scan
  does not recognize does not reach the tape service.
- A snapshot taken without an interrupt overwrites the 24 bytes below the stack
  pointer with the tail.

## Not in the first version

- MSX2+ and turbo R: the V9958's registers above 23 and the turbo R's R800 mode.

## Formats

### Image

All numbers are little-endian, and the CRC-16 is CRC-16/CCITT-FALSE: polynomial
1021h, initial value FFFFh, not reflected, no final XOR. The image holds 4,096 bytes
of header and tables, padded with zeros, then each record's 16,384 bytes in table
order: the RAM pages, then the service segments, then the VRAM blocks.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | `SNAPCAS1` |
| 8 | 2 | CRC-16 of the main ROM's 32 KB |
| 10 | 2 | CRC-16 of the sub-ROM's 16 KB, or 0 on an MSX1 |
| 12 | 1 | Number of records |
| 13 | 1 | Number of fix-ups |
| 14 | 1 | Number of port writes |
| 15 | 1 | T0's record number, or FFh without the tape service |
| 16 | 24 | AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC |
| 40 | 1 | I |
| 41 | 1 | Interrupt mode |
| 42 | 1 | IFF1: 1 when interrupts are on |
| 43 | 1 | Slot register |
| 44 | 4 | Subslot registers of slots 0 to 3, 0 when not expanded |
| 48 | 4 | Mapper registers FCh to FFh |
| 52 | 2 | Tail address |
| 54 | 10 | Zero |
| 64 | 4 per record | Record table |
| | 4 per fix-up | Fix-up table |
| | 2 per port write | Port writes: port, value |

| Record byte | RAM page | Service segment | VRAM block |
|---|---|---|---|
| 0 | 1 | 2 | 3 |
| 1 | Slot ID | 0 | Block number, 0 to 7 |
| 2 | Page | 0 | 0 |
| 3 | Segment, or FFh when not in a mapper | 0 | 0 |

A fix-up holds a record number, a 2-byte offset in that record, and the number of a
service segment's record: the restorer writes that service segment's segment number
at the offset. The fix-ups give T0 its tape segments and the reader's T0 segment,
and the entry code T0's segment.

### Port writes

`build.py` lists the writes in this order:

1. For each PSG register from 0 to 15, its number to port A0h and its value to port
   A1h, with register 7's bits 7 and 6 forced to 1 and 0; then the last selected
   register to port A0h.[^ports]
2. PPI port C to port AAh.
3. On a V9938: 0 to register 16, the 16 palette entries to port 9Ah, 2 bytes each,
   then 32 with auto-increment to register 17 and registers 32 to 45 to port
   9Bh.[^v9938]
4. VDP registers 0 to 7, or 0 to 23, to port 99h, as a value and 80h plus the
   register's number.
5. The VRAM pointer to port 99h: its low byte, then its high bits with 40h for a
   write setup. A read setup writes the pointer minus 1, because the VDP reads ahead
   and advances the pointer.
6. The first byte held in the VDP register latch to port 99h, and the one held in
   the palette latch to port 9Ah, when the snapshot holds them.

### CAS data

A CAS file is a sequence of blocks, each starting with the 8-byte header
`1F A6 DE BA CC 13 7D 74` at an offset that is a multiple of 8. A file's first block
holds 10 bytes of its type and a 6-byte name: D0h for a binary file loaded with
`BLOAD"CAS:",R`, D3h for a BASIC program loaded with `CLOAD`, and EAh for an ASCII
program loaded with `RUN"CAS:"`. The capture stops with an error when the first
block has none of these types. The tape position is an offset in this data: `TAPION`
moves it past the next header, and `TAPIN` past one byte.

### `state.txt`

One `name value` per line, values in hexadecimal:

- `af`, `bc`, `de`, `hl`, `af2`, `bc2`, `de2`, `hl2`, `ix`, `iy`, `sp`, `pc`, `i`,
  `im`, `iff1`.
- `a8`, `sub0` to `sub3`, `fc` to `ff`, `ppic`.
- `psg0` to `psg15`, `psgsel`.
- `vdp` (`msx1` or `v9938`), `vdp0` to `vdp23`, `vdp32` to `vdp45`, `pal0` to
  `pal15`, `vramptr`, `vramwrite`, `reglatch` and `pallatch` (the held byte, or
  `-`).
- `ram <ps>-<ss>-<page>` and the page's segment, or `-` when not in a mapper.
- `tapepos`, the tape position in side 1, or `-` when the BIOS read nothing.

### Game file

One setting per line: a key, a space and a value. A line that starts with `#` is a
comment, and blank lines are ignored. Times are decimal emulated seconds; addresses
and bytes are hexadecimal.

| Key | Value |
|---|---|
| `cas`, `side2` | A file name in the `--cas` folder |
| `sha1` | The 40-digit SHA-1 of `cas`, then that of `side2` when there is one |
| `keys` | A time, then a key name, held for 0.1 seconds, or a text in quotes that `openMSX` types; one press per line |
| `continue` | A key name |
| `snapshot` | `at` and a time |
| `patch` | A place, the old bytes, `>`, the new bytes: `patch 1-x-3:0D31 CD E1 00 > CD E1 FC` |

A place is a RAM page as `<ps>-<ss>-<page>:<offset>`, or the tape as
`side1:<offset>` or `side2:<offset>`. `build.py` stops with an error when the old
bytes differ.

### Key names

The key names are the MSX keyboard matrix's special keys, which have the same place
on every keyboard layout.[^keys]

| Row | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 6 | `shift` | `ctrl` | `graph` | `caps` | `code` | `f1` | `f2` | `f3` |
| 7 | `f4` | `f5` | `esc` | `tab` | `stop` | `bs` | `select` | `return` |
| 8 | `space` | `home` | `ins` | `del` | `left` | `up` | `down` | `right` |

[^slots]: Slot register at port A8h, subslot register at FFFFh, which reads back
    inverted: MSX Red Book, chapter 1.
[^sys]: The hooks from FD9Ah to FFC9h, `SLTATR` at FCC9h, `SLTWRK` at FD09h, `SLTTBL`
    at FCC5h, `HIMEM` at FC4Ah, `JIFFY` at FC9Eh and `RG1SAV` at F3E0h: MSX Red
    Book, chapter 6. `EXTBIO` at FFCAh, `DISINT` at FFCFh and `ENAINT` at FFD4h:
    map.grauw.nl, system variables.
[^clear]: `CLEAR` sets `HIMEM` and accepts no value above F380h: MSX Red Book, chapter
    5.
[^tape]: The jump table entries of `TAPION`, `TAPIN`, `TAPIOF`, `TAPOON`, `TAPOUT`,
    `TAPOOF`, `STMOTR` (00F3h) and `OUTDO`, and the routines' addresses in the
    standard BIOS: MSX Red Book, chapter 4.
[^ports]: VDP ports 98h and 99h, and VDP registers 0 to 7: MSX Red Book, chapter 2.
    PSG ports A0h, A1h and A2h, and registers 7, 14 and 15: chapter 3. PPI port C at
    AAh, whose bit 4 controls the cassette motor: chapter 1.
[^v9938]: V9938 registers 0 to 45, register 14 for VRAM above 16 KB, register 17's
    indirect access through port 9Bh, and the palette port 9Ah: MSX2 Technical
    Handbook, chapter 4.
[^grauw]: `EXBRSA` at FAF8h, the slot of the sub-ROM, and `RAMAD0` to `RAMAD3` at
    F341h to F344h, DOS's RAM slots: map.grauw.nl, system variables.
[^dos2]: `ALL_SEG`, through the jump table that `EXTBIO` returns: MSX-DOS 2 Program
    Interface Specification, sections 5.2 and 5.4.
[^fcb]: `_FOPEN` 0Fh, `_SETDTA` 1Ah and `_RDBLK` 27h, the FCB functions of MSX-DOS 1
    that MSX-DOS 2 keeps: MSX-DOS 2 Function Codes Specification.
[^keys]: The keyboard matrix, rows 6 to 8: MSX Red Book, chapter 1.
