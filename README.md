# snapcas

`snapcas` lets you play MSX tape games on your real MSX, without a tape player. It
works from CAS files, which are MSX tapes saved as files on a computer.

The goal of the project is that any CAS file plays on any MSX as the original tape
did, whatever cartridges the MSX has and in whatever slot order. That includes games
whose original tape fails on some machines, because its loader expects one machine's
memory layout or no disk interface.

## What it is

`snapcas` is a program for your computer. It turns a game's CAS file into a single
`.SNP` file. You copy that file to your MSX's disk or SD card and type one command.
The game then starts right away, already loaded.

It works in three steps:

1. It loads the game's tape in `openMSX`, an MSX emulator that is set up like your
   MSX.
2. Once the game has loaded, it saves the contents of the MSX's memory to the `.SNP`
   file. This is like taking a photo of the game.
3. On your real MSX, the program `SNAPCAS.COM` puts that memory back, and the game
   continues from there.

Some games read the tape again while you play, for example to load the next level.
The `.SNP` file also holds the rest of the tape, so those games work too. Other
games do not work on every MSX, and `snapcas` changes them so that they work on
yours. `snapcas` knows 1,545 games and 13 MSX machines.

## Let an AI do it

An AI coding agent, such as Claude Code, can do each task of this page for you. The
file [AGENTS.md](AGENTS.md) describes every task to the agent, step by step. Get
`snapcas` (step 1 of [Play a game](#play-a-game)), open the `snapcas` folder in your
agent, and ask in your own words, for example:

| You want to | Ask the AI |
|---|---|
| Play a game | "Make Gauntlet for my Sanyo PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2. Check it, and copy my games to the card at /Volumes/MSX." |
| Add a machine | "Add my MSX to snapcas: a Toshiba HX-10 with a Carnivore2 in slot 1. Follow AGENTS.md, Add a machine." |
| Add a game | "Add the tape ~/Downloads/MYGAME.CAS to snapcas as a custom game, and make it for hx10-carnivore2. Follow AGENTS.md, Add a game." |
| Fix a game | "Gauntlet fails on hx10-carnivore2. Follow AGENTS.md, Fix a game that fails." |

Always tell the AI your MSX's model and what is in each cartridge slot. The AI can
test a game only in the emulator. It cannot see your real MSX, so play the game
there and tell the AI what happens.

The next sections give the same tasks as steps that you do by hand.

## Play a game

You need three things:

- An MSX that `snapcas` knows, with a disk or an SD card
  ([what the MSX needs](docs/PLAYING.md#what-you-need)).
- A computer with Python 3 and `openMSX`.
- The system ROMs of your MSX, installed in `openMSX`. `openMSX` needs them to
  emulate your MSX.

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

   The command shows the game's name, `GAUNTLET`.

3. Find your MSX:

   ```
   ./snapcas.py machines
   ```

   A machine's name is the MSX's model, followed by its cartridges in slot order. A
   Sanyo PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2 is
   `phc28s-ram64k-carnivore2`. Give the whole name, because each cartridge changes
   the `.SNP` file. If your MSX is not in the list, add it first
   ([Add a machine](#add-a-machine)).

4. Make the game's `.SNP` file:

   ```
   ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2
   ```

   The command downloads the game's tape from File-Hunter and makes
   `images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`.

5. Put the MSX's card in your computer and copy your games to it. In this example,
   `/Volumes/MSX` is the card's folder on your computer:

   ```
   ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
   ```

6. Put the card back in the MSX. On the MSX, go to the folder of the game's first
   letter and start the game:

   ```
   CD \SNAPCAS\G
   \BIN\SNAPCAS GAUNTLET
   ```

While you play, three keys control the tape. You need them only for a game that
loads its levels from the tape ([Tape keys](docs/PLAYING.md#tape-keys)).

## Add a machine

A machine is an MSX together with its cartridges. `snapcas` keeps one small text
file for each machine, in the `machines/` folder. This example adds a Toshiba HX-10
with a Carnivore2 in slot 1.

1. Give the machine a name: its model, followed by each cartridge in slot order. In
   this example, the name is `hx10-carnivore2`.

2. Copy the file of a machine that has the same disk cartridge as yours:

   ```
   cp machines/vg8020-carnivore2.txt machines/hx10-carnivore2.txt
   ```

3. Open the copy in a text editor and make three changes:

   - Change the first comment line, so that it describes your MSX.
   - Change the `openmsx` line to your MSX's model:
     `openmsx -machine Toshiba_HX-10 -ext Carnivore2`. The model's name is the name
     of its file in `openMSX`'s `share/machines/` folder, without `.xml`.
   - Change the `variant` line to `variant hx10`. The next step makes that variant.

4. Make the capture variant. Some games load only without the disk cartridge, so
   `snapcas` loads them on a second machine file: your MSX without that cartridge.
   Copy the variant of the machine that you copied, and change its `openmsx` line to
   your model, `openmsx -machine Toshiba_HX-10`:

   ```
   cp machines/capture/vg8020.txt machines/capture/hx10.txt
   ```

5. Make a game with the `--check` option, which also tests the game's `.SNP` file
   in `openMSX`:

   ```
   ./snapcas.py snap gauntlet hx10-carnivore2 --check
   ```

   The command prints four lines that start with `check`. If all four say `pass`,
   the machine works.

6. If a line says `fail`, or the command stops with a message, follow the full
   steps ([AGENTS.md, Add a machine](AGENTS.md#add-a-machine)). Those steps list
   each message and its fix.

Many games need a small fix for each machine. The most common fix is to load the
game on the capture variant, and `snapcas` tries that fix by itself. When a game
fails on your MSX, `snap` tries the game again on the capture variant and keeps the
image that works. One command does this for every game whose tape you have, and
writes each fix into the game's folder
([AGENTS.md, Run the collection](AGENTS.md#7-run-the-collection)):

```
make games MACHINE=hx10-carnivore2
```

## Add a game

If `./snapcas.py list` does not find a game and you have its CAS file, you can add
the game yourself.

1. Make a folder for the game in `custom/` and put the CAS file in it:

   ```
   custom/MYGAME/MYGAME.CAS
   ```

2. In the same folder, create a text file named `game.txt` with one line that names
   the CAS file:

   ```
   cas MYGAME.CAS
   ```

   A game on two tapes needs a second line for the other tape:
   `side2 MYGAMEB.CAS`.

3. Make the game with the `--check` option:

   ```
   ./snapcas.py snap custom/MYGAME phc28s-ram64k-carnivore2 --check
   ```

   The command prints four lines that start with `check`. If all four say `pass`,
   the game works. Copy it to the card and play it, as in
   [Play a game](#play-a-game).

4. If a line says `fail`, the game needs more lines in its `game.txt`. The full
   steps show how to find those lines
   ([AGENTS.md, Fix a game that fails](AGENTS.md#fix-a-game-that-fails)).

## Learn more

| Page | What it holds |
|---|---|
| [docs/PLAYING.md](docs/PLAYING.md) | What the MSX needs, and the keys that control the tape while you play |
| [docs/CLI.md](docs/CLI.md) | Every `snapcas.py` command and its options |
| [docs/FILES.md](docs/FILES.md) | Every line of a machine file and of a game file |
| [AGENTS.md](AGENTS.md) | Every task in full, step by step, for an AI agent or for you |
| [custom/README.md](custom/README.md) | Your own games |
| [docs/DESIGN.md](docs/DESIGN.md) | How `snapcas` works, and what it cannot do yet |
| [docs/INTERNALS.md](docs/INTERNALS.md) | The capture, the build, the restorer and the check in detail |
| [docs/FORMATS.md](docs/FORMATS.md) | The `.SNP` file and the other files, byte by byte |
| [docs/NOTES.md](docs/NOTES.md) | The games that taught each rule |
| [docs/BUILD.md](docs/BUILD.md) | The folders, and the `make` commands that build and test `snapcas` |
