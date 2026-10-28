# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX1 or MSX2. `openMSX` loads
the game from its CAS file, in its own cassette player, on a copy of the user's
machine, and `snapcas` saves the machine's state when the game is ready. A program
on the real machine, the restorer, restores that state and transfers control to the
game. A game that loads further data during play also receives a tape service, which
supplies the rest of the tape.

## Terms

| Term | Meaning |
|---|---|
| Page | One of the four 16 KB parts of the Z80's 64 KB address space: page 0 is 0000h to 3FFFh, page 3 is C000h to FFFFh |
| Slot, subslot | Where the memory in a page comes from: one of four primary slots, and in an expanded slot one of four subslots[^slots] |
| Segment | A 16 KB block of a memory mapper, selected into a page by the mapper registers at ports FCh to FFh |
| Snapshot | The emulated machine's state at one moment ([Capture](#capture)) |
| Image | `<GAME>.IMG`, the snapshot in the restorer's format ([Formats](#formats)) |
| Restorer | `<GAME>.COM`, the program that restores the image on the real machine |
| Tail | The last code of the restore, written into the game's RAM ([Restorer](#restorer)) |
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
| `out/<game>/scan.txt` | `tools/build.py` | The scan's findings |
| `out/<game>/check/` | `tools/check.py` | Screenshots and the check's report |
| `bin/RESTORE.COM`, `bin/SLOTS.COM` | The developers | Built from `src/` with sjasmplus 1.24.0, and shipped |

Each game is processed by four commands, in this order:

1. `tools/capture.py <game> <machine> --cas <dir>` loads the game in `openMSX` and
   saves the snapshot ([Capture](#capture)). `<dir>` holds the user's CAS files.
2. `tools/build.py <game> <machine> --cas <dir>` writes the image, the restorer and
   the scan's findings ([Build](#build)).
3. `tools/check.py <game> <machine>` runs the restorer in `openMSX` and verifies the
   restore ([Check](#check)).
4. The user copies `<GAME>.COM` and `<GAME>.IMG` to a disk of the real machine and
   runs `<GAME>`.

The tools are Python 3 programs that require only Python 3 and `openMSX` 22.0, so
they run on macOS, Linux and Windows. They print errors on standard error, naming
the file and the problem, and exit with 0 on success, 1 for an error in the input
files, 2 when `openMSX` fails or a wait times out, and 3 when a check fails.

## Machine file

A machine file holds one `openmsx` line, one `disk` line, one `dos` line and any
number of `boot` lines, as in this example for a Sanyo PHC-28S with a RAM cartridge
and a Carnivore2:

```
openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2
disk hda
dos /home/me/msx/nextor
boot "Carnivore 2 MFC" esc
boot "DefConfig" space
```

| Line | Meaning |
|---|---|
| `openmsx` | The `openMSX` arguments that reproduce the machine |
| `disk` | The command that inserts `check.py`'s disk image: `hda` for an IDE interface, `diska` for a floppy drive |
| `dos` | A folder with the DOS system files that `check.py` puts on its disk |
| `boot` | A text on the screen during boot and the key to press when it appears; one line per key, matched in order |

`openMSX` puts each `-ext` cartridge in the next free external slot, so the order of
the `-ext` options sets the slots, and it must match the real machine's.
`bin/SLOTS.COM` confirms it ([Shipped files](#shipped-files)). `boot` lines pass a
cartridge's boot menu, such as the Carnivore2's; the capture reads the screen with
`get_screen`, so such a menu must be in a text mode. The `dos` folder holds
`NEXTOR.SYS` and `COMMAND2.COM`, `MSXDOS2.SYS` and `COMMAND2.COM`, or `MSXDOS.SYS`
and `COMMAND.COM`, which `snapcas` cannot ship.

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
| `rewind` | The key that sends the tape to the start of its side | STOP, without CTRL |
| `flip` | The key that turns the tape over | SELECT |
| `entry` | The high byte of the page 3 address of the tape service's entries | FCh |
| `tail` | A page 3 address for the tail | Below the stack pointer |
| `patch` | A change to the snapshot's RAM or tape | None |
| `probe` | A tape routine for `check.py` to run, with registers and the expected block | The scan's findings |

A patch fits only the dump that it was made for, so `build.py` stops with an error
when the game file has `patch` lines and a CAS file's SHA-1 differs from `sha1`.

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

`check.py` checks each shipped machine file with a reference game. To confirm that a
machine file matches the real machine, the user runs `SLOTS.COM` on the real
machine. It prints the slot register, `EXPTBL`, for each slot whether it is expanded
and which pages hold RAM, and the CRC-16 of the main ROM and the sub-ROM. `check.py`
runs `SLOTS.COM` in `openMSX`, reads its output with `get_screen`, and prints it;
the two outputs must match.

## Capture

`tools/capture.py` writes a Tcl script with the game file's settings and runs
`openmsx`, with the machine file's arguments and that script, with the throttle off,
the renderer off and the sound off. All times are emulated seconds. The script
writes the snapshot to `snap/`, or `snap/error.txt` when a wait exceeds 120 seconds,
and quits. It performs the following steps:

1. Starts `openMSX`'s reverse recording, boots the machine with no disk, presses the
   `boot` keys, and waits for BASIC's `Ok`.
2. Removes the disk system from page 3 with `debug write`: RET (C9h) in every hook
   from FD9Ah to FFC9h and at `EXTBIO`, `DISINT` and `ENAINT`, so that nothing calls
   the disk system; 00h at F37Dh, which some loaders read to refuse to run with a
   disk system; and zeros in `SLTATR` and `SLTWRK`, so that no extension ROM claims
   them.[^sys] It types `CLEAR200,&HF380`, which sets `HIMEM` to a cassette
   machine's F380h.[^clear]
3. Inserts the CAS file of side 1 into the cassette player and types the load
   command for the first header's type ([Formats](#formats)): `BLOAD"CAS:",R`,
   `CLOAD` followed by `RUN`, or `RUN"CAS:"`. Times in `keys` and `snapshot` count
   from this moment.
4. Presses the `keys`, and counts the tape's progress: a breakpoint at 1A63h, the
   BIOS's `TAPION` code, and one at 1ABCh, its `TAPIN` code,[^tape] keep the number
   of headers read and the bytes read since the last one.
5. Waits until the cassette motor, bit 4 of PPI port C (0 = on),[^ports] has been
   off for 10 seconds. With `snapshot at`, it instead waits for that time and goes
   to step 6. Otherwise it goes back with the reverse recording to 1 second after
   the motor stopped, and proceeds:
   - If the game has read every block of side 1, except trailing blocks under 16
     bytes and blocks identical to a block before them, it goes to step 6.
   - Otherwise it tries the keys that continue a load that waits for a key: the game
     file's `continue` key, then space, then Return, each from that same moment. If
     the motor starts within 10 seconds of a key, the load was waiting for that key,
     and step 5 restarts. If no key starts it, the remaining blocks are loaded
     during play, and it goes to step 6 from that moment.
6. Runs until the CPU accepts the next interrupt, at 0038h in interrupt mode 1 or at
   the vector's target in mode 2, and takes the snapshot at that instruction. When
   no interrupt comes within 1 second, it takes the snapshot where the CPU is, and
   the game file needs a `tail` line.

A load that waits for a choice that none of these keys makes, such as Gauntlet's
choice of players and character with the joystick, therefore gets its snapshot at
that screen. The player makes the choice on the real machine, and the tape service
supplies the rest of the load ([Tape service](#tape-service)).

The snapshot holds these files:

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each page that holds RAM, by primary slot, subslot (`x` when not expanded) and page |
| `rom.bin` | 32 KB: pages 0 and 1 of the main ROM |
| `subrom.bin` | 16 KB: the MSX2 sub-ROM |
| `vram.bin` | All of video RAM |
| `state.txt` | The registers and the tape position ([Formats](#formats)) |

The capture reads the RAM pages, `rom.bin` and `subrom.bin` from the
`slotted memory` debuggable. A page holds RAM when its device in `slotmap` is RAM or
a memory mapper; the main ROM is in the slot that `EXPTBL` names, and the sub-ROM in
the one that `EXBRSA` names.[^exbrsa] For a mapper, the pages are the four segments
selected at the snapshot. Video RAM comes from the `VRAM` debuggable, whose size
gives the VDP type: 16 KB for an MSX1 VDP, 64 or 128 KB for a V9938.

| Register | Source in `openMSX` |
|---|---|
| CPU registers, interrupt mode and state | `reg` |
| Slot register and PPI port C | `debug read` on ports A8h and AAh |
| Subslot register of each expanded slot | The byte at FFFFh, inverted, read while a `debug write` to port A8h selects that slot in page 3; port A8h is then written back |
| Mapper registers | `MSX Memory Mapper I/O` |
| VDP registers, palette | `VDP regs` (0 to 7, or 0 to 23 on a V9938), `VDP palette` |
| VRAM pointer and VDP latches | `VRAM pointer`, `VRAM access status`, `VDP register latch status`, `VDP data latch value` |
| PSG registers 0 to 15 | `PSG regs` |

## Build

`tools/build.py` writes the image ([Formats](#formats)) and copies `bin/RESTORE.COM`
to `<GAME>.COM` with the image's name written at a fixed offset, because MSX-DOS 1
does not tell a program its own name. It also:

- Keeps the VRAM blocks that the game uses: all 16 KB blocks in screen modes 5 to 8,
  and otherwise the blocks that the VDP's table base registers point into.
- Writes the tail into the game's page 3: below the stack pointer when the stack
  pointer is in page 3 and the 64 bytes below it hold neither C000h's page boundary
  nor FFFFh, and otherwise at `tail`. At an interrupt's entry, the bytes below the
  stack pointer hold nothing, because the handler that runs next pushes onto them.
- With the tape service: writes the service's entries and their code into the game's
  page 3, and its routines into the image ([Tape service](#tape-service)), runs the
  scan, and checks `rom.bin`'s jump table.
- Prints the number of mapper segments that the restorer needs: the RAM pages in the
  mapper, T0, and the tape data at 16,380 bytes per segment.

It stops with an error when the tail or the entries have no free place.

## Restorer

`<GAME>.COM` runs under MSX-DOS 1, MSX-DOS 2 or Nextor, and requires DOS's own
memory to be in a memory mapper. It performs the following steps:

1. Computes the CRC-16 of the main ROM and of the sub-ROM through `RDSLT`, and stops
   with a message when they differ from the image's: the machine file does not
   describe this machine.[^rdslt]
2. Finds free mapper segments in DOS's mapper: under MSX-DOS 2 and Nextor with
   `ALL_SEG` from the primary mapper;[^dos2] under MSX-DOS 1, the segments above the
   four it maps, counted by writing each segment's number into its first byte from
   the highest down and reading them back from 4 up, with segments 0 to 3's first
   bytes saved and restored. It stops with a message, naming the segments needed and
   free, when there are too few.
3. Reads the image with the FCB functions `_FOPEN`, `_SETDTA` and `_RDBLK`,[^fcb] 16
   KB at a time, and places each part as it arrives:
   - A VRAM block goes to the VDP, with the display blanked (register 1, bit 6, 0)
     and interrupts off.
   - A RAM page in a mapper goes into a free segment, which takes the place of the
     segment that the snapshot had selected; the tail selects it. A RAM page in a
     mapper other than DOS's stops the restorer with a message.
   - Any other RAM page is copied to its slot, subslot and page with interrupts off,
     by code in a page other than its target. In an expanded slot, the copy of page
     3 stops at FFFEh, because FFFFh is the subslot register.
   - The tape service's routines and the tape data go into free segments.
4. With the tape service, builds T0: copies page 0 of the main ROM into a free
   segment, checks its jump table ([Tape service](#tape-service)), writes the
   service's routines at 19DDh and a jump to them at 00F3h, `STMOTR`'s entry, and
   writes the segment numbers into T0 and into the entries in the game's page 3.
5. Waits 3 seconds with interrupts on, so that a floppy drive's motor stops, then
   disables interrupts. From this point on, it calls neither DOS nor the BIOS.
6. Writes the PSG registers 0 to 15 through ports A0h and A1h, with register 7's
   bits 7 and 6 forced to 1 and 0, PPI port C through port AAh, and the VDP:[^ports]
   - An MSX1 VDP: registers 0 and 2 to 7, then the VRAM pointer.
   - A V9938: registers 0 and 2 to 23 except 14 to 16, the palette through port 9Ah,
     registers 16, 15 and 14, then the VRAM pointer.[^v9938]

   It then writes the VDP register latch's first byte, when the snapshot holds one,
   and register 1 last.
7. Sets the subslot register of each expanded slot that holds no memory of DOS's,
   while page 3 selects that slot.
8. Selects the game's page 3 and jumps to the tail. The code that does it runs in a
   page of DOS's mapper whose subslot stays the same in the snapshot's subslot
   register of that slot, writes that register when the slot is expanded, then
   writes mapper register FFh and the slot register's page 3 bits. When no such page
   exists, `build.py` has already stopped with an error.
9. The tail writes the subslot register of the game's page 3 slot, when it is
   expanded and is not DOS's, then mapper registers FCh to FEh and the slot
   register, loads the CPU registers, the I register and the interrupt mode, and
   jumps to the snapshot's program counter with interrupts off, as the CPU left them
   when it accepted the interrupt. The R register is not restored.

## Tape service

The tape service exists only in the image of a game with unread blocks or a `side2`
file. It keeps the tape in mapper segments, both sides complete, and has these
parts:

| Part | Location | Function |
|---|---|---|
| T0 | A segment, in page 0 in place of the BIOS ROM | The BIOS with the service's routines from 19DDh |
| Tape data | Segments, 16,380 bytes each | Side 1, then side 2, as in the CAS files |
| Entries | `XXE1h`, `XXE4h`, `XXE7h`, where XX is `entry` | `TAPION`, `TAPIN` and `TAPIOF` for code that goes around T0 |
| Entry code | `SLTWRK` | Selects T0, calls the routine, restores the slots |
| `H.PARD` | FEB2h | Calls the entry code that selects T0, before each BASIC device load[^tape] |

T0 replaces the BIOS's tape code at the addresses that the standard MSX BIOS uses,
so `build.py` checks `rom.bin`, and the restorer the real ROM: each jump table entry
below must jump to its address.[^tape]

| Entry | Routine | Address it must jump to |
|---|---|---|
| 00E1h | `TAPION` | 1A63h |
| 00E4h | `TAPIN` | 1ABCh |
| 00E7h | `TAPIOF` | 19E9h |
| 00EAh | `TAPOON` | 19F1h |
| 00EDh | `TAPOUT` | 1A19h |
| 00F0h | `TAPOOF` | 19DDh, the start of the tape code |
| 0018h | `OUTDO` | 1B45h, the first byte after the tape code |

The service's routines fit the 360 bytes from 19DDh to 1B44h, and behave as the
BIOS's, with carry clear on success and carry set on CTRL+STOP:

| Routine | What it does |
|---|---|
| `TAPION` | Moves the tape position past the next CAS header ([Formats](#formats)) |
| `TAPIN` | Returns the tape's next byte in A; past a block's end, the next block's CAS header follows, as in the CAS file |
| `TAPIOF` | Returns |
| `TAPOON`, `TAPOUT`, `TAPOOF` | Return with carry set: the tape cannot be written |
| `STMOTR` | Returns, through the jump at 00F3h, because the BIOS's code at 1384h is outside the replaced range |

`TAPIN` reads a byte by selecting the byte's segment in page 0, from code in T0: T0
holds `OUT (C),D` at 3FFAh and `RET` at 3FFFh, and each tape segment holds
`LD E,(HL)` and `OUT (C),B` at 3FFCh, which read the byte into E and select T0
again. The entry code switches to its own stack in `SLTWRK`, and the restorer sets
the mapper slot's page 0 subslot to the mapper before the game starts, so that
selecting T0 changes only the slot register and mapper register FCh.

The tape position starts at the next byte that the game had not read at the
snapshot, and moves on these events:

| Event | New position |
|---|---|
| `TAPION` or `TAPIN` reads past side 1's last block | Side 2's first block, as when the player turns the tape over; side 1's first block when there is no side 2 |
| `TAPION` or `TAPIN` reads past side 2's last block | Side 2's first block, as after a rewind |
| `TAPION` is called while the `rewind` key is held | The first block of the current side |
| `TAPION` is called while the `flip` key is held | The first block of the other side |

`H.PARD` reaches `LOAD`, `BLOAD`, `RUN` and `OPEN` on `CAS:`. `CLOAD` does not call
it, so a BASIC program that selects the ROM in page 0 and then uses `CLOAD` is not
covered.

## Scan

With the tape service, `build.py` scans the snapshot's RAM pages and the unread
blocks for code that reaches the tape without going through T0, and writes its
findings to `scan.txt`:

| Code | Instructions | Patch |
|---|---|---|
| A stub built with `TAPION`'s entry | `LD DE,00E1h / PUSH DE / LD DE,CDD9h / PUSH DE`, or the same with HL | The pushed address's high byte becomes `entry` |
| A tape call after the ROM is selected in page 0 | `IN A,(0A8h) / AND 0F0h / OUT (0A8h),A`, which selects the ROM in pages 0 and 1, then `CALL 00E1h` or `CALL 00E4h` | The call's high byte becomes `entry` |
| A reader of the cassette signal | `IN A,(0A2h)`, then a test of bit 7, in a loop | None: listed, for a `patch` line that sends its callers to the service |

The stub stores `TAPION`'s address in RAM, and the game later changes its low byte
to E4h for `TAPIN`, so the entries keep the BIOS's low bytes. A stub that pushes
00EAh, `TAPOON`, writes the tape, and the scan leaves it alone. A finding in code
that ran only during the load is harmless; `check.py` reports which findings it
reaches.

## Check

`tools/check.py` makes a disk image with `openMSX`'s `diskmanipulator`, with the
`dos` folder's files, the restorer, the image and an `AUTOEXEC.BAT` that runs
`<GAME>`. It boots the machine with that disk and the `boot` keys, and verifies
these points, writing its report to `check/report.txt`:

1. At the snapshot's program counter, after the tail's jump, the RAM pages, the
   stored VRAM blocks and the registers equal the snapshot's, except the tail's
   bytes and the mapper registers, which select the restorer's segments.
2. The game runs: a screenshot every 10 seconds for 60 seconds, in `check/`.
3. With the tape service, from the restored state saved with `savestate`, each scan
   finding and each `probe` runs once with its registers, reaches the tape service,
   and reads the expected block; the state is loaded back after each.

Code that a game builds only when the player reaches a level is not visible to the
scan or to point 3. It appears as a hang during play, and a trace of that load in
`openMSX` provides the `patch` line.

## Decisions

| Decision | Reason |
|---|---|
| Restore a snapshot | The game's loader runs once, in `openMSX`, so its slot code, stubs and checks need no changes on the real machine |
| Capture on a copy of the user's machine, with the disk system's hooks and work area removed | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Snapshot at an interrupt's entry | The CPU's state is complete, interrupts are off, and the bytes below the stack pointer are free for the tail |
| Mapper pages restored into the restorer's own segments | No page is copied over DOS's memory, and the image needs no room for a second copy of those pages |
| ROM checksums checked by the restorer | A snapshot runs only on the ROMs it was taken with |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| Scan the snapshot and the unread blocks | A search of the 1,653 files of File-Hunter's MSX CAS collection for files that leave over 10% and 2 KB unread in a test load and hold a rewind or play prompt found 62 files of 51 games; 20 of those games build stubs that T0 alone does not intercept |
| A tape with both sides, a wrap, and rewind and flip keys | In 41 of those 51 games the unread blocks have no names, so only the tape's position decides which block a game reads, as with a real tape |

## Limits

- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- DOS's own memory must be in a memory mapper, and the game's mapper pages in that
  same mapper.
- A game that needs the tape service runs only on a machine whose BIOS keeps its
  tape code where the standard MSX BIOS does.
- A BASIC program that selects the ROM in page 0 and then uses `CLOAD` does not
  reach the tape service.
- A program that requires the cassette signal itself, such as Head Alignment Kit,
  does not run. A game that reads the signal only to build bytes requires a `patch`
  line.

## Not in the first version

- MSX2+ and turbo R: the V9958's registers above 23 and the turbo R's R800 mode.

## Formats

### Image

All numbers are little-endian. The image holds a 256-byte header, then each VRAM
block as a 1-byte block number and 16,384 bytes, then each RAM page as a 4-byte
record and 16,384 bytes, then the tape service's routines, then side 1's and side
2's CAS data.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | `SNAPCAS1` |
| 8 | 1 | VDP type: 0 for an MSX1 VDP, 1 for a V9938 |
| 9 | 1 | Flags: bit 0 set with the tape service |
| 10 | 2 | CRC-16 of the main ROM's 32 KB |
| 12 | 2 | CRC-16 of the sub-ROM's 16 KB, or 0 |
| 14 | 1 | Number of VRAM blocks |
| 15 | 1 | Number of RAM pages |
| 16 | 24 | AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC |
| 40 | 1 | I |
| 41 | 1 | Interrupt mode |
| 42 | 1 | Slot register |
| 43 | 4 | Subslot registers of slots 0 to 3, 0 when not expanded |
| 47 | 4 | Mapper registers FCh to FFh at the snapshot |
| 51 | 1 | PPI port C |
| 52 | 16 | PSG registers 0 to 15 |
| 68 | 24 | VDP registers 0 to 23 |
| 92 | 32 | Palette: 16 entries of 2 bytes, as written to port 9Ah |
| 124 | 3 | VRAM pointer |
| 127 | 1 | VRAM access: 0 for write, 1 for read |
| 128 | 1 | VDP register latch: 0 when empty, 1 when it holds a first byte |
| 129 | 1 | That first byte |
| 130 | 2 | Tail address |
| 132 | 2 | Length of the tape service's routines, or 0 |
| 134 | 1 | `entry` |
| 135 | 2 | Address in the game's page 3 of the segment numbers that the restorer fills in |
| 137 | 4 | `rewind` and `flip` keys: row and mask of each |
| 141 | 3 | Length of side 1's CAS data |
| 144 | 3 | Length of side 2's CAS data, or 0 |
| 147 | 3 | Tape position at the snapshot: offset in side 1 |
| 150 | 106 | Zero |

A RAM page's record holds the primary slot, the subslot (FFh when not expanded), the
page, and the mapper segment (FFh when the page is not in a mapper). The CRC-16 is
CRC-16/CCITT: polynomial 1021h, initial value FFFFh.

### CAS data

A CAS file is a sequence of blocks, each starting with the 8-byte header
`1F A6 DE BA CC 13 7D 74`. A file's first block holds 10 bytes of its type and a
6-byte name: D0h for a binary file loaded with `BLOAD"CAS:",R`, D3h for a BASIC
program loaded with `CLOAD`, and EAh for an ASCII program loaded with `RUN"CAS:"`.
The capture stops with an error when the first block has none of these types.

### `state.txt`

One `name value` per line, values in hexadecimal: `af` to `pc`, `i`, `im`, `iff1`,
`a8`, `sub0` to `sub3`, `fc` to `ff`, `ppic`, `psg0` to `psg15`, `vdp0` to `vdp23`,
`pal0` to `pal15`, `vramptr`, `vramread`, `latch`, `latchbyte`, `vdp` (`msx1` or
`v9938`), and `tapepos`, the offset in side 1 of the next byte to read.

### Game file

One setting per line: a key, a space and a value. A line that starts with `#` is a
comment, and blank lines are ignored. Times are decimal emulated seconds; addresses
and bytes are hexadecimal.

| Key | Value |
|---|---|
| `cas`, `side2` | A file name in the `--cas` folder |
| `sha1` | One or two 40-digit SHA-1s |
| `keys` | A time, then a key name, or a text in quotes that `openMSX` types |
| `continue`, `rewind`, `flip` | A key name |
| `snapshot` | `at` and a time |
| `entry` | A byte, such as `FC` |
| `tail` | An address in page 3 |
| `patch` | A place, the old bytes, `>`, the new bytes: `patch 1-x-3:0D31 CD E1 00 > CD E1 FC` |
| `probe` | A place, registers, and the expected block: `probe 1-x-3:0D31 hl=9000 de=0010 block=7` |

A place is a RAM page as `<ps>-<ss>-<page>:<offset>`, or the tape as
`side1:<offset>` or `side2:<offset>`.

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
[^sys]: The hooks from FD9Ah to FFC9h, `SLTATR` at FCC9h, `SLTWRK` at FD09h and
    `HIMEM` at FC4Ah: MSX Red Book, chapter 6. `EXTBIO` at FFCAh, `DISINT` at FFCFh
    and `ENAINT` at FFD4h: map.grauw.nl, system variables.
[^clear]: `CLEAR` sets `HIMEM` and accepts no value above F380h: MSX Red Book, chapter
    5.
[^tape]: The jump table entries of `TAPION`, `TAPIN`, `TAPIOF`, `TAPOON`, `TAPOUT`,
    `TAPOOF`, `STMOTR` (00F3h) and `OUTDO`, the routines' addresses in the standard
    BIOS, and the hook `H.PARD` at FEB2h, called from the device name parser: MSX
    Red Book, chapters 4 and 6.
[^ports]: VDP ports 98h and 99h, and VDP registers 0 to 7: MSX Red Book, chapter 2.
    PSG ports A0h, A1h and A2h, and registers 7, 14 and 15: chapter 3. PPI port C at
    AAh, whose bit 4 controls the cassette motor: chapter 1.
[^v9938]: V9938 registers, register 14 for VRAM above 16 KB, and the palette port 9Ah:
    MSX2 Technical Handbook, chapter 4.
[^exbrsa]: `EXBRSA` at FAF8h, the slot of the sub-ROM: map.grauw.nl, system variables.
[^rdslt]: `RDSLT` at 000Ch, which MSX-DOS keeps in page 0: MSX Red Book, chapter 4.
[^dos2]: `ALL_SEG`, through the jump table that `EXTBIO` returns: MSX-DOS 2 Program
    Interface Specification, sections 5.2 and 5.4.
[^fcb]: `_FOPEN` 0Fh, `_SETDTA` 1Ah and `_RDBLK` 27h, the FCB functions of MSX-DOS 1
    that MSX-DOS 2 keeps: MSX-DOS 2 Function Codes Specification.
[^keys]: The keyboard matrix, rows 6 to 8: MSX Red Book, chapter 1.
