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
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` ([Machine file](#machine-file)) |
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

The machine file holds one `openmsx` line, one `disk` line and any number of `boot`
lines:

| Line | Example | Meaning |
|---|---|---|
| `openmsx` | `openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2` | The `openMSX` arguments that reproduce the machine, with its cartridges in the same slots |
| `disk` | `disk hda` | The `openMSX` command that inserts the disk image of `check.py`: `hda` for an IDE interface, such as the Carnivore2's, or `diska` for a floppy drive |
| `boot` | `boot 2 esc` | A key pressed at a time in seconds after power-on, to pass a cartridge's boot menu, such as the Carnivore2's; one line per key |

## Game file

The game file holds one `key value` pair per line. Only `cas` is required.

| Key | Example | Meaning | Default |
|---|---|---|---|
| `cas` | `GAUNTLET.CAS` | The CAS file | |
| `side2` | `GAUNTLEB.CAS` | The CAS file of the tape's second side | None |
| `keys` | `100 space` | A key that the capture presses, and the time in seconds; one line per key | None |
| `pause` | `return` | The key that the capture presses when the load waits for a key | `space` |
| `snapshot` | `at 120` | The time of the snapshot, in place of the moment the capture determines | Determined by the capture |
| `rewind` | `graph` | The key that the player holds to rewind the tape | `stop` |
| `entry` | `F000` | The address of the tape service's entry in page 3, when the game uses `SLTWRK` | `SLTWRK` |
| `patch` | `8D31 CD E1 00 > CD E1 FC` | A change to the snapshot's RAM: address, old bytes, new bytes | None |
| `probe` | `8D31 hl=9000 de=0010` | A tape routine that `check.py` runs, with its register values | The routines that the scan finds |

## Capture

`tools/capture.py` runs `openMSX` with the machine file's arguments and the script
`tools/capture.tcl`. The script performs the following steps:

1. Boots the machine with no disk, presses the `boot` keys, and waits for BASIC's
   `Ok`. It then sets page 3 as `CASGO`'s stage 2 does: RET (C9h) in every hook from
   FD9Ah to FFC9h, 00h at F37Dh, which some loaders read to refuse a disk system,
   and zeros in `SLTATR` and `SLTWRK`.[^sys] It types `CLEAR200,&HF380`, which sets
   BASIC's memory top to a cassette machine's.
2. Inserts the CAS file into the cassette player and types the load command that the
   first block's type requires: `BLOAD"CAS:",R`, `CLOAD` followed by `RUN`, or
   `RUN"CAS:"`.
3. Presses the keys listed under `keys`.
4. Counts the bytes that the game reads, with a breakpoint on the BIOS routine
   `TAPIN`, and waits until the game has not read the tape for 10 seconds. It then
   proceeds as follows:
   - If the game has read every block, the script takes the snapshot.
   - Otherwise, the script saves `openMSX`'s state and presses the `pause` key. If
     the game reads the tape again within 10 seconds, the load was waiting for that
     key, and step 4 restarts. If not, the script reloads the saved state and takes
     the snapshot; the unread blocks are then loaded during play.

A load that waits for a choice that the `pause` key cannot make, such as Gauntlet's
choice of players and character with the joystick, therefore gets its snapshot at
that screen. The player makes the choice on the real machine, and the tape service
supplies the rest of the load
([Games that load during play](#games-that-load-during-play)). The capture never
needs a joystick, and the snapshot holds no choice that the player would make.

The capture writes the snapshot to `snap/`:

| File | Contents | `openMSX` source |
|---|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each page that holds RAM, by primary slot, subslot and page | The `slotted memory` debuggable; a page holds RAM when its device in `slotmap` is RAM or a memory mapper |
| `bios.bin` | 16 KB: page 0 of the main ROM, the slot that `EXPTBL` names | The `slotted memory` debuggable |
| `vram.bin` | All of video RAM: 16 KB with an MSX1 VDP, 64 or 128 KB with a V9938 | `VRAM`; its size gives the VDP type |
| `state.txt` | CPU registers, interrupt mode and state, slot register, subslot registers, mapper registers, PPI port C, VDP type, VDP registers (0 to 7 with an MSX1 VDP, 0 to 23 and the 16 palette entries with a V9938), PSG registers 0 to 13, and the number of bytes read | `reg` for the CPU; `debug read` on `MapperIO`, `VDP regs`, `VDP palette`, `PSG regs` and port AAh; for each expanded slot, the byte at FFFFh, inverted, read while a `debug write` to port A8h selects that slot in page 3 |

## Image

`tools/build.py` writes `<GAME>.IMG` in the following format:

| Part | Size | Contents |
|---|---|---|
| Header | 256 bytes | Signature `SNAPCAS1`, the values of `state.txt`, the VRAM size, the number of RAM pages, a flag for the tape service, and the length of the tape data |
| VRAM | 16, 64 or 128 KB | `vram.bin` |
| RAM pages | 4 bytes and 16 KB each | Primary slot, subslot (FFh when the slot is not expanded), page, mapper segment (FFh when the page is not in a mapper), then the page's contents, with the `patch` lines and the scan's patches applied |
| Tape | Remainder of the file | Present only with the tape service: the unread blocks of side 1, then those of side 2, each with its CAS header |

`build.py` also writes the tail, the code that ends the restore, into the page that
holds the stack pointer, immediately below it ([Restorer](#restorer)). It stops with
an error when those bytes are in use, which it detects as a difference between two
snapshots taken one second apart.

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
`side2` file. T0 replaces the BIOS's tape code where the standard MSX BIOS has it,
so `build.py` first checks `bios.bin` as `CASGO` checks the BIOS: the jump table's
tape entries and `OUTDO`'s entry must point to the addresses that `CASGO`'s
`bios_entries` lists. Otherwise it stops with an error.

| Part | Location | Function |
|---|---|---|
| T0 | A mapper segment that the game does not use, selected in page 0 in place of the BIOS ROM | A copy of the machine's BIOS in which the tape routines `TAPION`, `TAPIN`, `TAPIOF` and `STMOTR`[^tape] are replaced by the service's routines, as in `CASGO` (`src/tape.asm`, `src/t0.asm`) |
| Tape data | Mapper segments | The image's tape data, 16381 bytes per segment, read through page 0 as `CASGO`'s T0 reads it |
| Entry in page 3 | `SLTWRK` when its 128 bytes are still zero in the snapshot, or else the game file's `entry` address; with neither, `build.py` stops with an error | Selects T0 in page 0, calls `TAPION` or `TAPIN`, and restores the game's slots, as `CASGO`'s trampolines do |
| `H.PARD` | FEB2h | Selects T0 in page 0 before each BASIC load[^tape] |

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

| Code | Pattern | Patch |
|---|---|---|
| A stub built with the tape's entry address | `CASGO`'s `stub_build`, `stub_build_hl` and the loader family's build code | The high byte of the pushed entry address is changed to point to the entry in page 3 |
| A call to the tape after the ROM is selected in page 0 | `CASGO`'s `rom_back`, followed by `CALL 00E1h` or `CALL 00E4h` | The call is redirected to the entry in page 3 |
| A routine that reads the cassette signal | `IN A,(0A2h)` followed by a test of bit 7, in a loop | None; the scan lists the routine, and a `patch` line redirects its callers to the service |

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
| Restore a snapshot instead of emulating the tape for the game's loader | The loader runs once, in `openMSX`, so its slot code, stubs and checks require no changes |
| Capture on a copy of the user's machine, with the disk system disabled | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Install the tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| Scan both the snapshot and the unread blocks | Of 51 multi-load games in `CASGO`'s corpus, 20 build stubs that T0 alone does not intercept |
| Model the tape position with sides, a wrap and a rewind key | 41 of those 51 games read their blocks in order, without names, as from a real tape |
| Verify later loads by the scan and by running each tape routine | Playing every game up to its later loads is not feasible |

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
[^ports]: VDP ports 98h and 99h, and VDP registers 0 to 7: MSX Red Book, chapter 2. PSG
    ports A0h, A1h and A2h: chapter 3. PPI port C at AAh: chapter 1.
[^slots]: Slot register at port A8h, subslot register at FFFFh, which reads back
    inverted: MSX Red Book, chapter 1.
[^tape]: `TAPION` 00E1h, `TAPIN` 00E4h, `TAPIOF` 00E7h, `STMOTR` 00F3h, `H.PARD` FEB2h: MSX Red
    Book, chapters 4 and 6.
[^sys]: The hooks from FD9Ah to FFC9h, `SLTATR` at FCC9h, `SLTWRK` at FD09h and
    `HIMEM` at FC4Ah, whose value on a cassette machine is F380h: MSX Red Book,
    chapter 6.
[^v9938]: V9938 registers, register 14 for VRAM above 16 KB, and the palette port 9Ah:
    MSX2 Technical Handbook, chapter 4.
[^fcb]: `_FOPEN` 0Fh, `_SETDTA` 1Ah and `_RDBLK` 27h, the FCB functions of MSX-DOS 1
    that MSX-DOS 2 keeps: MSX-DOS 2 Function Codes Specification.
