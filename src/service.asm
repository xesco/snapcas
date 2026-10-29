; SERVICE.BIN: the code that tools/build.py writes into images (docs/DESIGN.md,
; SERVICE.BIN). It is never run as it is: build.py and the restorer fill in
; the operands and the data that are 0 here.
;
; The file starts with its version and a table of its parts. build.py refuses
; a SERVICE.BIN whose version is not the one it expects.

        include "service.inc"

VERSION equ 4

        org 0

        db VERSION
        db 6                    ; number of parts
        dw tail, tail_end-tail          ; part 0: the tail
        dw t0_start, t0_end-t0_start    ; part 1: T0's stubs, for 19DDh
        dw p3_start, p3_end-p3_start    ; part 2: page 3, for E_ENTRY
        dw code_start, code_end-code_start  ; part 3: the code segment
        dw fields, fields_end-fields    ; part 4: places for build.py
        dw relocs, 0                    ; part 5: the bytes that move with page 3,
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
        jr t_tapiof
t_stmotr:                       ; STMOTR, through the jump at 00F3h
        ret
        ds 19E9h-$,0
t_tapiof:                       ; 19E9h, TAPIOF
        ld a,(E_INSIDE)         ; the entry code enables interrupts itself
        or a
        ret nz
        ei
        ret
        ds 19F1h-$,0
t_tapoon:                       ; 19F1h, TAPOON: the tape cannot be written
        scf
        ret
        ds 1A19h-$,0
t_tapout:                       ; 1A19h, TAPOUT: the tape cannot be written
        scf
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
        db 0,0,0,0,0            ; E_SLOT, E_T0, E_CODE, E_FC, E_INSIDE

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
        ds 8,0                  ; C_BORDER to C_VDP1

; The colours of the flash after GRAPH and CODE, and when the position changes
; side or goes back to a side's start by itself.
SIDE_A  equ 3                   ; light green
SIDE_B  equ 9                   ; light red

c_tapion:
        call keys
        ret c                   ; CTRL+STOP
        push bc
        bit 2,c
        call z,side_a           ; GRAPH
        pop bc
        bit 4,c
        call z,side_b           ; CODE
        ; Find the next header at a multiple of 8 bytes.
.search:
        call keys
        ret c
        ld hl,C_POS
        ld a,(hl)
        add a,7
        jr nc,.low
        inc hl                  ; the carry into the upper bytes
        inc (hl)
        jr nz,.up
        inc hl
        inc (hl)
.up:
        ld hl,C_POS
.low:
        and 0F8h
        ld (hl),a
        call wrap
        ld hl,header
        ld b,8
.compare:
        push bc
        push hl
        call next_byte
        pop hl
        pop bc
        cp (hl)
        jr nz,.search
        inc hl
        djnz .compare
        or a
        ret

c_tapin:
        call keys
        ret c                   ; CTRL+STOP
; Returns in A the byte at the tape position, and advances the position.
next_byte:
        ld hl,(C_POS)
        ld a,(C_POS+2)
        add a,a
        add a,a
        ld c,a
        ld a,h
        rlca
        rlca
        and 3
        or c                    ; the segment's number in C_SEGS
        ld e,a
        ld d,0
        push hl
        ld hl,C_SEGS
        add hl,de
        ld d,(hl)
        pop hl
        ld a,h
        and 3Fh
        ld h,a
        ld a,(C_SEGS)
        ld b,a
        ld c,0FCh
        call reader
        push de
        ld hl,C_POS
        inc (hl)
        jr nz,.wrap
        inc hl
        inc (hl)
        jr nz,.wrap
        inc hl
        inc (hl)
.wrap:
        call wrap
        pop de
        ld a,e
        or a
        ret

; Flashes the screen in the border colour E for 0.1 second, counted by the
; VDP's frame flag in status register 0: it blanks the display, which then
; shows only the border. It then writes the game's registers 7 and 1 again.
; The VDP's registers cannot be read, so C_BORDER and C_SCREEN point to the
; game's values: RG7SAV and RG1SAV, or C_VDP7 and C_VDP1 for a game that does
; not keep them (DESIGN.md, Tape service).
mark:
        in a,(99h)              ; also resets the VDP's register latch
        ld hl,(C_SCREEN)
        ld a,(hl)
        push af
        and 0BFh                ; bit 6 clear: the display blanked
        ld d,81h
        call vdp
        ld hl,(C_BORDER)
        ld a,(hl)
        push af
        and 0F0h                ; the text colour of screen 0
        or e
        ld d,87h
        call vdp
        ld a,(C_FRAMES)
        ld b,a
.frame:
        in a,(99h)
        rlca
        jr nc,.frame
        djnz .frame
        pop af
        ld d,87h
        call vdp
        pop af
        ld d,81h
; Writes A to the VDP register that D selects, as 80h plus its number.
vdp:
        out (99h),a
        ld a,d
        out (99h),a
        ret

; Returns rows 6 in C and 7 in A of the keyboard matrix, read through the PPI,
; and carry when CTRL+STOP is held.
keys:
        ld a,6
        call row
        ld c,a                  ; SHIFT CTRL GRAPH CAPS CODE ...
        ld a,7
        call row                ; ... STOP BS SELECT RETURN
        bit 1,c
        ret nz
        bit 4,a
        ret nz
        scf
        ret
row:
        ld b,a
        in a,(0AAh)
        and 0F0h
        or b
        out (0AAh),a
        in a,(0A9h)
        or a
        ret

; After the position changed: at or past side 1's end without a side 2, side 1's
; start; at or past side 2's end, side 2's start. TAPION's rounding can pass
; a side's end, so the tests are not for equality. Side 2 starts at side 1's
; end, so a read that reaches it changes only C_SIDE. Each change shows the
; side's border colour.
wrap:
        call on_side1
        ld a,0
        jr c,.side
        call one_side
        jr z,side_a             ; past side 1's end without a side 2
        ld hl,C_POS
        ld de,C_TOTAL
        call lt24
        jr nc,side_b.two        ; past side 2's end
        ld a,1
.side:
        ld hl,C_SIDE
        cp (hl)
        ret z
        ld (hl),a               ; side 1's end reached: side 2
        ld e,SIDE_B
        jp mark

; Returns Z when the tape has no side 2.
one_side:
        ld hl,C_S1END
        ld de,C_TOTAL
        jp eq24

set_pos:
        ld de,C_POS
        ld bc,3
        ldir
        ret

; CODE: side 2's start, or side 1's without a side 2. GRAPH: side 1's start.
side_b:
        call one_side
        jr z,side_a
.two:
        ld hl,C_S1END
        ld de,1*256+SIDE_B
        jr to_side
side_a:
        ld hl,C_START
        ld de,0*256+SIDE_A
; Moves the tape position to the 3 bytes at HL, which are on side 1 for D = 0
; and on side 2 for D = 1, and shows the border colour E.
to_side:
        ld a,d
        ld (C_SIDE),a
        push de
        call set_pos
        pop de
        jp mark

; Returns carry when the tape position is on side 1.
on_side1:
        ld hl,C_POS
        ld de,C_S1END
; Returns carry when the 3 bytes at HL are below those at DE: (HL) minus (DE),
; byte by byte with the borrow.
lt24:
        or a
        ld b,3
.byte:
        ld a,(de)
        ld c,a
        ld a,(hl)
        sbc a,c
        inc hl
        inc de
        djnz .byte
        ret

; Returns Z when the 3 bytes at HL equal those at DE.
eq24:
        ld b,3
.byte:
        ld a,(de)
        cp (hl)
        ret nz
        inc hl
        inc de
        djnz .byte
        ret

        ds (8-($ & 7)) & 7,0    ; the tape starts at a multiple of 8
        ent
code_end:

; For build.py: STMOTR's address, the code segment's data, the tape's most
; segments, E_FC, and the marker's data.
fields:
        dw t_stmotr, C_POS, SEGS_MAX, E_FC, C_BORDER
fields_end:

; tools/relocs.py appends here the offsets of the bytes that differ when
; P3_PAGE is FBh: the high bytes of the addresses in the page 3 part.
relocs:
