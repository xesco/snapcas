# Formats

This page defines the files and the memory layouts that the tools and the restorer
share, byte by byte: the snapshot's files, the image, the tape service's tables and
the tape files' formats. Why each holds what it holds is in [DESIGN.md](DESIGN.md).

## Snapshot files

| File | Contents |
|---|---|
| `ram/<ps>-<ss>-<page>-<seg>.bin` | 16 KB for each RAM page kept, by primary slot, subslot (`x` when not expanded), page and segment (`x` when not in a mapper) |
| `rom.bin` | 32 KB: pages 0 and 1 of the main ROM, from the slot that `EXPTBL` names |
| `subrom.bin` | 16 KB on an MSX2: the sub-ROM, from the slot that `EXBRSA` names |
| `vram.bin` | The `physical VRAM` debuggable: 16 KB with an MSX1 VDP, 64 or 128 KB with a V9938. With a V9938, the capture reads it with bit 3 of register 8, VR, set for the read, because `openMSX` shows it through VR's addressing: a game that clears VR, as Boulder Dash does with an MSX1 write to register 8, would otherwise give a view that the restorer's linear writes do not reproduce |
| `state.txt` | One `name value` per line, as below. The values are in hexadecimal, each with all the digits of its width, except `tapetime`, which is in decimal |
| `side1.cas` | Side 1 with the game file's `side1` patches and those of `patches.txt`, when there are any: the tape that the capture loads |
| `slots.txt` | The slot map, one line for each page, `page <n> empty <slots> with <slot>`: the primary slots that hold nothing in that page, with commas between them, or `-` for none, and the slot that replaces them in a slot register value, or -1 ([INTERNALS.md, Slot patches](INTERNALS.md#slot-patches)) |
| `patches.txt` | The slot patches on the tape that the capture found, as `patch` lines |
| `log.txt` | The logged events and the capture's decisions, in time order: each stop of the load with the screen's text, the key that continued it, each mapper's size, and how the snapshot was taken. A capture that stops with an error logs the error with the screen's text, as the last of these lines. The log's last line then names the `continue` key that worked |
| `error.txt` | The error of a capture that stopped with one, on one line |

| `state.txt` names | Source in `openMSX` |
|---|---|
| `af`, `bc`, `de`, `hl`, `af2`, `bc2`, `de2`, `hl2`, `ix`, `iy`, `sp`, `pc`, `i`, `im` | `reg` |
| `iff` | Bit 0 of `reg IFF`: 1 when interrupts are on |
| `a8`, `ppic` | `debug read` on ports A8h and AAh |
| `sub0` to `sub3`, `-` when not expanded | For a slot that `EXPTBL` marks expanded, the byte at FFFFh, inverted, read while page 3 selects that slot |
| `fc` to `ff`, `-` without a mapper | `MSX Memory Mapper I/O`: the values written, which each mapper masks to its size |
| `mapper<ps>-<ss>`, one for each mapper that holds a kept RAM page | The mapper's size in segments, for the mapper in primary slot `<ps>` and subslot `<ss>` (`x` when not expanded), as in the RAM pages' file names. A register of `fc` to `ff` selects the segment that is its value modulo this size. A snapshot of an older capture has no such line, and the build then takes the register's value as the segment |
| `vdp0` to `vdp23`, `vdp32` to `vdp45` | `VDP regs`, which holds only 0 to 7 with an MSX1 VDP |
| `pal0` to `pal15` | `VDP palette` |
| `vramptr` | `VRAM pointer`, 14 bits, with bits 14 to 16 from register 14 |
| `vramwrite` | `VRAM access status`: 1 after a write setup, 0 after a read setup |
| `psg0` to `psg15`, `psgsel` | `PSG regs`, and the port A0h watchpoint. While register 7's bit 7 is clear, I/O port B is an input and register 15 reads its pins, FFh, so `psg15` is then the last value written to it, from the port A1h watchpoint |
| `tapepos`, `service` | The tape position in side 1, and 1 when the game gets the tape service |
| `tapetime`, `tapeside` | The player's position in seconds, in decimal with two decimals, and its side, 1 or 2, for the non-standard blocks that the game has read ([INTERNALS.md, Tape files](INTERNALS.md#tape-files)) |

## T0's jump table

`build.py` checks that each entry of the BIOS's tape jump table jumps to its address
before it builds T0 ([INTERNALS.md, Tape service](INTERNALS.md#tape-service)). The
addresses are those of T0's stubs, which `build.py` reads from `SERVICE.BIN`'s
symbols ([SERVICE.BIN](#servicebin)):

| Entry | Routine | Address it must jump to |
|---|---|---|
| 00E1h | `TAPION` | 1A63h |
| 00E4h | `TAPIN` | 1ABCh |
| 00E7h | `TAPIOF` | 19E9h |
| 00EAh | `TAPOON` | 19F1h |
| 00EDh | `TAPOUT` | 1A19h |
| 00F0h | `TAPOOF` | 19DDh, the start of the tape code |
| 0018h | `OUTDO` | 1B45h, the first byte after the tape code |

## The code segment

The code segment holds the service's data, its routines and then the tape, which
starts at a multiple of 8 bytes. The tape position and the sides' starts and ends
count bytes from the code segment's start, across the code segment and the tape
segments after it. `src/tape.inc` declares the data once, for the code segment and
for T0 in the mode without a part in page 3
([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)),
and `build.py` finds each field by its name ([SERVICE.BIN](#servicebin)). The code
segment's fields are these:

| Offset | Size | Field |
|---|---|---|
| 0000h | 3 | The tape position |
| 0003h | 3 | Side 1's end, which is side 2's start |
| 0006h | 3 | Side 2's end, equal to side 1's end without a side 2 |
| 0009h | 3 | Side 1's start |
| 000Ch | 8 | The CAS header |
| 0014h | 64 | The code segment, then the other tape segments, filled in by the restorer |
| 0054h | 1 | The tape's mode, filled in by the restorer: 1 for the manual tape of `/M`, 0 for the automatic tape |
| 0055h | 2 | The address of the game's value of VDP register 7: `RG7SAV`, F3E6h, when it equals the snapshot's register 7, otherwise 0058h |
| 0057h | 1 | The frames in 0.1 second: 5 when bit 7 of the ROM's byte 002Bh is set, for 50 Hz, otherwise 6 |
| 0058h | 1 | The snapshot's VDP register 7 |
| 0059h | 1 | The side that the tape position is on: 0 for side 1, 1 for side 2, set by `build.py` from the position at the snapshot |
| 005Ah | 2 | The address of the game's value of VDP register 1: `RG1SAV`, F3E0h, when it equals the snapshot's register 1, otherwise 005Ch |
| 005Ch | 1 | The snapshot's VDP register 1 |
| 005Dh | 1 | 1 when the tape has a side 2, set by `build.py` |
| 005Eh | 3 | The tape position while `TAPIN` looks for a header |
| 0061h | 3 | Side 1's end before its padding, set by `build.py` when the tape has a side 2, otherwise side 1's end |
| 0064h | 4 | Where a read of the manual tape starts again after GRAPH or CODE, and its stack pointer |
| 0068h | | The routines, then the tape |

In the mode without a part in page 3, T0 holds the same fields from 19DDh, in the
same order, with three differences. The table of segments holds 16 segments, all of
them the tape's. T0 has no field after the byte that says whether the tape has a
side 2. In place of the tape's mode, after the table of segments, T0 holds 6 bytes
for the page that `TAPIN` borrows:

| Byte | What it holds |
|---|---|
| 1 | The game's slot register value, while `TAPIN` borrows the page |
| 2 | The mask that clears the page's bits in a slot register value |
| 3 | The slot of DOS's mapper in the page's bits, filled in by the restorer |
| 4 | The port of the page's mapper register, FDh or FEh |
| 5 | The high byte of the page's first address |
| 6 | The game's segment in the page |

## The entry code's data

The service's part of page 3 keeps its data after its entries, before its code:

| Address | Value |
|---|---|
| FCF6h | DOS's mapper's slot ID, filled in by the restorer |
| FCF7h | T0's segment, filled in by the restorer |
| FCF8h | The code segment, filled in by the restorer |
| FCF9h | The game's mapper register FCh, from `build.py`, or T0's segment when T0 replaces the ROM |
| FCFAh | 1 while the manual tape is stopped ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)): set by `build.py` when the motor is off at the snapshot, by `TAPIOF` and `STMOTR`, and when a read reaches a side's end |

The restorer writes the first three bytes, and the fourth when T0 replaces the ROM,
one after the other, so `src/service.inc` asserts their order.

## Image

All numbers are little-endian, and the CRC-16 is CRC-16/CCITT-FALSE: polynomial
1021h, initial value FFFFh, not reflected, no final XOR. The image holds 4,096 bytes
of header and tables, padded with zeros, then the data of each record in table
order, 16,384 bytes each, except a block of zeros, which holds none. A record's
number is its place in the record table, from 0. `src/service.inc` defines this
layout once, under names that start with `H_`, `REC_` and `FLAG_`. The restorer is
assembled with these names, and `build.py` reads them from `SERVICE.BIN`'s symbols
([SERVICE.BIN](#servicebin)).

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | The mark: `SNAPCAS6`. Its last character is the format's number, which changes when the image's format changes, and when the places change where the restorer writes in the image's service segments ([The code segment](#the-code-segment)) |
| 8 | 2 | CRC-16 of the main ROM's 32 KB |
| 10 | 2 | CRC-16 of the sub-ROM's 16 KB, or 0 on an MSX1 |
| 12 | 1 | Number of records |
| 13 | 1 | Number of port writes |
| 14 | 1 | Flags: bit 0 set for `rom keep`, bit 1 for `service t0` ([FILES.md, Game file](FILES.md#game-file)) |
| 15 | 1 | The page of the tape service's part of page 3, whose entries start at E1h of it: FCh unless it moved, or 0 without the tape service |
| 16 | 24 | AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC |
| 40 | 1 | I |
| 41 | 1 | Interrupt mode |
| 42 | 1 | IFF1: 1 when interrupts are on |
| 43 | 1 | Slot register |
| 44 | 4 | Subslot registers of slots 0 to 3, 0 when not expanded |
| 48 | 4 | Mapper registers FCh to FFh |
| 52 | 2 | Tail address |
| 54 | 1 | The snapshot's VDP register 1 |
| 55 | 1 | Without a part in page 3, the page that `TAPIN` borrows, 1 or 2, otherwise 0 |
| 56 | 1 | Bit n set when slot n is not expanded in the capture |
| 57 | 1 | The number of the record that holds the tail |
| 58 | 1 | With the tape service, the number of the record that holds the game's page 3, otherwise 0 |
| 59 | 1 | Number of places |
| 60 | 4 | Zero |
| 64 | 4 per record | Record table |
| 64 + 4 × records | 2 per port write | Port writes: port, value |
| After the port writes | 3 per place | Places: the record's number, then the offset in the record's data, 2 bytes |

| Record byte | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| RAM page in a mapper | 1 | Slot ID | Page | Segment |
| RAM page not in a mapper | 2 | Slot ID | Page | 0 |
| Service segment: T0 first, then the tape in order | 3 | 0 | 0 | 0 |
| VRAM block | 4 | Block number, 0 to 7 | 0 | 0 |
| VRAM block of zeros | 5 | Block number, 0 to 7 | 0 | 0 |

The header holds each table's length in one byte, so an image has at most 255
records, 255 port writes and 255 places, and a record's number is at most 254.

A game can select one mapper segment in two pages. The segment has one record, with
the lower of the two pages in its page byte. So the restorer does not find the tail
and the game's page 3 by a record's page byte. The header names the two records, in
its bytes 57 and 58.

A place is a byte in a RAM page, and the byte's value depends on the machine that
restores the image. The restorer writes into each place the slot register value that
selects DOS's mapper in page 0. That value is the header's slot register value with
the primary slot of DOS's mapper in the bits of page 0. `build.py` lists a place for
each stub of `TAPION` that it patches in the mode without a part in page 3
([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)).

## Tail

The tail is 26 bytes of code that the restorer and `build.py` complete.
`src/service.inc` names the offsets of the bytes that they fill in, as `TAIL_MAP` to
`TAIL_AF`, and `src/service.asm` checks these offsets against the tail's code.

| Offset | Bytes | Instruction |
|---|---|---|
| 0 | `3E nn` | `LD A,nn`: the snapshot's value of the worker's page's mapper register, filled in by the restorer |
| 2 | `D3 nn` | `OUT (nn),A`: FDh or FEh, filled in by the restorer |
| 4 | `3E nn` | `LD A,nn`: the slot register, filled in by the restorer |
| 6 | `D3 A8` | `OUT (0A8h),A` |
| 8 | `3E nn` | `LD A,nn`: the subslot register of DOS's mapper's slot, filled in by the restorer when the tail writes it |
| 10 | `32 FF FF` or `00 00 00` | `LD (0FFFFh),A` when the tail writes that register, otherwise three `NOP`s |
| 13 | `31 nn nn` | `LD SP,nnnn`: the tail's address plus 24 |
| 16 | `F1` | `POP AF` |
| 17 | `31 nn nn` | `LD SP,nnnn`: the snapshot's SP |
| 20 | `FB` or `00` | `EI` when IFF1 is set, otherwise `NOP` |
| 21 | `C3 nn nn` | `JP nnnn`: the snapshot's PC |
| 24 | 2 bytes | AF |

## Port writes

`build.py` lists the writes in this order:

1. For each PSG register from 0 to 15, its number to port A0h and its value to port
   A1h, with register 7's bits 7 and 6 forced to 1 and 0, then `psgsel` to port A0h.
2. PPI port C to port AAh.
3. On a V9938: 0 to register 16, the 16 palette entries to port 9Ah, 2 bytes each in
   the order that the `VDP palette` debuggable holds them, red and blue first, then
   32 to register 17, for auto-increment, and registers 32 to 45 to port 9Bh.
4. VDP registers 0 to 7, or 0 to 23, to port 99h, as a value and 80h plus the
   register's number.
5. The VRAM pointer to port 99h: its low byte, then its high bits with 40h for a
   write setup. A read setup writes the pointer minus 1, because the VDP reads ahead
   and advances the pointer. When the pointer's low 14 bits are 0, register 14 is
   written again first, with its value minus 1.

## SERVICE.BIN

`SERVICE.BIN` starts with a table of its parts:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | Version: 15. `build.py` stops with an error on any other |
| 1 | 1 | Number of parts: 7 |
| 2 | 4 per part | Each part's offset and length in the file, 2 bytes each |

The first five parts hold the code that `build.py` places, with the operands and the
data that `build.py` and the restorer fill in set to 0:

| Part | What it holds |
|---|---|
| 0 | The tail ([Tail](#tail)) |
| 1 | T0's stubs, for 19DDh to 1B44h ([INTERNALS.md, Tape service](INTERNALS.md#tape-service)) |
| 2 | The service's part of page 3, for FCE1h to FD6Fh |
| 3 | The code segment's data and routines, from 0000h, up to the tape's start |
| 4 | T0's data and routines without a part in page 3, for 19DDh to 1B44h ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)) |
| 5 | The symbols: for each, in the order of their names, its value in 2 bytes, its name's length in 1 byte, and its name in ASCII |
| 6 | The offsets in the file of the bytes that move with the part of page 3, 2 bytes each: the high bytes of the addresses in that part, those of part 5's symbols among them |

The symbols are the only source of the service's addresses for `build.py`, which
looks each one up by its name. They are the labels and constants that
`src/service.asm` names in its `EXPORT` lines, under the names of the assembly:

| Symbols | What they are |
|---|---|
| `E_PAGE`, `E_ENTRY`, `E_CODE`, `E_FC`, `E_STOP`, `e_sp` | The page of the part of page 3, its first entry, three of its data bytes ([The entry code's data](#the-entry-codes-data)), and its first scratch byte, where the check's watch ends |
| `P3_FREE`, `P3_FREE_END` | FCC9h and FD88h: the area that must be zero for the part to stay at FCE1h |
| `T0_CODE`, `T0_END` | 19DDh and 1B45h: the BIOS's tape code in T0, and the first byte after it |
| `t_tapion`, `t_tapin`, `t_tapiof`, `t_tapoon`, `t_tapout`, `t_tapoof`, `t_stmotr` | T0's stubs. The first six are at the addresses that the ROM's jump table must hold ([T0's jump table](#t0s-jump-table)), and the last is where `build.py` points the entry 00F3h |
| `D_POS`, `D_S1END`, `D_TOTAL`, `D_START`, `D_S1REAL`, `D_BORDER`, `D_FRAMES`, `D_VDP7`, `D_SIDE`, `D_SCREEN`, `D_VDP1`, `D_TWO`, `SEGS_MAX` | The code segment's fields that `build.py` fills in ([The code segment](#the-code-segment)), and the most segments of the code segment and the tape |
| `wrap.one`, `wrap.two` | The code segment's two jumps that leave the end of the tape's last side, for a tape of one side and for side 2, where the check learns that the game has read the tape to its end ([INTERNALS.md, Check](INTERNALS.md#check)) |
| The names that start with `t0m.`, and `T_SEGS_MAX` | The same for T0 without a part in page 3: its routines for the jump table's entries, as `t0m.tapion`, its fields, with those of the borrowed page, as `t0m.D_PAGE_MASK`, and the most segments of the tape |
| `TAIL_PORT`, `TAIL_STACK`, `TAIL_SP`, `TAIL_EI`, `TAIL_JP`, `TAIL_PC`, `TAIL_AF` | The offsets in the tail of the bytes that `build.py` fills in, and of the two that the check reads: the port of the worker's page's mapper register, and the jump to the game ([Tail](#tail)) |
| `IMAGE_FORMAT`, `H_SIZE`, `DATA_SIZE`, the names that start with `H_`, `REC_SIZE`, `WRITE_SIZE`, `PLACE_SIZE` | The image's layout: the format's number as the mark's last character, the header's 4,096 bytes, a record's 16,384 bytes of data, each header field's offset, and the size of an entry of each table ([Image](#image)) |
| `FLAG_ROM_KEEP`, `FLAG_T0` | The bits of the header's flags: 1 and 2 |
| `REC_MAPPER`, `REC_RAM`, `REC_SERVICE`, `REC_VRAM`, `REC_ZEROS` | The record types, 1 to 5 |

The Makefile assembles `src/service.asm` twice, with the part of page 3 at FCE1h and
at FBE1h, one page lower. `tools/relocs.py` appends each assembly's symbols as part
5, and then lists the bytes that differ between the two assemblies as the last part.
These bytes differ by exactly 1, and the assembly at FCE1h is the file. `build.py`
moves the part by adding the difference of the pages to each listed byte, so a
symbol in the part has the moved part's address.

## CAS data

A CAS file is a sequence of blocks, each starting with the 8-byte header
`1F A6 DE BA CC 13 7D 74`. Most files put each header at an offset that is a
multiple of 8, but 105 tapes of the test collection do not pad their blocks, among
them Engesoft's and the Super MSX magazine's, and `openMSX` and `tools/cas.py` find
a header at any offset. A file's first block holds 10 bytes of its type and a 6-byte
name: D0h for a binary file loaded with `BLOAD"CAS:",R`, D3h for a BASIC program
loaded with `CLOAD`, and EAh for an ASCII program loaded with `RUN"CAS:"`. The
capture stops with an error when the first block has none of these types. The tape
position is an offset in the tape service's tape ([INTERNALS.md, Tape files](INTERNALS.md#tape-files)).

## TSX data

A TSX file is a TZX file, the tape format of the ZX Spectrum, with a block of its
own for MSX, 4Bh (the makeTSX project's tutorial,
github.com/nataliapc/makeTSX/wiki). It starts with `ZXTape!`, 1Ah and a 2-byte
version, and then holds blocks, each an ID byte and its body (TZX format 1.20,
worldofspectrum.net/TZXformat.html). `tools/tsx.py` reads the 12 blocks that the
2354 files use, and stops with an error at any other, and at a block that the file's
end cuts, with the block's offset: 10h, 11h and 4Bh hold bytes,
15h a recording of the signal, 12h, 13h and 20h pulses and pauses, and 21h, 22h,
30h, 32h and 35h groups and text. It counts each block's pulses and pauses in
T-states of 3.5 MHz, the TZX format's clock, for the block's time, and the times end
where `openMSX` ends the tape, within 0.01 seconds. Block 4Bh's body holds these
fields:

| Offset | Size | Field |
|---|---|---|
| 00h | 4 | The body's length after this field |
| 04h | 2 | The pause after the block, in milliseconds |
| 06h | 2 | The length of a pilot pulse, in T-states |
| 08h | 2 | The number of pilot pulses: 30720 for a header's long tone at 1200 baud, 7680 for a data block's short one |
| 0Ah | 2 | The length of a pulse of a 0 bit, in T-states |
| 0Ch | 2 | The length of a pulse of a 1 bit, in T-states |
| 0Eh | 1 | The pulses of a 0 bit in the high 4 bits, and of a 1 bit in the low 4 |
| 0Fh | 1 | The start bits, their value, the stop bits, their value and the bit order: 54h for 1 start bit 0, 2 stop bits 1 and bit 0 first |
| 10h | | The bytes |

A 4Bh block in the BIOS's format is a standard block: 24h at 0Eh, 1 start bit 0, 2
or more stop bits 1 and bit 0 first at 0Fh, a 1 bit's pulse half a 0 bit's, and a 0
bit's pulse from that of 2400 baud less 15% to that of 1200 baud plus 15%. TAPION
measures the header's tone to set its timing, so it reads the tapes that were
recorded between the two speeds, and TAPIN waits for each start bit, so it reads
After Burner's side B, whose blocks have 3 stop bits. Pico Pico's tape, recorded at
about 1660 baud, loads through TAPION to its end in the capture. Any other block
that holds bytes is a non-standard block. Of the 2354 TSX files above, 2027 hold
only standard blocks, and their bytes are those of the collection's CAS files for
the 792 tapes that both hold.
