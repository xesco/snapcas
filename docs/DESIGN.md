# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX. openMSX loads the game
from its CAS file, in its own cassette player, on a copy of the user's machine, and
`snapcas` saves the machine's state when the game is ready. A program on the real
machine, the restorer, restores that state and transfers control to the game. A game
that loads further data during play also receives a tape service, which supplies the
remaining blocks of the CAS file.

## Files

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | The openMSX arguments that reproduce the machine, with its cartridges in the same slots |
| `games/<game>/game.txt` | A person or an LLM | The game's settings |
| `games/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/<game>/<GAME>.IMG` | `tools/build.py` | The image that the restorer reads |
| `out/<game>/<GAME>.COM` | `tools/build.py` | The restorer, built from `src/` |

Each game is processed by four commands, in this order:

1. `tools/capture.py <game> <machine>` loads the game in openMSX and saves the
   snapshot ([Capture](#capture)).
2. `tools/build.py <game>` writes the image and the restorer ([Image](#image)).
3. `tools/check.py <game> <machine>` runs the restorer in openMSX and saves
   screenshots ([Check](#check)).
4. `<GAME>`, on the real machine, restores the snapshot and starts the game
   ([Restorer](#restorer)).

The tools are Python 3 programs that require only Python 3 and openMSX, so they run
on macOS, Linux and Windows.

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
| `patch` | `8D31 CD E1 00 > CD E1 FC` | A change to the snapshot's RAM: address, old bytes, new bytes | None |
| `probe` | `8D31 hl=9000 de=0010` | A tape routine that `check.py` runs, with its register values | The routines that the scan finds |

## Capture

`tools/capture.py` runs openMSX with the machine file's arguments and the script
`tools/capture.tcl`. The script performs the following steps:

1. Boots with `SHIFT` held, so that the disk system remains disabled and the machine
   starts BASIC as a cassette machine with these cartridges does. *To verify* with
   Nextor on a Carnivore2.
2. Inserts the CAS file into the cassette player and types the load command that the
   first block's type requires: `BLOAD"CAS:",R`, `CLOAD` followed by `RUN`, or
   `RUN"CAS:"`.
3. Presses the keys listed under `keys`.
4. Counts the bytes that the game reads, with a breakpoint on the BIOS routine
   `TAPIN`, and waits until the game has not read the tape for 10 seconds. It then
   proceeds as follows:
   - If the game has read every block, the script takes the snapshot.
   - Otherwise, the script saves openMSX's state and presses the `pause` key. If the
     game reads the tape again within 10 seconds, the load was waiting for that key,
     and step 4 restarts. If not, the script reloads the saved state and takes the
     snapshot; the unread blocks are then loaded during play.

The capture writes the snapshot to `snap/`:

| File | Contents | openMSX source |
|---|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each page that holds RAM, by primary slot, subslot and page | The `slotted memory` debuggable; a page holds RAM when its device in `slotmap` is RAM or a memory mapper |
| `vram.bin` | 16 KB of video RAM | `VRAM` |
| `state.txt` | CPU registers, interrupt mode and state, slot register, subslot registers, mapper registers, VDP registers 0 to 7, PSG registers 0 to 13, and the number of bytes read | `reg`, `debug read` |

## Image

`tools/build.py` writes `<GAME>.IMG` in the following format:

| Part | Size | Contents |
|---|---|---|
| Header | 256 bytes | Signature `SNAPCAS1`, the values of `state.txt`, the number of RAM pages, a flag for the tape service, and the length of the tape data |
| VRAM | 16 KB | `vram.bin` |
| RAM pages | 4 bytes and 16 KB each | Primary slot, subslot (FFh when the slot is not expanded), page, mapper segment (FFh when the page is not in a mapper), then the page's contents, with the `patch` lines and the scan's patches applied |
| Tape | Remainder of the file | Present only with the tape service: the unread blocks of side 1, then those of side 2, each with its CAS header |

`build.py` also writes the tail, the code that ends the restore, into the page that
holds the stack pointer, immediately below it ([Restorer](#restorer)). It stops with
an error when those bytes are in use, which it detects as a difference between two
snapshots taken one second apart.

## Restorer

`<GAME>.COM` runs under Nextor or MSX-DOS 2 and requires a memory mapper. It
performs the following steps:

1. Reads the image into free mapper segments, allocated with the DOS mapper routine
   `ALL_SEG`.[^dos2] It stops with a message when the mapper is too small.
2. Disables interrupts. From this point on, it calls neither DOS nor the BIOS.
3. Writes the VRAM and VDP registers 0 to 7 through ports 98h and 99h, and PSG
   registers 0 to 13 through ports A0h and A1h.[^ports]
4. If the game uses the tape service, builds T0 and installs the service
   ([Tape service](#tape-service)).
5. Copies each RAM page to its slot, subslot, page and mapper segment. The copier
   runs from one of the restorer's own segments: from page 3 while it writes page 1,
   then from page 1 while it writes pages 0, 2 and 3. It reads each page through a
   window: page 2 while it writes pages 0, 1 and 3, and page 0 while it writes page
   2. It sets each subslot register at FFFFh while that slot is selected in page
      3,[^slots] and sets the subslot register of the snapshot's page 3 slot last.
6. Jumps to the tail, below the game's stack pointer, in the game's page 3 slot. The
   tail sets the slot register and the mapper registers, loads the CPU registers,
   sets the interrupt mode, enables interrupts if they were enabled at the snapshot,
   and jumps to the game's program counter. The R register is not restored.

## Tape service

The restorer installs the tape service only for a game with unread blocks or a
`side2` file.

| Part | Location | Function |
|---|---|---|
| T0 | A mapper segment that the game does not use, selected in page 0 in place of the BIOS ROM | A copy of the machine's BIOS in which the tape routines `TAPION`, `TAPIN`, `TAPIOF` and `STMOTR`[^tape] are replaced by the service's routines, as in `CASGO` (`src/tape.asm`, `src/t0.asm`) |
| Tape data | Mapper segments | The image's tape data, 16381 bytes per segment, read through page 0 as `CASGO`'s T0 reads it |
| Entry in page 3 | `SLTWRK`, when the snapshot shows that area empty | Selects T0 in page 0, calls `TAPION` or `TAPIN`, and restores the game's slots, as `CASGO`'s trampolines do |
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
appears as a hang during play, and a trace of that load in openMSX provides the
required `patch` line.

## Decisions

| Decision | Reason |
|---|---|
| Restore a snapshot instead of emulating the tape for the game's loader | The loader runs once, in openMSX, so its slot code, stubs and checks require no changes |
| Capture on a copy of the user's machine, with the disk system disabled | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Install the tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| Scan both the snapshot and the unread blocks | Of 51 multi-load games in `CASGO`'s corpus, 20 build stubs that T0 alone does not intercept |
| Model the tape position with sides, a wrap and a rewind key | 41 of those 51 games read their blocks in order, without names, as from a real tape |
| Verify later loads by the scan and by running each tape routine | Playing every game up to its later loads is not feasible |

## Limits

- An image runs only on the machine described by its machine file.
- A game that requires a joystick before its snapshot requires a person during the
  capture, because openMSX cannot operate a joystick from a script.
- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- A program that requires the cassette signal itself, such as Head Alignment Kit,
  does not run. A game that reads the signal only to build bytes requires a `patch`
  line.

## Not in the first version

- MSX2 video: video RAM above 16 KB and VDP registers above 7.

[^dos2]: `ALL_SEG`, through the jump table that `EXTBIO` returns: MSX-DOS 2 Program
    Interface Specification, section 5.2.
[^ports]: VDP ports 98h and 99h, PSG ports A0h, A1h and A2h: MSX Red Book, chapter
    *to verify*.
[^slots]: Slot register at port A8h, subslot register at FFFFh, which reads back
    inverted: MSX Red Book, chapter 1.
[^tape]: `TAPION` 00E1h, `TAPIN` 00E4h, `TAPIOF` 00E7h, `STMOTR` 00F3h, `H.PARD` FEB2h: MSX Red
    Book, chapters 4 and 6.
