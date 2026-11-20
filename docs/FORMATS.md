# Binary & File Formats

This reference specifies the byte-level formats shared by `tools/`, `SERVICE.BIN`, and `SNAPCAS.COM`: snapshot folders, `.SNP` images, the 26-byte tail, port writes, `SERVICE.BIN`, tape service tables, and `.CAS`/`.TSX` inputs. For the architectural rationale, see [DESIGN.md](DESIGN.md).

## Snapshot files

`tools/capture.py` writes a snapshot folder under `out/work/<machine>/<game>/snap/`:

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>-<seg>.bin` | 16 KB RAM dump per kept page (`ps` = primary slot, `ss` = subslot or `x`, `page` = 0–3, `seg` = mapper segment or `x`). |
| `rom.bin` | 32 KB main ROM (pages 0–1 from `EXPTBL`'s slot). |
| `subrom.bin` | 16 KB sub-ROM on MSX2/MSX2+ (from `EXBRSA`'s slot). |
| `vram.bin` | `physical VRAM` dump: 16 KB (MSX1) or 64/128 KB (V9938/V9958). On V9938+, bit 3 of R#8 (`VR`) is temporarily set during capture so `openMSX` exposes linear addressing. |
| `state.txt` | `name value` pairs in hex (fixed width), except `tapetime` in decimal seconds. |
| `side1.cas` | Patched Side 1 tape actually loaded by capture (only written when patches apply). |
| `slots.txt` | Slot map: `page <n> empty <slots\|-> with <slot\|-1>` ([Capture](internals/capture.md#slot-map)). |
| `patches.txt` | Automatic tape patches discovered during capture, in `patch` line format. |
| `log.txt` | Chronological log of load events, key retries, mapper sizes, snapshot trigger, and unpatched slot writes. |
| `error.txt` | Single-line error message if capture failed. |

### `state.txt` fields

| Key(s) | Source in `openMSX` |
|---|---|
| `af`, `bc`, `de`, `hl`, `af2`, `bc2`, `de2`, `hl2`, `ix`, `iy`, `sp`, `pc`, `i`, `im` | CPU registers (`reg`). |
| `iff` | Bit 0 of `reg IFF` (`1` = interrupts enabled). |
| `a8`, `ppic` | Ports `A8h` and `AAh`. |
| `sub0`–`sub3` | Inverted `FFFFh` for each expanded slot (`-` if unexpanded). |
| `fc`–`ff` | `MSX Memory Mapper I/O` values (`-` if no mapper). |
| `mapper<ps>-<ss>` | Segment count for each mapper holding a kept RAM page (register values are taken modulo this size). |
| `vdp0`–`vdp23`, `vdp32`–`vdp45`, `vdp25`–`vdp27` | VDP registers (0–7 on MSX1, 0–23 + 32–45 on V9938, plus 25–27 on V9958). |
| `pal0`–`pal15` | V9938/V9958 palette entries. |
| `vramptr`, `vramwrite` | 17-bit VRAM pointer (14-bit counter + R#14) and access mode (`1` = write, `0` = read). |
| `psg0`–`psg15`, `psgsel` | PSG registers and selected register (`A0h`). When R#7 bit 7 is 0 (port B input), `psg15` records the last value written to R#15 rather than floating pins (`FFh`). |
| `tapepos`, `service`, `tapetime`, `tapeside` | Tape offset in Side 1, whether tape service is needed (`1`/`0`), player time (s), and active side (`1`/`2`). |

## Image

All multi-byte integers are little-endian. CRC-16 uses CRC-16/CCITT-FALSE (polynomial `1021h`, init `FFFFh`, no reflection, no final XOR). An image starts with a 4,096-byte zero-padded header and table region, followed by record payloads in table order (16,384 bytes each, except type `5` zero-VRAM records which store 0 bytes). `src/service.inc` is the single source of truth for `H_*`, `REC_*`, and `FLAG_*` constants.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | Magic mark `SNAPCAS6` (last digit is `IMAGE_FORMAT`; bumped on header or service-segment layout changes) |
| 8 | 2 | CRC-16 of the 32 KB main ROM |
| 10 | 2 | CRC-16 of the 16 KB sub-ROM (`0` on MSX1) |
| 12 | 1 | Number of records (max 255) |
| 13 | 1 | Number of port writes (max 255) |
| 14 | 1 | Flags: bit 0 = `rom keep`, bit 1 = `service t0`, bit 2 = entry code has `sub0` |
| 15 | 1 | Page 3 entry page of the tape service (`FCh` default, `0` without page 3 part); entries start at `xxE1h` |
| 16 | 24 | CPU registers: `AF`, `BC`, `DE`, `HL`, `AF'`, `BC'`, `DE'`, `HL'`, `IX`, `IY`, `SP`, `PC` |
| 40 | 1 | `I` register |
| 41 | 1 | Interrupt mode (`IM`) |
| 42 | 1 | `IFF1` (`1` = interrupts enabled) |
| 43 | 1 | Primary slot register (`A8h`) |
| 44 | 4 | Subslot registers for slots 0–3 (`0` if unexpanded) |
| 48 | 4 | Mapper registers `FCh`–`FFh` |
| 52 | 2 | Tail address |
| 54 | 1 | Snapshot VDP register 1 |
| 55 | 1 | Borrowed page for `TAPIN` in `T0` mode (`1` or `2`), else `0` |
| 56 | 1 | Unexpanded-slot mask: bit `n` set when slot `n` was unexpanded at capture |
| 57 | 1 | Record index holding the tail |
| 58 | 1 | Record index holding the game's page 3 (with tape service), else `0` |
| 59 | 1 | Number of places (max 255) |
| 60 | 4 | Reserved (`0`) |
| 64 | 4 per record | Record table |
| 64 + 4 × records | 2 per port write | Port writes: `(port, value)` |
| After the port writes | 3 per place | Places: `(record_index, offset_lo, offset_hi)` |

### Record table entries

| Type | Byte 0 | Byte 1 | Byte 2 | Byte 3 |
|---|---|---|---|---|
| RAM page in a mapper | `1` | Slot ID | Page (0–3) | Segment |
| RAM page not in a mapper | `2` | Slot ID | Page (0–3) | `0` |
| Service segment (`T0` first, then code + tape segments) | `3` | `0` | `0` | `0` |
| VRAM block (16 KB) | `4` | Block (0–7) | `0` | `0` |
| VRAM block of all zeros (0 payload bytes) | `5` | Block (0–7) | `0` | `0` |

When a game maps one mapper segment into two pages, it appears once in the record table with the lower page number; bytes 57–58 identify the tail and page 3 records explicitly. Each **place** entry names a byte in RAM where `SNAPCAS.COM` writes the slot-register value selecting DOS's mapper in page 0 (used for `TAPION` stubs in `T0` mode).

## Tail

The tail is 26 bytes of code written below the game's `SP` and completed by `build.py` and `SNAPCAS.COM` (`TAIL_*` offsets in `src/service.inc`):

| Offset | Bytes | Instruction |
|---|---|---|
| 0 | `3E nn` | `LD A,nn` — snapshot mapper register for worker's page (restorer) |
| 2 | `D3 nn` | `OUT (nn),A` — worker's mapper port `FDh` or `FEh` (restorer) |
| 4 | `3E nn` | `LD A,nn` — snapshot slot register `A8h` (restorer) |
| 6 | `D3 A8` | `OUT (0A8h),A` |
| 8 | `3E nn` | `LD A,nn` — subslot register of DOS's mapper slot, if needed (restorer) |
| 10 | `32 FF FF` or `00 00 00` | `LD (0FFFFh),A` when needed, else `NOP × 3` (restorer) |
| 13 | `31 nn nn` | `LD SP,nnnn` — `tail_addr + 24` (`build.py`) |
| 16 | `F1` | `POP AF` |
| 17 | `31 nn nn` | `LD SP,nnnn` — snapshot `SP` (`build.py`) |
| 20 | `FB` or `00` | `EI` if `IFF1 = 1`, else `NOP` (`build.py`) |
| 21 | `C3 nn nn` | `JP nnnn` — snapshot `PC` (`build.py`) |
| 24 | 2 bytes | Snapshot `AF` (`build.py`) |

## Port writes

`tools/build.py` emits `(port, value)` pairs in fixed order:

1. **PSG (`A0h`/`A1h`):** Registers 0–15 (R#7 bits 7–6 forced to `10` = port A input, port B output), followed by `psgsel` to `A0h`.
2. **PPI (`AAh`):** Port C (`ppic`).
3. **V9938+ palette & command registers:** R#16 = `0`, 16 palette entries (2 bytes each) to `9Ah`, R#17 = `32`, then R#32–R#45 to `9Bh`.
4. **VDP registers (`99h`):** R#0–R#7 (MSX1) or R#0–R#23 (V9938), plus R#25–R#27 on V9958.
5. **VRAM pointer (`99h`):** Low byte, then high bits (`| 40h` for write mode). Read mode subtracts 1 to compensate for VDP read-ahead (decrementing R#14 first if the low 14 bits are 0).

## SERVICE.BIN

`bin/SERVICE.BIN` packages the Z80 payloads and exported symbols that `tools/build.py` embeds in `.SNP` images.

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | Version (`20`); `build.py` rejects any other version. |
| 1 | 1 | Part count (`9`). |
| 2 | 4 × parts | `(offset, length)` table (16-bit LE each). |

| Part | Contents |
|---|---|
| 0 | Tail (26 bytes). |
| 1 | `T0` BIOS stubs (`19DDh`–`1B44h`), plus `t_s`/`t_c` sub-ROM `CALSLT` helpers and `t_res` resident hook. |
| 2 | Page 3 service part (assembled at `FCE1h`–`FD7Eh`: 26-byte entries + data up to `E_STOP`, then 132-byte code block from `P3_CODE`). |
| 3 | Code segment header, data tables, and tape routines (`0000h` up to tape start). |
| 4 | `T0`-only tape service (`19DDh`–`1B44h`, no page 3 part). |
| 5 | Resident call routines (`res3`, `resb`, `res3g`, `resbg`, `res3e`, `resbe`) and `sub0`. |
| 6 | Sorted symbol table: `(value_u16, name_len_u8, ascii_name)`. |
| 7 | High-byte relocation offsets for moving the page 3 part (derived by assembling at `FCE1h` and `FBE1h`). |
| 8 | 16-bit relocation offsets for moving the page 3 code block independently (`tools/relocs.py`, third assembly shifted `+0111h`). |

## Tape service tables

### BIOS jump table checked for `T0`

| Entry | Routine | Expected target |
|---|---|---|
| `00E1h` | `TAPION` | `1A63h` |
| `00E4h` | `TAPIN` | `1ABCh` |
| `00E7h` | `TAPIOF` | `19E9h` |
| `00EAh` | `TAPOON` | `19F1h` |
| `00EDh` | `TAPOUT` | `1A19h` |
| `00F0h` | `TAPOOF` | `19DDh` |
| `0018h` | `OUTDO` | `1B45h` (first byte after tape code) |

### Code segment header (`0000h`–`0067h`)

| Offset | Size | Field |
|---|---|---|
| `0000h` | 3 | Current tape position (24-bit byte offset from code segment start) |
| `0003h` | 3 | Side 1 end (= Side 2 start) |
| `0006h` | 3 | Side 2 end (= Side 1 end if single-sided) |
| `0009h` | 3 | Side 1 start |
| `000Ch` | 8 | CAS header (`1F A6 DE BA CC 13 7D 74`) |
| `0014h` | 64 | Segment table (code segment + up to 63 tape segments, filled by restorer) |
| `0054h` | 1 | Mode (`1` = `/M` manual, `0` = automatic; filled by restorer) |
| `0055h` | 2 | Border register source (`RG7SAV` `F3E6h` if valid at snapshot, else `0058h`) |
| `0057h` | 1 | Frames per 0.1 s (`5` for 50 Hz, `6` for 60 Hz from ROM `002Bh` bit 7) |
| `0058h` | 1 | Snapshot VDP R#7 |
| `0059h` | 1 | Current side (`0` = Side 1, `1` = Side 2) |
| `005Ah` | 2 | VDP R#1 source (`RG1SAV` `F3E0h` if valid at snapshot, else `005Ch`) |
| `005Ch` | 1 | Snapshot VDP R#1 |
| `005Dh` | 1 | `1` if tape has Side 2 |
| `005Eh` | 3 | Saved position while `TAPIN` scans for a header |
| `0061h` | 3 | Side 1 end before padding |
| `0064h` | 4 | Manual-tape restart address and `SP` after `GRAPH`/`CODE` |
| `0068h` | — | Tape routines, then 8-byte-aligned tape data |

In `T0`-only mode (`19DDh`), the segment table holds up to 16 tape segments, fields after `005Dh` are omitted, and 6 borrowed-page bytes replace the manual-mode byte (saved `A8h`, page mask, DOS mapper slot bits, mapper port `FDh`/`FEh`, page high address byte, game's segment).

### Page 3 entry data (`xxF6h`–`xxFAh`)

| Offset | Field |
|---|---|
| `xxF6h` (`E_SLOT`) | DOS's mapper slot ID (restorer) |
| `xxF7h` (`E_T0`) | `T0` segment (restorer) |
| `xxF8h` (`E_CODE`) | Code segment (restorer) |
| `xxF9h` (`E_FC`) | Game's `FCh` register (`build.py`) or `T0` segment (restorer) |
| `xxFAh` (`E_STOP`) | `1` while manual tape is stopped |

## CAS and TSX

- **CAS (`tools/cas.py`):** Sequence of blocks prefixed by `1F A6 DE BA CC 13 7D 74` (matched at any byte offset, not only multiples of 8, since some compilations omit padding). First-block header bytes identify the default load command: `D0h` (`BLOAD"CAS:",R`), `D3h` (`CLOAD`), `EAh` (`RUN"CAS:"`).
- **TSX (`tools/tsx.py`):** TZX 1.20 (`ZXTape!\x1A` + 2-byte version) plus MSX block `4Bh`. Supports all 12 block types used across the 2,354-tape TSX collection (`10h`, `11h`, `12h`, `13h`, `15h`, `20h`, `21h`, `22h`, `30h`, `32h`, `35h`, `4Bh`), timing pulses in 3.5 MHz T-states. A `4Bh` block is treated as BIOS-standard when byte `0Eh` is `24h`, byte `0Fh` specifies 1 start bit (`0`), ≥2 stop bits (`1`), LSB first, 1-bit pulses are half of 0-bit pulses, and 0-bit timing lies within ±15% of 1200–2400 baud.
