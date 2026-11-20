# Capture Internals

This document covers how `tools/capture.py` and `tools/tcl/capture.tcl` load a cassette game in `openMSX` and produce a snapshot folder.

**Internals:** **Capture** · [Automatic Patches](patches.md) · [Tape Service & Resident Calls](service-and-resident.md) · [Restorer & Check](restorer-and-check.md)

## Pipeline

`tools/capture.py` boots a headless, muted `openMSX` instance configured from the machine file (or a capture variant) and executes six stages:

1. **Boot to BASIC:** Applies any `hold`/`press` rules, matches `boot` prompts in order, and if the machine file has a `dos` line, types `BASIC` at the DOS prompt. Waits up to 120 emulated seconds for BASIC's `Ok`, then waits 10 more seconds (needed by some disk cartridges before cassette I/O stabilizes).
2. **Prepare cassette-like state:** Removes disk system hooks (`FD9Ah`–`FFC8h` reset to `RET`), clears disk work area (`FCC9h`–`FD88h` zeroed so `build.py` can detect game usage vs. DOS leftovers), applies `width <n>` if configured, selects BASIC's RAM subslot in all pages when appropriate ([Subslot Setup](#subslot-setup)), and builds the machine's [Slot Map](#slot-map).
3. **Start the load:** Inserts the Side 1 tape (with any `side1:` patches applied), skips to `start <name>` if specified, sets `TAPION`/`TAPIN`/motor/reset/slot watchpoints, and types the load command (`load` directive or auto-detected from Block 1: `BLOAD"CAS:",R`, `CLOAD`, or `RUN"CAS:"`).
4. **Monitor load & flip sides:** Tracks tape position in lockstep with `TAPION` calls, logs resets without aborting (some loaders reset intentionally), and flips to Side 2 (waiting 0.05 s so the last byte of Side 1 finishes) when Side 1 reaches its end and `side2` is set.
5. **Detect load completion & retry keys:** When the cassette motor stays off for 30 emulated seconds (or the tape reaches its end), capture checks whether the game is waiting for a key to continue loading. Using `savestate`/`loadstate` rewinds (never `reverse goto`, which replays input), it tries `continue <key>`, `Space`, and `Return`, re-arming watchpoints after every rewind. If a key starts another load, step 5 restarts (up to 20 times); if a `snapshot at <sec>` directive is set, capture stops at that exact time instead.
6. **Take the snapshot:** Waits for the next interrupt entry (`PC = 0038h` with interrupts off, ensuring complete CPU state and 26 free bytes below `SP` for the tail). If interrupts stay disabled or the game is waiting in `TAPION` for Side 2, capture falls back to the last `TAPION` entry or the current instruction. Dumps kept RAM pages, `rom.bin`, `subrom.bin`, `vram.bin` (with V9938 R#8 `VR` bit temporarily forced to 1), `state.txt`, `slots.txt`, `patches.txt`, and `log.txt` ([FORMATS.md](../FORMATS.md#snapshot-files)).

### Kept RAM pages

Capture records every 16 KB RAM page that is either selected at snapshot time or was written during the load (`ram/<ps>-<ss>-<page>-<seg>.bin`). Each mapper's segment count is written to `state.txt` as `mapper<ps>-<ss>` so `build.py` resolves register values modulo the real mapper size.

## Tape files

`tools/tape.py` defines a format-neutral block model produced by `tools/cas.py` (`.CAS`) and `tools/tsx.py` (`.TSX`). All later stages—capture, patchers, build, and check—operate solely on this model:

- **Standard vs. non-standard blocks:** Every `.CAS` block is BIOS-standard. `.TSX` files may mix standard MSX `4Bh` blocks with custom/turbo blocks (`10h`, `11h`, `15h`, etc.). Non-standard blocks are allowed before the snapshot (capture plays them in `openMSX`), while post-snapshot blocks must be standard unless `service no` is set.
- **Compilations (`start <name>`):** To capture a later program on a multi-game tape, `tape.py` locates the first header matching `<name>` (case-insensitive, padded to 6 bytes), slices the tape from that offset, and logs the byte offset so `side1:` patches still use offsets in the original tape file.

## Slot map

Before typing the load command, capture inspects every primary slot `0–3` across pages `0–3` and writes `snap/slots.txt`:

```text
page 0 empty 1,2 with 3
page 1 empty 1,2 with 3
page 2 empty 1,2 with 3
page 3 empty 1,2 with 3
```

For each page, the slot map records:
- **`empty`:** primary slots containing neither ROM nor RAM in that page.
- **`with`:** the primary slot holding RAM suitable to substitute when a loader writes an empty slot into `OUT (0A8h),A` or `WSLREG` (`-1` if none).

Both capture-time slot watchpoints and build-time RAM scans use `slots.txt` ([Automatic Patches](patches.md#slot-patches)).

## Subslot setup

On MSX2/MSX2+ machines whose BASIC RAM sits in an expanded slot (such as the Philips NMS 8250 in slot `3-2` or SX-2 in slot `3-0`), BASIC leaves pages 0 and 1 of that slot pointing at subslot 0 (often empty or a sub-ROM) while pages 2 and 3 point at RAM. Loaders that switch pages 0–1 to RAM by primary slot alone (`OUT (0A8h),A`) then map empty memory and crash.

Before loading, capture writes the RAM's subslot into all four pages of BASIC's RAM slot—**with two exceptions**:
- **Slot 0:** Never modified when BASIC's RAM shares slot 0 with the main ROM (e.g. `sx2-extramapper-mcp`, where main ROM is `0-0` and Extra-Mapper is `0-1`), because changing pages 0–1 would immediately map out the BIOS and BASIC.
- **`subslots keep`:** A game file directive that skips this step for games whose loader or stack breaks when pages 0–1 select RAM in that slot.

## Capture without expanded slot 0

Many 1980s loaders fail on machines with expanded slot 0 (such as Sony HB-F700P and SX-2) because they probe RAM via `OUT (0A8h),A` + `LD (0FFFFh),A` and corrupt slot 0's subslot register. Rather than patching hundreds of individual loaders, `snapcas` captures those games on a `noexp0` capture variant (`machines/capture/*-noexp0*.txt`), whose `openMSX` XML (generated by `make firmware`) puts the main ROM directly in an unexpanded slot 0.

When building the image for the real machine, `build.py` sets the corresponding bit in header byte `H_NOEXP` (`56`). At restore time, `SNAPCAS.COM` writes `00h` to slot 0's real subslot register—selecting subslot 0 (the main ROM)—so the game runs identically on the real expanded-slot-0 machine as long as it never writes slot 0's subslot register itself.

## Capture cache

`tools/games.py` and `tools/pipeline.py` cache capture separately from build and check:
- `out/work/<machine>/<game>/snap/.hash` stores a SHA-256 over the tape files, game/machine files, `openMSX` version, and capture-only tools (`CAPTURE_TOOLS`: `capture.py`, `cas.py`, `tsx.py`, `tape.py`, `gamefile.py`, `msx.py`, `tools/patches/*`, `tools/tcl/capture.tcl`).
- Changes to `build.py`, `resident.py`, `check.py`, `bin/SNAPCAS.COM`, `bin/SERVICE.BIN`, or `SNAPCAS_KEYS` do **not** invalidate `snap/.hash`, so `make games` and `tools/pipeline.py --skip-capture` reuse existing snapshots and re-run only build and check.

## Tools code layout

| Module | Role |
|---|---|
| `snapcas.py` | End-user CLI (`list`, `machines`, `snap`, `sync`, `try`). |
| `tools/pipeline.py` | Single-game capture → build → check orchestration and variant retry. |
| `tools/games.py` | Parallel `make games` batch runner, split hashing, and failure-list checking. |
| `tools/capture.py`, `tools/tcl/capture.tcl` | Headless `openMSX` loader and snapshotter. |
| `tools/patches/` | Automatic tape and RAM patchers ([patches.md](patches.md)). |
| `tools/build.py`, `tools/resident.py` | `.SNP` image builder, tape service placement, and resident call installation. |
| `tools/check.py`, `tools/tcl/check.tcl` | 4-point automated verification in `openMSX`. |
| `tools/msx.py`, `tools/gamefile.py`, `tools/snapshot.py` | Machine files (including `parent` inheritance), game files, and snapshot I/O. |
| `tools/tape.py`, `tools/cas.py`, `tools/tsx.py` | Format-neutral tape model and CAS/TSX readers. |
| `tools/download.py`, `tools/card.py`, `tools/try.py`, `tools/plain.py`, `tools/relocs.py` | File-Hunter downloads, safe SD card sync, interactive `try`, plain `openMSX` test, and `SERVICE.BIN` relocation builder. |
