# snapcas

`snapcas` lets you play MSX tape games on your real MSX, without a tape player. It
works from CAS files, which are MSX tapes saved as files on a computer.

The goal of the project is to play any CAS file on any MSX as the original tape
did, whatever cartridges the MSX has and in whatever slot order. That includes games
whose original tape fails on some machines, because its loader expects one machine's
memory layout or no disk interface, or other issues.

## What it is

`snapcas` is a program for your computer and for your MSX. On the computer, it turns
a game's CAS file into a single `.SNP` file. You copy that file to your MSX's disk
or SD card and type one command on the MSX. The game then loads and starts right
away.

It works in three steps:

1. It loads the game's tape (the CAS file) in `openMSX`, an MSX emulator that is set
   up like your own MSX.
2. Once the game has loaded, it saves the contents of the MSX's memory to the `.SNP`
   file. This is like taking a photo or a snapshot of the game.
3. On your real MSX, the program `SNAPCAS.COM` puts that memory back, and the game
   continues from there.

Some games read the tape again while you play, for example to load the next level.
The `.SNP` file also holds the rest of the tape, so those games work too. Some
games do not work on every MSX, and `snapcas` changes them with patches so that they
work on yours.

`snapcas` knows 1,545 games (CAS files) and 10 MSX machines, and you can add your
own games and machines. `snapcas` does not hold the CAS files of these games. It
downloads a game's CAS file from [File-Hunter](https://download.file-hunter.com)
when you make the game's `.SNP` file. What it holds for each game is a few small
text files that say how to load the game on a particular machine and list the
game's patches.

## Requirements

You need three things:

- An MSX with a memory mapper and a disk.
- A computer with Python 3 and `openMSX`.
- The system ROMs of your MSX, installed in `openMSX`.

## Ask an AI

An AI coding agent, such as Claude Code, can do the steps of this page for you.
Clone the repository, open the `snapcas` folder in the agent, and say what you want
to play:

```
git clone https://github.com/xesco/snapcas.git
```

> I want to play Gauntlet on my MSX. Follow "Guide a user" in AGENTS.md.

The agent asks you what it needs to know, such as your MSX's model and its
cartridges. Then it makes the game's `.SNP` file, copies it to your MSX's card, and
gives you the commands to type on the MSX.

You can also give the agent your own CAS file instead of a game's name:

> I want to play the CAS file ~/Downloads/mygame.cas on my MSX. Follow "Guide a
> user" in AGENTS.md.

The rest of this page gives the same steps for you to do instead of the agent.

## How to play a game

This example makes the `.SNP` file of Gauntlet for a Sanyo PHC-28S and starts the
game on that MSX.

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

   If your MSX is not in the list, add it first. An AI coding agent can add it for
   you. Open the `snapcas` folder in the agent, and tell it your MSX's model and
   what is in each cartridge slot:

   > Add my MSX to snapcas: a Toshiba HX-10 with a Carnivore2 in slot 1. Follow
   > steps 1 to 5 of "Add a machine" in AGENTS.md.

4. Make the game's `.SNP` file for your machine:

   ```
   ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2 --check
   ```

   Or for the machine that the agent added:

   ```
   ./snapcas.py snap gauntlet hx10-carnivore2 --check
   ```

   The command downloads the game's tape from
   [File-Hunter](https://download.file-hunter.com) and makes
   `images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`. The `--check` option
   also tests the file in `openMSX`. The command prints four lines that start with
   `check`. If all four say `pass`, the game works.

   File-Hunter is one person's site. Download only the games that you play, one at
   a time.

5. If a line says `fail`, or the command stops with an error, the game needs a fix
   for your MSX. An AI coding agent can find the fix for you:

   > Gauntlet fails on phc28s-ram64k-carnivore2. Fix it: follow steps 1 to 4 of
   > "Fix a game that fails" in AGENTS.md. Then run snap with --check again.

6. Once the game works, put the MSX's card in your computer and copy the game to it.
   In this example, `/Volumes/MSX` is the card's folder on your computer:

   ```
   ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
   ```

   The command puts `SNAPCAS.COM` in the card's `BIN` folder. It puts each game in
   the `SNAPCAS` folder, in a folder for the first letter of the game's name: `A` to
   `Z`, or `0-9` for a name that starts with a digit.

7. Put the card back in the MSX. On the MSX, go to the folder of the game's first
   letter and start the game:

   ```
   CD \SNAPCAS\G
   \BIN\SNAPCAS GAUNTLET
   ```

While you play, three keys control the tape. You need them only for a game that
loads its levels from the tape ([Tape keys](docs/PLAYING.md#tape-keys)).

## Add a custom game

If you want to play your own CAS file, you can add the game to the project.

1. Ask an AI coding agent to add the game. The agent writes the game's `game.txt`
   file, which tells `snapcas` how to load the game, and makes the game's `.SNP`
   file for your machine:

   > Add the CAS file ~/Downloads/mygame.cas to snapcas and make its image for
   > phc28s-ram64k-carnivore2. Follow steps 1 to 4 of "Add a game" in AGENTS.md.

2. Copy your games to the MSX's card:

   ```
   ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
   ```

   On the MSX, your own games are in the folder `\SNAPCAS\CUSTOM`. Go to that
   folder and start the game. The agent tells you the game's name, which is `MYGAME`
   in this example:

   ```
   CD \SNAPCAS\CUSTOM
   \BIN\SNAPCAS MYGAME
   ```

## Learn more

| Page | What it holds |
|---|---|
| [Playing a game](docs/PLAYING.md) | What the MSX needs, and the keys that control the tape while you play |
| [The `snapcas` command](docs/CLI.md) | Every `snapcas.py` command and its options |
| [Machine and game files](docs/FILES.md) | Every line of a machine file and of a game file |
| [Adding a machine](AGENTS.md#add-a-machine) | The steps to add your MSX by hand |
| [Adding a game](AGENTS.md#add-a-game) | The steps to add your own game by hand |
| [Fixing a game](AGENTS.md#fix-a-game-that-fails) | The steps to fix a game by hand |
| [Your own games](custom/README.md) | Your own games |
| [DOS system files](dos/README.md) | The DOS system files that `--check` needs |
| [The `snapcas` design](docs/DESIGN.md) | What each part of `snapcas` does and why |
| [Internals](docs/INTERNALS.md) | How each part works, step by step |
| [Formats](docs/FORMATS.md) | The files and memory layouts, byte by byte |
| [Notes](docs/NOTES.md) | The games and findings behind each rule |
| [Build and test](docs/BUILD.md) | The folders, and the `make` commands that build and test `snapcas` |
| [The `snapcas` plan](docs/PLAN.md) | The steps that built `snapcas`, and their tests |
| [openMSX](https://openmsx.org) | The `openMSX` emulator, and how to install your MSX's system ROMs in it |

## License

`snapcas` is under the [MIT License](LICENSE). The license covers the code, and it does not cover the games, the system ROMs, or the DOS files, which this repository does not hold.
