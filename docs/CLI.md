# The `snapcas` command (draft design)

`snapcas.py` is one command that makes a game's image for the user's machine from
the game's name. It downloads the game's tape from File-Hunter when it is missing,
captures the game in `openMSX`, builds the image, and can copy it to a card. It is
written for MSX owners who are not developers, so its main use is one line with two
words, and it needs only Python 3 and `openMSX`, on macOS, Linux or Windows. It runs
the tools that already exist ([DESIGN.md, Files and commands][files]) and adds no
new way to make an image. This page is a draft for review, and its sections move
into DESIGN.md and PLAN.md when it is signed off.

## Requirements

| What | Why |
|---|---|
| Python 3, with its standard library only | The tools are Python 3 programs. The download uses `urllib` and `zipfile`, so nothing needs installing with pip |
| `openMSX` 22.0, on the path or named by `OPENMSX` | The capture and the check run in it, as today |
| The system ROMs of the user's machine, in `openMSX`'s `share/systemroms` | `openMSX` needs them to emulate the machine, and `snapcas` cannot ship them |
| A network connection, the first time a game is made | The tapes come from File-Hunter, and `snapcas` cannot ship them either |

The user gets `snapcas` as today, as a clone or a zip of the repository, and runs
`python3 snapcas.py` in its folder. `bin/SNAPCAS.COM` and `bin/SERVICE.BIN` are
shipped, so the user needs no assembler.

## Make an image

The command takes a game and a machine:

```
$ python3 snapcas.py gauntlet phc28s
Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'] for phc28s-ram64k-carnivore2
download  GAUNTLET.CAS from File-Hunter, sha1 ok
download  GAUNTLEB.CAS from File-Hunter, sha1 ok
capture   done
build     done
image     out/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
```

The command finds the game from its first word in this order, without regard to
case:

| The word | The game |
|---|---|
| A folder below `games/`, such as `gauntlet` or `supermsx/thewall` | That folder's game |
| Any other text, such as `"the wall"` | The one game whose folder or title holds the text |

When the text matches several games, the command lists them and stops, so the user
picks one by its folder:

```
$ python3 snapcas.py wall phc28s
snapcas.py: "wall" matches 3 games. Give one of these folders:
  SUPERMSX/THEWALL  The Wall, the first game on the tape Super MSX n.7
  WALL-THE          Wall, The (1987)(Erbe Software)[RUN'CAS-']
  WALLBALL          Wallball (19xx)(Tynesoft)[BLOAD'CAS-',R]
```

The second word is the machine: a machine's name ([Machine names](#machine-names)),
or a start of it that no other machine's name has, such as `phc28s`. When the start
matches several machines, as `vg8020` does, the command lists them and stops, as it
does for a game. The command needs no subcommand for this main use, and it
downloads, captures and builds without being asked. A tape that is already in the
tapes folder is not downloaded again, and an image is made again each time.

These options add to the main use:

| Option | What it does | Default |
|---|---|---|
| `--to <dir>` | Copies the image, its replay and `SNAPCAS.COM` to the card at `<dir>`, and checks each copy by reading it back ([Card layout](#card-layout)) | No copy |
| `--check` | Runs `check.py` on the image. For a machine under Nextor, `snapcas` downloads Nextor 2.1.0's `NEXTOR.SYS` and `COMMAND2.COM`, pinned by SHA-256 as the Makefile does | No check |
| `--dos <dir>` | The DOS system files for `--check`, on a machine that is not under Nextor | |
| `--tapes <dir>` | The tapes folder | `tapes/` |

```
$ python3 snapcas.py gauntlet phc28s --check --to /Volumes/MSX
...
image     out/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
check     pass
copy      /Volumes/MSX/SNAPCAS/G/GAUNTLET.SNP, compared ok
copy      /Volumes/MSX/SNAPCAS/G/GAUNTLET.RPL, compared ok
copy      /Volumes/MSX/BIN/SNAPCAS.COM, compared ok
```

The command exits with the tools' codes: 0 on success, 1 for an error in the input
files or a game that it cannot find, 2 when `openMSX` fails or a wait times out, and
3 when a check fails.

## Find a game or a machine

Two options print a list and make nothing:

| Option | What it prints |
|---|---|
| `--list [text]` | The games whose folder or title holds the text, or every game, with the folder to give the command |
| `--machines` | The user machines, each with the first comment line of its machine file |

```
$ python3 snapcas.py --list gaunt
GAUNTLET   Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']
1 game

$ python3 snapcas.py --machines
fsa1-mfrsd                  Panasonic FS-A1 with a MegaFlashROM SCC+ SD
hb75p-mfrsd                 Sony HB-75P with a MegaFlashROM SCC+ SD
hbf1xd-mfrsd                Sony HB-F1XD with a MegaFlashROM SCC+ SD
hbf700p-ram512k-msxdos2     Sony HB-F700P with a 512 KB RAM cartridge and MSX-DOS 2
nms8245-ram512k-sunriseide  Philips NMS 8245 with a 512 KB RAM cartridge and a Sunrise IDE
nms8250-carnivore2          Philips NMS 8250 with a Carnivore2
phc28s-ram64k-carnivore2    Sanyo PHC-28S with a 64 KB RAM cartridge in slot 1 and a Carnivore2 in slot 2
vg8020-carnivore2           Philips VG-8020 with a Carnivore2
vg8020-picoverse            Philips VG-8020 with a PicoVerse
vg8020-sdmapper             Philips VG-8020 with an SD Mapper
vg8235                      Philips VG-8235, without cartridges
xp800-sdmapper              Gradiente Expert XP-800 with an SD Mapper
```

## Machine names

A machine's name is its model and then its cartridges in slot order, such as
`phc28s-ram64k-carnivore2`, and its capture variants are named in the same way
([DESIGN.md, Machine file][machine]). These names are in place already, so the
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

The `url` lines are in place ([DESIGN.md, Game file][gamefile]): each of the 1545
shipped game files has one.

For each side, the command does these steps:

1. When the tapes folder holds the side's file and its SHA-1 matches, it does
   nothing.
2. It downloads the zip, with a User-Agent that names `snapcas`.
3. It looks in the zip for the member whose SHA-1 matches the side's, whatever its
   name, because a compilation's zip holds many CAS files.
4. It saves that member under the game file's name, such as `GAUNTLET.CAS`, because
   the tools find a tape by that name. When no member matches, it stops with an
   error that names the zip, and writes nothing.

The programs of one compilation share a tape, so its zip is downloaded only for the
first of them. A game file without a `url` line, such as one that a user writes,
stops the command with the file to put in the tapes folder:

```
$ python3 snapcas.py mygame phc28s
snapcas.py: games/MYGAME/game.txt has no url line. Put the CAS file whose SHA-1 is
d122e3c80cce689efe28dbb4734f411f6487ed98 in tapes/ as MYGAME.CAS
```

## Card layout

`--to <dir>` writes the files that the user copies by hand today:

| File | Where on the card |
|---|---|
| `SNAPCAS.COM` | `<dir>/BIN/SNAPCAS.COM` |
| A game's image and replay | `<dir>/SNAPCAS/<letter>/<GAME>.SNP` and `.RPL`, with `0-9` as the letter of a name that starts with a digit |
| A compilation's program | `<dir>/SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP`, with the letter of the collection's name |

After each copy, it reads the file back and compares it with the original, and stops
at the first copy that differs. It never deletes a file on the card.

## Decisions

| Decision | Rejected | Why |
|---|---|---|
| The main use is `snapcas.py <game> <machine>`, with no subcommand, and the lists are options | Subcommands, such as `make`, `list` and `download` | The main use is one line of two words. A separate download step adds nothing, because the main use downloads what it needs |
| A machine given by a start of its name, such as `phc28s` | Only the full name | The user types the short part, and a start that matches several machines stops the command |
| The game by its folder, or by a text that matches one game | Only the folder | The user knows the title. Several matches stop the command, so it never makes the wrong game |
| One command, `snapcas.py`, at the repository's top. It takes over `tools/snapcas.py`, whose steps it runs | A new command beside `tools/snapcas.py` | Two commands that make an image would need two sets of docs and tests |
| A `url` key in the game file | Reading the link comment | A comment is free text, and its line is not fixed: Athletic Land's link is on its third line. Side 2 also needs a link |
| The tape found in the zip by its SHA-1 | By the member's name | `sha1` is already in every game file, and the member names differ from the game files' names |
| Python's standard library only | A package from pip, such as `requests` | Nothing to install beyond Python, on any OS |
| Downloads of the games that the user makes, one at a time | A download of the whole collection | File-Hunter is one person's site, and a user needs the games that they play |
| `openMSX`'s user home, as the tools use today | A home of the command's own, as the tests use | The tests' home links the system ROMs with a symbolic link, which Windows does not allow without rights |
| The machine's description from each machine file's first comment line | A table in the command | The machine file stays the one place for a machine's facts. The user machines' files get that comment line, as the capture variants have one today |

## Limits

| Limit | How the user sees it |
|---|---|
| A game file without a link, such as one that a user writes | The command stops and names the file and the SHA-1 to put in the tapes folder |
| A tape that File-Hunter has changed or removed | The command stops: no zip, or no member with the SHA-1 |
| A machine whose system ROMs are missing | `openMSX` does not start, and the command prints its error with exit code 2 |
| `vg8020-picoverse` needs a 192 KB mapper, which the Makefile makes for the tests | The command writes `ram192k.xml` into `openMSX`'s `share/extensions` when it is missing, as the Makefile does |
| The collection is checked on `phc28s-ram64k-carnivore2` and `vg8020-carnivore2` only | A game can fail on another machine, and `--check` shows it |
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
  ([DESIGN.md, Machine file][machine]).
- A record of the games tested on real hardware.

[files]: DESIGN.md#files-and-commands
[check]: DESIGN.md#check
[machine]: DESIGN.md#machine-file
[gamefile]: DESIGN.md#game-file
