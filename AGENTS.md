# Agents

This runbook is for AI coding agents working on `snapcas`. It defines hard rules, key paths, and step-by-step workflows for guiding users, building images, adding machines or games, and debugging failures in `openMSX` or on real MSX hardware. For schemas and internals, follow the linked docs rather than guessing.

## Hard rules

| Rule | Reason |
|---|---|
| Never commit, push, or open a PR unless the user asks | User reviews every change first |
| Never start a recommended next step until the user approves it | User controls what runs next |
| Builds must print zero warnings (`make all`) | Warnings mask real regressions |
| Never run `./snapcas.py try` yourself; ask the user to run it | Opens a visible `openMSX` window with audio; other tools run headless and muted |
| Never commit system ROMs or MSX-DOS; only add tapes to `tests/tapes/` with user approval | Redistribution limits and repo size |
| Fix individual games in game files, not in code | Only add code/patchers in `tools/patches/` when one pattern repeats across many tapes |
| Put a blank line and explanatory comment above every line added to a game file | Matches shipped style and records why each fix exists |

## Key debugging paths

For the full repository folder layout, see [docs/BUILD.md](docs/BUILD.md#repository-layout). These are the files you read most often when debugging:

| Path | Purpose |
|---|---|
| `out/games/<machine>.txt` | Results of `make games` (one line per game) |
| `out/work/<machine>/<GAME>/snap/log.txt` | Capture log (typed commands, `TAPION`, motor, resets, stop screen, unpatched slot writes) |
| `out/work/<machine>/<GAME>/snap/error.txt` | Capture failure message |
| `out/work/<machine>/<GAME>/scan.txt` | Build scan findings in `patch` format |
| `out/work/<machine>/<GAME>/check/report.txt` | 4-point check report and failure details |
| `tests/openmsx-failures.txt` | Games failing in plain `openMSX` (accepted by `make games`) |
| `tests/snapcas-failures.txt` | Known `snapcas` failures awaiting fixes (accepted by `make games`) |

## Guide a user

When a user asks to play a game (by name or local `.CAS`), execute the steps for them and ask only for information or physical actions they alone can provide—one question at a time. Explain each step in one sentence as you go.

1. **Gather missing info:** game name or `.CAS` path, plus MSX model and what is in every cartridge slot.
2. **Verify tools:** confirm Python 3 and `openMSX` run; if missing, give install instructions and wait.
3. **Match machine:** run `./snapcas.py machines`. If none matches, run [Add a machine](#add-a-machine) steps 1–5.
4. **Build and check:** run [Make a game's image](#make-a-games-image) steps 1 & 3 (or [Add a game](#add-a-game) steps 1–4 for a local `.CAS`). If unfixable, explain why and stop; never edit `tests/*-failures.txt` for a user's custom game.
5. **Sync to card:** ask the user to insert their MSX card and provide its path, run `./snapcas.py sync`, and give the two MSX commands (`CD \SNAPCAS\<letter>` or `\SNAPCAS\CUSTOM`, then `\BIN\SNAPCAS <GAME>`).
6. **Verify on hardware:** ask the user to play and report what they see:
   - `SNAPCAS` message at DOS prompt → usually wrong machine/slot match; confirm slots and return to step 3.
   - Stops during level load → give [Tape keys](docs/PLAYING.md#tape-keys) or `/M` mode.
   - Hangs, glitches, or reboots → follow [Fix a game that fails on the MSX](#fix-a-game-that-fails-on-the-msx).

## Make a game's image

1. **Find the game:** `./snapcas.py list <text>` (case-insensitive). Disambiguate if multiple match; if missing and the user has a `.CAS`, follow [Add a game](#add-a-game).
2. **Find the machine:** `./snapcas.py machines`. Every cartridge difference is a different machine; ask if model or slots are unspecified.
3. **Build and check:**
   ```sh
   ./snapcas.py snap <GAME> <machine> --check
   ```
   All 4 `check` lines must say `pass`. Handle failures by output:

   | Output | Action |
   |---|---|
   | Missing ROMs / firmware / DOS files / boot failure | Use the table in [Add a machine step 5](#5-check-three-games). Ask the user for ROMs or MSX-DOS files. |
   | Download failed | Inform the user, ask for their `.CAS`, and add it under `custom/`. |
   | `it passes, so the machine's game file needs: capture <variant>` | Add `capture <variant>` to `games/<GAME>/<machine>.txt` ([Write the fix](#4-write-the-fix)). |
   | `needs N free mapper segments, and DOS has M` | Unfixable hardware limit—report both numbers to the user. |
   | Any other capture/build error or `check fail` | Follow [Fix a game that fails](#fix-a-game-that-fails). |

4. **Sync (only when asked):** `./snapcas.py sync <machine> <destination>` and give the MSX launch commands ([docs/PLAYING.md](docs/PLAYING.md#running-an-image)).
5. **Hardware test:** remind the user that `--check` only runs 60 seconds in `openMSX`, and ask them to test on real hardware.

## Add a machine

Full schema: [docs/FILES.md](docs/FILES.md#machine-file). Example: Sony HB-75P with Carnivore2 in slot 1 (`hb75p-carnivore2`).

### 1. Name the machine
Use lowercase `<model>-<slot1>-<slot2>...` (`empty` for empty slots before a cartridge; short names: `carnivore2`, `ram64k`, `ram512k`, `mfrsd`, `sunriseide`, `sdmapper`, `msxdos2`). Verify uniqueness with `./snapcas.py machines`.

### 2. Inspect model and slots in `openMSX`
Check `share/machines/<Model>.xml` (`/opt/homebrew/opt/openmsx/openMSX.app/Contents/Resources/share/machines/` on macOS Homebrew; `/usr/share/openmsx/machines/` on Linux):
```sh
grep -n 'primary\|<RAM' .../share/machines/Sony_HB-75P.xml
```
`external="true"` marks cartridge slots; `-ext` fills them in order. Note which slot holds internal RAM (in BASIC without cartridges, `PRINT HEX$(INP(&HA8))` confirms slot layout).

### 3. Write `machines/<name>.txt`
Copy a similar machine file and update the model. The first comment sentence must follow `<Model> (<MSX gen>, <RAM>) with <cartridges>` (shown by `./snapcas.py machines`).

| Disk cartridge | Required lines | Reference |
|---|---|---|
| Carnivore2 | `disk hda`, `boot "DefConfig" space` | `vg8020-carnivore2` |
| MegaFlashROM SCC+ SD (Nextor-only) | `disk hda`, `firmware extensions/MegaFlashROM_SCC+_SD_Nextor.xml` | `fsa1-mfrsd` |
| MegaFlashROM SCC+ SD (stock) | `disk hda`, `dos "A:\>" B` | `hb75p-mfrsd` |
| SD Mapper v1 | `disk hda`, `firmware systemroms/snapcas/SDMAPPER.ROM` | `vg8020-sdmapper` |
| Sunrise IDE | `disk hda` | `nms8245-ram512k-sunriseide` |
| Built-in floppy | `disk diska` (or `disk diska 360`) | `hbf700p-ram512k-msxdos2` |

Add `dosfiles`, `width`, `hold`, `press`, `resident`, or `parent` as needed ([docs/FILES.md](docs/FILES.md#machine-file)).

### 4. Add capture variant(s)
If the disk cartridge sits in a lower slot than internal RAM, add a variant in `machines/capture/` without that cartridge (reuse an existing variant like `vg8020` if identical) and reference it with `variant`. If slot 0 is expanded and holds only the main ROM in subslot 0, add a `<model>-noexp0-...` variant (see `Sony_HB-F700P_noexp0.xml` in `Makefile`). Variants without a disk system may boot into built-in firmware menus and need `hold` or `press` lines.

### 5. Check three games
Test a single-load game, a multi-load game, and a variant-captured game (adding the variant's `capture` line for the third):
```sh
./snapcas.py snap CALDERO <machine> --check
./snapcas.py snap GAUNTLET <machine> --check
./snapcas.py snap ALIEN-SY <machine> --check
```

| Error | Fix |
|---|---|
| `Couldn't find ROM file for ...` | Ask the user for the missing system ROMs. |
| `needs ... make firmware makes it` | Run `make firmware`. |
| `boots msxdos1: put its files in dos/msxdos1/` | Ask the user for MSX-DOS files ([dos/README.md](dos/README.md)). |
| `capture: BASIC's Ok did not appear within 120 seconds` | Fix `boot`/`hold`/`press` lines (compare with a working machine using the same disk cartridge). |
| `the tail's jump did not run` (BASIC on screen) | Fix `disk`, `dos`, or `dosfiles`. |
| `check: the boot text '...' did not appear` | Fix `boot` text/keys. |

### 6. Update docs and run tests
Add the machine to [docs/MACHINES.md](docs/MACHINES.md#supported-machines) and update the machine count in [README.md](README.md). `tests/test_machines.py` tests every file in `machines/` automatically—run `make test`.

### 7. Run the full collection
```sh
make games MACHINE=<machine>
```
Runs all 1,544 games (~30 min), auto-retrying capture variants and writing `capture` lines into `<machine>.txt` (`FIX=0` disables retry). Do not edit `bin/` or `tools/` mid-run (hash changes trigger full rebuilds). Fix remaining failures, then update the working-games count in [docs/MACHINES.md](docs/MACHINES.md#supported-machines).

## Add a game

Custom games live in `custom/<GAME>/` (git-ignored; [custom/README.md](custom/README.md)).

1. Create `custom/<GAME>/` (uppercase, up to 8 alphanumeric chars) and copy the user's `.CAS` file(s) there without moving their originals.
2. Write `custom/<GAME>/game.txt` with a title comment, `cas <SIDE1>.CAS`, and optional `side2 <SIDE2>.CAS`.
3. Build and check: `./snapcas.py snap custom/<GAME> <machine> --check`.
4. Fix any failures in `custom/<GAME>/game.txt` or `custom/<GAME>/<machine>.txt` (add `sha1` via `shasum custom/<GAME>/*.CAS` if using `patch`). Never edit `tests/*-failures.txt` for custom games.
5. **Share (only if user asks):** move folder to `games/`, add `sha1` and `url`, move tapes to `downloads/`, run `make games` on machines with `out/games/` results, and increment the game count in [README.md](README.md).

## Fix a game that fails

### 1. Reproduce
```sh
./snapcas.py snap <GAME> <machine> --check
```
For faster iteration when only page patches or build/check settings change (snapshot already exists):
```sh
OPENMSX_HOME=$PWD/out/cache/openmsx-home python3 tools/pipeline.py <GAME> <machine> --dos dos/nextor --skip-capture
```
Add `SNAPCAS_KEYS=1` to exercise gameplay-start keys (`Space`, `0`, `1`, `Space`). If `snap` reports a capture variant passes, add `capture <variant>` to `<machine>.txt` and stop.

### 2. Diagnose from logs
Read `snap/log.txt`, `snap/error.txt`, `scan.txt`, and `check/report.txt`, comparing with a passing machine from `out/games/<machine>.txt`:

| Message | Cause | Fix |
|---|---|---|
| `CPU is halted with no interrupt` | Loader selected an empty slot | Capture variant or slot patch |
| `step 5 restarted more than 20 times` | Load waits for an untried key | `continue <key>` or `snapshot at <sec>` |
| `load ran for more than 3600 seconds` | Motor never stays off | `snapshot at <sec>` after load ends |
| `non-standard block` / `not a binary file` | Non-standard first block | `load 'RUN"CAS:"'` (or tape's command) |
| `tape needs N segments, more than M` | Tape exceeds service limit (`16` in `t0`, `64` with code segment) | `service at <addr>` (if limit 16); else `tests/snapcas-failures.txt` |
| `26 bytes below SP ...` | Failed load (stack in ROM) or low SP | Variant/slot patch, or later `snapshot at <sec>` |
| `stack reaches FFFFh` | Stack hits subslot register in expanded slot | Unexpanded variant, or patch `LD SP,0000h` → `LD SP,0FFFEh` |
| `page 3 is not a RAM page` | Loader switched page 3 away from RAM (`cuts off its code`) | Capture variant or slot patch |
| `no room for tape service` / `T0 in page 0 of DOS's mapper` | Page 3 full and page 0 is in DOS's mapper | Variant outside DOS's mapper, `service at <xxE1>`, or split `service at <xxE1> <code>` (entries may use `FFE1h` if game never calls BIOS) |
| `bytes at ... are not the patch's old bytes` | Patch targets a different dump | Re-derive patch and `sha1` for this dump |
| `point 1: fail` (`vdp14 is 07`, `vramptr 1C000`) | VRAM pointer = 0 in MSX1 mode | Later `snapshot at <sec>` |
| `point 1: fail` (other diff / restorer hang) | Restorer bug or segment shortage | Follow restorer message, or log in `tests/snapcas-failures.txt` |
| `point 2: fail` (writes tape service / `rescode` / `resstack`) | Game overwrites service or resident block in page 3 | `service at <xxE1> [<code>]`, `service t0`, `rescode`, `resstack <addr\|no>`, or `rescall no` |
| `point 3: fail` (reboot / `RST 38h` / SP wrap) | Crash after restore (slot switch, Spectrum `OUT (0FEh)`, MSX1 BIOS call, etc.) | Capture variant or targeted `patch` |
| `point 4: fail` (BASIC error) | BASIC program error | Patch BASIC text (note: `SNAPCAS_KEYS=1` typing `0`/`1` into pure BASIC prompts is a false positive) |

### 3. Patch the code
The tools already auto-patch 11 common loader/slot patterns ([docs/internals/patches.md](docs/internals/patches.md#patcher-catalog)). For remaining unpatched writes (logged as `for a patch line` in `snap/log.txt`):
1. Check `scan.txt` first (unread-block findings aren't auto-patched; fix block checksums if the loader verifies them).
2. Otherwise locate `D3 A8` (`OUT (0A8h),A`), `CD 3B 01` (`WSLREG`), `D3 FE` (Spectrum beeper on mapper port), or `DB A8` in the tape or snapshot RAM.
3. Compute slot register value `A8h` = `page3*64 + page2*16 + page1*4 + page0` (e.g. `FCh` = ROM in 0, RAM in 3; `A8h` = ROM in 0, RAM in 2; `14h` = PHC-28S internal page 3 in 0, RAM cart in 1). On expanded slot 0 (e.g. `sx2-extramapper-mcp`), write slot 0's subslot register at `FFFFh` (`54h` = BIOS p0 + RAM p1–3, `55h` = RAM all pages, `50h` = BASIC) and update `SLTTBL` (`FCC5h`) if the game calls `ENASLT`. See [docs/NOTES.md](docs/NOTES.md#loaders-and-slots).

### 4. Write the fix
Put universal fixes in `games/<GAME>/game.txt` and machine-specific fixes in `games/<GAME>/<machine>.txt`, with a blank line and explanatory comment above every directive.

### 5. Check whether `openMSX` itself fails
```sh
python3 -I tools/plain.py <GAME> <machine>
```
If plain `openMSX` fails identically (confirm against a passing machine's `snap/log.txt` if it prints `a graphics screen`), add an entry to `tests/openmsx-failures.txt`. Otherwise add an entry to `tests/snapcas-failures.txt` with the root cause.

### 6. Verify
Re-run `./snapcas.py snap <GAME> <machine> --check`, then `make games MACHINE=<machine>` (and on every machine in `out/games/` if `game.txt` changed), then `make test`.

## Fix a game that fails on the MSX

When all 4 check points pass in `openMSX` but the game fails on real hardware, ask the user for a photo/description of the screen, what happened before, and what they pressed (never run `./snapcas.py try` yourself):

| User sees | Cause | Fix |
|---|---|---|
| `not found` / `not a snapcas image` / `cut short` | Bad path or corrupt copy | Re-run `./snapcas.py sync` and verify `CD` folder |
| `made for another version of SNAPCAS.COM` | Stale `.SNP` or `SNAPCAS.COM` | Rebuild with `snap`, then `sync` |
| `made for another machine` / `slot ... is not RAM` / `slot 0 is not expanded` | Wrong machine or slot layout | Re-confirm model & slots, or [Add a machine](#add-a-machine) |
| `not in one memory mapper` / `too few free mapper segments` / `needs N ... DOS has M` | Hardware mapper limit | Unfixable—report numbers to user |
| `page 0 is in another subslot` / `rom keep needs` | Missing `sub0` or incompatible `rom keep` | Capture variant outside DOS's mapper, or drop `rom keep` |
| `service t0 needs` / `T0 cannot take` | `service t0` incompatible with machine | Capture variant outside DOS's mapper, or remove `service t0` |
| Reboots to boot screen or DOS | Post-restore crash missed by 60 s check | Capture variant or slot patch |
| Freezes, no keys respond | Disk-interface conflict | Try capture variant without disk system |
| Waits forever on music | `PLAY` at snapshot doesn't resume (PHC-28S) | `snapshot at <sec>` after music ends |
| Stops on tape load / yellow screen | Needs tape keys or overwrites tape entries | Give [Tape keys](docs/PLAYING.md#tape-keys); else `service t0` or `service at` |
| Corrupted pixels during tape load | Tape service faster than VDP accepts | No known fix (`tests/snapcas-failures.txt` if shipped) |
| Joystick/keys dead or erratic | Port state mismatch | `patch` lines (see `games/NAVY-MOV/game.txt`) |
| Silent menu or flashing title | Same in plain `openMSX` | Verify with `tools/plain.py`; not a bug |

After each fix, verify with `snap --check`, ask the user to `sync` and test past the failure point, and iterate if needed.
