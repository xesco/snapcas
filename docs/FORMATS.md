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
| `state.txt` | One `name value` per line, values in hexadecimal, as below |
| `side1.cas` | Side 1 with the game file's `side1` patches and those of `patches.txt`, when there are any: the tape that the capture loads |
| `slots.txt` | The slot map: for each page of each slot and subslot, whether it holds RAM, ROM or nothing ([INTERNALS.md, Slot patches](INTERNALS.md#slot-patches)) |
| `patches.txt` | The slot patches on the tape that the capture found, as `patch` lines |
| `log.txt` | The logged events and the capture's decisions, in time order: each stop of the load with the screen's text, the key that continued it, each mapper's size, and how the snapshot was taken. Its last line names the `continue` key that worked |

| `state.txt` names | Source in `openMSX` |
|---|---|
| `af`, `bc`, `de`, `hl`, `af2`, `bc2`, `de2`, `hl2`, `ix`, `iy`, `sp`, `pc`, `i`, `im` | `reg` |
| `iff` | Bit 0 of `reg IFF`: 1 when interrupts are on |
| `a8`, `ppic` | `debug read` on ports A8h and AAh |
| `sub0` to `sub3`, `-` when not expanded | For a slot that `EXPTBL` marks expanded, the byte at FFFFh, inverted, read while page 3 selects that slot |
| `fc` to `ff`, `-` without a mapper | `MSX Memory Mapper I/O`: the values written, which each mapper masks to its size |
| `vdp0` to `vdp23`, `vdp32` to `vdp45` | `VDP regs`, which holds only 0 to 7 with an MSX1 VDP |
| `pal0` to `pal15` | `VDP palette` |
| `vramptr` | `VRAM pointer`, 14 bits, with bits 14 to 16 from register 14 |
| `vramwrite` | `VRAM access status`: 1 after a write setup, 0 after a read setup |
| `psg0` to `psg15`, `psgsel` | `PSG regs`, and the port A0h watchpoint |
| `tapepos`, `service` | The tape position in side 1, and 1 when the game gets the tape service |
| `tapetime`, `tapeside` | The player's position in seconds and its side, 1 or 2, for the non-standard blocks that the game has read ([INTERNALS.md, Tape files](INTERNALS.md#tape-files)) |

## T0's jump table

`build.py` checks that each entry of the BIOS's tape jump table jumps to its address
before it builds T0 ([INTERNALS.md, Tape service](INTERNALS.md#tape-service)):

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
segments after it. The code segment's fields are these:

| Offset | Size | Field |
|---|---|---|
| 0000h | 6 | Jumps to `TAPION` and `TAPIN` |
| 0006h | 3 | The tape position |
| 0009h | 3 | Side 1's end, which is side 2's start |
| 000Ch | 3 | Side 2's end, equal to side 1's end without a side 2 |
| 000Fh | 3 | Side 1's start |
| 0012h | 8 | The CAS header |
| 001Ah | 64 | The code segment, then the other tape segments, filled in by the restorer |
| 005Ah | 2 | The address of the game's value of VDP register 7: `RG7SAV`, F3E6h, when it equals the snapshot's register 7, otherwise 005Dh |
| 005Ch | 1 | The frames in 0.1 second: 5 when bit 7 of the ROM's byte 002Bh is set, for 50 Hz, otherwise 6 |
| 005Dh | 1 | The snapshot's VDP register 7 |
| 005Eh | 1 | The side that the tape position is on: 0 for side 1, 1 for side 2, set by `build.py` from the position at the snapshot |
| 005Fh | 2 | The address of the game's value of VDP register 1: `RG1SAV`, F3E0h, when it equals the snapshot's register 1, otherwise 0061h |
| 0061h | 1 | The snapshot's VDP register 1 |
| 0062h | 1 | Unused, 0 |
| 0063h | 1 | 1 when the tape has a side 2, set by `build.py` |
| 0064h | 3 | The tape position while `TAPIN` looks for a header |
| 0067h | 3 | Side 1's end before its padding, set by `build.py` when the tape has a side 2, otherwise side 1's end |
| 006Ah | 1 | The tape's mode, filled in by the restorer: 1 for the manual tape of `/M`, 0 for the automatic tape |
| 006Bh | | The routines, then the tape |

## The entry code's data

The entry code keeps its data in page 3, before its code:

| Address | Value |
|---|---|
| FCF6h | DOS's mapper's slot ID, filled in by the restorer |
| FCF7h | T0's segment, filled in by the restorer |
| FCF8h | The code segment, filled in by the restorer |
| FCF9h | The game's mapper register FCh, from `build.py`, or T0's segment when T0 replaces the ROM |
| FCFAh | 1 while the entry code runs, so that T0's `TAPIOF` and `TAPOOF` leave interrupts off |
| FCFBh | 1 while the manual tape is stopped ([INTERNALS.md, The manual tape](INTERNALS.md#the-manual-tape)): set by `build.py` when the motor is off at the snapshot, by `TAPIOF` and `STMOTR`, and when a read reaches a side's end |

## Image

All numbers are little-endian, and the CRC-16 is CRC-16/CCITT-FALSE: polynomial
1021h, initial value FFFFh, not reflected, no final XOR. The image holds 4,096 bytes
of header and tables, padded with zeros, then the data of each record in table
order, 16,384 bytes each, except a block of zeros, which holds none.

| Offset | Size | Field |
|---|---|---|
| 0 | 8 | `SNAPCAS4`, which changes when the image's format changes |
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
| 57 | 7 | Zero |
| 64 | 4 per record | Record table |
| 64 + 4 × records | 2 per port write | Port writes: port, value |

| Record byte | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| RAM page in a mapper | 1 | Slot ID | Page | Segment |
| RAM page not in a mapper | 2 | Slot ID | Page | 0 |
| Service segment: T0 first, then the tape in order | 3 | 0 | 0 | 0 |
| VRAM block | 4 | Block number, 0 to 7 | 0 | 0 |
| VRAM block of zeros | 5 | Block number, 0 to 7 | 0 | 0 |

## Tail

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

`SERVICE.BIN` starts with a table of its parts, and `build.py` reads only the parts
that it names:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | Version: 12. `build.py` stops with an error on any other |
| 1 | 1 | Number of parts |
| 2 | 4 per part | Each part's offset and length in the file, 2 bytes each |

The parts hold the code that `build.py` places, with the operands and the data that
`build.py` and the restorer fill in set to 0:

| Part | What it holds |
|---|---|
| 0 | The tail ([Tail](#tail)) |
| 1 | T0's stubs, for 19DDh to 1B44h ([INTERNALS.md, Tape service](INTERNALS.md#tape-service)) |
| 2 | The service's part of page 3, for FCE1h to FD88h |
| 3 | The code segment's data and routines, from 0000h, up to the tape's start |
| 4 | The addresses of `STMOTR`'s stub, of the tape position in the code segment, of the byte at FCF9h, of the marker's data in the code segment and of `e_sp` in page 3, with the most segments that the code segment and the tape can use, 2 bytes each |
| 5 | T0's routines and data without a part in page 3, for 19DDh to 1B44h ([INTERNALS.md, Without a part in page 3](INTERNALS.md#without-a-part-in-page-3)) |
| 6 | The addresses of T0's routines for the jump table's entries from 00E1h to 00F3h, in their order, then of T0's tape position, borrowed page and flash's data, and the most segments of the tape, 2 bytes each |
| 7 | The offsets in the file of the bytes that move with the part of page 3, 2 bytes each: the high bytes of the addresses in that part |

The Makefile assembles `src/service.asm` twice, with the part of page 3 at FCE1h and
at FBE1h, one page lower, and `tools/relocs.py` lists the bytes that differ as the
last part. They differ by exactly 1, and the assembly at FCE1h is the file.

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
2354 files use, and stops with an error at any other: 10h, 11h and 4Bh hold bytes,
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
