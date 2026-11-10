; SERVICE.BIN: the code that tools/build.py writes into images (docs/FORMATS.md,
; SERVICE.BIN). It is never run as it is: build.py and the restorer fill in
; the operands and the data that are 0 here.
;
; The file starts with its version and a table of its parts. build.py refuses
; a SERVICE.BIN whose version is not the one it expects.

        include "service.inc"

VERSION equ 15

        org 0

        db VERSION
        db 7                    ; number of parts
        dw tail, tail_end-tail          ; part 0: the tail
        dw t0_start, t0_end-t0_start    ; part 1: T0's stubs, for T0_CODE
        dw p3_start, p3_end-p3_start    ; part 2: page 3, for E_ENTRY
        dw code_start, code_end-code_start  ; part 3: the code segment
        dw t0m_start, t0m_end-t0m_start ; part 4: T0 without a part in page 3
        dw file_end, 0                  ; part 5: the symbols that this file exports
        dw file_end, 0                  ; part 6: the bytes that move with page 3.
                                        ; tools/relocs.py appends parts 5 and 6

; Fills with zeros up to an address, which the code before it must not pass.
        macro fill_to address
        assert $ <= address
        ds address-$,0
        endm

; The tail (FORMATS.md, Tail): the restore's last code, written below the game's
; stack pointer. It selects the game's memory in the worker's page and the slot
; register, writes the subslot register of DOS's mapper's slot when the worker
; could not, loads AF and SP, and jumps to the game.
tail:
.map:   ld a,0                  ; restorer: the worker's page's mapper register
.port:  out (0),a               ; restorer: FDh or FEh
.a8:    ld a,0                  ; restorer: the slot register
        out (0A8h),a
.sub:   ld a,0                  ; restorer: the subslot register of DOS's mapper
.ld:    nop                     ; restorer: LD (0FFFFh),A, when it is needed
        nop
        nop
.stack: ld sp,0                 ; build.py: the address of .af
        pop af
.sp:    ld sp,0                 ; build.py: the snapshot's SP
.ei:    nop                     ; build.py: EI when IFF1 is set
.pc:    jp 0                    ; build.py: the snapshot's PC
.af:    dw 0                    ; build.py: AF
tail_end:
; The restorer's fill_tail and build.py's place_tail write these bytes by
; service.inc's offsets.
        assert tail_end-tail = TAIL_SIZE
        assert tail.map+1-tail = TAIL_MAP && tail.port+1-tail = TAIL_PORT
        assert tail.a8+1-tail = TAIL_A8 && tail.sub+1-tail = TAIL_SUB
        assert tail.ld-tail = TAIL_LD && tail.stack-tail = TAIL_LD+3
        assert tail.stack+1-tail = TAIL_STACK && tail.sp+1-tail = TAIL_SP
        assert tail.ei-tail = TAIL_EI && tail.pc-tail = TAIL_JP
        assert tail.pc+1-tail = TAIL_PC && tail.af-tail = TAIL_AF

; ---- T0's stubs, over the BIOS's tape code from 19DDh to 1B44h ----
;
; They keep the BIOS's entry addresses, which the jump table at 00E1h to 00F0h
; jumps to (MSX Red Book, chapter 4), and each returns as the BIOS's routine
; does. TAPION and TAPIN run in the code segment, through tramp in page 3,
; because page 0 changes under it. TAPIOF and STMOTR run in page 3 too, where
; the entries share them. The rest of the range is free.

t0_start:
        disp T0_CODE

t_tapoof:                       ; 19DDh, TAPOOF: every register kept
        ei
        ret
t_stmotr:                       ; STMOTR, through the jump at 00F3h
        jp stmotr
        fill_to 19E9h
t_tapiof:                       ; 19E9h, TAPIOF
        jp tapiof
        fill_to 19F1h
t_tapoon:                       ; 19F1h, TAPOON: the tape cannot be written, so
        di                      ; it returns as the BIOS's does for CTRL+STOP,
        scf                     ; with carry and interrupts off
        ret
        fill_to 1A19h
t_tapout:                       ; 1A19h, TAPOUT: the same. The BIOS's leaves
        scf                     ; the interrupts as they are
        ret
        fill_to 1A63h
t_tapion:                       ; 1A63h, TAPION
        di
        ld hl,tapion
        jp tramp
        fill_to 1ABCh
t_tapin:                        ; 1ABCh, TAPIN
        di
        ld hl,tapin
        jp tramp
        fill_to T0_END
        ent
t0_end:

; ---- Page 3, from E_ENTRY to E_STACK, by default FCE1h to FD6Fh ----

p3_start:
        disp E_ENTRY
; The entries, one for each entry of the BIOS's tape jump table from 00E1h to
; 00F3h, with the same low bytes (MSX Red Book, chapter 4). Each is 3 bytes,
; so a game that changes the low byte of a call reaches the matching entry.
        jp e_tapion             ; xxE1h, TAPION
        jp e_tapin              ; xxE4h, TAPIN
        jp tapiof               ; xxE7h, TAPIOF
        assert $ = E_ENTRY+3*3
        di                      ; xxEAh, TAPOON, as t_tapoon
        scf
        ret
        scf                     ; xxEDh, TAPOUT, as t_tapout
        ret
        nop
        assert $ = E_ENTRY+5*3
        ei                      ; xxF0h, TAPOOF, as t_tapoof
        ret
        nop
        jp stmotr               ; xxF3h, STMOTR
        assert $ = E_SLOT
        db 0,0,0,0              ; E_SLOT, E_T0, E_CODE, E_FC
        assert $ = E_STOP
        db 0

; STMOTR and TAPIOF stop the manual tape, which waits for the player's key at
; the next read (INTERNALS.md, The manual tape). STMOTR with A = 1 starts the
; motor and leaves the tape as it is. The automatic tape ignores E_STOP. They
; run here for the entries and for T0's stubs, with the caller's registers,
; stack and interrupts, as the BIOS's do: STMOTR changes only AF, and TAPIOF
; keeps every register and enables interrupts.
stmotr:
        cp 1
        ret z
        ld a,1
        ld (E_STOP),a
        ret
tapiof:
        push af
        ld a,1
        ld (E_STOP),a
        pop af
        ei
        ret

; From the entries of TAPION and TAPIN, which return with interrupts off, as
; the BIOS's TAPION does: selects DOS's mapper in page 0, calls the code
; segment's routine at HL on the stack below E_STACK, and selects the game's
; page 0 again, with mapper register FCh at E_FC, and the game's stack. It
; returns what tramp returns, so that an entry and T0's stub of the same
; routine leave the same registers: a game can count on the B = 0 that the
; BIOS's TAPIN leaves (tape.inc, next_byte).
e_tapin:
        ld hl,tapin
        jr e_run
e_tapion:
        ld hl,tapion
e_run:
        di
        ld (e_sp),sp
        ld sp,E_STACK
        in a,(0A8h)
        ld (e_a8),a             ; the game's slot register
        and 0FCh
        ld b,a
        ld a,(E_SLOT)
        and 3
        or b
        out (0A8h),a
        call tramp              ; A is also in D
        ld a,(E_FC)
        out (0FCh),a
        ld a,(e_a8)
        out (0A8h),a
        ld a,d
        ld sp,(e_sp)
        ret

; From T0's stubs and from e_run, with HL a routine of the code segment and
; interrupts off: selects the code segment in page 0, calls the routine, and
; selects T0 again. It returns the routine's A, flags, BC and HL, with A also
; in D, where the BIOS's TAPIN leaves the byte too.
tramp:
        ld a,(E_CODE)
        out (0FCh),a
        call .routine
        ld d,a
        ld a,(E_T0)
        out (0FCh),a
        ld a,d
        ret
.routine:
        jp (hl)
; With C = FCh, D the byte's tape segment and B the code segment: selects the
; tape segment in page 0, reads the byte at HL into E, and selects the code
; segment again.
reader:
        out (c),d
        ld e,(hl)
        out (c),b
        ret

; e_run's scratch bytes and stack. Its deepest path takes 20 bytes of the
; stack: 4 for the calls of tramp and of the routine, and 16 in the code
; segment, where a read under the header's compare of TAPION or TAPIN, which
; keeps BC and HL, 4, calls next_byte, 2, which keeps DE, 2, and calls wrap,
; 2, whose flash keeps two values, 4, and calls vdp, 2. The manual tape's
; wait takes as much.
e_sp:   dw 0                    ; the game's stack pointer
e_a8:   db 0                    ; the game's slot register
        ds 22,0
E_STACK:
        ent
p3_end:
; At FCE1h, the part is inside the area that build.py wants at zero.
        assert E_STACK-E_ENTRY = p3_end-p3_start
        assert E_PAGE != 0FCh || (E_ENTRY >= P3_FREE && E_STACK-1 <= P3_FREE_END)

; ---- The code segment, which runs in page 0 with interrupts off ----
;
; Its data, then TAPION and TAPIN. The tape follows it: side 1, padded to a
; multiple of 8 bytes, then side 2. The position is the offset of the next
; byte, counted from the start of this segment.

code_start:
        disp 0
T0MODE  equ 0
        include "tape.inc"
        align 8,0               ; the tape starts at a multiple of 8
        ent
code_end:
; The restorer writes these by service.inc's places.
        assert D_SEGS = C_SEGS && D_MODE = C_MODE

; ---- T0 without a part in page 3, from 19DDh to 1B44h ----
;
; T0's data and routines, for a game whose page 3 has no room for the service
; (INTERNALS.md, Without a part in page 3). The game reaches T0 through DOS's
; mapper in page 0, where mapper register FCh holds T0, and build.py points the
; jump table's entries from 00E1h to 00F3h at the routines here.

t0m_start:
        module t0m
        disp T0_CODE
T0MODE  equ 1
        include "tape.inc"
; T0 has no room for the manual tape, so the tape is automatic in this mode
; (INTERNALS.md, The manual tape), and TAPIOF and STMOTR have nothing to stop.
; Each returns as the BIOS's routine does, as T0's stubs above.
tapiof:                         ; TAPIOF and TAPOOF
tapoof:
        ei
stmotr:                         ; STMOTR
        ret
tapoon:                         ; TAPOON: the tape cannot be written
        di
tapout:                         ; TAPOUT
        scf
        ret
        fill_to T0_END          ; within the BIOS's tape code
        ent
        endmodule
t0m_end:
; The restorer writes these by service.inc's places.
        assert t0m.D_SEGS = T_SEGS && t0m.D_PAGE = T_PAGE && t0m.D_PAGE_SLOT = T_PAGE+2

; tools/relocs.py appends the symbols and the offsets of the bytes that differ
; when P3_PAGE is FBh: the high bytes of the addresses in the page 3 part.
file_end:

; ---- The symbols that build.py reads by name (FORMATS.md, SERVICE.BIN) ----

; The tail's fields and the image's layout, from service.inc.
        export TAIL_PORT
        export TAIL_STACK
        export TAIL_SP
        export TAIL_EI
        export TAIL_JP
        export TAIL_PC
        export TAIL_AF
        export IMAGE_FORMAT
        export H_SIZE
        export DATA_SIZE
        export H_ROM
        export H_SUBROM
        export H_RECS
        export H_WRITES
        export H_FLAGS
        export H_P3
        export H_REGS
        export H_I
        export H_IM
        export H_IFF
        export H_A8
        export H_SUB
        export H_MAP
        export H_TAIL
        export H_VDP1
        export H_BORROW
        export H_NOEXP
        export H_TAILREC
        export H_P3REC
        export H_PLACES
        export H_TABLE
        export REC_SIZE
        export WRITE_SIZE
        export PLACE_SIZE
        export FLAG_ROM_KEEP
        export FLAG_T0
        export REC_MAPPER
        export REC_RAM
        export REC_SERVICE
        export REC_VRAM
        export REC_ZEROS

; The part of page 3 and the area that it takes by default.
        export E_PAGE
        export P3_FREE
        export P3_FREE_END
        export E_ENTRY
        export E_CODE
        export E_FC
        export E_STOP
        export e_sp
; T0: the BIOS's tape code and the stubs at its routines' addresses.
        export T0_CODE
        export T0_END
        export t_tapion
        export t_tapin
        export t_tapiof
        export t_tapoon
        export t_tapout
        export t_tapoof
        export t_stmotr
; The code segment's data.
        export SEGS_MAX
        export D_POS
        export D_S1END
        export D_TOTAL
        export D_START
        export D_BORDER
        export D_FRAMES
        export D_VDP7
        export D_SIDE
        export D_SCREEN
        export D_VDP1
        export D_TWO
        export D_S1REAL
; The code segment's two jumps of a tape at its last side's end, for the check.
        export wrap.one
        export wrap.two
; T0 without a part in page 3: its routines for the jump table, and its data.
        export t0m.tapion
        export t0m.tapin
        export t0m.tapiof
        export t0m.tapoon
        export t0m.tapout
        export t0m.tapoof
        export t0m.stmotr
        export T_SEGS_MAX
        export t0m.D_POS
        export t0m.D_S1END
        export t0m.D_TOTAL
        export t0m.D_START
        export t0m.D_PAGE_MASK
        export t0m.D_PAGE_PORT
        export t0m.D_PAGE_HIGH
        export t0m.D_PAGE_SEG
        export t0m.D_BORDER
        export t0m.D_FRAMES
        export t0m.D_VDP7
        export t0m.D_SIDE
        export t0m.D_SCREEN
        export t0m.D_VDP1
        export t0m.D_TWO
