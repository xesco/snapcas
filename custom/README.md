# Your own games

This folder holds your own games: games that `snapcas` does not ship, or your own
dumps of a tape. Git ignores everything here except this file.

Each game has a folder of its own, with its game file and its tape files, CAS or
TSX:

```
custom/MYGAME/game.txt
custom/MYGAME/MYGAME.CAS
```

The game file needs one line, which names side 1's tape. The other lines are those
of a shipped game's file ([FILES.md, Game file](../docs/FILES.md#game-file)):

```
cas MYGAME.CAS
```

A custom game's name is `custom/` and its folder's name. The commands take it as
they take a shipped game's name:

```
./snapcas.py list custom
./snapcas.py snap custom/MYGAME phc28s-ram64k-carnivore2
./snapcas.py try custom/MYGAME phc28s-ram64k-carnivore2
```

`snap` reads the tapes from the game's folder and never downloads them. The image
goes to `images/<machine>/custom/MYGAME/`. To share a game, move its folder into
`games/`, add its `sha1` and `url` lines, and move its tapes into `downloads/`.
