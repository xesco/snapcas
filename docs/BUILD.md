# Build and test

This page is for a person who changes `snapcas` itself. It lists the folders of the
repository, and the `make` commands that build `snapcas` and run its tests. To make
and play a game you need none of this, because `bin/` already holds the built files
([README](../README.md)).

## Folders

| Folder | What it holds |
|---|---|
| `games/` | A game file for each MSX1 CAS game, without the game itself |
| `custom/` | Your own games, each with its game file and its tapes ([custom/README.md](../custom/README.md)) |
| `machines/` | One file for each MSX with its cartridges |
| `tools/` | The programs that make `.SNP` files |
| `bin/` | `SNAPCAS.COM`, which starts a `.SNP` file on your MSX |
| `downloads/` | The tape files that `snapcas` downloads from File-Hunter |
| `images/` | The `.SNP` files that you make, one folder per MSX |
| `dos/` | The DOS files that the checks boot ([dos/README.md](../dos/README.md)) |
| `out/` | The files that `snapcas` makes on the way, which you do not need |
| `docs/`, `src/`, `tests/` | The project's documents, source code and tests |

## The make commands

The Makefile builds `snapcas` and runs its checks. You need it only to change
`snapcas`, because `bin/` already holds the built files.

| Command | What it does |
|---|---|
| `make all` | Builds `bin/SNAPCAS.COM` and `bin/SERVICE.BIN`. It downloads the sjasmplus assembler's source into `out/cache/` and builds it first |
| `make unit` | Runs the tests that need no `openMSX` and no tape file, in about 3 seconds |
| `make test` | Runs all the tests, those of `make unit` and those that run in `openMSX`, in about 2 minutes, with the tape files of `tests/tapes/`. It downloads Nextor's files into `dos/nextor/` and the cartridges' firmware into `out/cache/` |
| `make games` | Makes and checks the image of every game in `games/` on one MSX, with the tape files of `downloads/`, and puts each image that passes in `images/`, for `sync`. It downloads no tape, so a game whose tape is missing fails |
| `make firmware` | Downloads the firmware of the machines that need it into `out/cache/openmsx-home/`, which `snapcas.py` then uses: `fsa1-mfrsd`, `hbf1xd-mfrsd`, `vg8020-sdmapper`, and `xp800-sdmapper`. It also makes the HB-F700P with its slot 0 not expanded there, from `openMSX`'s own file, for two capture variants of `hbf700p-ram512k-msxdos2` |
| `make clean` | Removes `out/test/` and the build's files in `out/`: the symbol files and the test games. It leaves `bin/`, whose files git holds |

The tests that need MSX-DOS 1 or MSX-DOS 2 look for its files in `dos/msxdos1/` and
`dos/msxdos2/` ([dos/README.md](../dos/README.md)), and are skipped without them.
The run names each skipped test, and it skips a test for no other reason. `DOS_DIR=`
names a folder that takes the place of `dos/`, with the same folders in it, and
`make games` then looks there too.

`make games` takes these settings:

| Setting | What it does | Default |
|---|---|---|
| `MACHINE=` | The MSX, as `./snapcas.py machines` lists it | `phc28s-ram64k-carnivore2` |
| `DOS=` | The folder of the DOS files that the check boots | The MSX's own folder below `dos/`: `nextor`, `msxdos1` or `msxdos2` |
| `FIX=0` | Turns off the retry. Without this setting, the run tries each game that fails on the MSX's capture variants. When a variant passes, the run writes the `capture` line into the machine's game file ([INTERNALS.md, The games run](INTERNALS.md#the-games-run)) | The retry is on |
| `FULL=1` | Runs every game again. Otherwise a game keeps its last result while its files, the code, the DOS files and `openMSX`'s version are unchanged | Off |

The results go to `out/games/<machine>.txt`, one line per game. The command fails
when a game fails that neither of two lists names. `tests/openmsx-failures.txt`
holds the games that fail in `openMSX` itself, and `tests/snapcas-failures.txt`
holds the known failures of `snapcas`. A first run takes hours. Ctrl-C stops a run,
and the next run keeps the results of the games that finished.
