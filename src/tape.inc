;; The tape service's routines (DESIGN.md, Tape service), which service.asm
;; assembles twice: in the code segment, which runs in page 0 and reads the
;; tape through the reader in page 3, and in T0 for the mode without a part in
;; page 3 (T0MODE), which reads the tape through a borrowed page 1 or 2. The
;; module that includes this file sets T0MODE and the data's places, D_POS to
;; D_VDP1, D_TWO, D_HEADER, D_SEGS and, in T0 mode, D_PAGE.
;;
;; TAPION and TAPIN behave as the BIOS's: carry clear on success, set when
;; CTRL+STOP is held, and they run with interrupts off, as the BIOS's do.

; The colours of the flash after GRAPH, CODE and RETURN, and when the position
; changes side or goes back to a side's start by itself.
SIDE_A  equ 3                   ; light green
SIDE_B  equ 9                   ; light red
PLAY    equ 11                  ; light yellow, after RETURN on the manual tape

c_tapion:
        di
        call keys
        ret c                   ; CTRL+STOP
        if !T0MODE
        ld hl,.search
        call manual
        jr z,.auto
        ; The manual tape: next_byte waits for the keys when it is stopped. A
        ; game that stopped the motor without the service, through the BIOS in
        ; ROM or with its own write, left PPI port C bit 4 set, and the tape
        ; stops too. TAPION starts the motor, as the BIOS's does.
        in a,(0AAh)
        bit 4,a
        jr z,.search
        res 4,a
        out (0AAh),a
        call stop
        jr .search
.auto:
        endif
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
        if !T0MODE
        ld hl,.again
        call manual
.again:
        ; build.py pads side 1 before side 2, and the padding is not on the
        ; tape. The TAPIN that reaches it is the one that waits while the
        ; tape is turned over, and it returns FFh, as the BIOS's does in
        ; openMSX when side 2 goes in: the next TAPIN reads side 2.
        ld hl,D_POS
        ld de,D_S1REAL
        call lt24
        jr c,.aligned
        ld hl,D_POS
        ld de,D_S1END
        call lt24
        jr nc,.aligned
        ld hl,D_S1END
        ld de,D_POS
        ld bc,3
        ldir
        ; The manual tape stops at side 1's end, and the read waits there.
        ld a,(D_MODE)
        or a
        jr z,.ff
        call stop
        call wait
        ret c
.ff:
        ld a,0FFh
        or a
        ret
.aligned:
        ; A block's header is a tone on a real tape, which TAPIN waits through,
        ; so a header at a multiple of 8 is skipped, as when a game reads on
        ; into the next block or past side 1's end.
        ld a,(D_POS)
        and 7
        jr nz,next_byte
        ld hl,D_POS
        ld de,D_SAVE
        ld bc,3
        ldir
        ld hl,D_HEADER
        ld b,8
.header:
        push bc
        push hl
        call next_byte
        pop hl
        pop bc
        cp (hl)
        jr nz,.data
        inc hl
        djnz .header
        jr next_byte            ; the byte after the header
.data:
        ld hl,D_SAVE
        ld de,D_POS
        ld bc,3
        ldir
        endif
; Returns in A the byte at the tape position, and advances the position. The
; manual tape, when stopped, first waits for the player's key, and returns
; carry for CTRL+STOP without a byte.
next_byte:
        if !T0MODE
        ld a,(D_STOP)
        or a
        call nz,wait
        ret c
        endif
        ld hl,(D_POS+1)
        add hl,hl
        add hl,hl
        ld e,h
        ld d,0                  ; the segment's number in D_SEGS: position / 4000h
        ld hl,D_SEGS
        add hl,de
        ld b,(hl)               ; the byte's segment
        ld hl,(D_POS)
        ld a,h
        and 3Fh
        ld d,a
        ld e,l                  ; the byte's offset in its segment
        if T0MODE
        ; Through the borrowed page, without the stack, which that page can
        ; hold: D_PAGE keeps the game's slot register meanwhile, then holds
        ; the slot register's mask and bits that select DOS's mapper there,
        ; its mapper register's port, its first address's high byte, and the
        ; game's segment there.
        ld hl,D_PAGE
        in a,(0A8h)
        ld (hl),a
        inc hl
        and (hl)
        inc hl
        or (hl)
        out (0A8h),a
        inc hl
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
        ld a,(D_PAGE)
        out (0A8h),a
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
        if !T0MODE
        ld a,(D_MODE)
        or a
        jp nz,wrap_manual
        endif
        ld a,(D_TWO)            ; 0 when the tape has no side 2
        or a
        jr z,side_a             ; past side 1's end without a side 2
        ld de,D_TOTAL
        call on_side1.pos
        jr nc,side_b.two        ; past side 2's end
        ld a,1
.side:
        ld hl,D_SIDE
        cp (hl)
        ret z
        ld (hl),a               ; side 1's end reached: side 2
        ld e,SIDE_B
        jp mark

; CODE: side 2's start, or side 1's without a side 2. GRAPH: side 1's start.
side_b:
        ld a,(D_TWO)
        or a
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
        ld de,D_POS
        ld bc,3
        ldir
        pop de
        jp mark

; Returns carry when the tape position is on side 1, or from .pos, below the 3
; bytes at DE.
on_side1:
        ld de,D_S1END
.pos:
        ld hl,D_POS
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

        if !T0MODE
; The manual tape stops at the last side's end, and at side 1's end until
; RETURN goes on to side 2 (DESIGN.md, The manual tape).
wrap_manual:
        ld de,D_TOTAL
        call on_side1.pos
        jr nc,stop              ; at or past the tape's end
        ld a,(D_SIDE)
        or a
        ret nz                  ; on side 2
stop:
        ld a,1
        ld (D_STOP),a
        ret

; For the manual tape: keeps HL, where the read starts, and the read's stack
; pointer, so that wait can start the read again. Returns NZ for the manual
; tape and Z for the automatic tape.
manual:
        ld a,(D_MODE)
        or a
        ret z
        ld (again),hl
        pop hl
        ld (again_sp),sp
        jp (hl)

; The stopped manual tape: waits for RETURN, GRAPH or CODE, held already or
; pressed, then for its release, so that the game does not read it. After
; RETURN it plays on. After GRAPH or CODE the read starts again at the new
; place, as after a rewind. Returns carry at once for CTRL+STOP, with the tape
; still stopped. The automatic tape returns at once.
wait:
        ld a,(D_MODE)
        or a
        ret z
.key:
        call keys
        ret c                   ; CTRL+STOP
        bit 2,c
        jr z,.graph
        bit 4,c
        jr z,.code
        bit 7,a                 ; RETURN
        jr nz,.key
        ld de,D_TOTAL
        call on_side1.pos
        jr nc,.key              ; the tape holds nothing more
        call release
        ; At side 1's end with a side 2, RETURN goes on at side 2's start, as
        ; when the tape is turned over.
        call on_side1
        jr c,.flash
        ld hl,D_SIDE
        ld a,(hl)
        or a
        jr nz,.flash
        inc (hl)
.flash:
        ld e,PLAY
        call mark
        jr .play
.graph:
        call release
        call side_a
        jr .again
.code:
        call release
        call side_b
.again:
        xor a
        ld (D_STOP),a
        ld sp,(again_sp)
        ld hl,(again)
        jp (hl)
.play:
        xor a
        ld (D_STOP),a
        ret

; Waits until RETURN, GRAPH and CODE are all released.
release:
        call keys
        bit 2,c
        jr z,release
        bit 4,c
        jr z,release
        bit 7,a
        jr z,release
        ret

again:  dw 0                    ; where the read starts again
again_sp: dw 0                  ; the read's stack pointer
        endif
