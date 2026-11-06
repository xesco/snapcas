# Machine and game files

`snapcas` makes an image from two kinds of text file: a machine file, which describes
one MSX and its cartridges, and a game file, which describes one game and its tape.
This page defines both, for the user who writes a custom game's file or a new
machine's, and lists the files that the repository ships. How the tools use them is
in [DESIGN.md](DESIGN.md).

## Machine file

A machine file describes one MSX and the cartridges in its slots. It holds one
`openmsx` line, one `disk` line, any number of `boot` lines, at most one `dos` line,
at most one `dosfiles` line and any number of `variant` lines, as in this example for a Sanyo PHC-28S with a RAM
cartridge and a Carnivore2:

```
# Sanyo PHC-28S (MSX1, 16 KB) with a 64 KB RAM cartridge and a Carnivore2. The RAM
# cartridge is in slot 1 and the Carnivore2 in slot 2, under Nextor.
openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2
disk hda
boot "DefConfig" space
variant phc28s-ram64k
variant phc28s-empty-carnivore2
```

| Line | Meaning |
|---|---|
| `openmsx` | The `openMSX` arguments that reproduce the machine |
| `disk` | The `openMSX` command that inserts `check.py`'s disk image, such as `hda` for an IDE interface or an SD card, or `diska` for a floppy drive. Then, optionally, the image's size in KB: 720, the default, or 360 for a single-sided drive, as the Philips VG-8235 has |
| `boot` | A text on the screen during boot and the key to press when it appears. Each key has its own line, matched in order. A menu can show its text before it reads the keyboard, so the key is pressed again each second while the text stays, up to 10 times |
| `hold` | A key held down from power-on, and the emulated seconds it is held, such as `hold del 6`. It is for a machine whose firmware starts a program in a graphics mode in place of BASIC, whose screen `boot` cannot read: the Panasonic FS-A1 starts its Desk Pac menu unless DEL is held |
| `dos` | For a machine that boots MSX-DOS from a disk of its own, as the MegaFlashROM SCC+ SD boots from the ROM disk in its flash: DOS's prompt, such as `A:\>`, and the drive letter of `check.py`'s disk. When the prompt appears, the capture types `BASIC`, because it loads the game from BASIC, and the check types that drive and `AUTOEXEC` |
| `dosfiles` | The folder below `dos/` that holds the DOS system files that the machine boots in `snapcas.py snap --check` and `try`: `msxdos1` or `msxdos2`. Without this line, the folder is `nextor` |
| `variant` | The name of one of the machine's capture variants. `snapcas.py snap` tries the variants in the order of these lines |

`openMSX` puts each `-ext` cartridge in the next free external slot, so the order of
the `-ext` options sets the slots, and it must match the real machine's. `boot`
lines pass a cartridge's boot menu, such as the Carnivore2's. The tools read the
screen with `get_screen`, so such a menu must be in a text mode. A line that starts
with `#` is a comment, and the file's first comment says what the machine is.

A machine file's name says what the file describes: the model, then each cartridge
in slot order, with `empty` for an empty slot before a cartridge. A cartridge's name
is `openMSX`'s name for it in lower case, such as `ram64k` or `carnivore2`, or a
short form of a long one, such as `sunriseide` and `mfrsd`. The PicoVerse is
`picoverse`, though two of `openMSX`'s cartridges stand in for it. So
`phc28s-ram64k-carnivore2` is a Sanyo PHC-28S with a 64 KB RAM cartridge in slot 1
and a Carnivore2 in slot 2, and two setups of one model have two names.

Machine files are of three kinds, each in its own place:

| Kind | Where | What it is |
|---|---|---|
| A user's machine | `machines/` | A real machine that the images are made for, given as the command's `<machine>` |
| A capture variant | `machines/capture/` | The same machine with fewer cartridges, for a game whose loader trips over a cartridge, or whose image needs fewer free mapper segments when the game runs in the machine's own RAM. A game's `capture` line names it |
| A test machine | `machines/test/`, given as `test/<name>` | A machine that only the tests use |

A capture variant only takes cartridges away: it keeps the machine's ROMs and every
other cartridge in its slot. The image built from its snapshot is still for the
user's machine and is checked there, so the restorer finds the RAM pages in the
slots that the snapshot names. A variant's name follows the same rule as a
machine's, so it names the cartridges that the variant holds, and not those that it
leaves out. So two machines whose variants hold the same cartridges share one
variant: the VG-8020 with a Carnivore2 and the VG-8020 with a PicoVerse both list
`vg8020`. The variant's first comment says which machines list it and why. A game's
`capture` line is in the machine's game file, which already names the machine that
the image is for, so the line names only the variant.

## Game file

A game file holds one setting per line: a key, a space and a value. A line that
starts with `#` is a comment, and blank lines are ignored. In the shipped game
files, each line after `cas`, `side2`, `sha1`, `url` and `name` has its own comment
above it, which says why the line is there, and a blank line before the comment.
Times are decimal emulated seconds from the moment the load command is typed.
Addresses and bytes are hexadecimal. Only `cas` is required. This example is for
Gauntlet, which loads its levels from the tape's second side:

```
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
```

| Key | Value | Default | File |
|---|---|---|---|
| `cas` | The CAS file of side 1, in the tapes folder. A game file has `cas` or `tsx` | | `game.txt` |
| `tsx` | The TSX file of side 1, in the tapes folder ([INTERNALS.md, Tape files](INTERNALS.md#tape-files)) | | `game.txt` |
| `side2` | The file of side 2, in side 1's format | None | `game.txt` |
| `load` | The load command, for a tape whose first block is not standard, quoted: `load 'RUN"CAS:"'` ([INTERNALS.md, Tape files](INTERNALS.md#tape-files)) | From the first block's type | `game.txt` |
| `start` | The name of a file on side 1, such as `start SKY`, for a game that is not the tape's first program: the load starts at the first file with that name ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)) | The tape's start | `game.txt` |
| `sha1` | The SHA-1 of `cas`, then that of `side2` | None | `game.txt` |
| `url` | The https link to the zip file that holds `cas`, then the link to the zip that holds `side2`, from which a tape is downloaded and found in its zip by its `sha1`. An apostrophe in a link is written `%27`, because the game file's lines are split as a shell splits words | None | `game.txt` |
| `name` | `<GAME>`, up to 8 letters and digits | The folder name in upper case, cut to 8 letters and digits | `game.txt` |
| `keys` | A time, then a key name ([Key names](#key-names)) held for 0.1 seconds, or a text in quotes that `openMSX` types. Each press has its own line | None | `game.txt` |
| `continue` | A key name that the capture tries before space and Return, to continue a load that waits for a key | None | `game.txt` |
| `snapshot` | `at` and a time, at which the capture takes the snapshot: for a game that asks the player to stop the tape, the moment it asks, because `openMSX`'s tape runs on and the tape service serves every later load | Found by the capture | `game.txt` |
| `capture` | A capture variant of the machine, on which the capture loads the game ([Machine file](#machine-file)) | The command's machine file | The machine's game file |
| `service` | `no` for a game that never reads the rest of its tape, though blocks of it stay unread. A game can read them only at its end, so `no` is for a game that someone has played to its end. A compilation's program also takes `no` when its capture reads the tape up to the next program's loader, because the blocks after it are the later programs' ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)). Or `at` and an address xxE1h in page 3, where the tape service's part of page 3 goes ([INTERNALS.md, Build](INTERNALS.md#build)). Or `t0`, for the tape service without a part in page 3 ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)). A file holds at most one `service` line, and `capture.py` and `build.py` stop with an error at a second one. A machine's game file's line replaces `game.txt`'s, as with any key that both give | Found by the capture, and by `build.py` | `game.txt`, or the machine's game file for a line that holds only on that machine, as the 8 shipped `t0` lines do |
| `patch` | A place, the old bytes, `>`, the new bytes: `patch page3:215F CD E1 00 > CD E1 FC` | None | `game.txt`, and a patch of a slot register's value the machine's game file |
| `rom` | `keep` for a game that must find the ROM in page 0 at the snapshot's slot: T0 does not replace the ROM, and the game reaches the tape service only through calls patched to the entries in page 3. So `rom keep` needs the part in page 3: a game file with `rom keep` and `service t0` is an error, and `build.py` stops when it would take the mode without a part in page 3 itself ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)) | T0 replaces the ROM when the restorer's rule allows it | `game.txt` |

A place is a RAM page as `page<n>:<offset>`, which names the RAM page that the
snapshot selects in page n, 0 to 3, and the offset from that page's start. A place
can also be on the tape, as `side1:<offset>` or `side2:<offset>`, an offset in the
tape file. A patch on the tape changes the tape that the capture loads and that the
tape service serves, so it also reaches the code that the capture runs. Neither form
names a slot, so a patch line holds on every machine that the game runs on, unless
its new bytes are a slot register's value. A patch fits only the dump that it was
made for, so `capture.py` and `build.py` stop with an error when the old bytes
differ, or when the game file has `patch` lines and `sha1` is missing or differs
from a tape file's SHA-1.

`game.txt` describes the game and its tape, and holds on every machine. A game's
folder can also hold a machine's game file: a game file for one machine, named after
that machine file, such as `phc28s-ram64k-carnivore2.txt` for
`phc28s-ram64k-carnivore2`. The tools read it after `game.txt` when they capture,
build or check for that machine. Its lines add to those of `game.txt`, and a value
that both give is the machine's game file's. It holds the lines that depend on where
the machine's RAM and cartridges are:

| Line | Why it depends on the machine |
|---|---|
| `capture` | It names one of the capture variants that the machine file lists ([Machine file](#machine-file)) |
| A patch of a slot register's value | The value names slots. Sootland writes FCh to the slot register, for RAM in slot 3, and crashes on the Sanyo PHC-28S. Without Nextor, that machine's BASIC keeps page 3 in the internal RAM, slot 0, and the RAM cartridge in slot 1 holds pages 0 to 2, so a patch to 14h keeps page 3 there and selects slot 1 for pages 1 and 2. The capture makes such a patch itself for a fixed value ([INTERNALS.md, Slot patches](INTERNALS.md#slot-patches)), so a game file needs one only for a value that the game computes |
| A `snapshot` that a real machine needs | Tokyo Nampa Street's snapshot comes after its music only because of the real PHC-28S ([DESIGN.md, Limits](DESIGN.md#limits)) |

## Shipped files

The repository ships a game file for each game of File-Hunter's MSX CAS collection
in `games/`, in a folder named after the short name of its side 1 CAS file, such as
`games/ABADIA/` for `ABADIA.CAS`. The folder name then also names the image. A
compilation's programs are the exception: each has a game file of its own, in a
folder named after the program's game, inside a folder named after the collection,
such as `games/ENGESOFT/ATHLETIC/`
([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)). Each game file starts with
a comment, the game's File-Hunter name. It then has the `sha1` of its dumps, which
finds a dump whatever its file name, and a `url` line with the links to its zips in
File-Hunter's MSX1 CAS folder. A side 2 is a zip of its own there, as Gauntlet's
Side B is. A side B, a later tape of a set or an expansion, which the collection's
`SIDES.TXT` lists, needs a tape before it, so it has no game file of its own. A dump
that File-Hunter marks `[b]`, a bad dump, has no game file either, and a game with a
better dump uses that one. A dump that File-Hunter lists more than once for one
release has one game file: Swing Man (Spectravideo) is listed as Swing Man, as Swing
Man (Side A) and under its catalogue number, SM-221, all with the same SHA-1, and
only `games/SWING-MA/` holds it. A dump in two releases, such as a Turbo Pack
program that is also its game's own tape, keeps a game file for each, as a
compilation's program does ([INTERNALS.md, A game later on the tape](INTERNALS.md#a-game-later-on-the-tape)).
Its `side2` lines pair the Side A and Side B files of a game, its `continue` lines
come from the key that the capture reports, its `service no` lines from games played
to their end, and its `patch` lines from `check.py` and from traces of failed loads.
The lines that hold only on one machine are in that machine's game file
([Game file](#game-file)), and the other game files hold on any machine. It also
ships these machine files, each checked with `check.py` and a single-load game, with
the number of machine's game files that each has:

| File | Configuration | Machine's game files |
|---|---|---|
| `vg8020-carnivore2` | Philips VG-8020: an MSX1 with 64 KB and a Carnivore2 | 123 |
| `nms8250-carnivore2` | Philips NMS 8250: an MSX2 with its own 128 KB and a floppy drive, and a Carnivore2 under Nextor, for the cartridge with a mapper and a disk interface that most MSX2 owners use | 54 |
| `nms8245-ram512k-sunriseide` | Philips NMS 8245: an MSX2 with a 512 KB RAM cartridge and a Sunrise IDE interface, under Nextor. Its own 128 KB leave Nextor too few free segments | 0 |
| `vg8020-picoverse` | Philips VG-8020 with a Sunrise IDE interface under Nextor and a 192 KB memory mapper, as the PicoVerse cartridge has them. `openMSX` has no PicoVerse, so these two cartridges stand in for it, and the Makefile makes the 192 KB mapper from `openMSX`'s 512 KB one | 54 |
| `phc28s-ram64k-carnivore2` | Sanyo PHC-28S: an MSX1 with 16 KB, a RAM cartridge in slot 1 and a Carnivore2 in slot 2 | 89 |
| `hb75p-mfrsd` | Sony HB-75P: an MSX1 with 64 KB and a MegaFlashROM SCC+ SD in `openMSX`'s stock setup, which boots MSX-DOS from the ROM disk in its flash, with the check's disk in SD card slot 1 as drive B: | 0 |
| `hbf700p-ram512k-msxdos2` | Sony HB-F700P: an MSX2 whose slot 0 is expanded, with a 512 KB RAM cartridge, under MSX-DOS 2. Its own mapper holds 256 KB | 8 |
| `vg8020-sdmapper` | Philips VG-8020 with an SD Mapper v1: its 512 KB mapper and Nextor on its SD cards. The Makefile downloads the cartridge's firmware, `SDMAPPER.ROM` 1.0.7, which `openMSX` needs | 0 |
| `xp800-sdmapper` | Gradiente Expert XP-800, a Brazilian MSX1 with 64 KB, with an SD Mapper v1, as `vg8020-sdmapper` | 0 |
| `fsa1-mfrsd` | Panasonic FS-A1: an MSX2 with 64 KB and no mapper, with a MegaFlashROM SCC+ SD whose flash holds only Nextor 2.1.4, which the Makefile makes. `openMSX`'s stock flash also holds a ROM disk, whose `AUTOEXEC.BAT` starts a file manager on an MSX2. DEL is held from power-on, which skips the FS-A1's Desk Pac menu | 0 |
| `hbf1xd-mfrsd` | Sony HB-F1XD: an MSX2 with 64 KB, no mapper and a floppy drive, with the MegaFlashROM SCC+ SD of `fsa1-mfrsd` | 0 |
| `vg8235` | Philips VG-8235: an MSX2 with a 128 KB mapper and a single-sided floppy drive, without cartridges. It boots MSX-DOS 1 from a 360 KB disk | 0 |

It also ships these capture variants in `machines/capture/`
([Machine file](#machine-file)), which the games' `capture` lines name. A row is a
variant and a machine that lists it, and its count is the number of that machine's
game files whose `capture` line names the variant:

| Variant | Machine | Leaves out | Used by |
|---|---|---|---|
| `phc28s-ram64k` | `phc28s-ram64k-carnivore2` | The Carnivore2, and so Nextor | 69 game files that crash when a disk system is present, or that select RAM by fixed slot values |
| `phc28s-empty-carnivore2` | `phc28s-ram64k-carnivore2` | The RAM cartridge in slot 1 | 9 game files whose loader trips over it |
| `vg8020` | `vg8020-carnivore2` | The Carnivore2, and so Nextor | 121 game files that fail in a capture with the Carnivore2 in slot 1. 6 of them also select RAM in slot 2 by fixed slot values |
| `vg8020` | `vg8020-picoverse` | The PicoVerse-like cartridge, and so its mapper and Nextor | 54 game files whose image needs more free mapper segments than Nextor leaves in 192 KB. In the VG-8020's own 64 KB, the game's RAM pages go straight to their slot, without holding segments |
| `nms8250` | `nms8250-carnivore2` | The Carnivore2, and so Nextor | 54 game files that fail in a capture with the Carnivore2 in slot 1 |
| `hbf700p-msxdos2` | `hbf700p-ram512k-msxdos2` | The RAM cartridge in slot 1 | 8 game files, Sootland among them, which is in the tests. La Abadia del Crimen crashed with the cartridge in either slot until the RAM search patch ([INTERNALS.md, The RAM search patch](INTERNALS.md#the-ram-search-patch)) |
| `vg8020` | `vg8020-sdmapper` | The SD Mapper, and so its mapper and Nextor | No game file yet |
| `xp800` | `xp800-sdmapper` | The SD Mapper, and so its mapper and Nextor | No game file yet |

## Compilations

The shipped files give each program of a compilation a game file of its own, so that
each image is named after its game and not after the tape, which holds more than one
game. The game files of one collection share a folder named after it, such as
`games/ENGESOFT/` for Engesoft's tapes and `games/SUPERMSX/` for the 27 issues of
the magazine Super MSX:

| Program | Its game file |
|---|---|
| The tape's first program | `cas` and `sha1`, without `start`. A magazine's intro belongs to it, because the intro loads that program itself |
| A later program | `cas`, `sha1` and `start` |
| A program that File-Hunter also has as a dump of its own | A game file in the collection's folder as well, as Exerion on Engesoft's MSXK-06 has beside `games/EXERION/`, because a tape's copy can differ from that dump. An earlier rule gave it none ([DESIGN.md, Decisions](DESIGN.md#decisions)) |

Each program's folder is named after its game, as `games/ENGESOFT/ATHLETIC/` is for
Athletic Land, the second program on Engesoft's MSXK-06 side A. A magazine renamed
the commercial games that it copied, and such a program's folder takes the
magazine's title, which its title screen shows: Super MSX's Attila is a copy of
Knightmare, in `games/SUPERMSX/ATTILA/`. The game file's first comment names the
game, the compilation and the program's place on it, and its `url` line links the
compilation's zip. A loader's file name, such as ATLET, seldom gives the title, so
the title comes from a list of the tape's contents. Each program has its own
machine's game files, because each program has its own loader. Athletic Land's
capture runs without the disk system only on the Sanyo PHC-28S, and Kung-Fu
Master's, before it on the tape, on the PHC-28S and on the Philips VG-8020. A
program that is not a game also has a game file, as De Demo's programs have.

## Key names

The key names are the MSX keyboard matrix's special keys, which have the same place
on every keyboard layout.

| Row | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 6 | `shift` | `ctrl` | `graph` | `caps` | `code` | `f1` | `f2` | `f3` |
| 7 | `f4` | `f5` | `esc` | `tab` | `stop` | `bs` | `select` | `return` |
| 8 | `space` | `home` | `ins` | `del` | `left` | `up` | `down` | `right` |
