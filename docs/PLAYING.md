# Play on the MSX

This page is for a person who has a game's `.SNP` file and wants to play it on a
real MSX. It says what the MSX needs, how to start the game, and which keys work
the tape while you play. The [README](../README.md) shows how to make the `.SNP`
file.

## What you need

- An MSX with a memory mapper and a disk system, such as MSX-DOS or Nextor.
- A computer with Python 3 and the emulator `openMSX`.
- A network connection, so that `snapcas` can download the game's tape file from
  File-Hunter. Without a connection, you need the tape file itself, a CAS file.

A CAS file is an MSX tape, saved as a file on your computer.

## Start a game

Copy `bin/SNAPCAS.COM` and the game's `.SNP` file to one folder of your MSX's disk.
On the MSX, go to that folder and type `SNAPCAS` and the file's name:

```
SNAPCAS GAUNTLET
```

`./snapcas.py sync` copies all your images for an MSX to its card at once
([CLI.md, Sync a card](CLI.md#sync-a-card)). It puts each image in the folder of its
first letter. On the MSX, go to the game's letter first:

```
CD \SNAPCAS\G
\BIN\SNAPCAS GAUNTLET
```

## Tape keys

Some games read the tape again while you play, for example to load the next level.
The `.SNP` file holds the rest of the tape, and `SNAPCAS.COM` acts as the tape
player. The tape stops and goes on where the game wants, and it turns over to side B
by itself. Three keys also work the tape when a game reads it. Hold the key down
when the game asks you to press play.

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
