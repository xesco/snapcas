# snapcas

`snapcas` lets you play MSX cassette games from a disk, on your own MSX. A CAS file
is a tape saved as a computer file. `snapcas` turns it into an image: a `.SNP` file
in its own format, which holds the game at the moment it is ready to play. The image
has the game's memory, the screen and the settings of the MSX's chips. For games
that use the cassette player while you play, the image also holds a tape service,
which lets the game read the rest of the tape from the image as you play. You copy
the image and `SNAPCAS.COM` to your MSX's disk, and `SNAPCAS.COM` puts the game back
in your MSX's memory and starts it.

## What snapcas can do

- **Play on your real MSX.** The game runs on your MSX, not in an emulator.
  `snapcas` uses the emulator `openMSX` once, on your computer, to help make the
  image.
- **Fit your MSX.** You describe your MSX in a machine file: its model, and which
  cartridges are in which slots. Each image is made for that machine, so the game
  finds its memory and slots as it would on yours.
- **Work with your disk.** The image starts from MSX-DOS 1, MSX-DOS 2 or Nextor,
  from a floppy disk, a hard disk or an SD card.
- **Fix games.** Each game has a game file in the `games/` folder, with its
  settings. A game file can patch the game, on the tape or in memory. It can also
  load the game without a cartridge that confuses its loader.
- **Find the game's tape calls.** Some games call the tape in their own way.
  `snapcas` finds those calls and sends them to its own tape.
- **Keep the whole tape.** Many games load more from the tape while you play.
  `snapcas` keeps the rest of the tape with the image, in your MSX's memory.
- **Act like a tape player.** When the game stops the tape, it waits there, and the
  next load goes on from the same place. When the game reads past the end of side A,
  it turns the tape over to side B. When the game asks you to wind the tape back,
  you press a key ([Tape keys](#tape-keys)).
- **Test the image first.** `snapcas` can start the image in `openMSX` and check
  that the game is exactly as it was saved, before you copy it to your MSX.
- **Come with game files.** The `games/` folder has a game file for each game of
  File-Hunter's MSX CAS collection, 1,314 games, with the link to download each.


## Folders

| Folder | What it holds |
|---|---|
| `bin/` | `SNAPCAS.COM`, which starts an image on your MSX, and `SERVICE.BIN`, the tape service that `build.py` puts into images |
| `games/` | A folder for each game, with its game file, `game.txt` |
| `machines/` | The machine files: `basic/` and `advanced/` for real machines, `test/` for the tests |
| `tools/` | The Python tools: `capture.py`, `build.py` and `check.py` |
| `src/` | The Z80 source code of `SNAPCAS.COM` and of the tape service |
| `docs/` | The design and the plan |
| `tests/` | The tests, which `make test` runs |
| `out/` | What the tools make, such as the images. It is not part of the project's files |


## What you need

- An MSX1 or MSX2 with a memory mapper, running MSX-DOS 1, MSX-DOS 2 or Nextor, and
  a disk or SD card that you can copy files to.
- A computer with Python 3 and `openMSX` 22.0, with the system ROMs of your MSX.
- The game's CAS file, from the link in its game file.

## Get started

These steps make Gauntlet for a Sanyo PHC-28S. Put your own game and machine in
their place.

1. Find your machine in `machines/`, or write a file that describes it
   ([Machine file](docs/DESIGN.md#machine-file)). `advanced/phc28s` is a Sanyo
   PHC-28S with a memory cartridge in slot 1 and a Carnivore2 in slot 2.
2. Load the game in `openMSX`. `--cas` names the folder with your CAS files:

   ```
   python3 tools/capture.py GAUNTLET advanced/phc28s --cas ~/tapes
   ```

3. Make the image, `out/advanced/phc28s/GAUNTLET/GAUNTLET.SNP`:

   ```
   python3 tools/build.py GAUNTLET advanced/phc28s --cas ~/tapes
   ```

4. If you like, try the image in `openMSX` first. `--dos` names a folder with your
   DOS's system files, such as `NEXTOR.SYS` and `COMMAND2.COM`:

   ```
   python3 tools/check.py GAUNTLET advanced/phc28s --dos ~/nextor
   ```

5. Copy `bin/SNAPCAS.COM` and `GAUNTLET.SNP` to your MSX's disk, and type:

   ```
   SNAPCAS GAUNTLET
   ```

## Tape keys

These keys work while a game reads the tape:

| Key | What it does |
|---|---|
| GRAPH | Goes back to the start of side A. The screen flashes green |
| CODE | Goes to the start of side B. The screen flashes red |
| CTRL+STOP | Stops a load, as on a real tape |

Hold the key down when the game starts to read the tape, for example when it says
"press play".

## Learn more

- [DESIGN.md](docs/DESIGN.md) explains how `snapcas` works, and its
  [limits](docs/DESIGN.md#limits).
- [PLAN.md](docs/PLAN.md) lists the build steps and the tests.
