# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX1 or MSX2. `openMSX` loads
the game from its tape file, in its own cassette player, on a copy of the user's
machine. `snapcas` saves the machine's state when the game is ready. On the real
machine, the restorer, `SNAPCAS.COM`, restores that state and transfers control to
the game. A game that loads further data during play also receives a tape service,
which supplies the rest of the tape from memory. The build steps and their tests are
in [PLAN.md](PLAN.md).

## Terms

| Term | Meaning |
|---|---|
| Page | One of the four 16 KB parts of the Z80's 64 KB address space. Page 0 is 0000h to 3FFFh, and page 3 is C000h to FFFFh |
| Slot, subslot | Where the memory in a page comes from. The memory comes from one of four primary slots and, in an expanded slot, from one of four subslots |
| Slot ID | A slot in one byte. Bit 7 is set when the slot is expanded, bits 3 and 2 are the subslot, and bits 1 and 0 are the primary slot |
| Segment | A 16 KB block of a memory mapper. The mapper registers at ports FCh to FFh select a segment into a page |
| DOS's mapper | The mapper that holds DOS's four pages on the real machine |
| DOS's segments | The segments in pages 0 to 3 when the restorer starts |
| Image | `<GAME>.SNP`, the snapshot in the restorer's format ([Formats](#formats)) |
| Worker | The part of the restorer that runs in page 1 or 2 while it changes the other pages |
| Tail | The restore's last code. The tail is 26 bytes written below the game's stack pointer |
| T0 | A RAM copy of the BIOS's page 0 whose tape routines call the tape service's routines ([Tape service](#tape-service)) |
| Code segment | The segment that holds the tape service's routines, then the start of the tape |
| Service segment | A segment that holds T0, the code segment, or the rest of the tape |

## Files and commands

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` |
| `games/<game>/game.txt` | A person or an LLM | The game's settings that hold on every machine |
| `games/<game>/<machine>.txt` | A person or an LLM, for a game that needs it | The game's settings that hold only on one machine. The file is named after the machine file, with `-` for `/` ([FILES.md, Game file](FILES.md#game-file)) |
| `games/<collection>/<game>/` | A person or an LLM | A compilation's program, with the same files as a game's folder. Its `<game>` below `images/<machine>/` and `out/work/<machine>/` is `<collection>/<game>` ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| `custom/<game>/` | The user | A custom game's `game.txt` and its tape files, which `snap` reads from the folder without downloading them. The game's `<game>` below `images/<machine>/` and `out/work/<machine>/` is `custom/<game>` ([CLI.md, Your own games](CLI.md#your-own-games)) |
| `downloads/<TAPE>` | `snapcas.py snap` | The tape files that `snap` downloads from File-Hunter. `snap` checks each file against its game file's SHA-1 ([CLI.md, Download](CLI.md#download)) |
| `tests/tapes/<TAPE>` | The developers | The tape files of the tests, in git |
| `images/<machine>/<game>/<GAME>.SNP` | `snapcas.py snap` | The image, which `snap` moves from the work folder when every step passes |
| `out/work/<machine>/<game>/<GAME>.SNP` | `tools/build.py` | The image, until `snap` moves it |
| `out/work/<machine>/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/work/<machine>/<game>/scan.txt` | `tools/build.py` | The scan's findings and patches |
| `out/work/<machine>/<game>/build.txt` | `tools/build.py` | What the check takes from the build: the tail's address, the offsets of the tail's bytes that the check reads, the area of page 3 that the capture clears (FCC9h to FD88h), the RAM bytes that the build patched, under each RAM file of their segment, the tape service's part of page 3, the addresses of the service's tape position and of the tape's end, and the addresses of the service's two jumps at the tape's end ([Check](#check)) |
| `out/work/<machine>/<game>/check/` | `tools/check.py` | The check's report and savestates |
| `out/work/<machine>/<game>/try/` | `tools/try.py` | The disk of `snapcas.py try` |
| `out/games/<machine>.txt` | `tools/games.py` | The result of each game file on the machine ([INTERNALS.md, The games run](INTERNALS.md#the-games-run)) |
| `dos/` | The user, and the Makefile for `dos/nextor/` | The DOS system files of the checks: `msxdos1/`, `msxdos2/`, and `nextor/` |
| `out/cache/` | The Makefile | The tools that it downloads and builds, and the test home of `openMSX` |
| `bin/SNAPCAS.COM` | The developers | The restorer, from `src/snapcas.asm` |
| `bin/SERVICE.BIN` | The developers | The code that `build.py` writes into images, from `src/service.asm`: the tape service's routines, entries, entry code and reader, the tail, and the symbols that give `build.py` their addresses ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)) |

The developers build the `bin/` files with sjasmplus 1.24.0 and ship them. Git keeps
only a short `README.md` in `custom/`, `downloads/`, `dos/`, `images/`, and `out/`,
and ignores the rest of those folders. `out/work/<machine>/<game>/` is a shipped or
custom game's work folder. A game folder elsewhere, as the tests make below
`out/test/`, holds its own work folder, `<folder>/<machine>/`. The tests therefore
write nothing to `out/work/` or `images/`. `<machine>` is a machine file's name
below `machines/` without `.txt`, such as `vg8020-carnivore2`
([FILES.md, Machine file](FILES.md#machine-file)). Four commands process each game,
in this order:

1. `tools/capture.py <game> <machine> --tapes <dir>` loads the game in `openMSX` and
   saves the snapshot ([Capture](#capture)). `<dir>` holds the tape files, CAS or
   TSX ([Tape files](#tape-files)). `<dir>` is `downloads/` for `snapcas.py snap`,
   and `tests/tapes/` for the tests.
2. `tools/build.py <game> <machine> --tapes <dir>` writes the image and `scan.txt`
   ([Build](#build)), and prints `<GAME>`.
3. `tools/check.py <game> <machine> --dos <dir>` runs the restorer in `openMSX` and
   verifies the restore ([Check](#check)). `<dir>` holds the user's DOS system
   files.
4. The user copies `SNAPCAS.COM` and `<GAME>.SNP` to a disk of the real machine and
   runs `SNAPCAS <GAME>`. With `/M`, the tape moves only when the player presses a
   key ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).

`./snapcas.py snap <game> <machine> [--check [--dos <dir>]]`, the `snapcas` command
at the repository's top ([CLI.md](CLI.md)), makes the image in one command. `snap`
downloads the game's tape files that are missing from `downloads/`. It then does
steps 1 and 2 with the tapes of `downloads/`, and with `--check` it also does
step 3. The check boots the DOS files of the machine's folder below `dos/`, unless
`--dos` gives others. The machine file's `dosfiles` line names that folder
([FILES.md, Machine file](FILES.md#machine-file)). For a machine under Nextor,
`snap` first downloads Nextor's files into `dos/nextor/` when they are missing.
`snap` pins that download by SHA-256, as the Makefile pins it. When every step
passes, `snap` moves a shipped or custom game's image to `images/`. The tests set
`SNAPCAS_DOWNLOADS` to `tests/tapes/`, so that `snap` finds their tapes there and
downloads nothing. `tools/pipeline.py` holds this sequence of steps, for `snap` and
for the games run, and calls each step as a function of its tool
([INTERNALS.md, The tools' code](INTERNALS.md#the-tools-code)).

When a step fails and the game file names no capture variant, `snap` does the steps
again on each capture variant that the machine file lists. `snap` takes the variants
in the order of the machine file's `variant` lines
([FILES.md, Machine file](FILES.md#machine-file)). A failed capture counts too,
because a loader that trips over a cartridge can crash during the capture. So does a
failed build, whose snapshot another capture can change. A capture that stops at an
error in the input files, with status 1, does not count, because a variant reads the
same files. `snap` keeps the first image that passes, and prints the `capture` line
that made it, for the machine's game file. Otherwise `snap` captures and builds the
image of the game file's own lines again, without the check. In that case, `snap`
exits with the status of the first step that failed. The option
`--capture <variant>` of `capture.py` and of `build.py` names the variant, in place
of the game file's `capture` line.

The tools are Python 3 programs that require only Python 3 and `openMSX` 22.0, so
they run on macOS, Linux, and Windows. They print errors on standard error, and each
error names the file and the problem. The tools exit with 0 on success, 1 for an
error in the command line or the input files, 2 when `openMSX` fails or a wait times
out, and 3 when a check fails.

The games run, `make games`, and the map of the tools' code are in
[INTERNALS.md](INTERNALS.md#the-games-run).

## Machine and game files

A machine file describes one MSX and its cartridges, and a game file describes one
game and its tape. [FILES.md](FILES.md) defines both and lists the shipped files.

## How it works

An image passes through the parts below. Each section says what its part does and
why, and [INTERNALS.md](INTERNALS.md) gives each part step by step.

### Tape files

`snapcas` reads two formats of tape file, CAS and TSX. A CAS file holds only the
blocks that the BIOS's tape routines read. A tape whose loader reads its own format,
as a turbo loader does, therefore needs a TSX file, which holds any MSX tape. Each
format has its own reader, which turns the file into the tape model. The tape model
is the file's blocks in tape order. The capture, the build, the patches, and the
check work only on the model, so a new format needs only a new reader
([INTERNALS.md, Tape files](INTERNALS.md#tape-files)).

### Capture

`tools/capture.py` loads the game in `openMSX`, on a copy of the user's machine,
from its own cassette player. `capture.py` first removes the disk system's hooks and
work area, so that the game loads as it does on a cassette machine. It then types
the load command, presses a key when the load waits for one, and follows the tape
position as the tape service would keep it. `capture.py` patches the code that would
select a slot that holds nothing on this machine. It takes the snapshot at an
interrupt's entry, when the CPU's state is complete and the bytes below the stack
pointer are free ([INTERNALS.md, Capture](INTERNALS.md#capture)).

### Build

`tools/build.py` turns the snapshot into the image. The image holds the RAM pages,
VRAM, and the port writes that restore the PSG, PPI, and VDP. The image also holds
the tail, the restore's last code. A game that reads its tape during play also gets
the tape service, which `build.py` builds from the ROM, the tape files, and
`SERVICE.BIN`. That game also gets a scan that sends the game's own tape calls to
the tape service ([INTERNALS.md, Build](INTERNALS.md#build)).

### Restorer

`SNAPCAS.COM` runs on the real machine under MSX-DOS 1, MSX-DOS 2, or Nextor. It
checks that the machine fits the image, by the ROMs' checksums and DOS's mapper. The
restorer reads each record into its slot and segment while DOS still runs. A RAM
page that belongs in one of DOS's own segments waits in a holding segment. The
restorer then stops DOS, does the port writes, copies the held pages into place, and
jumps to the tail, which starts the game
([INTERNALS.md, Restorer](INTERNALS.md#restorer)).

### Tape service

A game that loads more of its tape during play reads it from the tape service, which
keeps the rest of the tape in mapper segments. T0, a copy of the BIOS's page 0 whose
tape routines call the service, replaces the ROM in page 0. Entries in page 3 serve
the code that goes around T0. By default the tape turns over and rewinds by itself.
With `/M` the tape stops where a real tape stops, and waits for the player's key.
GRAPH goes back to side 1's start, and CODE goes back to side 2's start. A game that
needs all of its page 3 gets the whole service in T0
([INTERNALS.md, Tape service](INTERNALS.md#tape-service)).

### Check

`tools/check.py` runs the restorer in `openMSX`, on a disk with DOS, `SNAPCAS.COM`,
and the image, and lets the game run for 60 seconds. The image fails on any of four
points:

| Point | The image fails when |
|---|---|
| 1 | The restored machine differs from the snapshot in its RAM, its VRAM, or its registers |
| 2 | The game writes to the tape service's part of page 3 |
| 3 | The machine reboots |
| 4 | The game stops at a BASIC error |

The check cannot see a game that hangs or shows garbage, so the real machine stays
the last test ([INTERNALS.md, Check](INTERNALS.md#check)).

## Decisions

| Decision | Reason |
|---|---|
| A machine file named after its model and cartridges, such as `phc28s-ram64k-carnivore2` | A machine file is a model and the cartridges in its slots, and two setups of one model need two names ([FILES.md, Machine file](FILES.md#machine-file)) |
| A capture variant named after the cartridges that it holds, in `machines/capture/`, and listed by the machine file's `variant` lines | A name that lists the cartridges says what the capture ran on, and one variant can serve two machines, as `vg8020` does ([FILES.md, Machine file](FILES.md#machine-file)) |
| A capture variant that runs the HB-F700P with its slot 0 not expanded, for the loaders that fail because slot 0 is expanded | A patch needs the code of each loader, and these loaders differ. After the War's search and Mot's copy of `ENASLT` are two of them. One model loads them all, and the restorer already writes 0 to the subslot register of a slot that the capture did not expand, which selects the main ROM in subslot 0 ([INTERNALS.md, The capture with slot 0 not expanded](INTERNALS.md#the-capture-with-slot-0-not-expanded)) |
| One reader for each tape format, and a format-neutral tape model for the rest of the code | A TSX file holds the turbo blocks that a CAS file cannot hold, so converting a TSX file to CAS would lose the games that need TSX. If each tool handled both formats, the formats would mix in every tool, while the model keeps each format in one file ([Tape files](#tape-files)) |
| A game file for each program of a compilation, named after its game | A player looks for a game by its name, and an image named after the tape holds only the tape's first program. One game file for the tape, with a line for each program, would keep the tape's `cas` and `sha1` lines in one place. But that alternative needs both game files with sections and changes to every tool and to the collection's cache, to save two lines for each program ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| Every program of a compilation in the collection's folder, even when the game has a dump of its own | A compilation's copy can differ from that dump, because the magazines renamed the games and changed their title screens. A folder for each collection keeps their names, such as `GOLF` or `STAR`, apart from the games of `games/` |
| A reboot after the restore fails the check, and a reset alone does not | Points 1 and 2 compare the restore and watch page 3, so a game that crashes after the restore and reboots the machine passes both points. A loader can also reset the machine on purpose after the restore and then start the game. The point therefore judges where the machine ends, at DOS starting `SNAPCAS.COM` again or at the BIOS's boot screen ([Check](#check)). The capture only logs its resets, for the same reason |
| One `service` value for a game, and `rom keep` without the mode without a part in page 3 | `no`, `at`, and `t0` choose between ways to serve the tape, so a game takes one of them. The machine's game file can replace that value as it replaces other keys. `rom keep` leaves the game only the entries in page 3, and that mode removes those entries. The two together therefore give an image whose tape calls reach the BIOS. No shipped game file has both |
| Restore a snapshot | The game's loader runs once, in `openMSX`, so its slot code, stubs, and checks need no changes on the real machine |
| Capture on a copy of the user's machine, with the disk system's hooks and work area removed | The snapshot holds the slots that the game selects on that machine, as when the game loads from a real tape |
| Snapshot at an interrupt's entry | The CPU's state is complete, interrupts are off, and the bytes below the stack pointer are free for the tail |
| Mapper pages restored to their own segments, over DOS's at the end | The game finds the segment numbers that it wrote, and the restorer overwrites DOS's memory only when the restorer no longer needs DOS |
| ROM checksums checked by the restorer | A snapshot runs only on the ROMs that it was taken with, and `build.py` can build T0 from `rom.bin` |
| Port writes, T0, and the tail made by `build.py` | The restorer copies records and fills in only the values that depend on the real machine |
| One restorer for every image | The user updates one program, and DOS passes that program the image's name |
| A game file can name the machine for the capture | A loader can trip over a cartridge that the game itself never selects again. The game therefore loads without the cartridge, and its image runs with the cartridge in place. Digger Dungeon's loader trips over the HB-F700P's RAM cartridge |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| T0 kept out of page 0 when the game's page 0 RAM is in DOS's mapper | On a single-mapper MSX2, T0 and that RAM need the same mapper register |
| `rom keep` in the game file, not a rule of the restorer | T0 in page 0 serves a BASIC program, whose tape calls are in the ROM and cannot be patched. But T0 in page 0 changes the slot register's page 0 bits. Gauntlet's RAM search adds the slot that it finds to those bits, expecting the ROM's slot 0, and selects an empty slot |
| Find the slot patches of the load by watching it, and not by a search of the whole tape | A search also changes bytes that are data or code that never runs, and a loader that checks a block's sum then fails to load it. A write that the watch sees runs, and selects a slot that holds nothing, so its patch is needed |
| Scan the snapshot and the unread blocks | Many games that load during play build stubs that T0 alone does not intercept |
| Rewind the capture with `savestate` and `loadstate` | `openMSX`'s `reverse goto` replays the input recorded after its target, while each key try must start from the saved moment with no other input |
| A tape with both sides, a wrap, and fixed keys for each side's start | Most such games' unread blocks have no names, so only the tape's position decides which block a game reads, as with a real tape |
| An automatic tape by default, and a manual one with `/M` | The automatic tape needs nothing from the player, and most players want such a tape. The manual tape follows what the game tells the player. 4x4 Off-Road Racing, for example, asks to stop the tape and later to rewind it |
| GRAPH for side 1's start and CODE for side 2's | GRAPH and CODE alone type no character, BASIC ignores them, and games rarely read them. By contrast, STOP pauses a BASIC program, the function keys type text, and many games use SELECT in their menus. On a Japanese MSX, CODE's key is KANA, which also switches the kana lock |
| RETURN to play on, and a read that goes on only when the key is released | RETURN is the key that a player presses without thinking. Games read RETURN, so the service waits for the key's release. The game, which does not run while the service waits, never sees RETURN |

## Limits

- A game that reads a non-standard block of its TSX file after the snapshot, such as
  a turbo loader's next level, gets no image unless its game file has `service no`.
  The reason is that the tape service serves only standard blocks. The build's error
  names the block ([Tape files](#tape-files)).
- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- DOS's four pages must be in one memory mapper, with enough free segments for the
  image's holding segments, the image's service segments, and the worker. A game
  with a long tape needs a large mapper.
- A game with the tape service needs one of two things. Either its page 3 keeps 143
  bytes from an address xxE1h free for the service's part of page 3, at the snapshot
  and in every later load ([Build](#build)). Or the game meets the conditions of the
  mode without a part in page 3
  ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)).
  `build.py` takes that mode when page 3 has no room, or when the game file's
  `service t0` asks for it.
- A game that reads the tape with its own code gets no tape service, so it runs only
  if it loads in a single pass.
- Without a part in page 3, T0 has no room for `TAPIN`'s skip of a header and of
  side 1's padding. A game that reads on with `TAPIN` into the next block or side
  therefore gets the header's bytes in that mode.
- The shipped machine's game files, `phc28s-ram64k-carnivore2.txt` and
  `vg8020-carnivore2.txt`, hold only on their machine. On another machine, the games
  that have such a file may need a machine's game file of their own for that
  machine.
- A game in the mode without a part in page 3 has only the automatic tape, because
  T0 has no room for the manual tape
  ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).
- With `/M`, a game that stops the motor between two loads without a message on the
  screen still waits for RETURN. The player sees no reason for the wait
  ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).
- A slot value gets no slot patch when the code of neither form in
  [INTERNALS.md, Slot patches](INTERNALS.md#slot-patches) sets it. The capture only
  logs its write, for a `patch` line by hand.
- A slot patch replaces only a field that names a slot that holds nothing, and
  replaces it with the slot that the slot map gives. A game that needs another slot
  therefore keeps its `patch` lines by hand.
- A snapshot taken without an interrupt overwrites the 26 bytes below the stack
  pointer with the tail.
- The tail needs 26 bytes below the stack pointer, in a RAM page that the snapshot
  keeps, or else 26 bytes below the start of the stack pointer's page. A game whose
  stack pointer is below 26, or whose bytes there are not in a kept RAM page, gets
  no image, because `build.py` stops ([FORMATS.md, Tail](FORMATS.md#tail)).
- A capture variant with slot 0 not expanded needs the main ROM in subslot 0 of slot
  0, and nothing else in slot 0 that the game uses. A game that writes slot 0's
  subslot register after the restore changes the real register, which its capture
  did not have
  ([INTERNALS.md, The capture with slot 0 not expanded](INTERNALS.md#the-capture-with-slot-0-not-expanded)).
- A game whose stack reaches FFFFh writes the subslot register when page 3 is an
  expanded slot, and that write changes the game's slots. Page 3 is such a slot in a
  capture on the VG-8020, where page 3 holds the Carnivore2's RAM.
- Music that BASIC's `PLAY` statement is still playing at the snapshot does not
  resume on a real Sanyo PHC-28S, though it does in `openMSX`. The cause is not
  known. A game whose music must end gets a `snapshot at` after the music.
- A restored game can behave differently from its capture. Konami's Soccer and
  Budokan reset in their captures on the PHC-28S and not in their checks, and the
  cause is not known ([NOTES.md, Limits](NOTES.md#limits)).

## Formats

The formats of the snapshot's files, the image, the tail, the port writes,
`SERVICE.BIN`, the tape service's tables, and the tape files are in
[FORMATS.md](FORMATS.md).
