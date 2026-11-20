# Tape Service & Resident Program Calls

This document explains how `tools/build.py`, `tools/resident.py`, and `bin/SERVICE.BIN` serve multi-load tapes from mapper RAM and keep machine-resident programs (such as SX2RES) running during gameplay.

## Tape service

Single-load games receive no tape service—the restored machine is identical to the snapshot. Multi-load games (`service 1` in `state.txt`, unless overridden by `service no`) embed all remaining tape data (including Side 2) in DOS mapper segments and intercept BIOS cassette calls `00E1h`–`00F3h` (`TAPION`, `TAPIN`, `TAPIOF`, `TAPOON`, `TAPOUT`, `TAPOOF`, `STMOTR`).

The service has three cooperating pieces (layouts in [FORMATS.md](../FORMATS.md#tape-service-tables)):
- **`T0` (16 KB segment):** A RAM copy of BIOS page 0 (`rom.bin[0:4000h]`) whose tape routines at `19DDh`–`1B44h` are replaced with stubs from `SERVICE.BIN` part 1 (`00F3h` `STMOTR` is also repointed). `T0` intercepts any game or BASIC code that calls `00E1h`–`00F3h` through page 0.
- **Page 3 part (158 bytes):** Lives in the game's page 3 RAM so it stays visible while page 0 switches between `T0`, the game's page 0 RAM, and the code segment. Holds 26 bytes of entry jumps + data (`xxE1h`–`xxFAh`) and a 132-byte code block (`tramp`, `tapiof`, `stmotr`, `e_run`, and the `sub` helper).
- **Code segment + tape segments (up to 64 segments = 1 MB):** The code segment holds the 104-byte header, full `TAPION`/`TAPIN`/manual-tape routines, and the start of the tape; subsequent segments hold the rest of the tape. `TAPIN` preserves BIOS register contracts (including returning `B = 0`).

During build, `tools/patches/tapecode.py` scans RAM pages and patches direct `CALL`/`JP` instructions to `00E1h`–`00F3h` so they jump straight to the page 3 entries (`xxE1h`–`xxF3h`), catching loaders that page out `T0`.

## Page 3 part and split placement

By default, `build.py` places the 158-byte page 3 part at `FCE1h`–`FD7Eh` when `FCC9h`–`FD88h` (BASIC's `SLTATR`/`SLTWRK`) are all zero at the snapshot and clear of the tail. If that area is occupied, `build.py` searches downward from `F1E1h` to `C0E1h` for 158 contiguous zero bytes.

When automatic placement fails or a game writes to the chosen area during play, a game file can control placement with `service at`:
- **Contiguous:** `service at <xxE1>` (`C0E1h`–`FEE1h`) relocates the entire 158-byte part using `SERVICE.BIN` part 7 (high-byte relocations).
- **Split:** `service at <xxE1> <code>` places only the 26-byte entries/data block at `xxE1h` and moves the 132-byte code block independently to any page 3 address `<code>` using `SERVICE.BIN` part 8 (16-bit relocations).
- **Allowed bytes for explicit `service at`:** Zero bytes anywhere in page 3, unused `C9h` (`RET`) hooks inside `BIOS_HOOKS` (`FD9Ah`–`FFC8h`), and—for a split entries block at `FFE1h`—non-zero MSX2/MSX2+ BIOS system bytes in `FFE7h`–`FFFAh` (`RG8SAV`–`RG23SAV`, `MINROM`, `RG25SAV`) when the game never calls the BIOS (e.g., *Power Drift*'s `service at FFE1 FF01` on SX-2).

## `sub0` helper

When a multi-load game keeps RAM in page 0 inside DOS's expanded mapper slot (e.g. `sx2-extramapper-mcp`, where main ROM is `0-0` and Extra-Mapper RAM is `0-1`), switching page 0 to `T0` or the code segment requires changing slot 0's subslot register at `FFFFh` as well as port `FCh`—even if `sub0` was `55h` (all RAM) at snapshot time, because the game may later map `0-0` to call `TAPION`/`TAPIN`.

`build.py` (`needs_sub0()` / `place_sub0()`) detects this (`ps == 0 and ss != 0` on an expanded slot) and installs the 23-byte `sub0` helper from `SERVICE.BIN` part 5, pointing `e_run.call` at it and setting `FLAG_P0` in the image header. `place_sub0()` tries locations in order:
1. `xxC9h` immediately before the entries block (`00h`, or `00h`/`C9h` inside `BIOS_HOOKS`).
2. Unused `C9h` BIOS hooks in `FF01h`–`FFC7h`.
3. BASIC's zero `TRPTBL` bytes in `FC4Ch`–`FC9Dh`.

## `T0` mode

If page 3 has no room for the 158-byte part—or the game file requests `service t0`—`build.py` uses `SERVICE.BIN` part 4 to put the entire tape service inside `T0` (`19DDh`–`1B44h`), leaving page 3 untouched:
- **Requirements:** Page 0 RAM must not be in DOS's mapper (otherwise `T0` and the game's page 0 conflict on port `FCh`), `rom keep` must not be set, and the remaining tape must fit in at most **16 segments (256 KB)**.
- **Borrowed page:** Because `TAPIN` runs inside `T0` in page 0, it temporarily borrows page 2 (or page 1 if page 2 is not in a mapper) to read each tape segment, using no stack.
- **Stub patching:** `tools/patches/t0stub.py` patches `AND H / LD L,A` `TAPION` stubs and records image `places` so `SNAPCAS.COM` patches DOS's mapper slot into them.
- **Trade-offs:** No manual `/M` mode and no `TAPIN` header/padding skip (not enough room inside `19DDh`–`1B44h`).

### `T0` and sub-ROM in one slot

On machines where DOS's mapper and the MSX2/MSX2+ sub-ROM share one expanded slot (e.g., `sx2`: RAM in `3-0`, sub-ROM in `3-1`), BIOS `CALSLT` writes the sub-ROM's subslot to `FFFFh` while executing from page 0—which would map `T0` out underneath itself. `build.py` locates `CALSLT`'s subslot routine and `CLPRIM` jump inside `rom.bin` and redirects them to `t_s` and `t_c` in `T0`, which delegate the subslot switch to `sub` in page 3.

## Manual tape

Passing `/M` to `SNAPCAS.COM` sets the code segment's mode byte (`0054h`) to `1` (ignored in `T0` mode). `E_STOP` (`xxFAh`) tracks whether the virtual motor is stopped (initialized from snapshot `ppic` bit 4, and set by `TAPIOF`, `STMOTR`, or end-of-side). On the next `TAPION`, the service waits for a keypress—flashing the border (VDP R#7, restored from `RG7SAV` or snapshot R#7):
- `RETURN` (yellow): resume playback (waits for key release so the game never sees `RETURN`; advances to Side 2 if Side 1 ended).
- `GRAPH` (green): rewind to Side 1 start and play.
- `CODE` (red): jump to Side 2 start and play.
- `CTRL+STOP`: abort with carry set.

In automatic mode (`0054h = 0`), `GRAPH` and `CODE` are still polled on `TAPION` for manual rewinds/flips.

## Resident program calls

On machines declaring `resident <slot> <addr> <bytes...>` (e.g., `sx2-extramapper-mcp` with SX2RES 2.8+ at `3-0 4040h`), `tools/resident.py` refuses any snapshot keeping RAM in the resident slot and installs an interrupt call so the resident stays reachable during gameplay. Before every call, the stub verifies the first 2 signature bytes at `<addr>` (`F5 DB` for SX2RES), so the image still runs cleanly if the resident is not loaded.

`resident.py` selects the lowest-intrusion mechanism the snapshot allows (logged in `build.txt` as `rescall <mode>`):

| Mode | When used | Mechanism & stack |
|---|---|---|
| **`t_res`** | Image has `T0` (`service 1`, no `rom keep`) | Installed at `0038h` in `T0`; uses a private stack inside `T0` (`T_STACK`, below `t_tapion`), zero bytes in game's page 3. |
| **`resb` / `resbg`** | No `T0`, game uses BIOS interrupts (`H.KEYI`) | Installed in page 3 (`FD29h`, `FCC9h`, or `rescode`), hooked from `H.KEYI` (`FD9Ah`), calls entry via BIOS `RDSLT`/`CALSLT`. `resb` uses an 84-byte private stack (`SLTATR`/`SLTWRK` or `resstack`) with tail `resbe`; `resbg` (`resstack no`) runs on the game's stack and skips the call if `SP` is in the entry's page. |
| **`res3` / `res3g`** | Game installs its own interrupt handler (`rescall <addr...>`) or `rescode` without `H.KEYI` | Uses port `A8h` directly (no BIOS calls) to map the resident slot and call `<addr>`, plus 6-byte wrappers (17 bytes with tape service) jumping to each listed handler (`build.txt` prints `resvector`). `res3` uses a 64-byte private stack + `res3e`; `res3g` (`resstack no`) uses the game's stack. |
| **Omitted (`rescall no`)** | Game disables interrupts or overwrites all of page 3 | No resident call installed; game-file `patch` lines may still install a custom trampoline in page 1/2 (e.g., *Power Drift*). |

Both `rescode` and `resstack` accept zero bytes anywhere in page 3 or unused `C9h` hooks inside `BIOS_HOOKS` (`FD9Ah`–`FFC8h`), and point 2 of the check guards both regions against game writes.
