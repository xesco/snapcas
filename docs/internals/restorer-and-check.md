# Restorer & Check Internals

This document covers how `bin/SNAPCAS.COM` restores a `.SNP` image on real hardware, how `tools/check.py` verifies it in `openMSX`, and how `tools/games.py` runs the full collection.

**Internals:** [Capture](capture.md) · [Automatic Patches](patches.md) · [Tape Service & Resident Calls](service-and-resident.md) · **Restorer & Check**

## Restorer

`src/snapcas.asm` assembles to `bin/SNAPCAS.COM`, which runs under MSX-DOS 1, MSX-DOS 2, or Nextor. It performs five phases:

1. **Validate image and hardware:**
   - Parses `<GAME>` (and optional `/M` manual tape switch), opens `<GAME>.SNP`, reads the 4,096-byte header, and checks `SNAPCAS6` (`IMAGE_FORMAT`).
   - Computes CRC-16 of the machine's 32 KB main ROM (and 16 KB sub-ROM on MSX2/MSX2+) and stops if either differs from the header.
   - Verifies DOS's four pages live in a single memory mapper, confirms every target RAM slot is actually writable RAM (and matches `H_NOEXP`), and checks compatibility of `rom keep`, `service t0`, and `sub0` (`FLAG_P0`) with DOS's mapper slot.
2. **Plan segment allocation:**
   - Allocates free mapper segments (via MSX-DOS 2/Nextor `ALL_SEG`, or by probing mapper registers under MSX-DOS 1) for:
     - **Service segments:** `T0` + code segment + tape segments.
     - **Holding segments:** Temporary segments for any game RAM page whose target `(slot, segment)` collides with one of DOS's active segments (so DOS stays intact while reading the file).
     - **Worker segment:** A segment in page 1 or 2 where the final restore loop runs after DOS is shut down.
   - If free segments are insufficient, prints `needs N free mapper segments, and DOS has M` and exits cleanly to DOS.
3. **Stream records from disk:**
   - Reads each 16 KB record directly into its destination RAM/VRAM/service segment (or into its holding segment if it collides with DOS). Type `5` zero-VRAM records zero VRAM without reading disk bytes.
   - Patches `fill_page3` (`E_SLOT`, `E_T0`, `E_CODE`, `E_FC`, and `SLTTBL` if needed), fills the code segment's segment table and `/M` mode byte, and applies every `place` entry (DOS mapper slot in page 0 for `T0` mode).
   - Completes the restorer-owned bytes of the 26-byte tail (`TAIL_MAP`, `TAIL_PORT`, `TAIL_A8`, `TAIL_SUB`, `TAIL_LD`) inside the tail record (`H_TAILREC`).
4. **Stop floppy motor & shut down DOS:**
   - Waits 180 VDP ticks (~3 s) with interrupts enabled so floppy drive motors spin down cleanly.
   - Disables interrupts (`DI`), executes all header port writes (PSG, PPI, V9938+ palette/command regs, VDP regs, VRAM pointer), and switches into the worker segment.
5. **Copy held pages & jump to tail:**
   - Copies every held RAM page into its true DOS-mapper segment, writes subslot registers (writing `00h` for any slot flagged in `H_NOEXP`), restores mapper registers `FCh`–`FFh` (except the worker's page), loads CPU registers `BC`, `DE`, `HL`, `AF'`, `BC'`, `DE'`, `HL'`, `IX`, `IY`, `I`, and `IM`, and jumps to the 26-byte tail below the game's `SP`.
   - The tail maps the game's segment back into the worker's page, writes `A8h` (and `FFFFh` if the worker couldn't), pops `AF`, loads `SP`, optionally executes `EI`, and jumps to `PC`.

## Four-point check

`tools/check.py` + `tools/tcl/check.tcl` boots a temporary disk containing DOS, `SNAPCAS.COM`, `<GAME>.SNP`, and an `AUTOEXEC.BAT` running `SNAPCAS <GAME>`, then runs the restored game for **60 emulated seconds** (saving savestates at `10s`, `20s`, `30s`, `40s`, `50s`, `60s` and writing `check/report.txt` and, on resident machines, `check/rescall.txt`):

| Point | What it verifies | Failure conditions |
|---|---|---|
| **1 — Restore fidelity** | At the exact tail `JP`, compares every kept RAM page (excluding `build.txt`'s patched ranges and `FCC9h`–`FD88h` clear), VRAM, CPU registers, slots, mapper registers, VDP/palette/VRAM pointer, and PSG state against `snap/`. | Restorer exits with an error message, tail `JP` never executes within timeout, or any register/memory byte differs. |
| **2 — Page 3 protection** | Watchpoints monitor the tape service's page 3 block(s), `sub0`, `rescode`, and `resstack` (when `SP` is outside `resstack`) during the 60 s run. | The game writes into any guarded byte (excluding `E_STOP` writes from the service itself, or tape-service writes after the tape reaches its end). |
| **3 — Stability (no crash/reboot)** | Watches for `SNAPCAS.COM` starting again, the BIOS boot screen appearing at 2+ savestates, `RST 38h` (`FFh`) execution count, and `0038h` entries with `SP < 0100h`. | Reboots to DOS or boot screen, executes >100,000 `FFh` (`RST 38h`) bytes, or enters `0038h` with >32 distinct `SP` values below `0100h`. Intentional loader resets that start the game pass. |
| **4 — No BASIC error** | Inspects text screens at savestates for standard MSX-BASIC error messages (e.g. `Syntax error in ...`, `Overflow in ...`). | Any BASIC error message appears. Games intentionally pausing at `Ok` without an error pass. |

### Gameplay-start key mode (`SNAPCAS_KEYS=1`)

Setting `SNAPCAS_KEYS=1` injects simulated keypresses during the 60-second check to exercise menus and gameplay startup: `Space` at 15 s, `0` at 25 s, `1` at 35 s, and `Space` at 45 s. This catches post-menu overwrites of `rescode`/`resstack`, tape service collisions, and Spectrum `OUT (0FEh),A` or MSX1 BIOS crashes that idle title screens hide. (Pure BASIC programs waiting for input may report a false-positive `Syntax error` on `0`/`1`.)

## Batch runner

`make games MACHINE=<machine>` invokes `tools/games.py`, which runs `tools/pipeline.py` across all 1,544 games in parallel:

- **Two-level incremental hashing:**
  - **Capture hash (`snap/.hash`):** Covers tapes, game/machine files, `openMSX` version, and `CAPTURE_TOOLS`. When unchanged, `pipeline.py` runs with `--skip-capture`.
  - **Full hash (`out/games/<machine>.txt`):** Adds `build.py`, `resident.py`, `check.py`, `bin/SNAPCAS.COM`, `bin/SERVICE.BIN`, DOS files, and `SNAPCAS_KEYS`. Unchanged passing games are skipped entirely unless `FULL=1` is set.
- **Automatic variant retry (`FIX=1` default):** When a game without a `capture` line fails, `pipeline.py` retries each `variant` in the machine file in order. If a variant passes, `games.py` writes `capture <variant>` (with an explanatory comment) into `games/<GAME>/<machine>.txt` automatically. Pass `FIX=0` to disable.
- **Failure classification:** Results are grouped against `tests/openmsx-failures.txt` and `tests/snapcas-failures.txt`; `make games` exits non-zero only if an unlisted game fails. Passing images are copied to `images/<machine>/<GAME>/`.
