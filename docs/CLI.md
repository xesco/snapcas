# The `snapcas` command (draft design)

`snapcas.py` is one command that makes a game's image for the user's machine from
the game's name. It downloads the game's tape from File-Hunter when it is missing,
captures the game in `openMSX`, builds the image, and copies the images to a card. It is
written for MSX owners who are not developers, so its main use is one short line,
`snap`, a game and a machine, and it needs only Python 3 and `openMSX`, on macOS,
Linux or Windows. It runs the tools that already exist
([DESIGN.md, Files and commands][files]) and adds no new way to make an image. This
page is a draft for review, and its sections move into DESIGN.md and PLAN.md when it
is signed off.

## Requirements

| What | Why |
|---|---|
| Python 3, with its standard library only | The tools are Python 3 programs. The download uses `urllib` and `zipfile`, so nothing needs installing with pip |
| `openMSX` 22.0, on the path or named by `OPENMSX` | The capture and the check run in it, as today |
| The system ROMs of the user's machine, in `openMSX`'s `share/systemroms` | `openMSX` needs them to emulate the machine, and `snapcas` cannot ship them |
| A network connection, the first time a game is made | The tapes come from File-Hunter, and `snapcas` cannot ship them either |

The user gets `snapcas` as today, as a clone or a zip of the repository, and runs
`./snapcas.py` in its folder. The file starts with `#!/usr/bin/env python3` and git
keeps it executable, so macOS and Linux run it with Python 3. Windows runs it as
`py snapcas.py`, and a zip of the repository may lose the executable bit, so
`python3 snapcas.py` works on any OS. `bin/SNAPCAS.COM` and `bin/SERVICE.BIN` are
shipped, so the user needs no assembler.

## Commands

The command takes a verb, which says what to do, and the verb's own arguments:

| Command | What it does |
|---|---|
| `snap <game> <machine>` | Makes the game's image for the machine, and downloads the game's tapes first when they are missing ([Make an image](#make-an-image)) |
| `try <game> <machine>` | Starts the game's image in `openMSX`, to try it before the real machine ([Try an image](#try-an-image)) |
| `sync <machine> <destination>` | Copies the machine's images and `SNAPCAS.COM` to a card ([Sync a card](#sync-a-card)) |
| `list [text]` | Lists the games snapcas supports, or searches them by name ([Find a game or a machine](#find-a-game-or-a-machine)) |
| `machines` | Lists the machines that the command makes images for |

`./snapcas.py --help` lists the verbs, and `./snapcas.py snap --help` shows the
arguments and options of `snap`.

## Make an image

`snap` takes a game and a machine:

```
$ ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2
Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'] for phc28s-ram64k-carnivore2
download  Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'].zip from download.file-hunter.com
copy      Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'].cas to downloads/GAUNTLET.CAS, sha1 ok
download  Gauntlet (1986)(US Gold)(Side B)[RUN'CAS-'].zip from download.file-hunter.com
copy      Gauntlet (1986)(US Gold)(Side B)[RUN'CAS-'].cas to downloads/GAUNTLEB.CAS, sha1 ok
capture   done
build     done: 14 records, 52 port writes, up to 14 free mapper segments
image     images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
```

The first argument is the game's name, as `list` shows it, such as `gauntlet` or
`supermsx/thewall`, in any case. The second is the machine's name, as `machines`
shows it, such as `phc28s-ram64k-carnivore2` ([Machine names](#machine-names)). A
name that is not a game's or a machine's stops the command:

```
$ ./snapcas.py snap wall phc28s-ram64k-carnivore2
snapcas.py: no game is named "wall": snapcas.py list shows the games
```

`snap` downloads, captures and builds without being asked. It keeps the tapes that
it downloads in `downloads/`, so a tape is downloaded once, and it makes the image
again each time.

`snap` takes these options:

| Option | What it does | Default |
|---|---|---|
| `--check` | Runs `check.py` on the image. For a machine under Nextor, `snapcas` downloads Nextor 2.1.0's `NEXTOR.SYS` and `COMMAND2.COM` into `dos/nextor/`, pinned by SHA-256 as the Makefile does | No check |
| `--dos <dir>` | The DOS system files for `--check`, on a machine that is not under Nextor | `dos/nextor/` |

```
$ ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2 --check
...
check     pass  the restored machine equals the snapshot
check     pass  the game does not write to the tape service in page 3
check     pass  the machine does not reboot
check     pass  the game does not stop at a BASIC error
image     images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
```

The command exits with the tools' codes: 0 on success, 1 for an error in the input
files, a game that it cannot find or a download that fails, 2 when `openMSX` fails
or a wait times out, and 3 when a check fails.

## Try an image

`try` starts a game's image in `openMSX`, with its window and sound:

```
$ ./snapcas.py try temptati phc28s-ram64k-carnivore2
try       images/phc28s-ram64k-carnivore2/TEMPTATI/TEMPTATI.SNP: SNAPCAS TEMPTATI
```

`try` finds the game and the machine as `snap` does. It boots the machine with a
disk that holds Nextor's files, `SNAPCAS.COM` and the game's image. It passes the
machine's boot menu and types `SNAPCAS <GAME>` at DOS's prompt, as the player does
on the real machine, and the keyboard is then the user's. `--dos <dir>` gives the
DOS files of a machine that is not under Nextor. When the game has no image, `try`
stops and says that `snap` makes it.

## Your own games

`custom/` holds the user's own games: games that `snapcas` does not ship, or the
user's own dumps of a tape. Each has a folder with its game file and its tape files,
and its name is `custom/` and the folder's name, such as `custom/MYGAME`. `snap`,
`try` and `list` take that name as they take a shipped game's. `snap` reads a custom
game's tapes from its folder and never downloads them, and the image goes to
`images/<machine>/custom/MYGAME/`. Git ignores the games in `custom/`, and
[custom/README.md](../custom/README.md) shows how to write one. `make games` and
`make test` never read `custom/`.

## Find a game or a machine

Two verbs print a list and make nothing:

| Command | What it prints |
|---|---|
| `list [text]` | The games whose folder or title holds the text, or every game, with the name to give `snap`. A game's title names the File-Hunter file that it comes from: its zip, a CAS file in a zip, or a compilation's zip and the program's name, as in `Super MSX n.23 (settembre 1989) - cas_23 / Africa Film` |
| `machines` | The user machines, each with the first sentence of its machine file's first comment, up to a full stop or a colon |

```
$ ./snapcas.py list gaunt
GAUNTLET   Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']
1 game

$ ./snapcas.py machines
fsa1-mfrsd                  Panasonic FS-A1, an MSX2 with 64 KB and no memory mapper, with a MegaFlashROM SCC+ SD
hb75p-mfrsd                 Sony HB-75P, an MSX1 with 64 KB, with a MegaFlashROM SCC+ SD in openMSX's stock setup
hbf1xd-mfrsd                Sony HB-F1XD, an MSX2 with 64 KB, no memory mapper and a floppy drive, with a MegaFlashROM SCC+ SD
hbf700p-ram512k-msxdos2     Sony HB-F700P, an MSX2 with a 256 KB mapper and an expanded slot 0, with a 512 KB memory mapper cartridge, under MSX-DOS 2
nms8245-ram512k-sunriseide  Philips NMS 8245, an MSX2 with a 128 KB mapper, with a 512 KB memory mapper cartridge and a Sunrise IDE interface under Nextor
nms8250-carnivore2          Philips NMS 8250, an MSX2 with a 128 KB mapper and a floppy drive, with a Carnivore2 under Nextor
phc28s-ram64k-carnivore2    Sanyo PHC-28S, an MSX1 with 16 KB, with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2, under Nextor
vg8020-carnivore2           Philips VG-8020, an MSX1 with 64 KB, with a Carnivore2 under Nextor
vg8020-picoverse            A Philips VG-8020 with a cartridge like the PicoVerse
vg8020-sdmapper             Philips VG-8020, an MSX1 with 64 KB, with an SD Mapper v1 (Fabio Belavenuto)
vg8235                      Philips VG-8235, an MSX2 with a 128 KB memory mapper and a single-sided floppy drive, without cartridges
xp800-sdmapper              Gradiente Expert XP-800, a Brazilian MSX1 with 64 KB, with an SD Mapper v1 (Fabio Belavenuto)
```

## Machine names

A machine's name is its model and then its cartridges in slot order, such as
`phc28s-ram64k-carnivore2`, and its capture variants are named in the same way
([FILES.md, Machine file][machine]). These names are in place already, so the
command needs no change of its own to them.

## Download

A game file's `url` line holds the link to side 1's zip and, for a game with a side
2, the link to side 2's zip, in the order of `sha1`:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
url https://download.file-hunter.com/Games/MSX1/CAS/Gauntlet%20(1986)(US%20Gold)(Side%20A)%5BRUN%27CAS-%27%5D.zip https://download.file-hunter.com/Games/MSX1/CAS/Gauntlet%20(1986)(US%20Gold)(Side%20B)%5BRUN%27CAS-%27%5D.zip
```

The `url` lines are in place ([FILES.md, Game file][gamefile]): each of the 1545
shipped game files has one.

For each side, the command does these steps:

1. When `downloads/` holds the side's file and its SHA-1 matches, it does nothing.
   When the file's SHA-1 differs, it stops, names both SHA-1s and keeps the file,
   so that the user can look at it before moving it away.
2. It downloads the zip, with a User-Agent that names `snapcas`.
3. It looks in the zip for the member whose SHA-1 matches the side's, whatever its
   name, because a compilation's zip holds many CAS files.
4. It saves that member under the game file's name, such as `GAUNTLET.CAS`, because
   the tools find a tape by that name. When no member matches, it stops with an
   error that names the zip, and writes nothing.

The programs of one compilation share a tape, so its zip is downloaded only for the
first of them. A game file in `games/` without a `url` line stops the command with
the file to put in `downloads/`:

```
$ ./snapcas.py snap mygame phc28s-ram64k-carnivore2
snapcas.py: games/MYGAME/game.txt has no url line. Put the file whose SHA-1 is
d122e3c80cce689efe28dbb4734f411f6487ed98 in downloads as MYGAME.CAS
```

## Sync a card

`sync` copies a machine's images from `images/<machine>/` and `SNAPCAS.COM` to a
card. Its second argument is the destination, the card's top folder:

```
$ ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
copy      /Volumes/MSX/BIN/SNAPCAS.COM, compared ok
copy      /Volumes/MSX/SNAPCAS/T/TEMPTATI.SNP, compared ok
copied 2, unchanged 1544
```

The files go to these places, so that no folder of the card holds every image:

| File | On the card |
|---|---|
| `SNAPCAS.COM` | `BIN/SNAPCAS.COM` |
| A game's image and replay | `SNAPCAS/<letter>/<GAME>.SNP` and `.RPL`, with `0-9` as the letter of a name that starts with a digit |
| A compilation's program | `SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP`, with the letter of the collection's name |
| A custom game's image | `SNAPCAS/C/CUSTOM/<GAME>.SNP`, as a program of a collection named `CUSTOM` |

`sync` copies only the files that the card lacks or holds with other bytes. It reads
each copy back and compares it with the original, and stops at the first copy that
differs. It never deletes a file on the card, so an image deleted from `images/`
stays there. A destination named `SNAPCAS` or `BIN` stops the command, because the
destination is the folder that holds them. Two images that go to the same place
stop it too, before it copies anything.

`SNAPCAS.COM` opens the image in the current folder, so on the MSX the player goes
to the image's folder first:

```
CD \SNAPCAS\G
\BIN\SNAPCAS GAUNTLET
```

## Decisions

| Decision | Rejected | Why |
|---|---|---|
| A verb for each command: `snap`, `list` and `machines` | A main use without a verb, `snapcas.py <game> <machine>`, with the lists as the options `--list` and `--machines` | Without a verb, the game and the machine are required for the main use and absent for the lists, which a parser cannot state, so its help would show them as optional. With a verb, each command states its own arguments and has its own help, for one word more. A `download` verb would add nothing, because `snap` downloads what it needs |
| A machine given by its whole name, such as `phc28s-ram64k-carnivore2` | A start of its name, such as `phc28s` | The name says the machine's cartridges, which change the image. A start that names one machine today can name another when a machine file is added |
| The game by its name, as `list` shows it | A text that matches one game, as in `snap gaunt` | A text that matches one game today can match two when a game file is added. `list` finds a game by a part of its name or title |
| One command, `snapcas.py`, at the repository's top. It takes over `tools/snapcas.py`, whose steps it runs | A new command beside `tools/snapcas.py` | Two commands that make an image would need two sets of docs and tests |
| A `url` key in the game file | Reading the link comment | A comment is free text, and its line is not fixed: Athletic Land's link is on its third line. Side 2 also needs a link |
| The tape found in the zip by its SHA-1 | By the member's name | `sha1` is already in every game file, and the member names differ from the game files' names |
| Python's standard library only | A package from pip, such as `requests` | Nothing to install beyond Python, on any OS |
| Downloads of the games that the user makes, one at a time | A download of the whole collection | File-Hunter is one person's site, and a user needs the games that they play |
| `openMSX`'s user home, as the tools use today | A home of the command's own, as the tests use | The tests' home links the system ROMs with a symbolic link, which Windows does not allow without rights |
| The machine's description from the first sentence of each machine file's first comment | A table in the command | The machine file stays the one place for a machine's facts. The user machines' files get that comment line, as the capture variants have one today |

## Limits

| Limit | How the user sees it |
|---|---|
| A game file in `games/` without a link | The command stops and names the file and the SHA-1 to put in `downloads/` |
| A tape that File-Hunter has changed or removed | The command stops: no zip, or no member with the SHA-1 |
| A machine whose system ROMs are missing | `openMSX` does not start, and the command prints its error with exit code 2 |
| `vg8020-picoverse` needs a 192 KB mapper, which the Makefile makes for the tests | The command writes `ram192k.xml` into `openMSX`'s `share/extensions` when it is missing, as the Makefile does |
| The games run, `make games`, checks every game file on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` only ([DESIGN.md, The games run][gamesrun]) | A game can fail on another machine, and `snap --check` shows it |
| MSX-DOS 1 has no folders | A machine under MSX-DOS 1, such as `vg8235`, cannot use the card's layout: `SNAPCAS.COM` and the image go into one folder by hand |
| A game that hangs or shows garbage passes the check ([DESIGN.md, Check][check]) | The image fails only on the real machine |

## To verify

- That a Windows install of `openMSX` 22.0 puts `openmsx` on the path. Otherwise
  `OPENMSX` names the program.
- That File-Hunter allows downloads by a program, one zip at a time, on a user's
  request.
- The lowest Python 3 version that the tools run on, which the requirements then
  name.
- That `openMSX` prints a missing system ROM as an error that the command can show.

## Not in the first version

- Several games in one run. A shell loop runs the command once for each game.
- A download of the whole collection.
- Tapes from any site other than File-Hunter, and TSX files.
- A package for pip, or a program built for each OS.
- A machine file made by the command: a new machine is still described by hand
  ([FILES.md, Machine file][machine]).
- A record of the games tested on real hardware.

[files]: DESIGN.md#files-and-commands
[check]: INTERNALS.md#check
[machine]: FILES.md#machine-file
[gamefile]: FILES.md#game-file
[gamesrun]: INTERNALS.md#the-games-run
