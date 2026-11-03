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
- **Know 1,322 games.** The `games/` folder has a file for each game. The file tells
  `snapcas` how to make the game's `.SNP` file, and where to download the game.

## What you need

- An MSX with a memory mapper and a disk system, such as MSX-DOS or Nextor.
- A computer with Python 3 and the emulator `openMSX`.
- The game's CAS or TSX file.

## Get started

This example makes Gauntlet for a Sanyo PHC-28S.

1. Find Gauntlet in `games/GAUNTLET/game.txt`. Its first lines have the link to
   download `GAUNTLET.CAS`. Put the file in a folder, for example `~/tapes`.
2. Find your MSX in the `machines/` folder. A file's name is the MSX's model, then
   its cartridges in slot order. A Sanyo PHC-28S with a 64 KB RAM cartridge in slot
   1 and a Carnivore2 in slot 2 is `machines/phc28s-ram64k-carnivore2.txt`. You will
   call it `phc28s-ram64k-carnivore2`.
3. Make the `.SNP` file:

   ```
   python3 tools/snapcas.py GAUNTLET phc28s-ram64k-carnivore2 --tapes ~/tapes
   ```

   You get `out/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`.
4. Copy `bin/SNAPCAS.COM` and `GAUNTLET.SNP` to your MSX's disk. On the MSX, type:

   ```
   SNAPCAS GAUNTLET
   ```

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
| `machines/` | One file for each MSX with its cartridges |
| `tools/` | The programs that make `.SNP` files |
| `bin/` | `SNAPCAS.COM`, which starts a `.SNP` file on your MSX |
| `out/` | The `.SNP` files that you make |
| `docs/`, `src/`, `tests/` | The project's documents, source code and tests |

## Learn more

[DESIGN.md](docs/DESIGN.md) explains how `snapcas` works, what it cannot do yet, and
how to describe a new MSX.
