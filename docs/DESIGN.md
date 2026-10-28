# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX. `openMSX` loads the game
from its CAS file, in its own cassette player, on a copy of the user's machine, and
`snapcas` saves the machine's state when the game is ready. A program on the real
machine, the restorer, restores that state and transfers control to the game. A game
that loads further data during play also receives a tape service, which supplies the
remaining blocks of the CAS file.

## Files

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` |
| `games/<game>/game.txt` | A person or an LLM | The game's settings |
| `games/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/<game>/<GAME>.IMG` | `tools/build.py` | The image that the restorer reads |
| `out/<game>/<GAME>.COM` | `tools/build.py` | The restorer, built from `src/` |

Each game is processed by four commands, in this order:

1. `tools/capture.py <game> <machine>` loads the game in `openMSX` and saves the
   snapshot ([Capture](#capture)).
2. `tools/build.py <game>` writes the image and the restorer ([Image](#image)).
3. `tools/check.py <game> <machine>` runs the restorer in `openMSX` and saves
   screenshots ([Check](#check)).
4. `<GAME>`, on the real machine, restores the snapshot and starts the game
   ([Restorer](#restorer)).

The tools are Python 3 programs that require only Python 3 and `openMSX`, so they
run on macOS, Linux and Windows.

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
| `openmsx` | The `openMSX` arguments that reproduce the machine, with its cartridges in the same slots |
| `disk` | The command that inserts the disk image of `check.py`: `hda` for an IDE interface, `diska` for a floppy drive |
| `boot` | A text on the screen during boot, and the key to press when it appears; one line per key, matched in order |

`boot` lines pass a cartridge's boot menu, such as the Carnivore2's. The capture
reads the screen with `openMSX`'s `get_screen`, so such a menu must be in a text
mode.

## Game file

A game file holds one `key value` pair per line. Only `cas` is required. This
example is for Gauntlet, which loads its levels from the tape's second side:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5
```

| Key | Meaning | Default |
|---|---|---|
| `cas` | The CAS file | |
| `side2` | The CAS file of the tape's second side | None |
| `keys` | A time in seconds and a key that the capture presses then; one line per key | None |
| `continue` | A key that the capture tries before space and Return, to continue a load that waits for a key | None |
| `snapshot` | `at` and the time of the snapshot, in place of the moment the capture determines | Determined by the capture |
| `rewind` | The key that the player holds to rewind the tape | `stop` |
| `sha1` | The SHA-1 of the CAS file that the game file was made for | None |
| `entry` | The address of the tape service's entry in page 3 | `SLTWRK` |
| `patch` | A change to the snapshot's RAM: address, old bytes, `>`, new bytes | None |
| `probe` | A tape routine that `check.py` runs: its address and register values | The routines that the scan finds |

A patch fits only the dump it was made for, so `build.py` stops with an error when
the game file has `patch` lines and the user's CAS file has another SHA-1. `entry`
is needed only when the game uses `SLTWRK` ([Tape service](#tape-service)).

## Shipped files

The repository ships game files and machine files, so that a user needs to write
neither for a known game or a common machine.

`games/` holds a game file for each tape of File-Hunter's MSX CAS collection, named
after its File-Hunter file name. Each holds the tape's `sha1` and the `side2`,
`continue` and `patch` lines that the game needs, found by running the capture on
the tape.

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

`check.py` checks each shipped machine file with a reference game. A machine file
must list the cartridges in the slots that they occupy on the real machine. To
confirm it, the user runs `SLOTS.COM`, built from `src/slots.asm`, on the real
machine: it prints the slot register, `EXPTBL` and, for each slot, whether it is
expanded and which pages hold RAM. `check.py` prints the same output for the machine
file in `openMSX`, and the two must match.

## Capture

`tools/capture.py` runs `openMSX` with the machine file's arguments and the script
`tools/capture.tcl`. The script performs the following steps:

1. Boots the machine with no disk, presses the `boot` keys, and waits for BASIC's
   `Ok`. It then removes the disk system from page 3: RET (C9h) in every hook from
   FD9Ah to FFC9h, so that no interrupt reaches the disk system; 00h at F37Dh, which
   some loaders read to refuse to run with a disk system; and zeros in `SLTATR` and
   `SLTWRK`, so that no extension ROM claims them.[^sys] It types `CLEAR200,&HF380`,
   which sets BASIC's memory top to a cassette machine's.
2. Inserts the CAS file into the cassette player and types the load command that the
   first block's type requires: `BLOAD"CAS:",R`, `CLOAD` followed by `RUN`, or
   `RUN"CAS:"`.
3. Presses the keys listed under `keys`.
4. Counts the bytes that the game reads, with a breakpoint on the BIOS routine
   `TAPIN`, and waits until the game has not read the tape for 10 seconds. It then
   proceeds as follows:
   - If the game has read every block, the script takes the snapshot.
   - Otherwise, the script saves `openMSX`'s state and tries the keys that continue
     a load that waits for a key: the game file's `continue` key, then space, then
     Return. After each key, if the game reads the tape again within 10 seconds, the
     load was waiting for that key, and step 4 restarts. If not, the script reloads
     the saved state and tries the next key. When no key continues the load, the
     script reloads the saved state and takes the snapshot; the unread blocks are
     then loaded during play.

A load that waits for a choice that none of these keys makes, such as Gauntlet's
choice of players and character with the joystick, therefore gets its snapshot at
that screen. The player makes the choice on the real machine, and the tape service
supplies the rest of the load
([Games that load during play](#games-that-load-during-play)). The capture never
needs a joystick, and the snapshot holds no choice that the player would make.

The capture writes the snapshot to `snap/`:

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each page that holds RAM, by primary slot, subslot and page |
| `bios.bin` | 16 KB: page 0 of the main ROM |
| `vram.bin` | All of video RAM |
| `state.txt` | The registers in the table below, and the number of bytes read |

The capture reads the RAM pages and `bios.bin` from the `slotted memory` debuggable.
A page holds RAM when its device in `slotmap` is RAM or a memory mapper, and the
main ROM is in the slot that `EXPTBL` names. Video RAM comes from the `VRAM`
debuggable, whose size gives the VDP type: 16 KB for an MSX1 VDP, 64 or 128 KB for a
V9938.

| Register | Source in `openMSX` |
|---|---|
| CPU registers, interrupt mode and state | `reg` |
| Slot register and PPI port C | `debug read` on ports A8h and AAh |
| Subslot register of each expanded slot | The byte at FFFFh, inverted, read while a `debug write` to port A8h selects that slot in page 3 |
| Mapper registers | `debug read` on `MapperIO` |
| VDP registers | `debug read` on `VDP regs`: 0 to 7 for an MSX1 VDP, 0 to 23 for a V9938 |
| Palette, on a V9938 | `debug read` on `VDP palette`: 16 entries |
| PSG registers 0 to 13 | `debug read` on `PSG regs` |

## Image

`tools/build.py` writes `<GAME>.IMG` in the following format:

| Part | Size | Contents |
|---|---|---|
| Header | 256 bytes | Signature `SNAPCAS1`, the registers of `state.txt`, the VRAM size, the number of RAM pages, a flag for the tape service, the tape data's length |
| VRAM | 16, 64 or 128 KB | `vram.bin` |
| RAM pages | 4 bytes and 16 KB each | A record per page, as in the next table, then its 16 KB |
| Tape | The rest of the file | Only with the tape service: the unread blocks of side 1, then side 2's, each with its CAS header |

| Byte of a RAM page's record | Value |
|---|---|
| 0 | Primary slot |
| 1 | Subslot, or FFh when the slot is not expanded |
| 2 | Page |
| 3 | Mapper segment, or FFh when the page is not in a mapper |

The pages hold the snapshot's RAM with the `patch` lines and the scan's patches
applied. `build.py` also writes the tail, the code that ends the restore, into the
page that holds the stack pointer, immediately below it ([Restorer](#restorer)). It
stops with an error when those bytes are in use, which it detects as a difference
between two snapshots taken one second apart.

## Restorer

`<GAME>.COM` runs under MSX-DOS 1, MSX-DOS 2 or Nextor, and requires a memory
mapper. It performs the following steps:

1. Reads the image with the FCB functions `_FOPEN`, `_SETDTA` and `_RDBLK`, which
   every MSX-DOS version has,[^fcb] into mapper segments. Under MSX-DOS 2 and Nextor
   it allocates them with the mapper routine `ALL_SEG`.[^dos2] Under MSX-DOS 1,
   which uses only the four segments it maps, it uses the segments above them, in
   the mapper in page 3's slot, and counts them by writing a mark into each one's
   first byte through page 2 and reading the marks back. It stops with a message
   when the mapper is too small.
2. Disables interrupts. From this point on, it calls neither DOS nor the BIOS.
3. Writes the PSG registers 0 to 13 through ports A0h and A1h, PPI port C through
   port AAh,[^ports] and the video state, by VDP type:
   - MSX1 VDP: the 16 KB of VRAM and registers 0 to 7, through ports 98h and 99h.
   - V9938: the VRAM through port 98h, with register 14 selecting each 16 KB block,
     then registers 0 to 23 through port 99h and the palette through port
     9Ah.[^v9938]
4. If the game uses the tape service, builds T0 and installs the service
   ([Tape service](#tape-service)).
5. Copies each RAM page to its slot, subslot, page and mapper segment. The copier
   runs from one of the restorer's own segments, which it selects in page 3 while it
   writes page 1 and in page 1 while it writes the other pages. It reads the
   snapshot's data through a window in page 2, or in page 0 while it writes page 2.
   It sets each slot's subslot register at FFFFh while page 3 selects that
   slot,[^slots] and sets the subslot register of the snapshot's page 3 slot last.
6. Jumps to the tail, below the game's stack pointer, in the game's page 3 slot. The
   tail sets the slot register and the mapper registers, loads the CPU registers,
   sets the interrupt mode, enables interrupts if they were enabled at the snapshot,
   and jumps to the game's program counter. The R register is not restored.

## Tape service

The restorer installs the tape service only for a game with unread blocks or a
`side2` file. T0 replaces the BIOS's tape code at the addresses where the standard
MSX BIOS has it, so `build.py` first checks `bios.bin`: each jump table entry in the
table below must jump to its address. Otherwise it stops with an error.[^tape]

| Entry | Routine | Address it must jump to |
|---|---|---|
| 00E1h | `TAPION` | 1A63h |
| 00E4h | `TAPIN` | 1ABCh |
| 00E7h | `TAPIOF` | 19E9h |
| 00EAh | `TAPOON` | 19F1h |
| 00EDh | `TAPOUT` | 1A19h |
| 00F0h | `TAPOOF` | 19DDh, the start of the tape code |
| 0018h | `OUTDO` | 1B45h, the end of the tape code |

The service has four parts:

| Part | Location | Function |
|---|---|---|
| T0 | A mapper segment that the game does not use, in page 0 | The BIOS, with the service's tape routines |
| Tape data | Mapper segments | The image's tape data |
| Entry | `SLTWRK`, or the game file's `entry` | Calls `TAPION` or `TAPIN` with T0 in page 0 |
| `H.PARD` | FEB2h | Selects T0 in page 0 before each BASIC load[^tape] |

T0 is a copy of the machine's BIOS, selected in page 0 in place of the BIOS ROM,
whose tape code from 19DDh to 1B44h is replaced by the service's routines for
`TAPION`, `TAPIN`, `TAPIOF` and `STMOTR`. Each segment of tape data holds 16381
bytes: `TAPIN` reads a byte by selecting the byte's segment in page 0, from code in
T0, so the last 3 bytes of each segment hold the instructions that read the byte and
select T0 again.

The entry in page 3 selects T0 in page 0, calls `TAPION` or `TAPIN`, and restores
the game's slots. It goes in `SLTWRK` when the 128 bytes there are still zero in the
snapshot, which shows that the game did not use them; otherwise at the game file's
`entry` address. With neither, `build.py` stops with an error.

The service records the tape position as a block number, treating side 1's unread
blocks and side 2's blocks as one tape:

| Event | New position |
|---|---|
| `TAPION` finds the next header | The block that follows it |
| `TAPION` reads past a side's last block | That side's first block |
| `TAPION` is called while the `rewind` key is held | The first block of the current side |

## Scan

`build.py` scans the snapshot's RAM pages and the unread blocks for code that
accesses the tape without going through T0:

| Code | Patch |
|---|---|
| A stub built with the tape's entry address | The pushed entry address points to the entry in page 3 |
| A call to the tape after the ROM is selected in page 0 | The call goes to the entry in page 3 |
| A routine that reads the cassette signal | None: a `patch` line redirects its callers to the service |

The scan recognises each kind by these instructions:

- A stub: `LD DE,00E1h / PUSH DE / LD DE,CDD9h / PUSH DE`, the same with 00EAh, and
  the same with HL in place of DE.
- A call after the ROM is selected: `IN A,(0A8h) / AND 0F0h / OUT (0A8h),A`, which
  selects the ROM in pages 0 and 1, followed by `CALL 00E1h` or `CALL 00E4h`.
- A reader of the cassette signal: `IN A,(0A2h)` followed by a test of bit 7, in a
  loop.

The scan reports each finding with its address and patch, and stops with an error
when a finding has no patch and no `patch` line covers it.

## Check

`tools/check.py` boots the machine of the machine file with its disk system, runs
the restorer, and saves a screenshot every 10 seconds. If the game uses the tape
service, it also runs each routine that the scan finds, and each `probe`, once from
the restored state with the given register values, and verifies that the code
reaches the tape service and reads the expected block. Code that a game generates
only when the player reaches a given level is not visible to the scan. Such code
appears as a hang during play, and a trace of that load in `openMSX` provides the
required `patch` line.

## Decisions

| Decision | Reason |
|---|---|
| Restore a snapshot | The game's loader runs once, in `openMSX`, so its slot code, stubs and checks need no changes on the real machine |
| Capture on a copy of the user's machine, without the disk system | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| Scan the snapshot and the unread blocks | Of 51 games that load during play, among the 1,653 files of File-Hunter's MSX CAS collection, 20 build stubs that T0 alone does not intercept |
| Tape position with sides, a wrap and a rewind key | 41 of those 51 games read their blocks in order, without names, as from a real tape |
| Later loads verified by the scan and by running each tape routine | Playing every game up to its later loads is not feasible |

## Limits

- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- Under MSX-DOS 1, the restorer runs only when page 3's slot holds the memory
  mapper.
- A game that needs the tape service runs only on a machine whose BIOS keeps its
  tape code where the standard MSX BIOS does.
- A program that requires the cassette signal itself, such as Head Alignment Kit,
  does not run. A game that reads the signal only to build bytes requires a `patch`
  line.

## Not in the first version

- MSX2+ and turbo R: the V9958's registers above 23 and the turbo R's R800 mode.

[^dos2]: `ALL_SEG`, through the jump table that `EXTBIO` returns: MSX-DOS 2 Program
    Interface Specification, section 5.2.
[^ports]: VDP ports 98h and 99h, and VDP registers 0 to 7: MSX Red Book, chapter 2.
    PSG ports A0h, A1h and A2h: chapter 3. PPI port C at AAh: chapter 1.
[^slots]: Slot register at port A8h, subslot register at FFFFh, which reads back
    inverted: MSX Red Book, chapter 1.
[^tape]: The jump table entries of `TAPION`, `TAPIN`, `TAPIOF`, `TAPOON`, `TAPOUT`,
    `TAPOOF`, `STMOTR` (00F3h) and `OUTDO`, the routines' addresses in the standard
    BIOS, and the hook `H.PARD` at FEB2h: MSX Red Book, chapters 4 and 6.
[^sys]: The hooks from FD9Ah to FFC9h, `SLTATR` at FCC9h, `SLTWRK` at FD09h and
    `HIMEM` at FC4Ah, whose value on a cassette machine is F380h: MSX Red Book,
    chapter 6.
[^v9938]: V9938 registers, register 14 for VRAM above 16 KB, and the palette port 9Ah:
    MSX2 Technical Handbook, chapter 4.
[^fcb]: `_FOPEN` 0Fh, `_SETDTA` 1Ah and `_RDBLK` 27h, the FCB functions of MSX-DOS 1
    that MSX-DOS 2 keeps: MSX-DOS 2 Function Codes Specification.
