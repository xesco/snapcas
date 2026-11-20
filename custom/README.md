# Custom Games

Store your own `.CAS` games here—titles not shipped in `games/` or personal dumps. Git ignores everything in this folder except this file.

Create one uppercase folder per game (up to 8 letters or digits) containing `game.txt` and your tape file(s):

```text
custom/MYGAME/game.txt
custom/MYGAME/MYGAME.CAS
```

A minimal `game.txt` names Side 1 (plus `side2` for two-sided tapes; see [FILES.md](../docs/FILES.md#game-file)):

```text
cas MYGAME.CAS
```

Pass `custom/<GAME>` to `snapcas.py`:

```sh
./snapcas.py list custom
./snapcas.py snap custom/MYGAME phc28s-ram64k-carnivore2 --check
./snapcas.py try custom/MYGAME phc28s-ram64k-carnivore2
```

`snap` reads local tapes directly without downloading and writes images to `images/<machine>/custom/MYGAME/`. `sync` copies them to `SNAPCAS/CUSTOM/` on your card. See [AGENTS.md](../AGENTS.md) for the full custom-game workflow.
