; SERVICE.BIN: the code that tools/build.py writes into images (docs/DESIGN.md,
; SERVICE.BIN). It is never run as it is: build.py and the restorer fill in
; the operands and the data that are 0 here.
;
; The file starts with its version and a table of its parts. build.py refuses
; a SERVICE.BIN whose version is not the one it expects.

        include "service.inc"

VERSION equ 11

        org 0

        db VERSION
        db 8                    ; number of parts
        dw tail, tail_end-tail          ; part 0: the tail
        dw t0_start, t0_end-t0_start    ; part 1: T0's stubs, for 19DDh
        dw p3_start, p3_end-p3_start    ; part 2: page 3, for E_ENTRY
        dw code_start, code_end-code_start  ; part 3: the code segment
        dw fields, fields_end-fields    ; part 4: places for build.py
        dw t0m_start, t0m_end-t0m_start ; part 5: T0 without a part in page 3
        dw t0m_fields, t0m_fields_end-t0m_fields  ; part 6: its places
        dw relocs, 0                    ; part 7: the bytes that move with page 3,
                                        ; which tools/relocs.py appends

; The tail (DESIGN.md, Tail): the restore's last code, written below the game's
; stack pointer. It selects the game's memory in the worker's page and the slot
; register, writes the subslot register of DOS's mapper's slot when the worker
; could not, loads AF and SP, and jumps to the game.
tail:
        ld a,0                  ; restorer: the worker's page's mapper register
        out (0),a               ; restorer: FDh or FEh
        ld a,0                  ; restorer: the slot register
        out (0A8h),a
        ld a,0                  ; restorer: the subslot register of DOS's mapper
        nop                     ; restorer: LD (0FFFFh),A, when it is needed
        nop
        nop
        ld sp,0                 ; build.py: the tail's address plus 24
        pop af
        ld sp,0                 ; build.py: the snapshot's SP
        nop                     ; build.py: EI when IFF1 is set
        jp 0                    ; build.py: the snapshot's PC
        dw 0                    ; build.py: AF
tail_end:

; ---- T0's stubs, over the BIOS's tape code from 19DDh to 1B44h ----
;
; They keep the BIOS's entry addresses, which the jump table at 00E1h to 00F0h
; jumps to (MSX Red Book, chapter 4). TAPION and TAPIN run in the code
; segment, through tramp in page 3, because page 0 changes under it. The rest
; of the range is free.

t0_start:
        disp 19DDh

t_tapoof:                       ; 19DDh, TAPOOF
        jr tapoof
t_stmotr:                       ; STMOTR, through the jump at 00F3h
        jr stmotr
        ds 19E9h-$,0
t_tapiof:                       ; 19E9h, TAPIOF
        jr tapiof
        ds 19F1h-$,0
t_tapoon:                       ; 19F1h, TAPOON: the tape cannot be written
        scf
        ret
        ds 1A19h-$,0
t_tapout:                       ; 1A19h, TAPOUT: the tape cannot be written
        scf
        ret
; STMOTR and TAPIOF stop the manual tape, which waits for the player's key at
; the next read (DESIGN.md, The manual tape). STMOTR with A = 1 starts the
; motor and leaves it. The automatic tape ignores E_STOP.
stmotr:
        cp 1
        ret z
        ld a,1
        ld (E_STOP),a
        ret
tapiof:
        ld a,1
        ld (E_STOP),a
tapoof:
        ld a,(E_INSIDE)         ; the entry code enables interrupts itself
        or a
        ret nz
        ei
        ret
        ds 1A63h-$,0
t_tapion:                       ; 1A63h, TAPION
        di
        xor a                   ; c_tapion
        jp tramp
        ds 1ABCh-$,0
t_tapin:                        ; 1ABCh, TAPIN
        di
        ld a,3                  ; c_tapin
        jp tramp
        ds 1B45h-$,0
        ent
t0_end:

; ---- Page 3, from E_ENTRY to E_STACK, by default FCE1h to FD88h ----

p3_start:
        disp E_ENTRY
; The entries, one for each entry of the BIOS's tape jump table from 00E1h to
; 00F3h, with the same low bytes: TAPION, TAPIN, TAPIOF, TAPOON, TAPOUT,
; TAPOOF and STMOTR (MSX Red Book, chapter 4). A game that changes the low
; byte of a call reaches the matching entry.
        rept 7
        call e_entry
        endr
        assert $ = E_SLOT
        db 0,0,0,0,0,0          ; E_SLOT, E_T0, E_CODE, E_FC, E_INSIDE, E_STOP

; From an entry: the entry's low byte, which is its jump table entry's, from
; the return address, with the game's HL kept and its A, STMOTR's argument,
; passed on.
e_entry:
        ld (e_arg),a
        ex (sp),hl
        ld a,l
        pop hl
        sub 3
; Selects DOS's mapper and T0 in page 0, calls T0's jump table entry A, and
; selects the game's page 0 again, with mapper register FCh at E_FC. After
; TAPIOF and TAPOOF it enables interrupts, as the BIOS's do.
e_call:
        di
        ld (.call+1),a
        cp 0E7h
        jr z,.ei
        cp 0F0h
.ei:
        ld a,0                  ; NOP
        jr nz,.keep
        ld a,0FBh               ; EI
.keep:
        ld (.end),a
        ld (e_sp),sp
        ld sp,E_STACK
        ld a,1
        ld (E_INSIDE),a
        in a,(0A8h)
        ld (e_a8),a
        and 0FCh
        ld b,a
        ld a,(E_SLOT)
        and 3
        or b
        out (0A8h),a
        ld a,(E_T0)
        out (0FCh),a
        ld a,(e_arg)
.call:
        call 0
        push af
        ld a,(E_FC)
        out (0FCh),a
        ld a,(e_a8)
        out (0A8h),a
        xor a
        ld (E_INSIDE),a
        pop af
        ld sp,(e_sp)
.end:
        nop                     ; EI after TAPIOF and TAPOOF
        ret

; Called from T0 with A a routine's offset in the code segment: selects the
; code segment in page 0, calls the routine, and selects T0 again, with the
; routine's AF. Interrupts stay off, as in the BIOS's TAPION and TAPIN.
tramp:
        ld (.call+1),a
        ld a,(E_CODE)
        out (0FCh),a
.call:
        call 0
        push af
        ld a,(E_T0)
        out (0FCh),a
        pop af
        ret
; With C = FCh, D the byte's tape segment and B the code segment: selects the
; tape segment in page 0, reads the byte at HL into E, and selects the code
; segment again.
reader:
        out (c),d
        ld e,(hl)
        out (c),b
        ret

e_sp:   dw 0
e_a8:   db 0
e_arg:  db 0
        assert $ <= E_STACK-24  ; the stack, for T0 and the code segment
        ds E_STACK-$,0
        ent
p3_end:

; ---- The code segment, which runs in page 0 with interrupts off ----
;
; TAPION and TAPIN behave as the BIOS's: carry clear on success, set when
; CTRL+STOP is held. The tape follows the code: side 1 from C_START, padded
; to a multiple of 8 bytes, then side 2. The position is the offset of the
; next byte, counted from the start of this segment.

code_start:
        disp 0
        jp c_tapion             ; 0000h
        jp c_tapin              ; 0003h
        assert $ = C_POS
        ds 12,0                 ; C_POS, C_S1END, C_TOTAL, C_START
header: db 1Fh,0A6h,0DEh,0BAh,0CCh,13h,7Dh,74h
        assert $ = C_SEGS
        ds SEGS_MAX,0
        assert $ = C_BORDER
        ds 10,0                 ; C_BORDER to C_TWO
        assert $ = C_SAVE
        ds 6,0                  ; C_SAVE and C_S1REAL
        assert $ = C_MODE
        db 0

T0MODE  equ 0
D_POS   equ C_POS
D_S1END equ C_S1END
D_TOTAL equ C_TOTAL
D_START equ C_START
D_HEADER equ header
D_SEGS  equ C_SEGS
D_BORDER equ C_BORDER
D_FRAMES equ C_FRAMES
D_VDP7  equ C_VDP7
D_SIDE  equ C_SIDE
D_SCREEN equ C_SCREEN
D_VDP1  equ C_VDP1
D_TWO   equ C_TWO
D_SAVE  equ C_SAVE
D_S1REAL equ C_S1REAL
D_MODE  equ C_MODE
D_STOP  equ E_STOP
        include "tape.inc"

        align 8,0               ; the tape starts at a multiple of 8
        ent
code_end:

; For build.py: STMOTR's address, the code segment's data, the tape's most
; segments, E_FC, and the marker's data.
fields:
        dw t_stmotr, C_POS, SEGS_MAX, E_FC, C_BORDER
fields_end:

; ---- T0 without a part in page 3, from 19DDh to 1B44h ----
;
; T0's routines and data, for a game whose page 3 has no room for the service
; (DESIGN.md, Without a part in page 3). The game reaches T0 through DOS's
; mapper in page 0, where mapper register FCh holds T0, and build.py points the
; jump table's entries from 00E1h to 00F3h at the routines here.

t0m_start:
        module t0m
        disp T_POS
        ds 12,0                 ; T_POS, T_S1END, T_TOTAL, T_START
        assert $ = T_HEADER
header: db 1Fh,0A6h,0DEh,0BAh,0CCh,13h,7Dh,74h
        assert $ = T_SEGS
        ds T_SEGS_MAX,0
        assert $ = T_PAGE
        ds 6,0
        assert $ = T_BORDER
        ds 10,0                 ; as C_BORDER to C_TWO

T0MODE  equ 1
D_POS   equ T_POS
D_S1END equ T_S1END
D_TOTAL equ T_TOTAL
D_START equ T_START
D_HEADER equ T_HEADER
D_SEGS  equ T_SEGS
D_PAGE  equ T_PAGE
D_BORDER equ T_BORDER
D_FRAMES equ T_BORDER+2
D_VDP7  equ T_BORDER+3
D_SIDE  equ T_BORDER+4
D_SCREEN equ T_BORDER+5
D_VDP1  equ T_BORDER+7
D_TWO   equ T_BORDER+9

; T0 has no room for the manual tape, so the tape is automatic in this mode
; (DESIGN.md, The manual tape).
tapiof:                         ; TAPIOF and TAPOOF, as the BIOS's
tapoof:
        ei
stmotr:                         ; STMOTR
        ret
tapoon:                         ; TAPOON and TAPOUT: the tape cannot be written
        scf
        ret
        include "tape.inc"
        assert $ <= 1B45h       ; within the BIOS's tape code
        ds 1B45h-$,0
        ent
        endmodule
t0m_end:

; For build.py: the jump table's targets from 00E1h to 00F3h, in its order
; TAPION, TAPIN, TAPIOF, TAPOON, TAPOUT, TAPOOF, STMOTR, then T0's data.
t0m_fields:
        dw t0m.c_tapion, t0m.c_tapin, t0m.tapiof, t0m.tapoon, t0m.tapoon, t0m.tapoof, t0m.stmotr
        dw T_POS, T_PAGE, T_BORDER, T_SEGS_MAX
t0m_fields_end:

; tools/relocs.py appends here the offsets of the bytes that differ when
; P3_PAGE is FBh: the high bytes of the addresses in the page 3 part.
relocs:
