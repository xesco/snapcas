# Agents

This page is for an AI agent that works on `snapcas`. The page gives each task as
steps in order. Each step names the files that the step changes and the command that
checks the step. Tables give the fix for each message that a step can print. The
page has four tasks: to make a game's image, to add a machine, to add a game, and to
fix a game that fails. The [README](README.md) gives the first three in short form
for a person. The reasons behind the rules are in [docs/DESIGN.md](docs/DESIGN.md).
The formats of the files are in [docs/FILES.md](docs/FILES.md), and the games that
taught each rule are in [docs/NOTES.md](docs/NOTES.md).

## Rules

These rules hold for every task:

| Rule | Why |
|---|---|
| Commit, push, or open a pull request only when the user asks | The user reviews each change first |
| Start a step that you recommend only when the user tells you to start it | The user decides what comes next |
| A build prints no warnings | A warning hides the next one |
| Do not run `./snapcas.py try` yourself. Ask the user to run it | The command opens `openMSX`'s window with the sound on, and the user hears the sound. The other tools run `openMSX` muted, without a window |
| Never add system ROMs or MSX-DOS to git. Add a tape file to the tests' `tests/tapes/` only when the user agrees | `snapcas` cannot ship ROMs or DOS, and git ignores `dos/`, `downloads/`, `images/`, and `out/`. The tests' tapes are in git, so each tape adds to the repository |
| Fix a game with lines in its game file, not with code | Each loader differs. Code gets a fix only when one form repeats over many tapes. The automatic patches in `tools/patches/` fix such forms |
| Above each line that you add to a game file, write a comment that says why. Put a blank line before the comment | The shipped game files have that form, and the next reader needs the reason |

## Where things are

| Path | What it holds |
|---|---|
| `machines/<machine>.txt` | A machine: the `openMSX` arguments, the disk, and the boot keys |
| `machines/capture/<variant>.txt` | A capture variant: a machine with fewer cartridges |
| `games/<GAME>/game.txt` | A game file: the lines that hold on every machine |
| `games/<GAME>/<machine>.txt` | A machine's game file: the lines that hold on one machine only |
| `custom/<GAME>/` | A custom game: its game file and its tape files. Git ignores both ([custom/README.md](custom/README.md)) |
| `images/<machine>/<GAME>/<GAME>.SNP` | A game's image, which `./snapcas.py snap` makes and `sync` copies to a card |
| `bin/SNAPCAS.COM` | The restorer, which starts an image on the MSX |
| `downloads/` | The tape files, which `./snapcas.py snap` downloads |
| `out/games/<machine>.txt` | The results of `make games`, one line per game |
| `out/work/<machine>/<GAME>/snap/log.txt` | The capture's log: what the capture typed, each `TAPION`, the motor, each reset, where the load stopped, and the screen at that moment. When the capture failed, the log's last line holds the error and the screen at that moment |
| `out/work/<machine>/<GAME>/snap/error.txt` | The capture's error, when the capture failed |
| `out/work/<machine>/<GAME>/scan.txt` | The scan's findings, in `patch` line form |
| `out/work/<machine>/<GAME>/check/report.txt` | The check's report: a line per point, then what failed and the screen's text |
| `tests/openmsx-failures.txt` | The games that fail in `openMSX` itself, which `make games` accepts |
| `tests/snapcas-failures.txt` | The games that fail because of `snapcas` and still need a fix. `make games` accepts these games too, and lists them apart from a new failure |

## Make a game's image

The user names a game and their MSX. The result is the game's image, `<GAME>.SNP`.
You check the image in `openMSX` and, when the user asks, copy the image to the
user's card.

### 1. Find the game

Run `./snapcas.py list <text>` to list the games whose folder or title holds the
text. The command ignores the case of the letters. When several games match, ask the
user which game they want. When no game matches and the user has the game's tape
file, add the game first ([Add a game](#add-a-game)).

### 2. Find the machine

To list the machines, run `./snapcas.py machines`. A machine is a model with its
cartridges in slot order, and a machine with one cartridge more or fewer is another
machine. So when the user has not named the model or said what is in each cartridge
slot, ask the user. When no machine matches, add the machine first
([Add a machine](#add-a-machine)).

### 3. Make and check the image

```
./snapcas.py snap <GAME> <machine> --check
```

When the game's tape is missing, the command downloads the tape from File-Hunter
into `downloads/`. The command prints four `check` lines and the image's path,
`images/<machine>/<GAME>/<GAME>.SNP`. When a step fails, go to
[Fix a game that fails](#fix-a-game-that-fails). The messages about the machine's
system ROMs, firmware, and DOS files are in the table of
[Check three games](#5-check-three-games).

### 4. Copy the images to the card

Copy the images only when the user asks, to the folder that the user names:

```
./snapcas.py sync <machine> <destination>
```

The command copies `SNAPCAS.COM` and the machine's images that are new or changed,
reads each copy back, and deletes no image on the card
([docs/CLI.md, Sync a card](docs/CLI.md#sync-a-card)). Then give the user the two
lines to type on the MSX, `CD \SNAPCAS\<first letter>` and
`\BIN\SNAPCAS <GAME>` ([docs/PLAYING.md](docs/PLAYING.md)).

### 5. Ask the user to play the game

The check runs the image for 60 seconds in `openMSX`. It does not play the game, and
it does not run on the real MSX. So ask the user to play the game on their MSX. When
the game fails, ask the user to say what they see.

## Add a machine

A machine is a file in `machines/` that tells the tools how to start one MSX setup
in `openMSX`. The file gives the model, its cartridges, and the keys that pass its
boot ([docs/FILES.md, Machine file](docs/FILES.md#machine-file)). The tools capture
a game on the machine, and the check restores the image on the machine. The example
in each step is the Sony HB-75P with a Carnivore2 in slot 1, `hb75p-carnivore2`.

### 1. Name the machine

A machine's name is the model, then each cartridge in slot order, in lower case.
Write `empty` for an empty slot before a cartridge. A cartridge's name is
`openMSX`'s name for the cartridge in lower case, or a short form of a long name:

| Cartridge | Name |
|---|---|
| Carnivore2 | `carnivore2` |
| A 64 KB or 512 KB RAM cartridge | `ram64k`, `ram512k` |
| MegaFlashROM SCC+ SD | `mfrsd` |
| Sunrise IDE interface | `sunriseide` |
| SD Mapper v1 | `sdmapper` |
| The `msxdos2` cartridge | `msxdos2` |

So the Sony HB-75P with a Carnivore2 in slot 1 is `hb75p-carnivore2`. Check with
`./snapcas.py machines` that the name is new.

### 2. Find the model and its slots in openMSX

`openMSX` describes each model in an XML file in its `share/machines/` folder. On
macOS with Homebrew, the folder is
`/opt/homebrew/opt/openmsx/openMSX.app/Contents/Resources/share/machines/`, and on
Linux the folder is `/usr/share/openmsx/machines/`. The value of `-machine` is the
file's name without `.xml`. The file's `primary` lines show the slots:

```
$ grep -n 'primary\|<RAM' .../share/machines/Sony_HB-75P.xml
74:    <primary external="true" slot="1"/>
76:    <primary slot="2">
77:      <RAM id="Main RAM">
82:    <primary external="true" slot="3"/>
```

A slot with `external="true"` is a cartridge slot. `openMSX` puts each `-ext`
cartridge in the next free cartridge slot. So the order of the `-ext` options must
give each cartridge the slot that the cartridge has on the real machine. Note where
the machine's own RAM is, because step 4 needs the RAM's location. The HB-75P's RAM
is in slot 2. The cartridges are in `share/extensions/`, by the same rule.
`openMSX`'s file follows the real machine, but the user's machine decides. In BASIC,
without cartridges, `PRINT HEX$(INP(&HA8))` gives the slot of each page, as in
[Find the slot values](#find-the-slot-values).

### 3. Write the machine file

Write `machines/<name>.txt`. Copy the file of a machine with the same cartridge.
Then change the model:

```
# Sony HB-75P (MSX1, 64 KB) with a Carnivore2. The Carnivore2 is in slot 1 and runs
# Nextor. The HB-75P's own RAM is in slot 2.
openmsx -machine Sony_HB-75P -ext Carnivore2
disk hda
boot "DefConfig" space
variant hb75p
```

`./snapcas.py machines` shows the first sentence of the first comment. So write that
sentence as the model, then the MSX generation and the RAM in brackets, then the
cartridges: `Sony HB-75P (MSX1, 64 KB) with a Carnivore2`. Put the details in the
sentences after the first sentence. The other lines depend on the cartridge that
holds the disk:

| Disk cartridge | Lines | Example |
|---|---|---|
| Carnivore2 | `disk hda` and `boot "DefConfig" space`. The `boot` line passes the Carnivore2's boot menu | `vg8020-carnivore2` |
| MegaFlashROM SCC+ SD with Nextor only | `disk hda` and `firmware extensions/MegaFlashROM_SCC+_SD_Nextor.xml` | `fsa1-mfrsd` |
| MegaFlashROM SCC+ SD in `openMSX`'s stock setup | `disk hda` and `dos "A:\>" B`, because the cartridge boots MSX-DOS from its ROM disk | `hb75p-mfrsd` |
| SD Mapper v1 | `disk hda` and `firmware systemroms/snapcas/SDMAPPER.ROM` | `vg8020-sdmapper` |
| Sunrise IDE interface | `disk hda` | `nms8245-ram512k-sunriseide` |
| The machine's own floppy drive | `disk diska`, or `disk diska 360` for a single-sided drive | `vg8235` |

The DOS is Nextor unless a `dosfiles` line names `msxdos1` or `msxdos2`. A machine
whose firmware starts a menu in a graphics mode needs either a `hold` line, or
`press` lines that choose BASIC in the menu. The FS-A1's `hold del 6` is such a
`hold` line, and the `hb75p` capture variant has such `press` lines.
[docs/FILES.md, Machine file](docs/FILES.md#machine-file) describes each line.

### 4. Add a capture variant

A capture variant is the same machine with fewer cartridges, in `machines/capture/`.
The capture runs a game on the variant when the game's loader fails with the
cartridge present. A loader often looks for RAM from slot 0 up, and such a loader
finds the Carnivore2's RAM in slot 1 before the machine's own RAM. So a machine
whose disk cartridge is in a lower slot than the machine's own RAM gets a variant
without that cartridge. Name the variant after the cartridges that the variant
keeps. Give the machine a `variant` line for the variant:

```
# Sony HB-75P without cartridges, so without a disk system. It is the capture
# variant of hb75p-carnivore2, for a game whose loader finds the Carnivore2's RAM
# in slot 1 before the internal RAM in slot 2.
# The capture uses no disk, but a machine file needs this line.
openmsx -machine Sony_HB-75P
disk hda
# Without a disk system the HB-75P starts its Personal Data Bank menu, in a
# graphics mode. BASIC is its fifth item, four cursor moves down from the first.
press down 8
press down 8.5
press down 9
press down 9.5
press return 10
```

A machine whose slot 0 is expanded can need one more variant. Many loaders fail
because slot 0 is expanded, with or without cartridges
([docs/INTERNALS.md, The capture with slot 0 not expanded](docs/INTERNALS.md#the-capture-with-slot-0-not-expanded)).
When slot 0 holds only the main ROM, in subslot 0, add a variant that runs the model
with its slot 0 not expanded, as `hbf700p-noexp0-ram512k-msxdos2` does. The
Makefile's rule for `Sony_HB-F700P_noexp0.xml` makes that model from `openMSX`'s
file, and the variant's `firmware` line names the model. Such a variant has `noexp0`
after the model in its name.

When a variant with the same cartridges exists, such as `vg8020`, the machine lists
that variant in place of a new one. A model without a disk system can start a
program of its own in place of BASIC, as the HB-75P starts its Personal Data Bank
menu. So the variant can need `hold` or `press` lines that the machine does not
need. To see the screen, dump the screen with `openMSX`'s `[screen]` command, which
reads a text mode only. For a graphics mode, dump the screen with
`debug read_block VRAM 0 16384` and the `vdpreg` values. Put the commands in a
script that `tools/msx.py`'s `run` passes to a muted `openMSX`.

### 5. Check three games

On the new machine, make and check the image of three games: a game that loads once,
a game that loads during play, and a game that the capture variant captures. The
third game is one whose game file for a machine with the same cartridge has a
`capture` line, such as Alien Syndrome's `vg8020-carnivore2.txt`. In its game file
for the new machine, the third game needs that line with the new variant:

```
./snapcas.py snap CALDERO hb75p-carnivore2 --check
./snapcas.py snap GAUNTLET hb75p-carnivore2 --check
./snapcas.py snap ALIEN-SY hb75p-carnivore2 --check
```

Each command prints four `check pass` lines and the image's path. When a run stops
with a message instead, the message names the cause:

| Message | Fix |
|---|---|
| `Couldn't find ROM file for ...` | The user's system ROMs lack the model's ROMs. Ask the user for them |
| `needs ... make firmware makes it` | Run `make firmware` |
| `boots msxdos1: put its files in dos/msxdos1/` | Ask the user for MSX-DOS's files ([dos/README.md](dos/README.md)) |
| `capture: BASIC's Ok did not appear within 120 seconds` | The `boot` lines do not pass the boot. Compare the machine file with the machine file of a working machine that has the same disk cartridge. When only the third game stops, the variant boots into a program of the model's own, so add `hold` or `press` lines to the variant ([Add a capture variant](#4-add-a-capture-variant)) |
| `the tail's jump did not run within 120 seconds`, or more for a large image, with BASIC on the screen | DOS did not start the check's `AUTOEXEC.BAT`, because a `disk`, `dos`, or `dosfiles` line is wrong |
| `check: the boot text '...' did not appear within 120 seconds` | The check's boot never shows the text of a `boot` line. Compare the machine file with the machine file of a working machine that has the same disk cartridge |

### 6. List the machine in the docs

Add the machine to each place that lists the shipped machines:

| File | Change |
|---|---|
| `docs/FILES.md` | A row in the table of shipped machine files, with 0 machine's game files, and a row in the table of capture variants |
| `docs/CLI.md` | The output of `./snapcas.py machines` in the example of `machines`, copied from the command |
| `docs/PLAN.md` | The machine in its DOS's row of the test machines' table |
| `README.md` | The number of machines, in the last sentence of "What it is" |

The tests need no line for the machine. `Shipped` in `tests/test_machines.py` checks
Caldero on every machine file of `machines/`, with the DOS files that the machine
file names. Then run `make test`, which must pass.

### 7. Run the collection

A run of every game takes about 30 minutes. The run needs the tapes in `downloads/`,
and `snap` downloads the tapes one game at a time. Run every game on the new
machine:

```
make games MACHINE=hb75p-carnivore2
```

The run tries each game that fails on the machine's capture variants, as `snap` does
for one game. When a variant passes, the run writes the `capture` line into the
machine's game file, under a comment that names the variant and the failure. Most
failures of a new machine end there, so that the machine starts with its `capture`
lines. Read a few of the files that the run wrote. `FIX=0` turns the retry off.

Do not change `bin/` or `tools/` during the run. The run keeps each result with a
hash of the game's files, the machine's files, the code in those two folders, the
DOS files that the check boots, and `openMSX`'s version. A changed hash makes the
next run make that game's image again. So a change to the code makes the next run
take as long as the first. Ctrl-C stops the run, and the run keeps its results so
far. The results go to `out/games/hb75p-carnivore2.txt`. The image of each game that
passes goes to `images/hb75p-carnivore2/`, and `./snapcas.py sync` copies the images
from that folder to a card. Fix each game that fails as in
[Fix a game that fails](#fix-a-game-that-fails). Then write the number of the
machine's game files in the machine's row of `docs/FILES.md`.

## Add a game

A game that `snapcas` does not ship is a custom game. A custom game is a folder in
`custom/` that holds the game's game file and its tape files
([custom/README.md](custom/README.md)). Git ignores the folder, so the game stays on
the user's computer. The example is a game named `MYGAME`, on the machine
`hb75p-carnivore2`.

### 1. Make the game's folder

The image takes the folder's name. So name the folder after the game, in upper case,
with up to 8 letters and digits. Copy the user's CAS files into the folder. Leave
the user's own files where they are:

```
custom/MYGAME/MYGAME.CAS
```

### 2. Write the game file

Write `custom/MYGAME/game.txt`. The game file needs one line, which names side 1's
tape with a `cas` line. A game on two tapes gets a `side2` line for the other tape.
The first comment says which game it is:

```
# My Game (1986)(Its Publisher)
cas MYGAME.CAS
side2 MYGAMEB.CAS
```

[docs/FILES.md, Game file](docs/FILES.md#game-file) describes each line of a game
file.

### 3. Make and check its image

```
./snapcas.py snap custom/MYGAME hb75p-carnivore2 --check
```

`snap` reads the tapes from the game's folder and never downloads them. The command
prints four `check` lines, and the image goes to
`images/hb75p-carnivore2/custom/MYGAME/`.

### 4. Fix what fails

When a step fails, follow [Fix a game that fails](#fix-a-game-that-fails), with
`custom/MYGAME` as the game. The fix's lines go in `custom/MYGAME/game.txt`, or in
`custom/MYGAME/hb75p-carnivore2.txt` when the lines hold on that machine only.

### 5. Share the game

Share the game only when the user asks. Move the game's folder into `games/`. Add
the game's `sha1` and `url` lines
([docs/FILES.md, Game file](docs/FILES.md#game-file)). Move the game's tapes into
`downloads/`. Then run `make games` on each machine that has results in
`out/games/`, as in [Check the fix](#6-check-the-fix). Last, add 1 to the number of
games in the README's "What it is".

## Fix a game that fails

A game fails when a step of its image stops. The steps are the capture, the build,
and the check. The capture loads the game in `openMSX` and takes the snapshot, and
the build makes the image. The check restores the image and runs it for 60 seconds
([docs/INTERNALS.md, Check](docs/INTERNALS.md#check)). Most failures on a new
machine have one cause. The game's loader selects RAM by slot, and the new machine
keeps its RAM in another slot.

### 1. Reproduce the failure

Run the game alone, with the check:

```
./snapcas.py snap <GAME> <machine> --check
```

`<GAME>` is the game file's folder, as `make games` and `./snapcas.py list --all`
show it. When a step fails and the game file has no `capture` line, `snap` runs the
steps again on each capture variant that the machine file lists. `snap` skips the
variants when the capture stops at an error in the input files, with status 1,
because a variant reads the same files. When a variant passes, `snap` prints:

```
snapcas.py: it passes, so the machine's game file needs: capture hb75p
```

Then write that line in the machine's game file ([Write the fix](#4-write-the-fix)),
and the fix is done. `make games MACHINE=<machine>` does both for every game that
fails on a machine ([Run the collection](#7-run-the-collection)). A `capture` line
is the most common fix. Of the shipped machine's game files, 660 hold a `capture`
line. When no variant passes, continue with the next step.

### 2. Read the failure

Read the files that the step's message points to. Also read the same files of a
machine where the game passes. Find such a machine in `out/games/<machine>.txt`. The
step's message names the failure:

| Message | Cause | Fix |
|---|---|---|
| `capture: the CPU is halted with no interrupt, at XXXX` | The loader crashed, mostly because it selected a slot that holds no RAM | A capture variant, or a slot patch ([Patch the code](#3-patch-the-code)) |
| `capture: step 5 restarted more than 20 times` | The load waits for a key each time, and no key that the capture tries continues the load | `continue <key>` with the key that the game asks for, or `snapshot at <seconds>` |
| `capture: the load ran for more than 3600 seconds` | The load never stops the motor permanently | `snapshot at <seconds>` with a time after the load. Read the time in `log.txt` |
| `the first block is a non-standard block` or `is not a binary file, a BASIC` | The tape does not start with a block that the BIOS loads | `load 'RUN"CAS:"'`, or the command that the tape's label gives |
| `the tape needs N segments, more than M` | The tape is longer than the tape service holds. The tape service holds 64 segments, 1 MB, with the code segment, or 16 segments, 256 KB, in the mode without a part in page 3 | With a limit of 16 segments, `service at <address>` with an address xxE1h in page 3 that the game leaves alone. That line gives the tape service its part of page 3. With a limit of 64 segments, add a line to `tests/snapcas-failures.txt` |
| `the 26 bytes below SP XXXXh are not in a RAM page that the snapshot keeps`, or `cross a page boundary or include FFFFh` | Mostly, the load failed on this machine, so the snapshot shows BASIC or a crash, with the stack in the ROM. `snap/log.txt` shows where the load stopped and the screen at that moment. Otherwise the stack is too low for the restorer's tail at the snapshot | For a failed load, a capture variant or a slot patch. Otherwise `snapshot at <seconds>` with a later moment, when the stack has moved |
| `the game's stack reaches FFFFh, the subslot register of slot N`, in `snap/log.txt` | The game's stack is at the top of memory, and page 3 is in an expanded slot. The push writes the slot's subslot register and deselects the game's RAM | A capture variant whose RAM is in a slot that is not expanded. On a machine without one, a patch of the game's `LD SP,0000h` to `LD SP,0FFFEh`, as in Space Beater's game file |
| `page 3 is not a RAM page that the snapshot keeps` | The load failed on this machine. The loader selected a slot without RAM in page 3, where its own code runs. `snap/log.txt` names the write, with `cuts off its code` | A capture variant, or a slot patch |
| `page 3 has no room for the tape service's part, and rom keep needs it` | The game fills page 3, and the game file's `rom keep` does not allow the mode without a part in page 3 | `service at <address>` with an address xxE1h in page 3 that the game leaves alone, or the game file without `rom keep` |
| `the tape service without a part in page 3 keeps T0 in page 0 of DOS's mapper` | Either the game fills page 3 or its game file has `service t0`. The game also keeps RAM of DOS's mapper in page 0, where that mode puts T0 | A capture variant, whose RAM is outside DOS's mapper, or `service at <address>` |
| `the bytes at ... are not the patch's old bytes` | The patch was made for another dump | Make the patch again for this dump, with the `sha1` of its tape |
| `point 1: fail`, `the restorer stopped: ...` | The restorer refused the image and returned to DOS. The line holds the restorer's message | The message says what to fix. Often the problem is too few free segments |
| `point 1: fail`, `the tail's jump did not run within 120 seconds`, or more for a large image | The restore never reached the game, and the restorer printed no message. The report's screen shows where the restore stopped | DOS's message says what to fix. A restorer that hangs is a failure of `snapcas`, so add a line to `tests/snapcas-failures.txt` |
| A failed point with another line that starts with `check:` | A callback of `tools/tcl/check.tcl` failed, and the line holds the callback's error | A failure of `snapcas`, so add a line to `tests/snapcas-failures.txt` |
| `point 1: fail` with differences | The restored machine differs from the snapshot | A failure of `snapcas`, so add a line to `tests/snapcas-failures.txt` |
| `point 2: fail`, `the game writes XXXXh, in the tape service's part of page 3` | The game keeps data where the tape service's part goes | `service at <address>` with an address xxE1h in page 3 that the game leaves alone, or `service t0` |
| `point 3: fail` | The restored machine rebooted, mostly because the loader crashed after the restore | A capture variant, or a slot patch |
| `point 4: fail` with a BASIC error, such as `Overflow in 130` | The game's BASIC program stops at an error | A patch of the program's text, such as the patch in Field Master's game file |

`log.txt` holds the line `load stopped at tape position ..., screen: ...`. That line
shows where the load stopped before the snapshot. A reset there, or a screen that
shows BASIC or the boot screen, means that the loader crashed before the snapshot.
[docs/FILES.md, Game file](docs/FILES.md#game-file) describes each key of a game
file.

### 3. Patch the code

A slot patch changes the value that the loader writes to the slot register, port
A8h, so that the loader selects the machine's RAM. On any machine, the tools already
patch the forms in the next table, by the slot map that the capture makes of the
machine's RAM. The capture patches most of the forms, and the scan in the build
patches two. These forms need no line:

| Code | Automatic patch |
|---|---|
| `LD A,n / OUT (0A8h),A` or `LD A,n / CALL 013Bh`, run before the snapshot, whose n names a slot that holds nothing | [Slot patches](docs/INTERNALS.md#slot-patches), at each copy in the tape |
| The same in the snapshot's RAM, run after the snapshot | The scan, in the build |
| The same, run from page 3, that moves page 3 to a slot where the code differs | [The RAM search patch](docs/INTERNALS.md#the-ram-search-patch), which keeps page 3 |
| A stub of `TAPION` that selects the ROM in page 0 as `AND H / LD L,A`, in the mode without a part in page 3 | The scan, in the build ([Without a part in page 3](docs/INTERNALS.md#without-a-part-in-page-3)) |
| Level 9's, CasLink3's, and Engesoft's copies of page 3's slot to the other pages | [The page copy patch](docs/INTERNALS.md#the-page-copy-patch) |
| The interrupt handler of Aventuras AD's interpreter, which writes the slot register from the game's copy of it, on an MSX2 | [The interrupt slot patch](docs/INTERNALS.md#the-interrupt-slot-patch) |

`log.txt` names each write that the capture saw and did not patch, with
`for a patch line`. The log names each address and value once, and leaves out the
writes of the BIOS's own slot routines. Find the loader's write first:

1. Read `scan.txt`, which lists the scan's findings in `patch` line form. The build
   already patches a finding in the snapshot's RAM pages when the finding's line
   holds new bytes after `>`. The build does not patch the findings in the tape's
   unread blocks, so such a finding is a line to add. When the block's loader checks
   a sum, the line must also fix the block's sum.
2. Otherwise search the tape file for the forms that write the register:

   | Bytes | Code |
   |---|---|
   | `3E nn D3 A8` | `LD A,nn / OUT (0A8h),A` |
   | `3E nn CD 3B 01` | `LD A,nn / CALL 013Bh`, the BIOS's `WSLREG` |
   | `DB A8 ...` | `IN A,(0A8h)`, then code that computes the value, such as Level 9's and CasLink3's |

   ```
   python3 -c "import sys; d = open(sys.argv[1], 'rb').read(); i = d.find(bytes.fromhex('D3A8'))
   while i >= 0: print(hex(i - 2), d[i - 2:i + 2].hex(' ')); i = d.find(bytes.fromhex('D3A8'), i + 1)" downloads/<GAME>.CAS
   ```

   The offset of a write in the tape file is the write's place. Give the place as
   `side1:<offset>` in hex, or as `side2:<offset>` for the side 2 file. A place in
   the snapshot's RAM is `page<n>:<offset>`, where the offset counts from the start
   of the RAM page that the snapshot selects in page n.

#### Find the slot values

The slot register holds 2 bits per page. Bits 1 and 0 give page 0's slot, bits 3 and
2 give page 1's slot, bits 5 and 4 give page 2's slot, and bits 7 and 6 give page
3's slot. So a value is page 3's slot × 64 + page 2's slot × 16 + page 1's slot ×
4 + page 0's slot:

| Machine | Slots | Value |
|---|---|---|
| Philips VG-8020: ROM in slot 0, RAM in slot 3 | Page 0 in slot 0, pages 1 to 3 in slot 3 | FCh |
| Sony HB-75P: ROM in slot 0, RAM in slot 2 | Page 0 in slot 0, pages 1 to 3 in slot 2 | A8h |
| Sanyo PHC-28S: its own RAM in slot 0, page 3 only, and the RAM cartridge in slot 1 | Pages 1 and 2 in slot 1, pages 0 and 3 in slot 0 | 14h |

A loader that computes the value from the register, with `IN A,(0A8h)`, gets a patch
to `LD A,nn` with `NOP`s (`00`) to the same length. Emerald Isle's game file has
such a patch, and that game file's last patch also keeps the sum that ends the
block.
[docs/NOTES.md, Page 3's slot for the other pages](docs/NOTES.md#page-3s-slot-for-the-other-pages)
lists the loaders seen so far and their fixes.

### 4. Write the fix

A line that holds on every machine goes in `games/<GAME>/game.txt`. The machine's
game file, `games/<GAME>/<machine>.txt`, gets a line that holds on one machine only.
Such lines are a `capture` line, a `service t0` line, a `snapshot` line that only
that machine needs, and a patch whose new bytes are a slot value. The machine's game
file starts with a comment that names the machine. Each line has a comment above it
that says why:

```
# Lines for the Sony HB-75P with a Carnivore2 in slot 1.

# The capture runs without the Carnivore2, whose RAM in slot 1 the game's loader
# finds before the internal RAM in slot 2.
capture hb75p
```

```
# The game selects RAM in slot 2. The NMS 8250 has its RAM in slot 3.
# LD A,0A8h / OUT (0A8h),A selects slot 2 in pages 1 to 3. The patch selects
# slot 3 there.
patch side1:FD6 3E A8 D3 A8 > 3E FC D3 A8
```

A `patch` line needs the game file's `sha1` line, which every shipped game file has.

### 5. Decide whether openMSX itself fails

When no line fixes the game, load its tape in plain `openMSX`, without `snapcas`:

```
python3 -I tools/plain.py <GAME> <machine>
```

The command prints the screen 60 seconds after the tape's end, or
`a graphics screen`, an output that usually means that the game runs. The command
plays the tape as it is, without the game file's patches, keys, or side 2. A loader
that crashed in a graphics mode prints `a graphics screen` too. So for such an
output, also compare `snap/log.txt` with the log of a machine where the game passes.
When the plain load fails as the capture does, the game fails in `openMSX` itself,
so add a line to `tests/openmsx-failures.txt`. The line holds the machine, the
folder, and what fails. Otherwise the failure is one of `snapcas`, so add the same
kind of line to `tests/snapcas-failures.txt`, with the cause when you know it.
`make games` reads both lists before it starts, and stops at a line that it cannot
read. It prints the failures of each list as a group of their own, and fails only
for a game that fails and is in neither list.

### 6. Check the fix

Run `./snapcas.py snap <GAME> <machine> --check` again. The command must pass. Then
run `make games MACHINE=<machine>`. That command reruns only the games whose files
changed. When the code in `bin/` or `tools/`, the DOS files, or `openMSX`'s version
changed, the command reruns every game. A change to `game.txt` holds on every
machine, so also run `make games` on each machine that has results in `out/games/`.
Last, run `make test`.

## More

- [README.md](README.md): the tasks in short form, for a person.
- [docs/PLAYING.md](docs/PLAYING.md): what the MSX needs, and the tape's keys.
- [docs/BUILD.md](docs/BUILD.md): the folders and the `make` commands.
- [docs/CLI.md](docs/CLI.md): the `snapcas.py` commands.
- [docs/INTERNALS.md](docs/INTERNALS.md): the capture, the build, and the check.
