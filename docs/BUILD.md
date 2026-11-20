# Build & Test

This guide is for contributors modifying `snapcas` itself (`src/`, `tools/`, `tests/`, or `Makefile`). End users building or playing games do not need to build anything—prebuilt `bin/SNAPCAS.COM` and `bin/SERVICE.BIN` are already committed ([README.md](../README.md)).

## Prerequisites

- **Python 3** (standard library only)
- **`openMSX` 22.0+** on `PATH` (or via `OPENMSX=`), with system ROMs for the test machines and `msxdos2` cartridge
- **Assembler:** `sjasmplus` 1.24.0 — downloaded and built automatically into `out/cache/tools/` by `make` (verified by SHA-256)
- **DOS files:** Nextor 2.1.0 downloads automatically into `dos/nextor/`. Supply your own `dos/msxdos1/` and `dos/msxdos2/` files ([dos/README.md](../dos/README.md)) to run MSX-DOS 1 and MSX-DOS 2 tests (otherwise those tests are skipped). Override the folder with `DOS_DIR=<dir>`.

## Repository layout

| Folder | Contents |
|---|---|
| `src/` | Z80 assembly for `SNAPCAS.COM` and `SERVICE.BIN` (`sjasmplus`) |
| `bin/` | Prebuilt `SNAPCAS.COM` and `SERVICE.BIN` (tracked in git) |
| `tools/` | Python pipeline, automatic patchers (`tools/patches/`), and `openMSX` Tcl scripts (`tools/tcl/`) |
| `machines/` | Shipped machine files, capture variants (`machines/capture/`), and test-only machines (`machines/test/`) |
| `games/` | Shipped game files (1,544 titles; no tape files) |
| `tests/` | Unit and emulator tests, test runner (`tests/run.py`), small test tapes (`tests/tapes/`), and failure lists |
| `custom/`, `dos/`, `downloads/`, `images/`, `out/` | Local working directories ignored by git |

## Make targets

| Command | Description |
|---|---|
| `make all` | Build `bin/SNAPCAS.COM` and `bin/SERVICE.BIN` (builds `sjasmplus` first if needed). Must produce zero warnings. |
| `make firmware` | Download cartridge firmware (`SDMAPPER.ROM`, Nextor-only MegaFlashROM flash) and generate `openMSX` machine XMLs (`hbf700p-noexp0`, SX-2 models) in `out/cache/openmsx-home/`. Pass `SX2_BIOS=/path/to/OCM-BIOS.DAT` if `OCM-BIOS.DAT` is not in your system ROMs. |
| `make unit` | Run the pure Python test tier (~3 seconds; no `openMSX`, no tapes). |
| `make test` | Run both pure and emulator test tiers (~2–3 minutes; headless `openMSX` + `tests/tapes/`). |
| `make games` | Build and check all 1,544 games in `games/` for one machine using cached tapes in `downloads/` (never downloads). Writes results to `out/games/<machine>.txt` and passing `.SNP` files to `images/<machine>/`. |
| `make clean` | Remove `out/test/` and intermediate build artifacts while keeping `bin/` and caches. |

### `make games` options

| Variable | Default | Purpose |
|---|---|---|
| `MACHINE=` | `phc28s-ram64k-carnivore2` | Target machine name from `./snapcas.py machines`. |
| `DOS=` | Machine's `dosfiles` folder (`nextor`, `msxdos1`, or `msxdos2`) | Override the DOS system folder for checks. |
| `FIX=0` | Retry enabled | Disable automatic capture-variant retry and `capture` line generation on failures. |
| `FULL=1` | Incremental | Ignore cached hashes and rebuild every game from scratch. |
| `SNAPCAS_KEYS=1` | Unset | Inject gameplay-start keys (`Space`, `0`, `1`, `Space`) during the 60-second check. |

`make games` caches capture (`snap/.hash`) and build/check hashes separately so code or check-only changes reuse valid snapshots when possible ([Restorer & Check](internals/restorer-and-check.md#batch-runner)). `Ctrl-C` stops cleanly and preserves finished results.

## Test tiers

`tests/run.py` runs test classes across 8 parallel worker processes:

- **Pure tier (`make unit`):** No `openMSX`, no tapes (`OPENMSX` is cleared so any accidental emulator call fails). Covers game/machine parsing, tape readers, snapshots, image building, `docs/FORMATS.md` layout checks, automatic patcher logic, CLI argument handling, and card sync.
- **Emulator tier (`make test`):** Runs headless `openMSX` against `tests/tapes/` and synthetic images. Covers `SNAPCAS.COM` restoration, tape service contracts, manual tape mode, 4-point check, automatic slot/loader patchers, and one single-load game (`CALDERO`) on every shipped machine.

Run a filtered subset directly:

```sh
python3 -I tests/run.py --pure test_build
python3 -I tests/run.py --workers 4 restore
python3 -I tests/run.py --list
```

## Test machines

In addition to the 13 shipped machines in `machines/` (each tested automatically by `tests/test_machines.py`), `machines/test/` holds 6 test-only configurations:

| Machine file | DOS | Purpose |
|---|---|---|
| `test/nms8250-dos1` | `msxdos1` | MSX-DOS 1 restore coverage (no shipped machine uses MSX-DOS 1). |
| `test/nms8250-512k` | `msxdos2` | 512 KB single mapper (needed for Moonwalker's 236 KB tape). |
| `test/nms8250-128k` | `msxdos2` | 128 KB single mapper (tests out-of-segments error path). |
| `test/nms8250-4m-dos1` | `msxdos1` | 4 MB mapper under MSX-DOS 1 (segment 255 free). |
| `test/nms8250-4m-ram4mb-dos1` | `msxdos1` | Dual 4 MB mappers (tests segment 255 in a secondary mapper). |
| `test/hc90a-msxdos2` | `msxdos2` | Main ROM and mapper sharing slot 0 (tests `rom keep` rejection). |

## Known-failure lists

`make games` fails only on unexpected failures—games not listed in either file:

- `tests/openmsx-failures.txt` — games that fail identically in plain `openMSX` without `snapcas` (verified with `python3 -I tools/plain.py <GAME> <machine>`).
- `tests/snapcas-failures.txt` — known `snapcas` limitations or bugs that still need a fix.

## Releases and versioning

`src/version.inc` defines `MAJOR.MINOR`, year, and author:
- Bump `MAJOR` when `IMAGE_FORMAT` in `src/service.inc` changes (older `SNAPCAS.COM` refuses newer images).
- Bump `MINOR` for all other releases.

To release: update `src/version.inc`, run `make all`, commit both, and push git tag `v<MAJOR>.<MINOR>`. `.github/workflows/release.yml` verifies the tag matches `src/version.inc` and publishes both the repository zip and standalone `SNAPCAS.COM`.
