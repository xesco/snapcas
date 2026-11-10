# snapcas

`snapcas` lets you play MSX tape games on your real MSX, from a disk instead of a
tape.

You give it a game's tape file, a CAS file or a TSX file. Both are a tape, saved as
a file on your computer. A TSX file also holds the fast loaders of some games, which
a CAS file cannot. `snapcas` turns the tape file into a `.SNP` file. The `.SNP` file
holds the game at the moment it is ready to play. You copy it to your MSX, and the
game starts.

## What snapcas can do

- **Fit your MSX.** You tell `snapcas` which MSX you have, and which cartridges are
  in it. It makes the `.SNP` file for that exact MSX.
- **Fix games.** Some games do not work on every MSX. `snapcas` can change them so
  that they work on yours.
- **Act like a tape player.** Some games read the tape again while you play, for
  example to load the next level. `snapcas` keeps the rest of the tape in the `.SNP`
  file. It stops and goes on where the game wants. It turns the tape over to side B
  by itself. You can also wind it back with a key ([Tape keys](#tape-keys)).
- **Know 1,545 games.** The `games/` folder has a file for each game. The file tells
  `snapcas` how to make the game's `.SNP` file, and where to download the game.

## What you need

- An MSX with a memory mapper and a disk system, such as MSX-DOS or Nextor.
- A computer with Python 3 and the emulator `openMSX`.
- A network connection, from which `snapcas` downloads the game's tape file from
  File-Hunter, or the tape file itself, a CAS or TSX file.

## Get started

This example makes Gauntlet for a Sanyo PHC-28S.

1. Find the game:

   ```
   ./snapcas.py list gauntlet
   ```

   It shows `GAUNTLET`, the folder of `games/GAUNTLET/game.txt`, and the File-Hunter
   file that the game comes from.
2. Find your MSX:

   ```
   ./snapcas.py machines
   ```

   A machine's name is the MSX's model, then its cartridges in slot order. A Sanyo
   PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2 is
   `phc28s-ram64k-carnivore2`. Give the whole name, because each cartridge changes
   the image.
3. Make the `.SNP` file:

   ```
   ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2
   ```

   It downloads the game's two tape files from File-Hunter into the `downloads/`
   folder, `GAUNTLET.CAS` and `GAUNTLEB.CAS`, unless they are there. You get
   `images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`.
4. Copy `bin/SNAPCAS.COM` and `GAUNTLET.SNP` to your MSX's disk. On the MSX, type:

   ```
   SNAPCAS GAUNTLET
   ```

   To put all your images for an MSX on its SD card at once, run
   `./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX` with the card's folder.
   On the MSX, go to the game's letter first: `CD \SNAPCAS\G`, then
   `\BIN\SNAPCAS GAUNTLET` ([CLI.md, Sync a card](docs/CLI.md#sync-a-card)).

## Tape keys

The tape works by itself. These keys work when a game reads the tape. Hold the key
down when the game asks you to press play.

| Key | What it does |
|---|---|
| GRAPH | Goes back to the start of side A. The screen flashes green |
| CODE | Goes to the start of side B. The screen flashes red |
| CTRL+STOP | Stops the tape |

### Work the tape yourself

Type `/M` after the game's name to work the tape yourself, as on a real tape player:

```
SNAPCAS GAUNTLET /M
```

The tape then stops when the game stops it, and at the end of each side. When the
game reads the tape again, the tape waits for one of these keys:

| Key | What it does |
|---|---|
| RETURN | Plays on. At the end of side A, it goes on with side B. The screen flashes yellow |
| GRAPH | Goes back to the start of side A, and plays. The screen flashes green |
| CODE | Goes to the start of side B, and plays. The screen flashes red |
| CTRL+STOP | Stops the tape |

When a game says "rewind the tape and press a key", press the game's key first. Then
press GRAPH or CODE to wind the tape back. With a few games, `/M` does not work.
`SNAPCAS` then says so, and the tape works by itself.

## Folders

| Folder | What it holds |
|---|---|
| `games/` | A game file for each MSX1 CAS game, without the game itself |
| `custom/` | Your own games, each with its game file and its tapes ([custom/README.md](custom/README.md)) |
| `machines/` | One file for each MSX with its cartridges |
| `tools/` | The programs that make `.SNP` files |
| `bin/` | `SNAPCAS.COM`, which starts a `.SNP` file on your MSX |
| `downloads/` | The tape files that `snapcas` downloads from File-Hunter |
| `images/` | The `.SNP` files that you make, one folder per MSX |
| `dos/` | The DOS files that the checks boot ([dos/README.md](dos/README.md)) |
| `out/` | The files that `snapcas` makes on the way, which you do not need |
| `docs/`, `src/`, `tests/` | The project's documents, source code and tests |

## Build and test

The Makefile builds `snapcas` and runs its checks. You need it only to change
`snapcas`, because `bin/` already holds the built files.

| Command | What it does |
|---|---|
| `make all` | Builds `bin/SNAPCAS.COM` and `bin/SERVICE.BIN`. It downloads the sjasmplus assembler's source into `out/cache/` and builds it first |
| `make unit` | Runs the tests that need no `openMSX` and no tape file, in about 3 seconds |
| `make test` | Runs all the tests, those of `make unit` and those that run in `openMSX`, in about 2 minutes, with the tape files of `tests/tapes/`. It downloads Nextor's files into `dos/nextor/` and the cartridges' firmware into `out/cache/` |
| `make games` | Makes and checks the image of every game in `games/` on one MSX, with the tape files of `downloads/`, and puts each image that passes in `images/`, for `sync`. It downloads no tape, so a game whose tape is missing fails |
| `make firmware` | Downloads the firmware of the machines that need it into `out/cache/openmsx-home/`, which `snapcas.py` then uses: `fsa1-mfrsd`, `hbf1xd-mfrsd`, `vg8020-sdmapper`, `xp800-sdmapper` and `vg8020-picoverse` |
| `make clean` | Removes `out/test/` and the build's files in `out/`: the symbol files and the test games. It leaves `bin/`, whose files git holds |

The tests that need MSX-DOS 1 or MSX-DOS 2 look for its files in `dos/msxdos1/` and
`dos/msxdos2/` ([dos/README.md](dos/README.md)), and are skipped without them. The
run names each skipped test, and it skips a test for no other reason. `DOS_DIR=`
names a folder that takes the place of `dos/`, with the same folders in it, and
`make games` then looks there too.

`make games` takes these settings:

| Setting | What it does | Default |
|---|---|---|
| `MACHINE=` | The MSX, as `./snapcas.py machines` lists it | `phc28s-ram64k-carnivore2` |
| `DOS=` | The folder of the DOS files that the check boots | The MSX's own folder below `dos/`: `nextor`, `msxdos1` or `msxdos2` |
| `FULL=1` | Runs every game again. Otherwise a game keeps its last result while its files, the code, the DOS files and `openMSX`'s version are unchanged | Off |

The results go to `out/games/<machine>.txt`, one line per game. The command fails
when a game fails that neither of two lists names. `tests/openmsx-failures.txt`
holds the games that fail in `openMSX` itself, and `tests/snapcas-failures.txt`
holds the known failures of `snapcas`. A first run takes hours. Ctrl-C stops a run,
and the next run keeps the results of the games that finished.

## Learn more

[DESIGN.md](docs/DESIGN.md) explains how `snapcas` works and what it cannot do yet.
[FILES.md](docs/FILES.md) shows how to describe a new MSX or a game, and
[FORMATS.md](docs/FORMATS.md) defines the image and the other files byte by byte.
