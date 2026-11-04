# `snapcas` design

`snapcas` starts a cassette game from disk on one real MSX1 or MSX2. `openMSX` loads
the game from its tape file, in its own cassette player, on a copy of the user's
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
| Replay | `<GAME>.RPL`, a recording of the load's screen and sound that the restorer can play before the restore ([PLAN.md, The replay's design](PLAN.md#the-replays-design)) |

## Files and commands

| File | Written by | Contents |
|---|---|---|
| `machines/<machine>.txt` | A person, once per machine | How to start the machine in `openMSX` |
| `games/<game>/game.txt` | A person or an LLM | The game's settings that hold on every machine |
| `games/<game>/<machine>.txt` | A person or an LLM, for a game that needs it | The game's settings that hold only on one machine, named after the machine file with `-` for `/` ([FILES.md, Game file](FILES.md#game-file)) |
| `games/<collection>/<game>/` | A person or an LLM | A compilation's program, with the same files as a game's folder. Its `<game>` below `images/<machine>/` and `out/work/<machine>/` is `<collection>/<game>` ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| `custom/<game>/` | The user | A custom game: its `game.txt` and its tape files, which `snap` reads from the folder without downloading them. Its `<game>` below `images/<machine>/` and `out/work/<machine>/` is `custom/<game>` ([CLI.md, Your own games](CLI.md#your-own-games)) |
| `downloads/<TAPE>` | `snapcas.py snap` | The tape files that it downloads from File-Hunter, each checked against its game file's SHA-1 ([CLI.md, Download](CLI.md#download)) |
| `tests/tapes/<TAPE>` | The developers | The tape files of the tests, in git |
| `images/<machine>/<game>/<GAME>.SNP` | `snapcas.py snap` | The image, which `snap` moves from the work folder when every step passes |
| `images/<machine>/<game>/<GAME>.RPL` | `snapcas.py snap` | The replay, beside the image, once the replay is built |
| `out/work/<machine>/<game>/<GAME>.SNP` | `tools/build.py` | The image, until `snap` moves it |
| `out/work/<machine>/<game>/snap/` | `tools/capture.py` | The snapshot |
| `out/work/<machine>/<game>/scan.txt` | `tools/build.py` | The scan's findings and patches |
| `out/work/<machine>/<game>/build.txt` | `tools/build.py` | What the check takes from the build: the RAM bytes that the build patched, under each RAM file of their segment, the tape service's part of page 3, and the address of its tape position `C_POS` ([Check](#check)) |
| `out/work/<machine>/<game>/check/` | `tools/check.py` | The check's report and savestates |
| `out/work/<machine>/<game>/try/` | `tools/try.py` | The disk of `snapcas.py try` |
| `out/games/<machine>.txt` | `tools/games.py` | The result of each game file on the machine ([INTERNALS.md, The games run](INTERNALS.md#the-games-run)) |
| `dos/` | The user, and the Makefile for `dos/nextor/` | The DOS system files of the checks: `msxdos1/`, `msxdos2/` and `nextor/` |
| `out/cache/` | The Makefile | The tools that it downloads and builds, and the test home of `openMSX` |
| `bin/SNAPCAS.COM` | The developers | The restorer, from `src/snapcas.asm` |
| `bin/SERVICE.BIN` | The developers | The code that `build.py` writes into images: the tape service's routines, entries, entry code and reader, and the tail, from `src/service.asm` ([FORMATS.md, SERVICE.BIN](FORMATS.md#servicebin)) |

The `bin/` files are built with sjasmplus 1.24.0 and shipped. Git keeps only a short
`README.md` in `custom/`, `downloads/`, `dos/`, `images/` and `out/`, and ignores
the rest of them. `out/work/<machine>/<game>/` is a shipped or custom game's work
folder. A game folder elsewhere, as the tests make below `out/test/`, holds its own
work folder, `<folder>/<machine>/`, so the tests write nothing to `out/work/` or
`images/`. `<machine>` is a machine file's name below `machines/` without `.txt`,
such as `vg8020-carnivore2` ([FILES.md, Machine file](FILES.md#machine-file)). Each
game is processed by four commands, in this order:

1. `tools/capture.py <game> <machine> --tapes <dir>` loads the game in `openMSX` and
   saves the snapshot ([Capture](#capture)). `<dir>` holds the tape files, CAS or
   TSX ([Tape files](#tape-files)): `downloads/` for `snapcas.py snap`, and
   `tests/tapes/` for the tests.
2. `tools/build.py <game> <machine> --tapes <dir>` writes the image and `scan.txt`
   ([Build](#build)), and prints `<GAME>`.
3. `tools/check.py <game> <machine> --dos <dir>` runs the restorer in `openMSX` and
   verifies the restore ([Check](#check)). `<dir>` holds the user's DOS system
   files.
4. The user copies `SNAPCAS.COM` and `<GAME>.SNP` to a disk of the real machine and
   runs `SNAPCAS <GAME>`. The replay, `/R`, and the tape speed, `/T1200` and
   `/T2400`, are planned ([PLAN.md](PLAN.md), steps 7 and 8). With `/M`, the tape
   moves only when the player presses a key
   ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).

`./snapcas.py snap <game> <machine> [--check [--dos <dir>]]`, the `snapcas` command
at the repository's top ([CLI.md](CLI.md)), makes the image in one command. It
downloads the game's tape files that are missing from `downloads/`, then runs steps
1 and 2 with `--tapes downloads/`, and step 3 with `--check`, with Nextor's files
from `dos/nextor/` unless `--dos` gives others. It downloads Nextor's files there
first when they are missing, pinned by SHA-256 as the Makefile pins them. When every
step passes, it moves a shipped game's image to `images/`. The tests set
`SNAPCAS_DOWNLOADS` to `tests/tapes/`, so that `snap` finds their tapes there and
downloads nothing. When a step fails and the game file names no capture variant, it
runs these steps again on each capture variant that the machine file lists, in the
order of its `variant` lines ([FILES.md, Machine file](FILES.md#machine-file)). A
failed capture counts too, because a loader that trips over a cartridge can crash
during the capture. It keeps the first image that passes, and prints the `capture`
line that made it, for the machine's game file. Otherwise it makes the image of the
game file's own lines again, and exits with the status of the first step that
failed. `capture.py`'s `--capture <variant>` names the variant, in place of the game
file's `capture` line.

The tools are Python 3 programs that require only Python 3 and `openMSX` 22.0, so
they run on macOS, Linux and Windows. They print errors on standard error, naming
the file and the problem, and exit with 0 on success, 1 for an error in the input
files, 2 when `openMSX` fails or a wait times out, and 3 when a check fails.

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
blocks that the BIOS's tape routines read, so a tape whose loader reads its own
format, as a turbo loader does, needs a TSX file, which holds any MSX tape. Each
format has its own reader, which turns the file into the tape model, the file's
blocks in tape order. The capture, the build, the patches and the check work only on
the model, so a new format needs only a new reader
([INTERNALS.md, Tape files](INTERNALS.md#tape-files)).

### Capture

`tools/capture.py` loads the game in `openMSX`, on a copy of the user's machine,
from its own cassette player. It first removes the disk system's hooks and work
area, so that the game loads as on a cassette machine, then types the load command,
presses a key when the load waits for one, and follows the tape position as the tape
service would keep it. It patches the code that would select a slot that holds
nothing on this machine. It takes the snapshot at an interrupt's entry, when the
CPU's state is complete and the bytes below the stack pointer are free
([INTERNALS.md, Capture](INTERNALS.md#capture)).

### Build

`tools/build.py` turns the snapshot into the image: the RAM pages, VRAM, the port
writes that restore the PSG, PPI and VDP, and the tail, the restore's last code. A
game that reads its tape during play also gets the tape service, built from the ROM,
the tape files and `SERVICE.BIN`, and a scan that sends the game's own tape calls to
it ([INTERNALS.md, Build](INTERNALS.md#build)).

### Restorer

`SNAPCAS.COM` runs on the real machine under MSX-DOS 1, MSX-DOS 2 or Nextor. It
checks that the machine fits the image, by the ROMs' checksums and DOS's mapper, and
reads each record into its slot and segment while DOS still runs. A RAM page that
belongs in one of DOS's own segments waits in a holding segment. The restorer then
stops DOS, performs the port writes, copies the held pages into place, and jumps to
the tail, which starts the game ([INTERNALS.md, Restorer](INTERNALS.md#restorer)).

### Tape service

A game that loads more of its tape during play reads it from the tape service, which
keeps the rest of the tape in mapper segments. T0, a copy of the BIOS's page 0 whose
tape routines call the service, replaces the ROM in page 0, and entries in page 3
serve the code that goes around T0. By default the tape turns over and rewinds by
itself. With `/M` it stops where a real tape stops, and waits for the player's key.
GRAPH goes back to side 1's start and CODE to side 2's. A game that needs all of its
page 3 gets the whole service in T0
([INTERNALS.md, Tape service](INTERNALS.md#tape-service)).

### Check

`tools/check.py` runs the restorer in `openMSX`, on a disk with DOS, `SNAPCAS.COM`
and the image, and lets the game run for 60 seconds. The image fails on any of four
points:

| Point | The image fails when |
|---|---|
| 1 | The restored machine differs from the snapshot: its RAM, its VRAM or its registers |
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
| One reader for each tape format, and a format-neutral tape model for the rest of the code | A TSX file holds the turbo blocks that a CAS file cannot, so converting it to CAS would lose the games that need TSX. Teaching each tool both formats would mix them in every tool, while the model keeps each format in one file ([Tape files](#tape-files)) |
| A game file for each program of a compilation, named after its game | A player looks for a game by its name, and an image named after the tape holds only the tape's first program. One game file for the tape, with a line for each program, would keep the tape's `cas` and `sha1` lines in one place, but it needs game files with sections and changes to every tool and to the collection's cache, to save two lines for each program ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) |
| Every program of a compilation in the collection's folder, even when the game has a dump of its own | A compilation's copy can differ from that dump, because the magazines renamed the games and changed their title screens. A folder for each collection keeps their names, such as `GOLF` or `STAR`, apart from the games of `games/` |
| A reboot after the restore fails the check, and a reset alone does not | Points 1 and 2 compare the restore and watch page 3, so a game that crashes into a reboot after the restore passes them. A loader can also reset the machine on purpose after the restore and then start the game, so the point judges where the machine ends: DOS starting `SNAPCAS.COM` again, or the BIOS's boot screen ([Check](#check)). The capture only logs its resets, for the same reason |
| One `service` value for a game, and `rom keep` without the mode without a part in page 3 | `no`, `at` and `t0` choose between ways to serve the tape, so a game takes one of them, and the machine's game file can replace it as it replaces other keys. `rom keep` leaves the game only the entries in page 3, which that mode removes, so the two together give an image whose tape calls reach the BIOS. No shipped game file has both |
| Restore a snapshot | The game's loader runs once, in `openMSX`, so its slot code, stubs and checks need no changes on the real machine |
| Capture on a copy of the user's machine, with the disk system's hooks and work area removed | The snapshot holds the slots that the game selects on that machine, as when it loads from a real tape |
| Snapshot at an interrupt's entry | The CPU's state is complete, interrupts are off, and the bytes below the stack pointer are free for the tail |
| Mapper pages restored to their own segments, over DOS's at the end | The game finds the segment numbers that it wrote, and DOS's memory is overwritten only when DOS is no longer needed |
| ROM checksums checked by the restorer | A snapshot runs only on the ROMs it was taken with, and `build.py` can build T0 from `rom.bin` |
| Port writes, T0 and the tail made by `build.py` | The restorer copies records and fills in only the values that depend on the real machine |
| One restorer for every image | The user updates one program, and DOS passes it the image's name |
| A game file can name the machine for the capture | A loader can trip over a cartridge that the game itself never selects again, so the game loads without it, and its image runs with the cartridge in place. Sootland's loader trips over the HB-F700P's RAM cartridge |
| Replay a recording of the load, not the load | Loading again on the real machine, through the tape service from the start, brings back what the snapshot avoids: loaders that go around T0 through their own slot code, loaders that use the page 0 RAM where T0 is, and loaders that trip over the machine's slots |
| Tape service only for games that load during play | A game that loads in a single pass runs exactly as in the snapshot |
| T0 kept out of page 0 when the game's page 0 RAM is in DOS's mapper | On a single-mapper MSX2, T0 and that RAM need the same mapper register |
| `rom keep` in the game file, not a rule of the restorer | T0 in page 0 serves a BASIC program, whose tape calls are in the ROM and cannot be patched, but it changes the slot register's page 0 bits. Gauntlet's RAM search adds the slot that it finds to those bits, expecting the ROM's slot 0, and selects an empty slot |
| Find the slot patches of the load by watching it, and not by a search of the whole tape | A search also changes bytes that are data or code that never runs, and a loader that checks a block's sum then fails to load it. A write that the watch sees runs, and selects a slot that holds nothing, so its patch is needed |
| Scan the snapshot and the unread blocks | Many games that load during play build stubs that T0 alone does not intercept |
| The replay read into RAM before it plays | A disk read stops the frames and the tape's sound, and a compressed replay holds a few tens of KB, which fit in a few free segments |
| The replay starts at BASIC's screen, before the load command | The player sees the command typed and presses RETURN, as on a cassette machine, and the screen is the capture's, so it fits the machine |
| The tape speed as an option of `SNAPCAS`, fast by default | The player chooses at each run between a quick load and the experience of the tape, and the image stays the same |
| Rewind the capture with `savestate` and `loadstate` | `openMSX`'s `reverse goto` replays the input recorded after its target, while each key try must start from the saved moment with no other input |
| A tape with both sides, a wrap, and fixed keys for each side's start | Most such games' unread blocks have no names, so only the tape's position decides which block a game reads, as with a real tape |
| An automatic tape by default, and a manual one with `/M` | The automatic tape needs nothing from the player, and that is how most players want it. The manual tape follows what the game tells the player, as 4x4 Off-Road Racing does when it asks to stop the tape and later to rewind it, and with `/T1200` it avoids the wrap's reading of the rest of a side at tape speed |
| GRAPH for side 1's start and CODE for side 2's | GRAPH and CODE alone type no character, BASIC ignores them, and games rarely read them, while STOP pauses a BASIC program, the function keys type text, and many games use SELECT in their menus. On a Japanese MSX, CODE's key is KANA, which also switches the kana lock |
| RETURN to play on, and a read that goes on only when the key is released | RETURN is the key that a player presses without thinking. Games read it, so the service waits for its release, and the game, which does not run while the service waits, never sees it |

## Limits

- A game that reads a non-standard block of its TSX file after the snapshot, such as
  a turbo loader's next level, gets no image unless its game file has `service no`,
  because the tape service serves only standard blocks. The build's error names the
  block ([Tape files](#tape-files)).
- A game that uses more mapper segments than the four mapped at the snapshot does
  not run.
- DOS's four pages must be in one memory mapper, with enough free segments for the
  image's holding and service segments and the worker. A game with a long tape needs
  a large mapper.
- A game with the tape service needs one of two things. Either its page 3 keeps 168
  bytes from an address xxE1h free for the service's part of page 3, at the snapshot
  and in every later load ([Build](#build)). Or the game meets the conditions of the
  mode without a part in page 3, which `build.py` takes when page 3 has no room, or
  the game file's `service t0` asks for
  ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)).
- A game that reads the tape with its own code gets no tape service, so it runs only
  if it loads in a single pass.
- Without a part in page 3, T0 has no room for `TAPIN`'s skip of a header and of
  side 1's padding, so a game that reads on with `TAPIN` into the next block or side
  gets the header's bytes in that mode.
- The shipped machine's game files, `phc28s-ram64k-carnivore2.txt` and
  `vg8020-carnivore2.txt`, hold only on their machine. On another machine, the games
  that have one may need a machine's game file of their own for that machine.
- A game in the mode without a part in page 3 has only the automatic tape, because
  T0 has no room for the manual tape
  ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).
- With `/M`, a game that stops the motor between two loads without a message on the
  screen still waits for RETURN, and the player sees no reason for the wait
  ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)).
- A slot value that the code of neither form in
  [INTERNALS.md, Slot patches](INTERNALS.md#slot-patches) sets gets no slot patch.
  The capture only logs its write, for a `patch` line by hand.
- A slot patch replaces only a field that names a slot that holds nothing, and with
  the slot that the slot map gives, so a game that needs another slot keeps its
  `patch` lines by hand.
- The replay, once built, is a recording: a loader that lets the player act while it
  loads shows only what happened in the capture.
- A snapshot taken without an interrupt overwrites the 26 bytes below the stack
  pointer with the tail.
- The tail needs 26 bytes below the stack pointer, in a RAM page that the snapshot
  keeps, or else 26 bytes below the start of the stack pointer's page. A game whose
  stack pointer is below 26, or whose bytes there are not in a kept RAM page, gets
  no image: `build.py` stops ([FORMATS.md, Tail](FORMATS.md#tail)).
- A game whose stack reaches FFFFh writes the subslot register when page 3 is an
  expanded slot, as the Carnivore2's RAM is in a capture on the VG-8020, and its
  slots change under it.
- Music that BASIC's `PLAY` statement is still playing at the snapshot does not
  resume on a real Sanyo PHC-28S, though it does in `openMSX`, and the cause is not
  known. A game whose music must end gets a `snapshot at` after it.
- A restored game can behave differently from its capture: Konami's Soccer and
  Budokan reset in their captures on the PHC-28S and not in their checks, and why is
  not known ([NOTES.md, Limits](NOTES.md#limits)).

## Formats

The formats of the snapshot's files, the image, the tail, the port writes,
`SERVICE.BIN`, the tape service's tables, the replay stream and the tape files are
in [FORMATS.md](FORMATS.md).
