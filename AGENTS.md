# Agents

This page is for an AI agent that works on `snapcas`. It gives each task as steps in
order, with the files that each step changes, the command that checks it, and a
table from each message that a step can print to its fix. It has two tasks: adding
a machine, and fixing a game that fails. The reasons behind the rules are in
[docs/DESIGN.md](docs/DESIGN.md), the formats of the files in
[docs/FILES.md](docs/FILES.md), and the games that taught each rule in
[docs/NOTES.md](docs/NOTES.md).

## Rules

These rules hold for every task:

| Rule | Why |
|---|---|
| Commit, push or open a pull request only when the user asks | The user reviews each change first |
| Start a step that you recommend only when the user says go | The user decides what comes next |
| A build prints no warnings | A warning hides the next one |
| Do not run `./snapcas.py try` yourself, and ask the user to run it | It opens `openMSX`'s window with its sound on, and the user hears it. The other tools run `openMSX` muted, without a window |
| Never add system ROMs, MSX-DOS or tape files to git | `snapcas` cannot ship them. Git ignores `dos/`, `downloads/`, `images/` and `out/` |
| Fix a game with lines in its game file, not with code | Each loader differs. Code gets a fix only when one form repeats over many tapes, as the automatic patches in `tools/patches/` do |
| Give each line that you add to a game file a comment above it that says why, and a blank line before the comment | The shipped game files are written that way, and the next reader needs the reason |

## Where things are

| Path | What it holds |
|---|---|
| `machines/<machine>.txt` | A machine: the `openMSX` arguments, the disk, the boot keys |
| `machines/capture/<variant>.txt` | A capture variant: a machine with fewer cartridges |
| `games/<GAME>/game.txt` | A game file: the lines that hold on every machine |
| `games/<GAME>/<machine>.txt` | A machine's game file: the lines that hold on one machine only |
| `downloads/` | The tape files, which `./snapcas.py snap` downloads |
| `out/games/<machine>.txt` | The results of `make games`, one line per game |
| `out/work/<machine>/<GAME>/snap/log.txt` | The capture's log: what it typed, each `TAPION`, the motor, each reset, where the load stopped and the screen then |
| `out/work/<machine>/<GAME>/snap/error.txt` | The capture's error, when it failed |
| `out/work/<machine>/<GAME>/scan.txt` | The scan's findings, in `patch` line form |
| `out/work/<machine>/<GAME>/check/report.txt` | The check's report: a line per point, then what failed and the screen's text |
| `tests/openmsx-failures.txt` | The games that fail in `openMSX` itself, which `make games` accepts |
| `tests/snapcas-failures.txt` | The games that fail because of `snapcas`, still to fix |

## Add a machine

A machine is a file in `machines/` that tells the tools how to start one MSX setup
in `openMSX`: the model, its cartridges, and the keys that pass its boot
([docs/FILES.md, Machine file](docs/FILES.md#machine-file)). The tools capture a
game on it, and the check restores the image on it. The example in each step is
the Sony HB-75P with a Carnivore2 in slot 1, `hb75p-carnivore2`.

### 1. Name the machine

A machine's name is the model, then each cartridge in slot order, in lower case,
with `empty` for an empty slot before a cartridge. A cartridge's name is
`openMSX`'s name for it in lower case, or a short form of a long name:

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
macOS with Homebrew that is
`/opt/homebrew/opt/openmsx/openMSX.app/Contents/Resources/share/machines/`, and on
Linux `/usr/share/openmsx/machines/`. The file's name, without `.xml`, is the value
of `-machine`. Its `primary` lines show the slots:

```
$ grep -n 'primary\|<RAM' .../share/machines/Sony_HB-75P.xml
74:    <primary external="true" slot="1"/>
76:    <primary slot="2">
77:      <RAM id="Main RAM">
82:    <primary external="true" slot="3"/>
```

A slot with `external="true"` is a cartridge slot. `openMSX` puts each `-ext`
cartridge in the next free cartridge slot, so the order of the `-ext` options must
give each cartridge the slot that it has on the real machine. Note where the
machine's own RAM is, because step 4 needs it: the HB-75P's RAM is in slot 2. The
cartridges are in `share/extensions/`, by the same rule. `openMSX`'s file follows
the real machine, but the user's machine decides: in BASIC, without cartridges,
`PRINT HEX$(INP(&HA8))` gives the slot of each page, as in
[Find the slot values](#find-the-slot-values).

### 3. Write the machine file

Write `machines/<name>.txt`. Copy the file of a machine with the same cartridge, and
change the model:

```
# Sony HB-75P (MSX1, 64 KB) with a Carnivore2. The Carnivore2 is in slot 1 and runs
# Nextor. The HB-75P's own RAM is in slot 2.
openmsx -machine Sony_HB-75P -ext Carnivore2
disk hda
boot "DefConfig" space
variant hb75p
```

`./snapcas.py machines` shows the first sentence of the first comment, so that
sentence is the model, then in brackets the MSX generation and the RAM, then the
cartridges: `Sony HB-75P (MSX1, 64 KB) with a Carnivore2`. The details go in the
sentences after it. The other lines depend on the cartridge that holds the disk:

| Disk cartridge | Lines | Example |
|---|---|---|
| Carnivore2 | `disk hda` and `boot "DefConfig" space`, which passes its boot menu | `vg8020-carnivore2` |
| MegaFlashROM SCC+ SD with Nextor only | `disk hda` and `firmware extensions/MegaFlashROM_SCC+_SD_Nextor.xml` | `fsa1-mfrsd` |
| MegaFlashROM SCC+ SD in `openMSX`'s stock setup | `disk hda` and `dos "A:\>" B`, because it boots MSX-DOS from its ROM disk | `hb75p-mfrsd` |
| SD Mapper v1 | `disk hda` and `firmware systemroms/snapcas/SDMAPPER.ROM` | `vg8020-sdmapper` |
| Sunrise IDE interface | `disk hda` | `nms8245-ram512k-sunriseide` |
| The machine's own floppy drive | `disk diska`, or `disk diska 360` for a single-sided drive | `vg8235` |

The DOS is Nextor unless a `dosfiles` line names `msxdos1` or `msxdos2`. A machine
whose firmware starts a menu in a graphics mode needs a `hold` line, as the FS-A1's
`hold del 6`, or `press` lines that choose BASIC in the menu, as the `hb75p`
capture variant's. Each line is in
[docs/FILES.md, Machine file](docs/FILES.md#machine-file).

### 4. Add a capture variant

A capture variant is the same machine with fewer cartridges, in
`machines/capture/`. The capture runs a game on it when the game's loader fails
with the cartridge present: a loader often looks for RAM from slot 0 up, and it
finds the Carnivore2's RAM in slot 1 before the machine's own. So a machine whose
disk cartridge is in a lower slot than its own RAM gets a variant without that
cartridge, named after the cartridges that it keeps, and a `variant` line for it:

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

When a variant with the same cartridges exists, such as `vg8020`, the machine lists
it in place of a new one. A model without a disk system can start a program of its
own in place of BASIC, as the HB-75P starts its Personal Data Bank menu, so the
variant can need `hold` or `press` lines that the machine does not. To see the
screen, dump it with `openMSX`'s `[screen]` command, which reads a text mode only,
or with `debug read_block VRAM 0 16384` and the `vdpreg` values for a graphics
mode, in a script that `tools/msx.py`'s `run` passes to a muted `openMSX`.

### 5. Check three games

Make and check the image of a game that loads once, of a game that loads during
play, and of a game that the capture variant captures, on the new machine. The
third game is one whose game file for a machine with the same cartridge has a
`capture` line, such as Alien Syndrome's `vg8020-carnivore2.txt`, and it needs that
line, with the new variant, in its game file for the new machine:

```
./snapcas.py snap CALDERO hb75p-carnivore2 --check
./snapcas.py snap GAUNTLET hb75p-carnivore2 --check
./snapcas.py snap ALIEN-SY hb75p-carnivore2 --check
```

Each prints four `check pass` lines and the image's path. When a run stops with a
message instead, the message names the cause:

| Message | Fix |
|---|---|
| `Couldn't find ROM file for ...` | The user's system ROMs lack the model's. Ask the user for them |
| `needs ... make firmware makes it` | Run `make firmware` |
| `boots msxdos1: put its files in dos/msxdos1/` | Ask the user for MSX-DOS's files ([dos/README.md](dos/README.md)) |
| `capture: BASIC's Ok did not appear within 120 seconds` | The `boot` lines do not pass the boot. Compare with a working machine of the same disk cartridge. When only the third game stops, the variant boots into a program of the model's own: add `hold` or `press` lines to the variant ([Add a capture variant](#4-add-a-capture-variant)) |
| `the tail's jump did not run within 120 seconds`, with BASIC on the screen | DOS did not start the check's `AUTOEXEC.BAT`: a wrong `disk`, `dos` or `dosfiles` line |

### 6. List the machine in the docs and the tests

Add the machine where the shipped machines are listed:

| File | Change |
|---|---|
| `tests/test_step9.py` | An entry in `SHIPPED`, with the folder of its DOS's files: `test_step4.NEXTOR` for Nextor. The test checks Caldero on every shipped machine |
| `docs/FILES.md` | A row in the table of shipped machine files, with 0 machine's game files, and a row in the table of capture variants |
| `docs/CLI.md` | The output of `./snapcas.py machines` in the example of `machines`, copied from the command |
| `docs/PLAN.md` | The machine in its DOS's row of the test machines' table |

Then run `make test`, which must pass.

### 7. Run the collection

Run every game on the new machine. It takes about 30 minutes, and it needs the
tapes in `downloads/`, which `snap` downloads one game at a time:

```
make games MACHINE=hb75p-carnivore2
```

Do not change `bin/` or `tools/` while it runs: each result is kept with a hash of
the game's files, the machine's files and the code in those two folders, and a
changed hash makes the next run make that game's image again. So a change to the
code makes the next run take as long as the first. The results go to
`out/games/hb75p-carnivore2.txt`. Fix each game that fails as in
[Fix a game that fails](#fix-a-game-that-fails), then write the number of the
machine's game files in its row of `docs/FILES.md`.

## Fix a game that fails

A game fails when a step of its image stops: the capture, which loads the game in
`openMSX` and takes the snapshot, the build, which makes the image, or the check,
which restores the image and runs it for 60 seconds
([docs/INTERNALS.md, Check](docs/INTERNALS.md#check)). Most failures on a new
machine have one cause: the game's loader selects RAM by slot, and the new machine
keeps its RAM in another slot.

### 1. Reproduce the failure

Run the game alone, with the check:

```
./snapcas.py snap <GAME> <machine> --check
```

`<GAME>` is the game file's folder, as `make games` and `./snapcas.py list --all`
show it. When a step fails and the game file has no `capture` line, `snap` runs the
steps again on each capture variant that the machine file lists. When a variant
passes, it prints:

```
snapcas.py: it passes, so the machine's game file needs: capture hb75p
```

Then write that line in the machine's game file ([Write the fix](#4-write-the-fix)),
and the fix is done. That is the most common fix: 314 of the shipped machine's game
files hold a `capture` line. When no variant passes, go on.

### 2. Read the failure

The step's message names the failure. Read the files that it points to, and the
same files of a machine where the game passes, from `out/games/<machine>.txt`:

| Message | Cause | Fix |
|---|---|---|
| `capture: the CPU is halted with no interrupt, at XXXXh` | The loader crashed, mostly because it selected a slot that holds no RAM | A capture variant, or a slot patch ([Patch the code](#3-patch-the-code)) |
| `capture: step 5 restarted more than 20 times` | The load waits for a key each time, and no key that the capture tries continues it | `continue <key>`, the key that the game asks for, or `snapshot at <seconds>` |
| `capture: the load ran for more than 3600 seconds` | The load never stops the motor for good | `snapshot at <seconds>`, a time after the load, from `log.txt` |
| `the first block is a non-standard block` or `is not a binary file, a BASIC` | The tape does not start with a block that the BIOS loads | `load 'RUN"CAS:"'`, or the command that the tape's label gives |
| `the tape needs N segments, more than M` | The machine's mapper has too few free segments for the tape | A capture variant whose game runs in the machine's own RAM, or a line in `tests/snapcas-failures.txt` |
| `the N bytes below SP XXXXh are not in a RAM page that the snapshot keeps`, or `cross a page boundary` | The stack is too low for the restorer's tail at the snapshot | `snapshot at <seconds>`, a later moment, when the stack has moved |
| `page 3 has no room for the tape service's part` | The game fills page 3 | `service t0`: the tape service without a part in page 3 |
| `the bytes at ... are not the patch's old bytes` | The patch was made for another dump | Make the patch again for this dump, with the `sha1` of its tape |
| `point 1: fail`, `the tail's jump did not run within 120 seconds` | The restore never reached the game. The report's screen shows the restorer's or DOS's message | The message says what to fix, often too few free segments |
| `point 1: fail` with differences | The restored machine differs from the snapshot | A failure of `snapcas`: a line in `tests/snapcas-failures.txt` |
| `point 2: fail`, `the game writes XXXXh, in the tape service's part of page 3` | The game keeps data where the tape service's part goes | `service at <address>`, an address xxE1h in page 3 that the game leaves alone, or `service t0` |
| `point 3: fail` | The restored machine rebooted, mostly because the loader crashed after the restore | A capture variant, or a slot patch |
| `point 4: fail` with a BASIC error, such as `Overflow in 130` | The game's BASIC program stops at an error | A patch of the program's text, as Field Master's game file has |

`log.txt` holds the line `load stopped at tape position ..., screen: ...`, which
shows where the load stopped before the snapshot. A reset there, or a screen that
shows BASIC or the boot screen, means that the loader crashed before the
snapshot. Each key of a game file is in
[docs/FILES.md, Game file](docs/FILES.md#game-file).

### 3. Patch the code

A slot patch changes the value that the loader writes to the slot register, port
A8h, so that it selects the machine's RAM. Find the loader's write first:

1. Read `scan.txt`, which lists the scan's findings in `patch` line form. The
   build already patches the findings in the snapshot's RAM pages. The findings in
   the tape's unread blocks are not patched, so such a finding is a line to add,
   and the line must also fix the block's sum when the block's loader checks one.
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

   The offset of a write in the tape file is its place: `side1:<offset>` in hex,
   or `side2:<offset>` for the side 2 file. A place in the snapshot's RAM is
   `page<n>:<offset>`, the offset from the start of the RAM page that the snapshot
   selects in page n.

#### Find the slot values

The slot register holds 2 bits per page: bits 1 and 0 give page 0's slot, bits 3
and 2 page 1's, bits 5 and 4 page 2's, and bits 7 and 6 page 3's. So a value is
page 3's slot × 64 + page 2's × 16 + page 1's × 4 + page 0's:

| Machine | Slots | Value |
|---|---|---|
| Philips VG-8020: ROM in slot 0, RAM in slot 3 | Page 0 in slot 0, pages 1 to 3 in slot 3 | FCh |
| Sony HB-75P: ROM in slot 0, RAM in slot 2 | Page 0 in slot 0, pages 1 to 3 in slot 2 | A8h |
| Sanyo PHC-28S: its own RAM in slot 0, page 3 only, and the RAM cartridge in slot 1 | Pages 1 and 2 in slot 1, pages 0 and 3 in slot 0 | 14h |

A loader that computes the value from the register, with `IN A,(0A8h)`, gets a
patch to `LD A,nn` with `NOP`s (`00`) to the same length, as Emerald Isle's game
file has: its last patch also keeps the sum that ends the block.
[docs/NOTES.md, Page 3's slot for the other pages](docs/NOTES.md#page-3s-slot-for-the-other-pages)
lists the loaders seen so far and their fixes.

### 4. Write the fix

A line that holds on every machine goes in `games/<GAME>/game.txt`. A line that
holds on one machine only goes in the machine's game file,
`games/<GAME>/<machine>.txt`: a `capture` line, a `service t0` line, a `snapshot`
line that only that machine needs, and a patch whose new bytes are a slot value.
The machine's game file starts with a comment that names the machine, and each line
has a comment above it that says why:

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

It prints the screen 60 seconds after the tape's end, or `a graphics screen`, which
usually means that the game runs. It plays the tape as it is, without the game
file's patches, keys or side 2. When the plain load fails as the capture does, the
game fails in `openMSX` itself: add a line to `tests/openmsx-failures.txt`, with the
machine, the folder and what fails. Otherwise the failure is one of `snapcas`: add
the same kind of line to `tests/snapcas-failures.txt`, with the cause when known.

### 6. Check the fix

Run `./snapcas.py snap <GAME> <machine> --check` again, which must pass. Then run
`make games MACHINE=<machine>`, which reruns only the games whose files changed,
or every game when the code in `bin/` or `tools/` changed. A
change to `game.txt` holds on every machine, so run `make games` on each machine
that has results in `out/games/` as well. Last, run `make test`.

## More

- [README.md](README.md): the folders and the `make` commands.
- [docs/CLI.md](docs/CLI.md): the `snapcas.py` commands.
- [docs/INTERNALS.md](docs/INTERNALS.md): the capture, the build and the check.
