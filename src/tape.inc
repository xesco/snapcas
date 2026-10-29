;; The tape service's routines (DESIGN.md, Tape service), which service.asm
;; assembles twice: in the code segment, which runs in page 0 and reads the
;; tape through the reader in page 3, and in T0 for the mode without a part in
;; page 3 (T0MODE), which reads the tape through a borrowed page 1 or 2. The
;; module that includes this file sets T0MODE and the data's places, D_POS to
;; D_VDP1, D_TWO, D_HEADER, D_SEGS and, in T0 mode, D_PAGE.
;;
;; TAPION and TAPIN behave as the BIOS's: carry clear on success, set when
;; CTRL+STOP is held, and they run with interrupts off, as the BIOS's do.

; The colours of the flash after GRAPH and CODE, and when the position changes
; side or goes back to a side's start by itself.
SIDE_A  equ 3                   ; light green
SIDE_B  equ 9                   ; light red

c_tapion:
        di
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
.align:
        ld a,(D_POS)
        and 7
        jr z,.header
        call next_byte
        jr .align
.header:
        ld hl,D_HEADER
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
        di
        call keys
        ret c                   ; CTRL+STOP
; Returns in A the byte at the tape position, and advances the position.
next_byte:
        ld hl,(D_POS)
        ld a,(D_POS+2)
        add a,a
        add a,a
        ld c,a
        ld a,h
        rlca
        rlca
        and 3
        or c                    ; the segment's number in D_SEGS
        ld e,a
        ld d,0
        ld a,h
        and 3Fh
        ld h,a                  ; the byte's offset in its segment
        ex de,hl
        ld bc,D_SEGS
        add hl,bc
        ld b,(hl)               ; the byte's segment
        if T0MODE
        ; Through the borrowed page: D_PAGE holds its mapper register's
        ; port, its first address's high byte, and the game's segment there.
        ld hl,D_PAGE
        ld c,(hl)
        inc hl
        ld a,(hl)
        or d
        ld d,a
        inc hl
        ld a,(hl)
        ex de,hl
        out (c),b
        ld e,(hl)
        out (c),a
        else
        ; Through the reader in page 3, in page 0.
        ex de,hl
        ld d,b
        ld a,(D_SEGS)
        ld b,a
        ld c,0FCh
        call reader
        endif
        push de
        ld hl,D_POS
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
; The VDP's registers cannot be read, so D_BORDER and D_SCREEN point to the
; game's values: RG7SAV and RG1SAV, or D_VDP7 and D_VDP1 for a game that does
; not keep them (DESIGN.md, Tape service).
mark:
        in a,(99h)              ; also resets the VDP's register latch
        ld hl,(D_SCREEN)
        ld a,(hl)
        push af
        and 0BFh                ; bit 6 clear: the display blanked
        ld d,81h
        call vdp
        ld hl,(D_BORDER)
        ld a,(hl)
        push af
        and 0F0h                ; the text colour of screen 0
        or e
        ld d,87h
        call vdp
        ld a,(D_FRAMES)
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
; end, so a read that reaches it changes only D_SIDE. Each change shows the
; side's border colour.
wrap:
        call on_side1
        ld a,0
        jr c,.side
        call one_side
        jr z,side_a             ; past side 1's end without a side 2
        ld hl,D_POS
        ld de,D_TOTAL
        call lt24
        jr nc,side_b.two        ; past side 2's end
        ld a,1
.side:
        ld hl,D_SIDE
        cp (hl)
        ret z
        ld (hl),a               ; side 1's end reached: side 2
        ld e,SIDE_B
        jp mark

; Returns Z when the tape has no side 2.
one_side:
        ld a,(D_TWO)
        or a
        ret

set_pos:
        ld de,D_POS
        ld bc,3
        ldir
        ret

; CODE: side 2's start, or side 1's without a side 2. GRAPH: side 1's start.
side_b:
        call one_side
        jr z,side_a
.two:
        ld hl,D_S1END
        ld de,1*256+SIDE_B
        jr to_side
side_a:
        ld hl,D_START
        ld de,0*256+SIDE_A
; Moves the tape position to the 3 bytes at HL, which are on side 1 for D = 0
; and on side 2 for D = 1, and shows the border colour E.
to_side:
        ld a,d
        ld (D_SIDE),a
        push de
        call set_pos
        pop de
        jp mark

; Returns carry when the tape position is on side 1.
on_side1:
        ld hl,D_POS
        ld de,D_S1END
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

