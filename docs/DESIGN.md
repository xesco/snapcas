# snapcas design

snapcas starts a cassette game from disk on one real MSX. openMSX loads the game
from its CAS file, in its own cassette player, on a copy of the user's machine, and
snapcas saves the machine's state when the game is ready. A program on the real
machine, the restorer, puts that state back and jumps into the game. A game that
loads more of the tape during play also gets a tape service, which gives it the rest
of the CAS file.

## Files

| File | Written by | What it holds |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | The openMSX arguments that copy the machine, with its cartridges in the same slots |
| `games/<game>/game.txt` | A person or an LLM | What the game needs ([Game file](#game-file)) |
| `games/<game>/snap/` | `tools/capture.sh` | The snapshot ([Capture](#capture)) |
| `out/<game>/<GAME>.IMG` | `tools/build.py` | The image that the restorer reads ([Image](#image)) |
| `out/<game>/<GAME>.COM` | `tools/build.py` | The restorer, from `src/` ([Restorer](#restorer)) |

A game goes through four commands: `tools/capture.sh <game> <machine>`, then
`tools/build.py <game>`, then `tools/check.sh <game> <machine>` ([Check](#check)),
and then the user runs `<GAME>` on the real machine.

## Game file

One `key value` per line. Only `cas` is required.

| Key | Example | Meaning | Default |
|---|---|---|---|
| `cas` | `GAUNTLET.CAS` | The CAS file | |
| `side2` | `GAUNTLEB.CAS` | The CAS file of the tape's second side | None |
| `keys` | `100 space` | A key the capture presses, at a time in seconds; one line per key | None |
| `pause` | `return` | The key the capture presses when the load stops for a key | `space` |
| `snapshot` | `at 120` | The time of the snapshot, in place of the capture's own choice | The capture's choice |
| `rewind` | `graph` | The key the player holds to rewind the tape | `stop` |
| `patch` | `8D31 CD E1 00 > CD E1 FC` | A change to the snapshot's RAM: address, old bytes, new bytes | None |
| `probe` | `8D31 hl=9000 de=0010` | A tape routine that `check.sh` runs, with its registers | The scan's finds |

## Capture

`tools/capture.sh` runs openMSX with the machine file's arguments and
`tools/capture.tcl`, which does this:

1. Boots with SHIFT held, so the disk system stays off and the machine starts BASIC
   as a cassette machine with these cartridges does. *To verify* with Nextor on a
   Carnivore2.
2. Puts the CAS file in the cassette player and types the load command for the first
   block's type: `BLOAD"CAS:",R`, `CLOAD` then `RUN`, or `RUN"CAS:"`.
3. Presses the `keys`.
4. Counts the bytes the game reads, with a breakpoint on the BIOS's TAPIN, and waits
   until the game has not read the tape for 10 seconds. Then:
   - When it has read every block, it takes the snapshot.
   - Otherwise it saves openMSX's state and presses the `pause` key. If the game
     reads the tape again within 10 seconds, the load had stopped for that key, and
     step 4 starts again. If not, it loads the saved state and takes the snapshot,
     and the unread blocks are loaded during play.

The snapshot, in `snap/`:

| File | Contents | openMSX source |
|---|---|---|
| `ram/<ps>-<ss>-<page>.bin` | 16 KB for each page that holds RAM, by primary slot, subslot and page | The `slotted memory` debuggable; RAM pages are those whose device in `slotmap` is RAM or a memory mapper |
| `vram.bin` | 16 KB of video RAM | `VRAM` |
| `state.txt` | CPU registers, interrupt mode and state, slot register, subslot registers, mapper registers, VDP registers 0 to 7, PSG registers 0 to 13, and the number of bytes read | `reg`, `debug read` |

## Image

`tools/build.py` writes `<GAME>.IMG`:

| Part | Size | Contents |
|---|---|---|
| Header | 256 bytes | Signature `SNAPCAS1`, then the values of `state.txt`, the number of RAM pages, the tape service's flag and its tape's length |
| VRAM | 16 KB | `vram.bin` |
| RAM pages | 4 bytes and 16 KB each | Primary slot, subslot (FFh when not expanded), page, mapper segment (FFh when not a mapper), then the page, with the `patch` lines and the scan's patches applied |
| Tape | The rest | Only with the tape service: the unread blocks of side 1, then side 2, each block with its CAS header |

`build.py` also writes the tail into the page that holds the stack pointer, just
below it ([Restorer](#restorer)), and stops with an error when those bytes are not
free: when the bytes there differ between two snapshots taken a second apart.

## Restorer

`<GAME>.COM` runs under Nextor or MSX-DOS 2 with a memory mapper. It:

1. Reads the image into free mapper segments, which it takes with the DOS mapper
   routine ALL_SEG.[^dos2] It stops with a message when the mapper is too small.
2. Turns interrupts off. From here it calls neither DOS nor the BIOS.
3. Writes VRAM and VDP registers 0 to 7 through ports 98h and 99h, and PSG registers
   0 to 13 through ports A0h and A1h.[^ports]
4. With the tape service, builds T0 and installs the service
   ([Tape service](#tape-service)).
5. Copies each RAM page to its slot, subslot, page and mapper segment. The copier
   runs in one of its own segments: in page 3 while it writes page 1, then in page 1
   while it writes pages 0, 2 and 3. It reads each page through a window: page 2
   while it writes pages 0, 1 and 3, and page 0 while it writes page 2. It sets each
   subslot register at FFFFh while that slot is in page 3,[^slots] and the subslot
   register of the snapshot's page 3 slot last.
6. Jumps to the tail, below the game's stack pointer, in the game's page 3 slot. The
   tail sets the slot register and the mapper registers, loads the CPU registers,
   sets the interrupt mode, enables interrupts when they were enabled, and jumps to
   the game's PC. The R register is not restored.

## Tape service

Only for a game with unread blocks or a `side2`.

| Part | Where | What it does |
|---|---|---|
| T0 | A mapper segment the game does not use, in page 0 in place of the BIOS ROM | A copy of the machine's BIOS whose tape routines TAPION, TAPIN, TAPIOF and STMOTR[^tape] are the service's, as in CASGO (`src/tape.asm`, `src/t0.asm`) |
| Tape data | Mapper segments | The image's tape part, 16381 bytes in each segment, read through page 0 as CASGO's T0 does |
| Entry in page 3 | SLTWRK, when the snapshot shows it empty | Puts T0 in page 0, calls TAPION or TAPIN, and puts the game's slots back, as CASGO's trampolines do |
| H.PARD | FEB2h | Puts T0 in page 0 before each BASIC load[^tape] |

The service keeps the tape's position as a block number, with side 1's unread blocks
and side 2's blocks as one tape:

| Event | New position |
|---|---|
| TAPION finds the next header | The block after it |
| TAPION reads past a side's last block | That side's first block |
| TAPION is called while the `rewind` key is held | The first block of the current side |

## Scan

`build.py` scans the snapshot's RAM pages and the unread blocks for code that
reaches the tape around T0:

| Code | Pattern | Patch |
|---|---|---|
| Stub built with the tape's entry | CASGO's `stub_build`, `stub_build_hl` and the loader family's build code | The pushed entry's high byte becomes the entry in page 3 |
| ROM put in page 0, then a tape call | CASGO's `rom_back`, then `CALL 00E1h` or `CALL 00E4h` | The call goes to the entry in page 3 |
| Cassette signal read | `IN A,(0A2h)` with a test of bit 7, in a loop | None: listed, for a `patch` line that sends its callers to the service |

It prints each find with its address and patch, and stops with an error when a find
has no patch and no `patch` line covers it.

## Check

`tools/check.sh` boots the machine file's machine with its disk system, runs the
restorer, and saves a screenshot every 10 seconds. With the tape service it also
runs each scan find and each `probe` once, from the restored state, with the given
registers, and checks that the code reaches the tape service and reads the block it
expects. Code that a game builds only when the player gets to a level escapes the
scan; it shows as a hang in real play, and the trace of that one load in openMSX
gives its `patch` line.

## Decisions

| Decision | Why |
|---|---|
| Restore a snapshot instead of emulating the tape for the game's loader | The loader runs once, in openMSX, so its slot code, stubs and checks need nothing |
| Capture on a copy of the user's machine with the disk system off | The snapshot holds the slots that the game picks on that machine, as from a real tape |
| Tape service only for games that load during play | A game that loads in one go runs exactly as in the snapshot |
| Scan the snapshot and the unread blocks | Of 51 multi-load games in CASGO's corpus, 20 build stubs that T0 alone misses |
| Tape position with sides, a wrap and a rewind key | 41 of those 51 games read their blocks in order, without names, as from a real tape |
| Check later loads by the scan and by running each tape routine | Playing every game to its later loads is not possible |

## Limits

- An image runs only on the machine of its machine file.
- A game that needs a joystick before its snapshot needs a person at the capture,
  because openMSX cannot press a joystick from a script.
- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- A program that needs the cassette signal itself, such as Head Alignment Kit, does
  not run. A game that reads the signal only to build bytes needs a `patch` line.

## Not in the first version

- MSX2 video: video RAM over 16 KB and VDP registers above 7.

[^dos2]: ALL_SEG through the jump table that EXTBIO returns: MSX-DOS 2 Program
    Interface Specification, section 5.2.
[^ports]: VDP ports 98h and 99h, PSG ports A0h, A1h and A2h: MSX Red Book, chapter
    *to verify*.
[^slots]: Slot register at port A8h, subslot register at FFFFh, which reads back
    inverted: MSX Red Book, chapter 1.
[^tape]: TAPION 00E1h, TAPIN 00E4h, TAPIOF 00E7h, STMOTR 00F3h, H.PARD FEB2h: MSX Red
    Book, chapters 4 and 6.
