# `snapcas` plan

This page lists the steps that build the first version of `snapcas`, in order, and
the tests that each step adds. It is for the developers, and it follows the design
([DESIGN.md](DESIGN.md)). Each step ends with a review by the user before the next
one starts, and the whole test suite runs with one command, `make test`.

## Test setup

The build pins its tools, and the tests read the CAS files and the MSX-DOS system
files from two folders that the user names, because `snapcas` cannot ship them.

| Item | Value |
|---|---|
| Assembler | sjasmplus 1.24.0, downloaded and built by the Makefile, checked by SHA-256 |
| Emulator | `openMSX` 22.0, on the path, with the system ROMs of the test machines and of the `msxdos2` cartridge |
| Python | Python 3, standard library only |
| `CAS_DIR` | Make variable: the folder of the user's CAS files, by default `tapes/`, which git ignores |
| Nextor | `NEXTOR.SYS` 2.11 and `COMMAND2.COM` 2.44 from Nextor 2.1.0's `tools.zip`, downloaded by the Makefile into `out/dl/nextor/`, checked by SHA-256 |
| `DOS_DIR` | Make variable: a folder with `msxdos2/` (`MSXDOS2.SYS`, `COMMAND2.COM`) and `msxdos1/` (`MSXDOS.SYS`, `COMMAND.COM`) |

The test machines are the six shipped machine files and two machine files that only
the tests use, in `machines/test/`. Each one boots the DOS of its row:

| Machine file | DOS | Why |
|---|---|---|
| `advanced/phc28s`, `basic/vg8020`, `basic/msx2ide`, `advanced/mfrsd` | Nextor | Shipped |
| `basic/nms8250`, `advanced/hbf700p` | `DOS_DIR/msxdos2/`, with the `msxdos2` cartridge in the machine file | Shipped |
| `test/nms8250-dos1` | `DOS_DIR/msxdos1/`, from the NMS 8250's own disk ROM | No shipped machine runs MSX-DOS 1 |
| `test/nms8250-512k` | `DOS_DIR/msxdos2/` | An NMS 8250 whose single mapper holds 512 KB, because 128 KB cannot hold Moonwalker's 236 KB tape |

`test/nms8250-512k` uses a machine configuration that the tests install in a private
`openMSX` home, named by `OPENMSX_HOME`, with links to the user's system ROMs.

The corpus is a fixed set of CAS files from File-Hunter's collection, one or more
for each case that the design lists:

| Case | File | Load command |
|---|---|---|
| Single load, the first game that failed on the PHC-28S | `FREDDY.CAS` (Freddy Hardest) | `RUN"CAS:"` |
| Single load, slot search from slot 0 up | `FERNANDO.CAS` (Fernando Martin Basket Master) | `RUN"CAS:"` |
| Single load that pauses on its own for 16 seconds | `022-MOON.CAS` (Moonrider) | `RUN"CAS:"` |
| Single load that waits for a key, on an NMS 8250: on the PHC-28S its loader puts slot 1 in page 3 and crashes | `ABADIA.CAS` (La Abadia del Crimen) | `BLOAD"CAS:",R` |
| Single load, BASIC program | `CALDERO.CAS` (El Caldero Magico) | `CLOAD` |
| BASIC program that loads during play, T0 in place of the ROM | `COMPUTAD.CAS` (Computadora Adivina) | `CLOAD` |
| Load during play, side 2 | `TOUR-91.CAS` and `TOUR-91B.CAS` (Tour 91) | `RUN"CAS:"` |
| Load during play, side 2, joystick choice | `GAUNTLET.CAS` and `GAUNTLEB.CAS` (Gauntlet) | `RUN"CAS:"` |
| Load during play, page 0 RAM in DOS's mapper | `MOONWALK.CAS` (Moonwalker) | `RUN"CAS:"` |

## Step 1: build and harness

This step sets up the build and the code that every tool uses to run `openMSX`. It
adds:

- A Makefile that builds sjasmplus and `bin/SNAPCAS.COM`, and runs the tests.
- The machine file `advanced/phc28s`.
- `tools/msx.py`, which reads a machine file, starts `openMSX` with a Tcl script,
  presses the `boot` keys, and makes, with `diskmanipulator`, a disk image of the
  kind that the machine file's `disk` command takes.
- A first `SNAPCAS.COM` that opens `<GAME>.IMG`, prints its usage without a name,
  and prints an error when the file is missing or is not an image.

The test boots `advanced/phc28s` with a disk of Nextor's files, `SNAPCAS.COM` and
two bad images: `SHORT.IMG` of 3 bytes and `BAD.IMG`, which starts with `SNAPCAS2`.
It runs `SNAPCAS`, then `SNAPCAS` with `NONE`, `SHORT` and `BAD`, and reads the
usage and the three errors from the screen with `get_screen`. It proves the
assembler, the disk image, the boot keys and the screen reading.

## Step 2: capture

This step writes `tools/capture.py`: capture steps 1 to 6, the RAM rules and the
snapshot files ([Capture](DESIGN.md#capture)), and the machine file `basic/nms8250`.
The tests capture the single-load files of the corpus, all on `advanced/phc28s`
except `ABADIA.CAS` on `basic/nms8250`, and check:

- That `state.txt` holds every name of the register table, and that `service` is 0
  for the files on `advanced/phc28s`.
- That every kept page holds RAM and is in slot 0's page 3, in slot 1 or in the
  Carnivore2's subslot 2-2, and that the Carnivore2's mapper has 64 segments.
- That `ABADIA.CAS` continues after a key, and `log.txt` names it, and that its game
  file's `service no` leaves out the tape service, because its last 16 KB stay
  unread.
- That a second capture of the same file gives the same snapshot.

## Step 3: build

This step writes `tools/build.py` for games without the tape service, and
`src/service.asm` with the tail only. Python unit tests check the image header, the
record table, the port-write order and the tail's bytes against the design's tables
([Formats](DESIGN.md#formats)), on the snapshots of step 2 and on one of
`FREDDY.CAS` captured on `basic/nms8250`, for the V9938's port writes. They also
check that `build.py` stops with an error when `SERVICE.BIN`'s version byte is
wrong.

## Step 4: restorer and check

This step writes `SNAPCAS.COM` without the tape service, restorer steps 1 to 7
([Restorer](DESIGN.md#restorer)), `tools/check.py`, and the machine files of its
tests. The tests capture, build and check each single-load file of the corpus, first
on `advanced/phc28s`, then on `basic/vg8020`, `basic/nms8250`, `advanced/hbf700p`
and `test/nms8250-dos1`. Check point 1 must pass on each machine, except where the
restorer stops because DOS leaves too few free segments: the test then checks that
the restorer's message names the segments needed and free. The screenshots stay in
`check/` for the user to look at.

## Step 5: tape service

This step adds the tape service to `src/service.asm`, `build.py` and `SNAPCAS.COM`
([Tape service](DESIGN.md#tape-service)), and the machine file `test/nms8250-512k`
with its machine configuration. The tests capture, build and check `COMPUTAD.CAS`,
`TOUR-91.CAS` and `GAUNTLET.CAS` on `advanced/phc28s`, and `MOONWALK.CAS` on
`test/nms8250-512k`, and check that `service` is 1 in each `state.txt`. Each test's
Tcl script then gives the inputs that reach the game's next load, and checks in T0
that the tape position moves past its value at the snapshot. For Gauntlet, the
script sets the joystick's value in register A after `IN A,(0A2h)`, because
`openMSX` cannot press a joystick from a script. For Moonwalker, the test also
checks that T0 stays out of page 0.

## Step 6: scan

This step adds the scan and its patches ([Scan](DESIGN.md#scan)). The test reruns
the corpus search of the design's decisions over `CAS_DIR`, runs `build.py` on each
multi-load file that it finds, and checks that the stub findings in `scan.txt` cover
the 20 games with stubs. It then runs `check.py` on those games and records which
findings each one executes.

## Step 7: shipped files

This step writes the last two machine files, `basic/msx2ide` and `advanced/mfrsd`
([Shipped files](DESIGN.md#shipped-files)), and the game files for the collection,
by running the capture over `CAS_DIR` on `advanced/phc28s`. The tests check a
single-load game on each of the six shipped machine files, then capture, build and
check every game file on `advanced/phc28s` and `basic/vg8020`, and write a report of
passes and failures.

## Step 8: real hardware

The user runs the corpus on the Sanyo PHC-28S with the Sony HBM-64 in slot 1 and the
Carnivore2 in slot 2, and the results go in this page, with the machine and
cartridges named. A failure that `openMSX` does not show goes in the design's limits
until it is understood. `make try` starts `openMSX` with the same machine and the
same files, to compare.

| Date | Machine | Images | Result |
|---|---|---|---|
| 2026-10-29 | Sanyo PHC-28S, Sony HBM-64 in slot 1, Carnivore2 in slot 2, Nextor 2.1 | `FREDDY.IMG`, `FERNANDO.IMG`, `MOONRIDE.IMG`, `CALDERO.IMG`, from step 4 | All four games run |
