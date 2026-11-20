# snapcas

Play MSX cassette games straight from a disk or SD card—no tape deck needed. `snapcas` loads a `.CAS` tape inside `openMSX` configured to match your real MSX, snapshots the running game into a single `.SNP` image, and restores it on real hardware with `SNAPCAS.COM`.

It ships definitions for **1,544 games** across **13 MSX configurations**, and works with your own `.CAS` files too. Tape files are not stored in this repository; `snapcas` downloads them on demand from [File-Hunter](https://download.file-hunter.com).

## How it works

Cassette loaders frequently break on modern MSX setups because cartridge slot order, RAM location, or disk interfaces differ from a stock 1980s machine. `snapcas` solves this at build time:

- **Hardware-accurate capture:** Runs each loader in `openMSX` with your exact MSX model, RAM layout, and cartridges, applying per-game and per-machine patches when needed.
- **Built-in virtual tape:** Packs any remaining tape data (including Side B) into the `.SNP` file so multi-load games keep loading levels from RAM.
- **Keyboard tape control:** Rewind, flip sides, or step through loads manually using MSX keys.
- **Automated check:** Restores every image in `openMSX` and verifies state, memory safety, stability, and BASIC output before writing the final `.SNP`.

## Requirements

- **MSX hardware:** An MSX1, MSX2, or MSX2+ with a memory mapper and a disk/SD interface running Nextor, MSX-DOS 2, or MSX-DOS 1.
- **Host computer:** macOS, Linux, or Windows with Python 3 (standard library only) and [openMSX](https://openmsx.org).
- **System ROMs:** Your MSX model's BIOS ROMs installed in `openMSX`.

## Quickstart with an AI agent

Using an AI coding agent? Clone the repository and prompt it to run the matching workflow in [AGENTS.md](AGENTS.md):

```sh
git clone https://github.com/xesco/snapcas.git
```

- **Play a shipped game:**
  ```text
  I want to play Gauntlet on my MSX. Follow "Guide a user" in AGENTS.md.
  ```
- **Play your own `.CAS` file:**
  ```text
  I want to play ~/Downloads/mygame.cas on my MSX. Follow "Guide a user" in AGENTS.md.
  ```
- **Add a new MSX configuration** (slot order, boot menus, and capture variants can be tricky—the agent inspects `openMSX`'s machine XML, creates the machine file and variants, and verifies them):
  ```text
  Add my MSX: Toshiba HX-10 (64 KB) with a Carnivore2 in slot 1. Follow "Add a machine" in AGENTS.md.
  ```
- **Fix a game that fails `--check` or fails on your real MSX:**
  ```text
  Gauntlet fails --check on hb75p-carnivore2. Follow "Fix a game that fails" in AGENTS.md.
  ```
  ```text
  Gauntlet passed --check, but freezes on my real MSX after pressing Space. Follow "Fix a game that fails on the MSX" in AGENTS.md.
  ```

## Quickstart from the command line

This walkthrough builds *Gauntlet* for a Sanyo PHC-28S (`phc28s-ram64k-carnivore2`) and launches it on hardware. On Windows, use `py snapcas.py` instead of `./snapcas.py`.

1. **Install `snapcas`** — clone the repo or download a release zip (which includes prebuilt `bin/SNAPCAS.COM` and `bin/SERVICE.BIN`) from the [latest release](https://github.com/xesco/snapcas/releases/latest):

   ```sh
   git clone https://github.com/xesco/snapcas.git
   cd snapcas
   ```

2. **Find your game and machine:**

   ```sh
   ./snapcas.py list gauntlet
   ./snapcas.py machines
   ```

   If your exact setup is missing, see [Adding a machine](docs/MACHINES.md#adding-a-machine). Some machines also need a one-time `make firmware` step ([Firmware and ROMs](docs/CLI.md#firmware-and-roms)).

3. **Build and check the image:**

   ```sh
   ./snapcas.py snap gauntlet phc28s-ram64k-carnivore2 --check
   ```

   `snap` fetches missing tapes from File-Hunter into `downloads/`, captures and builds `images/phc28s-ram64k-carnivore2/GAUNTLET/GAUNTLET.SNP`, and runs a 4-point check in `openMSX`. All four `check` lines should print `pass`.

   > [!NOTE]
   > File-Hunter is community-run. Download only the games you intend to play, one at a time.

4. **Sync to your SD card:**

   ```sh
   ./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
   ```

   `sync` copies `SNAPCAS.COM` into `BIN/` and organizes images under `SNAPCAS/<letter>/` (`0-9` for leading digits), verifying every copy byte-for-byte.

5. **Run on your MSX:**

   ```text
   CD \SNAPCAS\G
   \BIN\SNAPCAS GAUNTLET
   ```

   For multi-load games, see [Tape keys](docs/PLAYING.md#tape-keys). If anything misbehaves on real hardware, see [Troubleshooting](docs/PLAYING.md#troubleshooting).

## Using your own CAS files

Drop your tape file(s) and a one-line `game.txt` into `custom/<GAME>/` ([custom/README.md](custom/README.md)), then build and sync as usual:

```sh
./snapcas.py snap custom/MYGAME phc28s-ram64k-carnivore2 --check
./snapcas.py sync phc28s-ram64k-carnivore2 /Volumes/MSX
```

Custom games sync to `\SNAPCAS\CUSTOM`:

```text
CD \SNAPCAS\CUSTOM
\BIN\SNAPCAS MYGAME
```

## Documentation

### Users
- [Playing on the MSX](docs/PLAYING.md) — launching images, tape keys, `/M` manual mode, and hardware troubleshooting
- [CLI Reference](docs/CLI.md) — `snapcas.py` commands, flags, environment variables, firmware setup, and exit codes
- [Supported Machines](docs/MACHINES.md) — all 13 shipped MSX setups, SX-2 configuration, and requesting or adding a machine
- Folders: [custom/](custom/README.md), [dos/](dos/README.md), [downloads/](downloads/README.md), [images/](images/README.md)

### Contributors & AI Agents
- [AGENTS.md](AGENTS.md) — operational runbook for guiding users, adding machines/games, and debugging failures
- [Machine & Game Files](docs/FILES.md) — schema reference for `machines/*.txt` and `games/<GAME>/*.txt`
- [Build & Test](docs/BUILD.md) — developer setup, `make` targets, test tiers, and known-failure lists

### Architecture & Internals
- [Design Overview](docs/DESIGN.md) — architecture, pipeline overview, design decisions, and limits
- [Binary & File Formats](docs/FORMATS.md) — `.SNP` image layout, tail, port writes, `SERVICE.BIN`, and CAS/TSX
- [Hardware & Game Notes](docs/NOTES.md) — MSX quirks and game case studies behind the rules
- Internals: [Capture](docs/internals/capture.md) · [Automatic Patches](docs/internals/patches.md) · [Tape Service & Resident Calls](docs/internals/service-and-resident.md) · [Restorer & Check](docs/internals/restorer-and-check.md)

## License

Released under the [MIT License](LICENSE). The license covers this project's code only; games, system ROMs, and DOS files are not included.
