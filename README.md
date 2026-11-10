# snapcas

`snapcas` lets you play MSX tape games on your real MSX, without a tape player.

## What it is

`snapcas` is a program for your computer. It turns a tape game into one file, a
`.SNP` file. You copy that file to your MSX's disk or SD card and type one command.
The game starts at once, already loaded.

It works in three steps:

1. It loads the game's tape in `openMSX`, an MSX emulator, set up like your MSX.
2. When the game has loaded, it saves what is in the MSX's memory to the `.SNP`
   file, like a photo of the game.
3. On your real MSX, the program `SNAPCAS.COM` puts that memory back, and the game
   goes on from there.

Some games read the tape again while you play, to load the next level. The `.SNP`
file holds the rest of the tape too, so those games also work. Some games do not
work on every MSX, and `snapcas` changes them so that they work on yours. It knows
1,545 games and 13 MSX machines.

## Play a game

You need three things:

- An MSX that `snapcas` knows, with a disk or an SD card
  ([what the MSX needs](docs/PLAYING.md#what-you-need)).
- A computer with Python 3 and `openMSX`.
- Your MSX's system ROMs in `openMSX`, which `openMSX` needs to start that MSX.

This example makes Gauntlet for a Sanyo PHC-28S.

1. Get `snapcas`:

   ```
   git clone https://github.com/xesco/snapcas.git
   cd snapcas
   ```

2. Find the game:

   ```
   ./snapcas.py list gauntlet
   ```

   It shows the game's name, `GAUNTLET`.

3. Find your MSX:

   ```
   ./snapcas.py machines
   ```

   A machine's name is the MSX's model, then its cartridges in slot order. A Sanyo
   PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2 is
   `phc28s-ram64k-carnivore2`. Give the whole name, because each cartridge changes
   the `.SNP` file. When your MSX is not in the list, add it first
   ([Add a machine](#add-a-machine)).

4. Make the game's `.SNP` file:

   ```
   ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2
   ```

   It downloads the game's tape from File-Hunter, and makes
   `images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`.

5. Put the MSX's card in your computer, and copy your games to it. `/Volumes/MSX`
   is the card's folder on your computer:

   ```
   ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
   ```

6. Put the card back in the MSX. On the MSX, go to the game's first letter and
   start the game:

   ```
   CD \SNAPCAS\G
   \BIN\SNAPCAS GAUNTLET
   ```

While you play, three keys work the tape, for a game that loads its levels from it
([Tape keys](docs/PLAYING.md#tape-keys)).

## Add a machine

A machine is your MSX with its cartridges. `snapcas` keeps one small text file for
each machine, in the `machines/` folder. This example adds a Sony HB-75P with a
Carnivore2 in slot 1.

1. Name the machine: the model, then each cartridge in slot order. The example is
   `hb75p-carnivore2`.

2. Copy the file of a machine that has the same disk cartridge as yours:

   ```
   cp machines/vg8020-carnivore2.txt machines/hb75p-carnivore2.txt
   ```

3. Open the copy in a text editor, and do three things:

   - Change the first comment line, so that it describes your MSX.
   - Change the `openmsx` line to your MSX's model:
     `openmsx -machine Sony_HB-75P -ext Carnivore2`. The model's name is the name of
     its file in `openMSX`'s `share/machines/` folder, without `.xml`.
   - Delete the lines that start with `variant`.

4. Make a game with `--check`, which also tries the game's `.SNP` file in
   `openMSX`:

   ```
   ./snapcas.py snap caldero hb75p-carnivore2 --check
   ```

   The command prints four lines that start with `check`. When all four say
   `pass`, the machine works.

5. When a line says `fail`, or the command stops with a message, follow the full
   steps, which list each message with its fix
   ([AGENTS.md, Add a machine](AGENTS.md#add-a-machine)).

## Add a game

Add a game when `./snapcas.py list` does not find it, and you have its tape file.
A tape file is a tape, saved as a file on your computer: a CAS file or a TSX file.

1. Make a folder for the game in `custom/`, and put the tape file in it:

   ```
   custom/MYGAME/MYGAME.CAS
   ```

2. In the same folder, make a text file named `game.txt` with one line, which
   names the tape file:

   ```
   cas MYGAME.CAS
   ```

   A game on two tapes gets a second line for the other tape:
   `side2 MYGAMEB.CAS`.

3. Make the game with `--check`:

   ```
   ./snapcas.py snap custom/MYGAME phc28s-ram64k-carnivore2 --check
   ```

   The command prints four lines that start with `check`. When all four say
   `pass`, the game works. Copy it to the card and play it, as in
   [Play a game](#play-a-game).

4. When a line says `fail`, the game needs more lines in its `game.txt`. The full
   steps show how to find them
   ([AGENTS.md, Fix a game that fails](AGENTS.md#fix-a-game-that-fails)).

## Let an AI do it

An AI coding agent, such as Claude Code, can do each of these tasks for you. The
file [AGENTS.md](AGENTS.md) gives the agent every task as steps. Open the `snapcas`
folder in your agent, and ask in your own words, like this:

| You want to | Ask the AI |
|---|---|
| Play a game | "Make Gauntlet for my Sanyo PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2. Check it, and copy my games to the card at /Volumes/MSX." |
| Add a machine | "Add my MSX to snapcas: a Sony HB-75P with a Carnivore2 in slot 1. Follow AGENTS.md, Add a machine." |
| Add a game | "Add the tape ~/Downloads/MYGAME.CAS to snapcas as a custom game, and make it for hb75p-carnivore2. Follow AGENTS.md, Add a game." |
| Fix a game | "Gauntlet fails on hb75p-carnivore2. Follow AGENTS.md, Fix a game that fails." |

Always tell the AI your MSX's model and what is in each cartridge slot. The AI tries
each game in the emulator only. It cannot see your real MSX, so play the game there
and tell the AI what happens.

## Learn more

| Page | What it holds |
|---|---|
| [docs/PLAYING.md](docs/PLAYING.md) | What the MSX needs, and the tape's keys while you play |
| [docs/CLI.md](docs/CLI.md) | Every `snapcas.py` command and its options |
| [docs/FILES.md](docs/FILES.md) | Every line of a machine file and of a game file |
| [AGENTS.md](AGENTS.md) | Each task as full steps, for an AI agent or for you |
| [custom/README.md](custom/README.md) | Your own games |
| [docs/DESIGN.md](docs/DESIGN.md) | How `snapcas` works, and what it cannot do yet |
| [docs/INTERNALS.md](docs/INTERNALS.md) | The capture, the build, the restorer and the check in detail |
| [docs/FORMATS.md](docs/FORMATS.md) | The `.SNP` file and the other files, byte by byte |
| [docs/NOTES.md](docs/NOTES.md) | The games that taught each rule |
| [docs/BUILD.md](docs/BUILD.md) | The folders, and the `make` commands that build and test `snapcas` |
