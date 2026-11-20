# Machine & Game Files

This reference defines the text file formats for machines (`machines/*.txt`) and games (`games/<GAME>/*.txt` and `custom/<GAME>/*.txt`), and summarizes the shipped configurations. For how the tools process these files, see [DESIGN.md](DESIGN.md).

## Machine file

A machine file describes one MSX model and its cartridges in slot order. Lines starting with `#` are comments; the first sentence of the opening comment is displayed by `./snapcas.py machines`.

```text
# Sanyo PHC-28S (MSX1, 16 KB) with a 64 KB RAM cartridge and a Carnivore2.
# The RAM cartridge is in slot 1 and the Carnivore2 is in slot 2, under Nextor.
openmsx -machine Sanyo_PHC-28S -ext ram64k -ext Carnivore2
disk hda
boot "DefConfig" space
variant phc28s-ram64k
variant phc28s-empty-carnivore2
```

| Directive | Required | Description |
|---|---|---|
| `openmsx <args...>` | Yes (1) | Arguments passed to `openMSX`. Each `-ext` fills the next free external slot, so `-ext` order must match your real cartridge slots. |
| `disk <cmd> [360\|720]` | Yes (1) | `openMSX` disk command (`hda`, `diska`, etc.) and optional floppy size in KB (default `720`; `360` for single-sided drives). |
| `boot "<text>" <key>` | 0+ | Wait for `<text>` on the text screen during boot and press `<key>` (retried every second up to 10 times while text remains). Matched in order. |
| `hold <key> <sec>` | 0+ | Hold `<key>` from power-on for `<sec>` emulated seconds to bypass graphics-mode firmware menus (e.g. `hold del 6` on FS-A1). |
| `press <key> <sec>` | 0+ | Press `<key>` for 0.1 s at `<sec>` seconds after power-on for graphics menus that need navigation (e.g. `hb75p` Personal Data Bank). |
| `dos "<prompt>" <drive>` | 0–1 | For cartridges that boot DOS from their own ROM disk (e.g. stock MegaFlashROM). Capture types `BASIC` at `<prompt>`; check switches to `<drive>:` and runs `AUTOEXEC`. |
| `dosfiles <msxdos1\|msxdos2>` | 0–1 | Subfolder under `dos/` booted by `--check`, `try`, `make games`, and tests. Defaults to `nextor`. |
| `width <1..80>` | 0–1 | Run `WIDTH <n>` in BASIC before loading (e.g. `width 37` on SX-2, whose sub-ROM boots into 80 columns). |
| `firmware <path>` | 0+ | Relative path under `openMSX`'s `share/` required by this machine and created by `make firmware` (e.g. `systemroms/snapcas/SDMAPPER.ROM`). |
| `variant <name>` | 0+ | Capture variant under `machines/capture/` tried in order when a capture/build/check fails. |
| `resident <slot> <addr> <bytes...>` | 0–1 | Resident program that must keep running under games (e.g. SX2RES: `resident 3-0 4040 F5 DB FD F5 3E 00 F1 F1 C9`). Requires at least 5 bytes; the first 2 are checked before every call ([Service & Resident](internals/service-and-resident.md#resident-program-calls)). |
| `parent <machine>` | 0–1 | Inherit machine-specific game files from `<machine>` when no `<this-machine>.txt` exists (used by `sx2-noexp0` → `parent sx2`). |

### Naming convention

Machine names are lowercase `<model>-<slot1>-<slot2>...`, using `empty` for an empty slot before a cartridge and short cartridge names (`carnivore2`, `ram64k`, `ram512k`, `mfrsd`, `sunriseide`, `sdmapper`, `msxdos2`).

Machine files live in three folders:
- `machines/` — shipped user machines (`<machine>` argument to `snapcas.py`).
- `machines/capture/` — capture variants referenced by `variant` / `capture`.
- `machines/test/` — test-only setups (`test/<name>`).

## Capture variants

A capture variant in `machines/capture/` represents the same MSX model with fewer cartridges (or unexpanded slot 0, named `<model>-noexp0-...`). Games are captured on the variant when a cartridge's RAM or expanded slot 0 breaks the loader, then built and checked for the full target machine. Multiple machines sharing the same stripped setup share one variant file (e.g. `vg8020` is shared by `vg8020-carnivore2` and `vg8020-sdmapper`).

## Game file

Each game lives in `games/<GAME>/` (or `custom/<GAME>/`) with a `game.txt` that applies to all machines. Lines are `<key> <value>`; `#` starts a comment and blank lines are ignored. Times are decimal emulated seconds after the load command; addresses and bytes are hexadecimal.

```text
# Gauntlet (1986)(US Gold)(Side A)[RUN'CAS-']
cas GAUNTLET.CAS
side2 GAUNTLEB.CAS
sha1 d9aaa5495dd7d507f1cbdd600ad1c216152ad0a5 d48793329d94266ada63d33c4a2897a85d6400b3
```

In shipped files, every directive after `cas`/`tsx`/`side2`/`sha1`/`url`/`name` has a blank line and an explanatory comment above it.

| Key | Value | Default | Typical file |
|---|---|---|---|
| `cas` / `tsx` | Side 1 tape filename (`.CAS` or `.TSX`). | Required | `game.txt` |
| `side2` | Side 2 tape filename (same format as Side 1). | None | `game.txt` |
| `sha1` | SHA-1 of Side 1, then optional SHA-1 of Side 2. Required whenever `patch` or `url` is used. | None | `game.txt` |
| `url` | HTTPS URL(s) to File-Hunter zip(s) for Side 1 (and Side 2). Encode `'` as `%27`. | None | `game.txt` |
| `name` | Image stem (`<GAME>`, up to 8 alphanumeric chars). | Uppercase folder name (alphanumeric, max 8) | `game.txt` |
| `load` | Quoted load command for non-standard first blocks (e.g. `load 'RUN"CAS:"'`). | Auto-detected from first block | `game.txt` |
| `start` | Filename on Side 1 where loading starts (for compilations, e.g. `start SKY`). | Start of tape | `game.txt` |
| `keys` | `<seconds> <key\|"text">` — hold `<key>` for 0.1 s or type Latin-1 text. Repeatable. | None | `game.txt` |
| `continue` | `<key>` tried before Space/Return when capture detects a key prompt during load. | None | `game.txt` |
| `snapshot` | `at <seconds>` — take snapshot at a fixed time instead of auto-detecting load end. | Auto-detected | `game.txt` or `<machine>.txt` |
| `capture` | Capture variant name from the machine's `variant` list. | Target machine | `<machine>.txt` |
| `service` | `no` (disable tape service), `t0` (no page 3 part), `at <xxE1>` (page 3 entry page `C0E1`–`FEE1`), or `at <xxE1> <code>` (split: 26-byte entries at `xxE1`, 132-byte code at `<code>` in page 3). Explicit `service at` accepts `00h` and unused `C9h` BIOS hooks (`FD9Ah`–`FFC8h`), and with a split `<code>` address may place entries at `FFE1h` over BIOS VDP register copies for games that never call BIOS (e.g. `POWER-DR`). At most one per file. | Auto-selected | `game.txt` or `<machine>.txt` |
| `patch` | `<place> <old hex...> > <new hex...>` where `<place>` is `page<0-3>:<hex>` (snapshot RAM) or `side1:<hex>` / `side2:<hex>` (tape offset). Repeatable. Requires `sha1`. | None | `game.txt` (slot patches in `<machine>.txt`) |
| `rom` | `keep` — keep original ROM in page 0 instead of `T0`; requires the page 3 tape service (invalid with `service t0` or when ROM and DOS mapper share slot 0). | `T0` replaces ROM when allowed | `game.txt` or `<machine>.txt` |
| `subslots` | `keep` — leave BASIC's RAM subslot register unchanged during capture instead of selecting RAM in all 4 pages ([Capture](internals/capture.md#subslot-setup)). | Select RAM in all pages | `<machine>.txt` |
| `rescall` | Up to 4 hex interrupt-handler addresses (e.g. `rescall 6010 6120`) to wrap with resident calls, or `no` to omit resident calls. Ignored without `resident`. | Auto | `<machine>.txt` |
| `rescode` | Hex address in page 3 (`C000`–`FFFE`) for resident call code/wrappers (`00h` or `C9h` in `FD9Ah`–`FFC8h`). | Auto (`FD29h` / `FCC9h`) | `<machine>.txt` |
| `resstack` | Hex address in page 3 for resident private stack (64 B for `res3`, 84 B for `resb`; `00h` or `C9h` in `FD9Ah`–`FFC8h`), or `no` to run on the game's stack. | Auto (`SLTATR`/`SLTWRK`) | `<machine>.txt` |

## Machine-specific game files

A file `games/<GAME>/<machine>.txt` overrides or appends to `game.txt` when building for `<machine>`. If a machine defines `parent <parent>`, the loader reads `game.txt` → `<parent>.txt` → `<machine>.txt` in order.

Put machine-dependent directives in `<machine>.txt`: `capture`, slot-register `patch` lines, `subslots keep`, machine-only `service` / `rom` / `snapshot`, and `rescall` / `rescode` / `resstack`.

## Shipped machines

| Machine | Summary | Machine game files | Capture variants |
|---|---|---|---|
| `fsa1-mfrsd` | Panasonic FS-A1 (MSX2, 64 KB), MegaFlashROM SCC+ SD (Nextor) | 72 | `fsa1` |
| `hb75p-carnivore2` | Sony HB-75P (MSX1, 64 KB), Carnivore2 | 77 | `hb75p` |
| `hb75p-mfrsd` | Sony HB-75P (MSX1, 64 KB), MegaFlashROM SCC+ SD (stock) | 70 | `hb75p` |
| `hbf700p-ram512k-msxdos2` | Sony HB-F700P (MSX2, 256 KB), 512 KB RAM, MSX-DOS 2 | 265 | `hbf700p-msxdos2`, `hbf700p-noexp0-ram512k-msxdos2`, `hbf700p-noexp0-msxdos2` |
| `nms8245-ram512k-sunriseide` | Philips NMS 8245 (MSX2, 128 KB), 512 KB RAM, Sunrise IDE | 31 | `nms8245` |
| `nms8250-carnivore2` | Philips NMS 8250 (MSX2, 128 KB), Carnivore2 | 89 | `nms8250` |
| `phc28s-ram64k-carnivore2` | Sanyo PHC-28S (MSX1, 16 KB), 64 KB RAM, Carnivore2 | 86 | `phc28s-ram64k`, `phc28s-empty-carnivore2` |
| `sx2` | SX-2 (MSX2+, 2048 KB), slot 0 expanded | 50 | `sx2-noexp0` |
| `sx2-extramapper-mcp` | SX-2 (MSX2+, 6144 KB), Extra-Mapper + SX2RES | 770 | `sx2-extramapper-noram30` |
| `sx2-noexp0` | SX-2 (MSX2+, 2048 KB), slot 0 unexpanded (`parent sx2`) | 0 | — |
| `vg8020-carnivore2` | Philips VG-8020 (MSX1, 64 KB), Carnivore2 | 125 | `vg8020` |
| `vg8020-sdmapper` | Philips VG-8020 (MSX1, 64 KB), SD Mapper v1 | 161 | `vg8020` |
| `xp800-sdmapper` | Gradiente Expert XP-800 (MSX1, 64 KB), SD Mapper v1 | 170 | `xp800` |

## Compilations

Each program on a multi-game compilation tape (e.g. `games/ENGESOFT/`, `games/SUPERMSX/`) has its own folder and `game.txt` so every built `.SNP` is named after the game rather than the compilation. The first program omits `start`; later programs set `start <name>`. Programs that also exist as standalone File-Hunter dumps still get a compilation entry because compilation loaders and dumps often differ.

## Key names

Special MSX keyboard matrix keys accepted by `boot`, `hold`, `press`, `keys`, and `continue`:

| Row | Bit 0 | Bit 1 | Bit 2 | Bit 3 | Bit 4 | Bit 5 | Bit 6 | Bit 7 |
|---|---|---|---|---|---|---|---|---|
| 6 | `shift` | `ctrl` | `graph` | `caps` | `code` | `f1` | `f2` | `f3` |
| 7 | `f4` | `f5` | `esc` | `tab` | `stop` | `bs` | `select` | `return` |
| 8 | `space` | `home` | `ins` | `del` | `left` | `up` | `down` | `right` |
