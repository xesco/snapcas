# Automatic Patches

This document catalogs the automatic patchers in `tools/patches/` that fix recurring MSX cassette loader bugs across hundreds of tapes without per-game overrides.

## Overview

`snapcas` follows a strict rule: individual game bugs are fixed in `games/<GAME>/`, while patterns repeating across many tapes are fixed once in `tools/patches/`. Each patcher is self-contained (a Python module plus an optional `.tcl` watch fragment) and reports findings via `tools/patches/finding.py`.

Patchers run at two points:
- **During capture:** Watchpoints in `capture.tcl` detect broken instructions as they execute, rewrite the matching bytes in `side1.cas` (preserving block checksums where applicable), record the patch in `snap/patches.txt`, and restart capture cleanly on the patched tape.
- **During build (`scan`):** `tools/build.py` scans the snapshot's RAM pages (applying patches automatically) and unread tape blocks (listing findings in `scan.txt` for manual review when a block checksum might exist).

## Patcher catalog

| Module | Runs at | Pattern matched | What it fixes |
|---|---|---|---|
| `slots.py` / `slots.tcl` | Capture + Build | `LD A,n / OUT (0A8h),A` (`3E nn D3 A8`) and `LD A,n / CALL 013Bh` (`3E nn CD 3B 01`) | Replaces empty primary-slot fields in `n` using `slots.txt`. Skips `3E` after `3A` (`LD A,(nn)`) during capture and any operand-ambiguous `3E` during build scan. |
| `ramsearch.py` / `ramsearch.tcl` | Capture + Build | Page-3 RAM search loops writing `OUT (0A8h),A` that deselect page 3 itself | Keeps page 3 mapped to its own RAM slot so the loader does not cut off its own code (fixes ~70 Opera Soft and similar tapes). |
| `pagecopy.py` / `pagecopy.tcl` | Capture | Loaders copying page 2/3 primary slot bits into pages 0–1 (`BIT 7/6`, `AND F0h` + shifts) | Rewrites the copy to select the machine's actual RAM slot in pages 0–1 (Level 9, CasLink3, Engesoft, Super MSX), preserving Level 9's 8-bit block sum. |
| `searchslot.py` / `searchslot.tcl` | Capture | Dinamic's `slots` routine copying page 2's slot into page 1 beside its RAM-search result | Aligns the copied slot with the slot the search actually found (31 tapes). |
| `enaslt.py` / `enaslt.tcl` | Capture | Loader copies of `ENASLT` using `AND B` instead of `AND H`, and restoring BASIC via `EXPTBL[1]` | Fixes `AND B` → `AND H` (preventing subslot wipe when `B = 00h`) and restores main ROM's actual slot (14 tapes: *Arkos*, *Satan*, *Made in Spain*, etc.). |
| `irqslot.py` / `irqslot.tcl` | Capture | Aventuras AD's interrupt handler writing a saved `A8h` copy during MSX2 sub-ROM calls | Guards the slot write so sub-ROM calls are not corrupted (13 games). |
| `subpoke.py` / `subpoke.tcl` | Capture | BASIC `POKE &HFFFF,&HAA` or `POKE -1,170` hardcoding MSX2 subslot 2 | Rewrites the value to the machine's actual RAM subslot (`50h` when RAM shares slot 0 with main ROM so BASIC remains mapped; 83+ games). |
| `hookfill.py` / `hookfill.tcl` | Capture | Loaders filling `FD9Ah`–`FFF6h` with `C9h` (`RET`) on MSX2/MSX2+ | Caps the fill at `FFC9h` so MSX2 VDP register copies `RG8SAV`–`RG23SAV` (`FFE7h`–`FFF6h`) stay intact (32 games). |
| `tramp.py` / `tramp.tcl` | Capture + Build | Spanish `FC9Ah` tape trampoline selecting BIOS in page 0 via `A8h` alone (220 games: Opera Soft, Topo Soft, Dro Soft) | On machines where RAM shares slot 0 with main ROM (`sx2-extramapper-mcp`), rewrites the trampoline to switch slot 0's subslot register (restoring the caller's original subslot and preserving block XOR checksums). During build, `tramp.serve` / `serve_live` retargets its tape call to the tape service's actual entry page (including moved parts such as `FFE1h`). |
| `tapecode.py` | Build | Direct `CALL`/`JP` to BIOS tape entries `00E1h`–`00F3h` and `00E1h`–`00F3h` addresses in RAM/unread blocks | Rewrites calls to the tape service's page 3 entries (`xxE1h`–`xxF3h`) and flags custom PSG port `A2h` cassette readers in `scan.txt`. |
| `t0stub.py` | Build | `TAPION` stubs computing `AND H / LD L,A` to select slot 0 before calling `00E1h` in `T0` mode | Replaces the pair with `LD L,nn` and emits an image `place` entry so `SNAPCAS.COM` writes DOS's mapper slot into page 0 at restore time. |

## Slot patches

When a loader writes to port `A8h` or calls `WSLREG` (`013Bh`), each 2-bit field selects a primary slot for page 0 (bits 1–0) through page 3 (bits 7–6). `slots.py` checks every 2-bit field of the written value against `snap/slots.txt`:
- Fields naming a slot that holds ROM or RAM on the target machine are left untouched.
- Fields naming an `empty` slot are replaced with the page's `with` RAM slot.
- If a write modifies page 3 away from RAM while executing from page 3 (`cuts off its code`), `ramsearch.py` handles the known search pattern; otherwise capture logs the write with `for a patch line` in `snap/log.txt`.

## How patchers hook capture

`tools/patches/__init__.py` collects all active capture patchers for the target machine:
1. `capture.py` injects each patcher's `.tcl` watchpoint into `capture.tcl` before starting the load.
2. When a watchpoint triggers, `capture.tcl` pauses and writes the event details (PC, instruction bytes, registers, active slot) to the capture log/IPC channel.
3. The Python patcher locates every matching copy of the instruction sequence in `side1.cas`, computes the replacement bytes (updating any 8-bit sum or XOR block checksum), appends the `patch side1:...` lines to `snap/patches.txt`, and re-runs the capture from a clean boot on the patched tape.
4. Any write that no patcher recognizes is logged once per `(PC, value)` in `snap/log.txt` as `for a patch line` so a contributor can add a manual patch to the game file.
