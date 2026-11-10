# The `snapcas` command

`snapcas.py` is one command that makes a game's image for the user's machine from
the game's name. The command downloads the game's tape from File-Hunter when the
tape is missing. It then captures the game in `openMSX`, builds the image, and
copies the images to a card. The command is for MSX owners who are not developers.
So its main use is one short line that holds `snap`, a game and a machine. It needs
only Python 3 and `openMSX`, on macOS, Linux or Windows. `snapcas.py` does the steps
of the tools that already exist ([DESIGN.md, Files and commands][files]) and adds no
new way to make an image.

## Requirements

| What | Why |
|---|---|
| Python 3, with its standard library only | The tools are Python 3 programs. The download uses `urllib` and `zipfile`, so the user installs nothing with pip |
| `openMSX` 22.0, on the path or named by `OPENMSX` | The capture and the check run in `openMSX` |
| The system ROMs of the user's machine, in `openMSX`'s `share/systemroms` | `openMSX` needs the system ROMs to emulate the machine, and `snapcas` cannot ship them. When a ROM is missing, the command shows `openMSX`'s message, and that message names the ROM |
| `make firmware`, once, for the machines `fsa1-mfrsd`, `hbf1xd-mfrsd`, `vg8020-sdmapper`, `xp800-sdmapper` and `vg8020-picoverse` | `make firmware` downloads the firmware of these machines into `out/cache/openmsx-home/`, an `openMSX` home with a link to the user's system ROMs. `snapcas` then uses that home in place of the default home. `OPENMSX_HOME` names another home. Without the firmware, `snap` and `try` stop and name `make firmware` |
| A network connection, the first time that the user makes a game | The tapes come from File-Hunter, and `snapcas` cannot ship the tapes either |

The user gets `snapcas` as a clone or a zip of the repository. In the repository's
folder, the user runs `./snapcas.py`. The file starts with `#!/usr/bin/env python3`,
and git keeps the file executable, so macOS and Linux run it with Python 3. Windows
runs the file as `py snapcas.py`. A zip of the repository may lose the executable
bit. `python3 snapcas.py` then runs the command on macOS and Linux. `snapcas` ships
`bin/SNAPCAS.COM` and `bin/SERVICE.BIN`, so the user needs no assembler.

## Commands

The command takes a verb that says what to do, and the verb's own arguments:

| Command | What it does |
|---|---|
| `snap <game> <machine>` | Makes the game's image for the machine, and downloads the game's tapes first when they are missing ([Make an image](#make-an-image)) |
| `try <game> <machine>` | Starts the game's image in `openMSX`, so that the user can try the image before the real machine ([Try an image](#try-an-image)) |
| `sync <machine> <destination>` | Copies the machine's images and `SNAPCAS.COM` to a card ([Sync a card](#sync-a-card)) |
| `list [text] [--all]` | Lists the games that `snapcas` supports, or searches them by name ([Find a game or a machine](#find-a-game-or-a-machine)) |
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
`supermsx/thewall`. The name can be in any mix of upper case and lower case. The
second argument is the machine's name, as `machines` shows it, such as
`phc28s-ram64k-carnivore2` ([Machine names](#machine-names)). When a name is not a
game's name or a machine's name, the command stops:

```
$ ./snapcas.py snap wall phc28s-ram64k-carnivore2
snapcas.py: no game is named "wall": snapcas.py list shows the games
```

`snap` downloads, captures and builds without being asked. It keeps the tapes that
it downloads in `downloads/`, so it downloads a tape once. `snap` makes the image
again each time that it runs.

`snap` takes these options:

| Option | What it does | Default |
|---|---|---|
| `--check` | Checks the image as `check.py` does ([INTERNALS.md, Check][check]), with the DOS files of the machine's `dosfiles` line ([FILES.md, Machine file][machine]). For a machine under Nextor, `snapcas` downloads Nextor 2.1.0's `NEXTOR.SYS` and `COMMAND2.COM` into `dos/nextor/`. `snapcas` pins the two files by SHA-256, as the Makefile does | No check |
| `--dos <dir>` | Names the DOS system files for `--check`, in place of the machine's files. A machine under MSX-DOS 1 or MSX-DOS 2 needs its files in `dos/msxdos1/` or `dos/msxdos2/` ([dos/README.md](../dos/README.md)). When those files are missing, `snapcas` stops and says that they are missing. The environment variable `DOS_DIR` names a folder that takes the place of `dos/` for these two folders | The machine's folder below `dos/` |

```
$ ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2 --check
...
check     pass  the restored machine equals the snapshot
check     pass  the game does not write to the tape service in page 3
check     pass  the machine does not reboot
check     pass  the game does not stop at a BASIC error
image     images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
```

The command exits with the tools' codes:

- 0 on success.
- 1 for an error in the input files, a game that the command cannot find or a
  download that fails.
- 2 when `openMSX` fails or a wait times out.
- 3 when a check fails.

Ctrl-C stops the command without a message, with code 130.

## Try an image

`try` starts a game's image in `openMSX`, with the `openMSX` window and sound:

```
$ ./snapcas.py try temptati phc28s-ram64k-carnivore2
try       images/phc28s-ram64k-carnivore2/TEMPTATI/TEMPTATI.SNP: SNAPCAS TEMPTATI
```

`try` finds the game and the machine as `snap` does. It boots the machine with a
disk that holds the machine's DOS files, `SNAPCAS.COM` and the game's image. `try`
then passes the machine's boot menu and types `SNAPCAS <GAME>` at DOS's prompt, as
the player does on the real machine. After that, the keyboard is the user's.
`--dos <dir>` names other DOS files, as it does for `snap`. When the game has no
image, `try` stops and says that `snap` makes the image.

## Your own games

`custom/` holds the user's own games. They are games that `snapcas` does not ship,
or the user's own dumps of a tape. Each game has a folder with its game file and its
tape files. The game's name is `custom/` followed by the folder's name, such as
`custom/MYGAME`. `snap`, `try` and `list` take that name as they take a shipped
game's name. `snap` reads a custom game's tapes from the game's folder and never
downloads them. The image goes to `images/<machine>/custom/MYGAME/`. Git ignores the
games in `custom/`, and [custom/README.md](../custom/README.md) shows how to write
one. `make games` and `make test` never read `custom/`.

## Find a game or a machine

Two verbs print a list and make nothing:

| Command | What it prints |
|---|---|
| `list [text] [--all]` | The games whose folder or title holds the text, or every game, each with the name to give `snap`. `list` shows a compilation's programs only with `--all`. Without `--all`, the last line counts the programs that hold the text. A game in a collection's folder, such as `SUPERMSX/GOLF`, is a compilation's program. So is one of 4 or more game files from one zip, as Turbo Pack A's game files are. Two or three game files from one zip are a game's parts or versions, such as `RUR-1` and `RUR-2`, and `list` always shows them. A game's title names the File-Hunter file that the game comes from. That file is the game's zip, a CAS file in a zip, or a compilation's zip and the program's name, as in `Super MSX n.23 (settembre 1989) - cas_23 / Africa Film`. When a CAS file's name starts with its zip's name, such as the zip's name with `[LOADERFIX]` added, the title names the zip alone |
| `machines` | The user machines, each with the first sentence of its machine file's first comment, up to a full stop or a colon |

```
$ ./snapcas.py list gaunt
GAUNTLET  Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']
1 game

$ ./snapcas.py list wall
WALL-THE  Wall, The (1987)(Erbe Software)[RUN'CAS-']
WALLBALL  Wallball (19xx)(Tynesoft)[BLOAD'CAS-',R]
2 games, and 1 in compilations, which --all lists

$ ./snapcas.py machines
fsa1-mfrsd                  Panasonic FS-A1 (MSX2, 64 KB) with a MegaFlashROM SCC+ SD
hb75p-carnivore2            Sony HB-75P (MSX1, 64 KB) with a Carnivore2
hb75p-mfrsd                 Sony HB-75P (MSX1, 64 KB) with a MegaFlashROM SCC+ SD
hbf1xd-mfrsd                Sony HB-F1XD (MSX2, 64 KB) with a MegaFlashROM SCC+ SD
hbf700p-ram512k-msxdos2     Sony HB-F700P (MSX2, 256 KB) with a 512 KB RAM cartridge, under MSX-DOS 2
nms8245-ram512k-sunriseide  Philips NMS 8245 (MSX2, 128 KB) with a 512 KB RAM cartridge and a Sunrise IDE
nms8250-carnivore2          Philips NMS 8250 (MSX2, 128 KB) with a Carnivore2
phc28s-ram64k-carnivore2    Sanyo PHC-28S (MSX1, 16 KB) with a 64 KB RAM cartridge and a Carnivore2
vg8020-carnivore2           Philips VG-8020 (MSX1, 64 KB) with a Carnivore2
vg8020-picoverse            Philips VG-8020 (MSX1, 64 KB) with a PicoVerse-like cartridge
vg8020-sdmapper             Philips VG-8020 (MSX1, 64 KB) with an SD Mapper v1
vg8235                      Philips VG-8235 (MSX2, 128 KB) with no cartridges, under MSX-DOS 1
xp800-sdmapper              Gradiente Expert XP-800 (MSX1, 64 KB) with an SD Mapper v1
```

## Machine names

A machine's name is its model and then its cartridges in slot order, such as
`phc28s-ram64k-carnivore2`. The machine's capture variants have names of the same
form ([FILES.md, Machine file][machine]).

## Download

A game file's `url` line holds the link to side 1's zip. For a game with a side 2,
the line also holds the link to side 2's zip. The links are in the order of `sha1`:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
url https://download.file-hunter.com/Games/MSX1/CAS/Gauntlet%20(1986)(US%20Gold)(Side%20A)%5BRUN%27CAS-%27%5D.zip https://download.file-hunter.com/Games/MSX1/CAS/Gauntlet%20(1986)(US%20Gold)(Side%20B)%5BRUN%27CAS-%27%5D.zip
```

Each of the 1545 shipped game files has a `url` line
([FILES.md, Game file][gamefile]).

For each side, the command does these steps:

1. When `downloads/` holds the side's file and the file's SHA-1 matches, the command
   does nothing. When the file's SHA-1 differs, the command stops, names both SHA-1s
   and keeps the file. The user can then look at the file before moving it away.
2. It downloads the zip, with a User-Agent that names `snapcas`.
3. It looks in the zip for the member whose SHA-1 matches the side's SHA-1. The
   member's name does not matter, because a compilation's zip holds many CAS files.
4. It saves that member under the game file's name, such as `GAUNTLET.CAS`, because
   the tools find a tape by that name. When no member matches, it stops with an
   error that names the zip, and writes nothing.

The programs of one compilation share a tape, so the command downloads the
compilation's zip only for the first of them. When a game file in `games/` has no
`url` line, the command stops and names the file to put in `downloads/`:

```
$ ./snapcas.py snap mygame phc28s-ram64k-carnivore2
snapcas.py: games/MYGAME/game.txt has no url line. Put the file whose SHA-1 is
d122e3c80cce689efe28dbb4734f411f6487ed98 in downloads as MYGAME.CAS
```

## Sync a card

`sync` copies a machine's images and `SNAPCAS.COM` to a card. It takes the images
from `images/<machine>/`, where `snap` and `make games` put them. Its second
argument is the destination, which is the card's top folder:

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
| A game's image | `SNAPCAS/<letter>/<GAME>.SNP`, with `0-9` as the letter of a name that starts with a digit |
| A compilation's program | `SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP`, with the letter of the collection's name |
| A custom game's image | `SNAPCAS/C/CUSTOM/<GAME>.SNP`, as a program of a collection named `CUSTOM` |

`sync` copies only the files that the card lacks or holds with other bytes. It
writes each copy under a temporary name in the same folder. The temporary name is
the file's name with `.$$$` in place of its ending. `sync` then has the system write
the bytes out to the card. Only then does `sync` give the copy the file's name. As a
result, a card that is full, or that is pulled out during the copy, holds no cut
file under an image's name. `sync` then reads each copy back, compares the copy with
the original, and stops at the first copy that differs.

`sync` never deletes an image on the card, so an image that was deleted from
`images/` stays on the card. It deletes only one kind of file. On a FAT card, macOS
keeps a file's extended attributes in a second file, named `._` followed by the
file's name. DOS lists that second file as one more file. `sync` removes the second
file of each copy that it makes.

A destination named `SNAPCAS` or `BIN` stops the command, because the destination is
the folder that holds `SNAPCAS` and `BIN`. Two images that go to the same place also
stop the command, before it copies anything.

`SNAPCAS.COM` opens the image in the current folder, so on the MSX the player goes
to the image's folder first:

```
CD \SNAPCAS\G
\BIN\SNAPCAS GAUNTLET
```

## Decisions

| Decision | Rejected | Why |
|---|---|---|
| A verb for each command: `snap`, `try`, `sync`, `list` and `machines` | A main use without a verb, `snapcas.py <game> <machine>`, with the lists as the options `--list` and `--machines` | Without a verb, the main use requires the game and the machine, and the lists take neither. A parser cannot state that rule, so the parser's help would show the game and the machine as optional. With a verb, each command states its own arguments and has its own help. The cost is one more word. A `download` verb would add nothing, because `snap` downloads what it needs |
| A machine given by its whole name, such as `phc28s-ram64k-carnivore2` | A start of its name, such as `phc28s` | The name says the machine's cartridges, and the cartridges change the image. A start that names one machine today can name another machine when a machine file is added |
| The game by its name, as `list` shows it | A text that matches one game, as in `snap gaunt` | A text that matches one game today can match two games when a game file is added. `list` finds a game by a part of its name or title |
| One command, `snapcas.py`, in the repository's top folder. It replaced an earlier tool, `tools/snapcas.py`, and took over that tool's steps | A new command beside the earlier tool | Two commands that make an image would need two sets of docs and tests |
| A `url` key in the game file | Reading the link comment | A comment is free text, and the comment's line is not fixed. Athletic Land's link is on its third line. Side 2 also needs a link |
| The tape found in the zip by its SHA-1 | By the member's name | `sha1` is already in every game file, and the member names differ from the game files' names |
| Python's standard library only | A package from pip, such as `requests` | The user installs nothing beyond Python, on any OS |
| Downloads of the games that the user makes, one at a time | A download of the whole collection | File-Hunter is one person's site, and a user needs the games that they play |
| `out/cache/openmsx-home/`, the home that `make firmware` makes, when that home exists and `OPENMSX_HOME` names no other home. Otherwise, `openMSX`'s user home | Always a home of the command's own, as the tests use | The tests' home links the system ROMs with a symbolic link, and Windows does not allow a symbolic link without rights. So only the machines that need `make firmware`'s files need that home |
| The machine's description from the first sentence of each machine file's first comment | A table in the command | The machine file stays the one place for a machine's facts. Each machine's file and each capture variant's file starts with that comment line |

## Limits

| Limit | How the user sees it |
|---|---|
| A game file in `games/` without a link | The command stops and names the file and the SHA-1 to put in `downloads/` |
| A tape that File-Hunter has changed or removed | The command stops, because it finds no zip, or no member with the SHA-1 |
| A machine whose system ROMs are missing | `openMSX` does not start, and the command prints `openMSX`'s error with exit code 2 |
| `vg8020-picoverse` needs a 192 KB mapper. The mapper is `ram192k.xml` in `openMSX`'s `share/extensions`, and `make firmware` makes that file | Without the mapper, the command stops and names `make firmware` |
| The games run, `make games`, checks every game file on one machine. The developers run it on three machines only: `phc28s-ram64k-carnivore2`, `vg8020-carnivore2` and `hb75p-carnivore2` ([INTERNALS.md, The games run][gamesrun]) | A game can fail on another machine, and `snap --check` shows the failure |
| MSX-DOS 1 has no folders | A machine under MSX-DOS 1, such as `vg8235`, cannot use the card's layout. The user puts `SNAPCAS.COM` and the image into one folder by hand |
| A game that hangs or shows garbage passes the check ([INTERNALS.md, Check][check]) | The image fails only on the real machine |

## To verify

- That a Windows install of `openMSX` 22.0 puts `openmsx` on the path. Otherwise,
  `OPENMSX` names the program.
- That File-Hunter allows downloads by a program, one zip at a time, on a user's
  request.
- The lowest Python 3 version that the tools run on. The requirements then name that
  version.

## What the command does not do

- Several games in one run. A shell loop runs the command once for each game.
- A download of the whole collection.
- Tapes from any site other than File-Hunter. A tape from another place goes in as
  a custom game ([Your own games](#your-own-games)).
- A package for pip, or a program built for each OS.
- A machine file made by the command. A new machine is still described by hand
  ([FILES.md, Machine file][machine]).
- A record of the games tested on real hardware.

[files]: DESIGN.md#files-and-commands
[check]: INTERNALS.md#check
[machine]: FILES.md#machine-file
[gamefile]: FILES.md#game-file
[gamesrun]: INTERNALS.md#the-games-run
