# CLI Reference

This page documents `snapcas.py` for end users and contributors: every subcommand, flag, environment variable, firmware prerequisite, and exit code.

Run `./snapcas.py` from the repository root on macOS/Linux (`python3 snapcas.py` if the executable bit was stripped), or `py snapcas.py` on Windows. `snapcas.py` uses only the Python 3 standard library and works with the prebuilt `bin/SNAPCAS.COM` and `bin/SERVICE.BIN`.

## Commands

| Command | Description |
|---|---|
| `snapcas.py list [text] [--all]` | Search or list shipped and custom games. |
| `snapcas.py machines` | List all 13 shipped MSX configurations. |
| `snapcas.py snap <game> <machine> [--check [--dos <dir>]]` | Download tapes, build a `.SNP` image, and optionally check it. |
| `snapcas.py sync <machine> <destination>` | Copy `SNAPCAS.COM` and built images to an SD card or disk folder. |
| `snapcas.py try <game> <machine> [--dos <dir>]` | Launch a built image interactively in `openMSX` with video and sound. |
| `snapcas.py --version` | Print the `snapcas` version and exit. |

Pass `--help` to `snapcas.py` or any subcommand for inline usage.

## list

```sh
./snapcas.py list [text] [--all]
```

Prints shipped games and `custom/` games whose folder path or title matches `text` (case-insensitive). Omit `text` to list all games.

- Compilation entries (subfolders such as `SUPERMSX/GOLF`, or zips holding 4 or more games) are hidden by default and counted in the footer. Multi-part titles with 2–3 entries from one zip (e.g., `RUR-1`, `RUR-2`) are always listed.
- Pass `--all` to include compilation entries.

```text
$ ./snapcas.py list wall
WALL-THE  Wall, The (1987)(Erbe Software)[RUN'CAS-']
WALLBALL  Wallball (19xx)(Tynesoft)[BLOAD'CAS-',R]
2 games, and 1 in compilations, which --all lists
```

## machines

```sh
./snapcas.py machines
```

Lists the 13 shipped machine configurations and their descriptions (see [MACHINES.md](MACHINES.md#supported-machines)).

```text
$ ./snapcas.py machines
fsa1-mfrsd                  Panasonic FS-A1 (MSX2, 64 KB) with a MegaFlashROM SCC+ SD
hb75p-carnivore2            Sony HB-75P (MSX1, 64 KB) with a Carnivore2
...
xp800-sdmapper              Gradiente Expert XP-800 (MSX1, 64 KB) with an SD Mapper v1
```

## snap

```sh
./snapcas.py snap <game> <machine> [--check [--dos <dir>]]
```

Builds `images/<machine>/<game>/<GAME>.SNP` for `<game>` (case-insensitive, e.g. `gauntlet`, `supermsx/golf`, or `custom/mygame`) and `<machine>`.

| Flag | Description |
|---|---|
| `--check` | Restore the `.SNP` in `openMSX` and run the 4-point check ([Restorer & Check](internals/restorer-and-check.md#four-point-check)). |
| `--dos <dir>` | Override the DOS directory used by `--check` (default: the machine's folder in `dos/`). Requires `--check`. |

Execution flow:
1. **Download (shipped games only):** Downloads missing tape zips from File-Hunter into `downloads/`, extracts each side matching the SHA-1 in `game.txt`, and verifies cached files before reusing them. Custom games (`custom/<GAME>`) read local files only.
2. **Capture and build:** Loads the game in headless `openMSX` and packs the `.SNP` image. If a step fails and the game has no `capture` line, `snap` automatically retries each capture variant declared in the machine file and prints the `capture <variant>` line to add if one succeeds.
3. **Check (`--check`):** Boots DOS (downloading Nextor 2.1.0 into `dos/nextor/` automatically when needed), runs `SNAPCAS.COM`, and evaluates all four checks.

```text
$ ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2 --check
Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'] for phc28s-ram64k-carnivore2
download  Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'].zip from download.file-hunter.com
copy      Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-'].cas to downloads/GAUNTLET.CAS, sha1 ok
download  Gauntlet (1986)(US Gold)(Side B)[RUN'CAS-'].zip from download.file-hunter.com
copy      Gauntlet (1986)(US Gold)(Side B)[RUN'CAS-'].cas to downloads/GAUNTLEB.CAS, sha1 ok
capture   done
build     done: 14 records, 52 port writes, up to 14 free mapper segments
check     pass  the restored machine equals the snapshot
check     pass  the game does not write to the tape service in page 3
check     pass  the machine does not reboot
check     pass  the game does not stop at a BASIC error
image     images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP
```

`snap` always rebuilds the image while reusing verified tapes in `downloads/`. Download only the games you plan to play rather than bulk-scraping File-Hunter.

## sync

```sh
./snapcas.py sync <machine> <destination>
```

Copies `bin/SNAPCAS.COM` and every built image under `images/<machine>/` to the root of an SD card or disk folder (e.g. `/Volumes/MSX`).

| Source | Destination on card |
|---|---|
| `bin/SNAPCAS.COM` | `BIN/SNAPCAS.COM` |
| Shipped game | `SNAPCAS/<letter>/<GAME>.SNP` (`0-9` for leading digits) |
| Compilation game | `SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP` |
| Custom game | `SNAPCAS/CUSTOM/<GAME>.SNP` |

- **Incremental & verified:** Copies only new or changed files, writes to a temporary `.$$$` file, flushes, renames, and reads back every file to confirm an exact byte match.
- **Non-destructive:** Never removes existing `.SNP` files from the card; cleans up macOS `._*` AppleDouble files beside copied files.
- **Guardrails:** Refuses to run if `<destination>` is named `SNAPCAS` or `BIN`, or if two images collide on the same target path.
- **MSX-DOS 1:** Subdirectories are unsupported, so copy `SNAPCAS.COM` and `.SNP` files to the root directory manually instead of using `sync`.

```text
$ ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
copy      /Volumes/MSX/BIN/SNAPCAS.COM, compared ok
copy      /Volumes/MSX/SNAPCAS/G/GAUNTLET.SNP, compared ok
copied 2, unchanged 0
```

## try

```sh
./snapcas.py try <game> <machine> [--dos <dir>]
```

Starts `openMSX` with a window and sound, boots DOS with `SNAPCAS.COM` and the built image from `images/<machine>/`, runs `SNAPCAS <GAME>`, and leaves keyboard control to you. Build the image with `snap` first. Use `--dos <dir>` to override the DOS folder.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENMSX` | `openmsx` | Path to the `openMSX` binary when it is not on `PATH`. |
| `OPENMSX_HOME` | `out/cache/openmsx-home` (if present), else `~/.openMSX` | `openMSX` user directory for system ROMs and generated firmware. |
| `DOS_DIR` | `dos/` | Directory holding `nextor/`, `msxdos1/`, and `msxdos2/` ([dos/README.md](../dos/README.md)). |
| `SNAPCAS_DOWNLOADS` | `downloads/` | Cache directory for downloaded `.CAS` files. |
| `SNAPCAS_KEYS` | unset | Set to `1` to inject gameplay-start keys (`Space`, `0`, `1`, `Space`) during checks. |

## Firmware and ROMs

- **System ROMs:** Put your MSX model's BIOS ROMs in `openMSX`'s `share/systemroms` folder (`snapcas` cannot ship ROMs). If a ROM is missing, `openMSX` prints the exact filename required.
- **Generated firmware:** Run `make firmware` once before building for `fsa1-mfrsd`, `vg8020-sdmapper`, `xp800-sdmapper`, `hbf700p-ram512k-msxdos2`, or any SX-2 target. It fetches cartridge firmware and generates machine XMLs in `out/cache/openmsx-home/`, symlinking your existing system ROMs.
- **SX-2 BIOS:** Place `OCM-BIOS.DAT` from your SX-2 SD card into `openMSX`'s `systemroms` directory, or pass `make firmware SX2_BIOS=/path/to/OCM-BIOS.DAT`.
- **DOS files:** Nextor downloads automatically. For MSX-DOS 1 or MSX-DOS 2 targets (`hbf700p-ram512k-msxdos2`), supply your own DOS files in `dos/msxdos1/` or `dos/msxdos2/` ([dos/README.md](../dos/README.md)).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Bad arguments, unknown game or machine, missing input/DOS/firmware files, or download error. |
| `2` | `openMSX` failed to start, crashed, or timed out. |
| `3` | `--check` failed one or more verification points. |
| `130` | Interrupted (`Ctrl-C`). |
