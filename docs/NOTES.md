# Hardware & Game Notes

This reference preserves the MSX hardware quirks and game case studies that shaped `snapcas`'s rules and automatic patchers. Use it when debugging a new failure or designing a patch. For the patcher implementations themselves, see [docs/internals/patches.md](internals/patches.md).

## Loaders and slots

### Primary-slot-only loaders
Many 1980s loaders compute `OUT (0A8h),A` or `CALL WSLREG` values assuming RAM sits in one unexpanded primary slot:
- **Fixed slot assumptions:** *Sootland* writes `FCh` (slot 3 RAM); on a PHC-28S without Nextor (internal RAM in slot 0 page 3, RAM cart in slot 1 pages 1–2), the matching value is `14h`. *Doki Doki Penguinland* explicitly selects slot 1 in page 3 and keeps a hand patch.
- **False-positive `3E` operands:** *Knight Orc* executes `LD A,(EF3Eh) / OUT (0A8h),A` (`3A 3E EF D3 A8`) whose tail resembles `LD A,EFh / OUT (0A8h),A`. Capture skips `3E` after `3A`, while the build scan skips any `3E` that could be an operand.
- **Page-copy loaders:** Level 9 adventures (*Emerald Isle*, *Red Moon*, *Adrian Mole*, etc.), CasLink3 tapes (*Hang-On*, *Lunar Ball*, *Quartet*), Engesoft's *Circus Charlie* / *Hyper Sports 3*, and Super MSX's *The Wall* copy page 2/3's slot bits into pages 0–1. Fixed machine-code forms are handled by the page-copy patcher (preserving Level 9's 8-bit block sum); BASIC `DATA` forms (*M-Droid*) use game-file patches.
- **Dinamic's `slots` program (31 tapes):** Searches for RAM in pages 0–1, then copies page 2's slot into page 1 beside the found value. On a PHC-28S with Carnivore2, *After the War* rendered bars for fonts and *Mega Phoenix* reset to BASIC before the search-slot patcher aligned both values.
- **Buggy `ENASLT` copies (14 tapes):** *Arkos I–III*, *Satan*, *Made in Spain*, and *Paris-Dakar* copy `ENASLT` with `AND B` instead of `AND H` (clearing the subslot register when `B = 00h` on `sx2-extramapper-mcp`) and restore BASIC using `EXPTBL[1]` (`00h`). Fixed globally by the `ENASLT`-copy patcher.
- **Aventuras AD interrupt handler (13 games):** *La Aventura Espacial*, *Ci-U-Than Trilogy II/III*, *Elfos de Maroland*, *R.U.R. 1/2*, and *Torreoscura* write a saved `A8h` value during interrupts, colliding with MSX2 sub-ROM calls (fixed by the interrupt-slot patcher). On `sx2`, where RAM (`3-0`) shares slot 3 with the sub-ROM (`3-1`), a 13-byte patch also saves/restores the subslot register around the handler's `013Ch` call.

### Expanded slot 0 & `noexp0` capture
On machines with expanded slot 0 (Sony HB-F700P, SX-2), loaders that probe RAM via `OUT (0A8h),A` and `LD (0FFFFh),A` frequently crash even in plain `openMSX`:
- *After the War*, *Altered Beast*, *Lorna*, and *Casanova* write `FFh` to slot 0's subslot register, leaving page 0 unmapped so every interrupt loops on `RST 38h`.
- *Mot* and *Mandragore* pass `EXPTBL[0]` (`80h`) to a broken `ENASLT` copy.
- Capturing on a `noexp0` variant (unexpanded slot 0 with main ROM in subslot 0) fixes 235+ games on `hbf700p-ram512k-msxdos2` without per-game patches.

### `FFFFh` as RAM in expanded slots
When page 3 sits in an expanded slot (all RAM on NMS 8250 and SX-2; Carnivore2 on MSX1), any write to `FFFFh` hits the subslot register and maps RAM out:
- **Stack at `0000h` / `FFFFh`:** *Space Beater* (`LD SP,0000h`), *Booga-Boo*, *Frog*, and *Johny Comomolo* (`LD SP,0FFFFh`, which also clobbers MSX2 `MAINROM` at `FFF7h` during `EXTROM`) patch `SP` to `FFFEh` or `F380h`. *Macadam Bumper* and *Las Tres Luces de Glaurung* use `subslots keep`.
- **Block copies / tables ending at `FFFFh`:** *Enchanted*, *Ocean Conqueror*, *The Wall*, *Jack the Nipper*, *RoboCop*, *Barbarian*, *Chuckie Egg*, *Knight Lore*, and *Alien Syndrome* all write `FFFFh` and keep targeted patches (updating block XOR/sum bytes where checked).
- **Hook fills past `FFC9h`:** 32 games (e.g. Super MSX's *Choplift*, *Tetratlon*, *Toruk*, *Digy Dung*, *Container*) fill `FD9Ah`–`FFF6h` with `C9h`, clobbering MSX2 VDP register copies `RG8SAV`–`RG23SAV` (`FFE7h`–`FFF6h`); the next screen-mode change writes `09h` to VDP R#15 and causes an infinite interrupt storm. The hook-fill patcher caps these fills at `FFC9h` on MSX2+.

### ZX Spectrum ports & MSX1 BIOS internals
- **`OUT (0FEh),A`:** Spectrum ports (*Mortadelo y Filemon*, *Double Dragon 88*, *Scramble*) write to Spectrum border/beeper port `FEh`. On MSX mappers, port `FEh` remaps page 2 and crashes the game into `RST 38h`. Patched to `7F 52` (`LD A,A / LD D,D`), which is a 2-byte no-op that preserves both 8-bit sum and XOR checksums (`D3 + FE = D1`, `7F + 52 = D1`; `D3 ^ FE = 2D`, `7F ^ 52 = 2D`).
- **Hardcoded MSX1 BIOS internals:** *The Queen's Footsteps Parts 1 & 2* call `0115h` (middle of a jump entry); *Khazzad-Dum* calls `046Fh` (MSX1 internal `BREAKX`, which is inside `CHKRAM` reset on MSX2/MSX2+—patched to `CALL 00B7h`).

## Tape service and memory

- **Register contracts:** *Gauntlet*'s level loader relies on `TAPIN` returning with `B = 0` (matching the BIOS), so `SERVICE.BIN` preserves `B = 0` in both page 3 and `T0` modes.
- **Side 1 padding:** *Saint Dragon* expects `TAPIN` to return `FFh` bytes during Side 1 trailing padding while flipping sides.
- **Post-end writes:** *7 Card Stud* writes variables into `FD00h` after reading its last tape block; check point 2 ignores writes to the tape service once the tape reaches its end.
- **Late overwrites:** *Altered Beast* overwrites `FCE1h` after loading Side B (past the 60 s check) and *Desperado* / *Gunsmoke* zero `FD68h` inside the reader when starting a phase; both use `service t0`.
- **Split placement:** *Power Drift*, *The Running Man*, and *SPQR* keep page 0 RAM in DOS's mapper (blocking `service t0`) and lack 158 contiguous free bytes at any `xxE1h`, motivating split `service at <xxE1> <code>` (and `FFE1h` entries for BIOS-free games like *Power Drift*). *Chase H.Q.* places its service inside an unused 255-byte `IM 2` vector table.
- **Same segment in two pages:** *Double Dragon* maps one mapper segment into two pages simultaneously, so the build tracks RAM by `(slot, segment)` and stores explicit tail/page-3 record indices in the image header.
- **Mapper capacity:** *Relics* requires 32–33 free mapper segments, exceeding 512 KB cartridges (26 free under MSX-DOS 2); supporting a second mapper would require a format change and ~500 lines for a single title.

## VDP and hardware

- **VDP R#8 `VR` bit:** *Boulder Dash* clears bit 3 (`VR`) of VDP R#8 on a V9938; capture forces `VR = 1` while dumping `physical VRAM` so linear restore matches.
- **PSG R#7 and R#15 (joystick ports):** *Desperado* / *Gunsmoke* / *Far West* set bit 6 of PSG R#7 (making port A an output, breaking discrete PSGs on PHC-28S/VG-8020/HB-75P) and leave R#7 bit 7 clear at snapshot time (making R#15 read `FFh`, which would drive joystick pin 8 high on restore). Capture tracks the last byte written to R#15 via port `A1h` watchpoint.
- **BASIC stack margin differences:** MSX2 BASIC (`SCREEN` via sub-ROM) uses more stack than MSX1, and NMS 8250 BASIC enforces a 160-byte free-stack check vs. 120 bytes on MSX1/HB-F700P. Loaders with tight `CLEAR` values (*Break Out!*, *Master of the Lamps*, *Happy Fret*, *Reflex*, *Wing Man*, *A View to a Kill*, *Spartan X*) fix this with `MAXFILES=0` or smaller `CLEAR` reserves.
- **Timing & resets during capture:** *Moonrider* requires 10 s after `Ok` on PHC-28S+Carnivore2 and pauses 16 s mid-load (hence the 30 s motor-off wait). *A-TEAM* showed that `loadstate` rewinds must re-arm memory watchpoints. *The Goonies*, *Alien 8*, *Raider*, and *Japan* reset intentionally during boot/start, so point 3 flags where the machine ends up rather than every reset.
- **Real PHC-28S quirks:** BASIC `PLAY` music active at snapshot time never finishes on real hardware (*Tokyo Nampa Street* snapshots after the music). *Konami's Soccer* and *Budokan* reset on real PHC-28S+Carnivore2 even when `openMSX` stayed on the title screen—capturing without Carnivore2 fixed both.

## MSX2+ and SX-2

- **80-column boot:** KdL's SX-2 sub-ROM resets width to 80 at every boot, breaking 37/40-column BASIC `LOCATE`/`PRINT` loaders; `width 37` in `sx2*.txt` fixes this.
- **`POKE &HFFFF,&HAA` (83 games):** Hardcodes MSX2 subslot 2 in every page; on SX-2 (RAM in `3-0` or `0-1`), the subslot-POKE patcher substitutes the machine's actual RAM subslot (`50h` when RAM shares slot 0 with main ROM so BASIC stays mapped).
- **`T0` sharing slot 3 with sub-ROM:** On `sx2`, DOS's mapper (`3-0`) and sub-ROM (`3-1`) share slot 3, so `T0` patches `CALSLT` (`t_s`/`t_c`) to switch subslots via page 3 without unmapping `T0` underneath itself.
- **Extra-Mapper (`sx2-extramapper-mcp`):** DOS and BASIC RAM sit in slot `0-1` beside main ROM (`0-0`), while SX2RES occupies slot `3-0`:
  - Capture skips setting RAM in all pages of slot 0 (which would map out main ROM).
  - 220 Spanish games (Opera Soft, Topo Soft, Dro Soft) share an `FC9Ah` tape trampoline that selects BIOS via `A8h` alone; the trampoline patcher converts it to slot 0's subslot register while preserving block XOR checksums and restoring the caller's original subslot (needed by *Budokan*, which enters with `54h` rather than `55h`).
  - *Gauntlet* overwrites `H.KEYI` (`FD9Ah`) 0.4 s after restore, motivating SX2RES calls from `T0` (`t_res`) and `rescall` wrappers (`rescall B45B`) for games that replace `0038h` in page 0 RAM.
  - *Thor*, *Knight Tyme*, *Map Game*, *Checkmate!*, *Finders Keepers*, and *Super MSX*/*Engesoft* loaders that probe primary slots for page 1 RAM patch their switches to slot 0's subslot register (`54h`/`55h`/`50h`) and update `SLTTBL` (`FCC5h`) when the game later calls `ENASLT`.
- **Open question:** The RAM-search patcher on a machine where found RAM lives in an expanded slot other than page 3's slot selects whichever subslot that slot's subslot register already holds.
