# `snapcas` plan

This page lists the steps that build the first version of `snapcas`, in order, and
the tests that each step adds. It is for the developers, and it follows the design
([DESIGN.md](DESIGN.md)). Each step ends with a review by the user before the next
one starts, and the whole test suite runs with one command, `make test`.

## Test setup

The build pins its tools, and the tests read their inputs from two folders that the
user names, because `snapcas` cannot ship CAS files or DOS system files.

| Item | Value |
|---|---|
| Assembler | sjasmplus 1.24.0, downloaded and built by the Makefile, checked by SHA-256 |
| Emulator | `openMSX` 22.0, on the path |
| Python | Python 3, standard library only |
| `CAS_DIR` | Make variable: the folder of the user's CAS files |
| `DOS_DIR` | Make variable: the folder of the DOS system files ([Check](DESIGN.md#check)) |
| Test machines | The shipped machine files, `advanced/phc28s` first |

The corpus is a fixed set of CAS files, one or more for each case that the design
lists:

| Case | File | Load command |
|---|---|---|
| Single load, ASCII loader | `FREDDY.CAS` (Freddy Hardest) | `RUN"CAS:"` |
| Single load, binary, slot search from slot 0 up | `FERNANDR.CAS` (Fernando Martin Basket Master) | `BLOAD"CAS:",R` |
| Load that waits for a key | `ABADIA.CAS` (La Abadia del Crimen), `MOONRIDE.CAS` (Moonrider) | `BLOAD"CAS:",R`, `RUN"CAS:"` |
| BASIC program | `COMPUTAD.CAS` (Computadora Adivina) | `CLOAD` |
| Load during play, side 2 | `TOUR-91.CAS` and `TOUR-91B.CAS` (Tour 91) | `RUN"CAS:"` |
| Load during play, side 2, joystick choice | `GAUNTLET.CAS` and `GAUNTLEB.CAS` (Gauntlet) | `RUN"CAS:"` |
| Page 0 RAM in DOS's mapper, on an NMS 8250 | `MOONWALK.CAS` (Moonwalker) | `RUN"CAS:"` |

## Step 1: build and harness

This step sets up the build and the code that every tool uses to run `openMSX`. It
adds:

- A Makefile that builds sjasmplus and `bin/SNAPCAS.COM`, and runs the tests.
- `tools/msx.py`, which reads a machine file, starts `openMSX` with a Tcl script,
  presses the `boot` keys, and makes a disk image with `diskmanipulator`.
- A first `SNAPCAS.COM` that opens `<GAME>.IMG` and prints an error when the file is
  missing or is not an image.

The test boots `advanced/phc28s` with a disk of `DOS_DIR`'s files and `SNAPCAS.COM`,
runs `SNAPCAS NONE`, and reads the error from the screen with `get_screen`. It
proves the assembler, the disk image, the boot keys and the screen reading.

## Step 2: capture

This step writes `tools/capture.py` for games without the tape service: capture
steps 1 to 6, the RAM rules and the snapshot files ([Capture](DESIGN.md#capture)).
The tests capture `FREDDY.CAS`, `FERNANDR.CAS`, `ABADIA.CAS`, `MOONRIDE.CAS` and
`COMPUTAD.CAS` on `advanced/phc28s`, and check:

- That `state.txt` holds every name of the register table.
- That the kept pages are the RAM of slots 0, 1 and 2-2 that the game selected, and
  that the Carnivore2's mapper has 64 segments.
- That `ABADIA.CAS` and `MOONRIDE.CAS` continue after a key, and `log.txt` names it.
- That a second capture of the same file gives the same snapshot.

## Step 3: build

This step writes `tools/build.py` for games without the tape service, and
`src/service.asm` with the tail only. Python unit tests check the image header, the
record table, the port-write order and the tail's bytes against the design's tables
([Formats](DESIGN.md#formats)), on the snapshots of step 2.

## Step 4: restorer and check

This step writes `SNAPCAS.COM` without the tape service, restorer steps 1 to 7
([Restorer](DESIGN.md#restorer)), and `tools/check.py`. The tests run `check.py` on
each single-load file of the corpus, first on `advanced/phc28s`, then on
`basic/vg8020`, `basic/nms8250` and `advanced/hbf700p`. Check point 1 must pass on
each machine, and the screenshots must show the game.

## Step 5: tape service

This step adds the tape service to `src/service.asm`, `build.py` and `SNAPCAS.COM`
([Tape service](DESIGN.md#tape-service)). The tests run `check.py` on `TOUR-91.CAS`
and `GAUNTLET.CAS` on `advanced/phc28s`, and on `MOONWALK.CAS` on `basic/nms8250`. A
Tcl script then plays each game past its next load and checks that the tape position
moves into side 2. For Gauntlet, the script sets the joystick's value in register A
after `IN A,(0A2h)`, because `openMSX` cannot press a joystick from a script.

## Step 6: scan

This step adds the scan and its patches ([Scan](DESIGN.md#scan)). The test runs
`build.py` on each of the 62 multi-load files that the corpus search found, and
checks that the 20 games with stubs have a stub finding in `scan.txt`. It then runs
`check.py` on those games and records which findings each one executes.

## Step 7: shipped files

This step writes the six machine files ([Shipped files](DESIGN.md#shipped-files))
and the game files for the collection, by running the capture over `CAS_DIR`. The
test runs `check.py` on every game file and writes a report of passes and failures.

## Step 8: real hardware

The user runs the corpus on the Sanyo PHC-28S with the Sony HBM-64 in slot 1 and the
Carnivore2 in slot 2, and the results go in this page, with the machine and
cartridges named. A failure that `openMSX` does not show goes in the design's limits
until it is understood.
