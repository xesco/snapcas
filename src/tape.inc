;; The tape service's routines (INTERNALS.md, Tape service), which service.asm
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
        jr z,.motor
        res 4,a
        out (0AAh),a
        call stop
        jr .motor
.auto:
        endif
        push bc
        bit 2,c
        call z,side_a           ; GRAPH
        pop bc
        bit 4,c
        call z,side_b           ; CODE
.motor:
        if !T0MODE
        call motor_on           ; at a tape speed
        ld hl,0
        ld (left),hl            ; the position moves: TAPIN checks all again
        endif
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
        if !T0MODE
        call leader             ; at a tape speed
        ret c                   ; CTRL+STOP
        endif
        or a
        ret

; At a tape speed, TAPIN reads each byte with the least work and plays it
; (INTERNALS.md, Tape speed and sound).
c_tapin:
        if !T0MODE
        ld a,(D_SPEED)
        or a
        jr z,tapin
        di
        call lean
        ret c
        push af
        call play
        pop af
        ret
        endif
tapin:
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
        call read_pos
        push de
        call inc_pos
        call wrap
        pop de
        ld a,e
        or a
        ret

; Returns in E the byte at the tape position, which stays. T0's copy has no
; room for the call, so it reads, advances and wraps in one.
read_pos:
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
        else
        ; Through the reader in page 3, in page 0.
        ex de,hl
        ld d,b
        ld a,(D_SEGS)
        ld b,a
        ld c,0FCh
        jp reader

; Advances the tape position by one byte.
inc_pos:
        ld hl,D_POS
        inc (hl)
        ret nz
        inc hl
        inc (hl)
        ret nz
        inc hl
        inc (hl)
        ret
        endif

; Flashes the screen in the border colour E for 0.1 second, counted by the
; VDP's frame flag in status register 0: it blanks the display, which then
; shows only the border. It then writes the game's registers 7 and 1 again.
; The VDP's registers cannot be read, so D_BORDER and D_SCREEN point to the
; game's values: RG7SAV and RG1SAV, or D_VDP7 and D_VDP1 for a game that does
; not keep them (INTERNALS.md, Tape service).
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
; RETURN goes on to side 2 (INTERNALS.md, The manual tape).
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

        if !T0MODE
; ---- The tape speed and its sound (INTERNALS.md, Tape speed and sound) ----
;
; At D_SPEED 1 or 2, the service works as a tape at 1200 or 2400 baud: each
; bit is one cycle of a square wave for a 0 and two cycles at twice the
; frequency for a 1, played on the keyclick bit, PPI port C bit 7, which the
; MSX sends to its sound output. The sound is the wait.

; For each speed: the loop counts of edge for a 1 bit's quarter cycle and a 0
; bit's half cycle, at the tape's frequencies, then the stop bits' edges and
; the pad's loops. An edge takes 61 T-states and 14 more for each loop, with
; the MSX's wait state on each opcode fetch. No edge comes between two bytes,
; while the service returns to the game and the game calls it again, so the
; stop bits leave out that time's quarter cycles, an even number, and the pad
; makes up the rest: a byte takes its 11 bits, measured in openMSX.
speeds: db 48,101,STOP1200,PAD1200
        db 21,47,STOP2400,PAD2400
STOP1200 equ 6
PAD1200 equ 1
STOP2400 equ 4
PAD2400 equ 1

; The counts of D_SPEED's row, which TAPION and the first TAPIN copy here.
nq:     db 0                    ; a 1 bit's quarter cycle
nh:     db 0                    ; a 0 bit's half cycle
nstop:  db 0                    ; the stop bits' edges
npad:   db 0                    ; the pad's loops
left:   dw 0                    ; the bytes that lean can read on
keyct:  db 0                    ; the bytes until lean reads the keys

; Copies D_SPEED's row of speeds to nq to npad.
counts:
        ld a,(D_SPEED)
        dec a
        add a,a
        add a,a
        ld c,a
        ld b,0
        ld hl,speeds
        add hl,bc
        ld de,nq
        ld bc,4
        ldir
        ret

; TAPIN's byte with the least work, so that the gap without edges between two
; bytes stays short: the keys after each 256 bytes, the sides' ends and side
; 1's padding by the countdown in left, and a header's check only where the
; byte at a multiple of 8 is the header's first. Otherwise, and when the manual
; tape is stopped, the whole TAPIN, which also sets the countdown again.
lean:
        ld a,(nq)
        or a
        call z,counts           ; a TAPIN before any TAPION
        ld hl,keyct
        dec (hl)
        jr nz,.stop
        call keys
        ret c                   ; CTRL+STOP
.stop:
        ld a,(D_STOP)
        ld b,a
        ld a,(D_MODE)
        and b
        jr nz,.whole            ; the manual tape is stopped
        ld hl,(left)
        ld a,h
        or l
        jr z,.whole
        ld a,(D_POS)
        and 7
        jr nz,.read
        call read_pos
        ld a,e
        ld hl,D_HEADER
        cp (hl)
        jr z,.whole             ; perhaps a header
.read:
        ld hl,(left)
        dec hl
        ld (left),hl
        call read_pos
        call inc_pos
        ld a,e
        or a
        ret
.whole:
        call tapin
        ret c
        push af
        call countdown
        pop af
        ret

; Sets left to the bytes that lean can read before the whole TAPIN must check
; the position: the least of side 1's padding's start, side 1's end less 1 and
; side 2's end less 1, each less the position, of those not below it, and at
; most 65535.
countdown:
        ld hl,0FFFFh
        ld (left),hl
        ld de,D_S1REAL
        xor a
        call .term
        ld de,D_S1END
        ld a,1
        call .term
        ld de,D_TOTAL
        ld a,1
; left takes the 3 bytes at DE, less A, less the position, when that is not
; below 0 and is less than left.
.term:
        ld (.less+1),a
        ld hl,D_POS
        ld a,(de)
        sub (hl)
        ld c,a
        inc de
        inc hl
        ld a,(de)
        sbc a,(hl)
        ld b,a
        inc de
        inc hl
        ld a,(de)
        sbc a,(hl)
        ret c
        ld h,a
        ld a,c
.less:
        sub 0
        ld c,a
        ld a,b
        sbc a,0
        ld b,a
        ld a,h
        sbc a,0
        ret c
        or a
        ret nz                  ; 65536 or more
        ld hl,(left)
        sbc hl,bc
        ret c
        ld (left),bc
        ret

; Plays the byte in A as the tape holds it: a start bit 0, the 8 data bits from
; bit 0 up, and 2 stop bits 1 (MSX Red Book, chapter 4), less the stop bits'
; edges that the gap to the next byte takes, then the pad.
play:
        ld e,a
        ld hl,(nq)              ; L: a quarter, H: a half
        or a                    ; the start bit
        call bit
        ld d,8
.data:
        rr e
        call bit
        dec d
        jr nz,.data
        ld a,(nstop)
        ld d,a
.stop:
        ld b,l
        call edge
        dec d
        jr nz,.stop
        ld a,(npad)
        ld b,a
.pad:
        djnz .pad
        ret

; Plays one bit, carry's value, with L a quarter's count and H a half's.
bit:
        jr c,.one
        ld b,h
        call edge
        ld b,h
        jr edge
.one:
        ld b,l
        call edge
        ld b,l
        call edge
        ld b,l
        call edge
        ld b,l
; Toggles the keyclick bit, then waits B loops: one edge of the wave.
edge:
        in a,(0AAh)
        xor 80h
        out (0AAh),a
.wait:
        djnz .wait
        ret

; Plays the leader tone before the header that TAPION found, as long as the
; BIOS's TAPOON writes it: the long one before a block that starts with a file
; type's 10 bytes (FORMATS.md, CAS data), and the short one, a quarter of it,
; before the others. The long one is 15,360 cycles of 2400 Hz at 1200 baud,
; 6.4 seconds, as a TSX file's pilot holds it, and lasts as long at 2400 baud.
; Returns carry for CTRL+STOP.
leader:
        ld a,(D_SPEED)
        or a
        ret z
        call counts
        ; The 10 bytes after the header, read ahead without moving the tape.
        ld hl,D_POS
        ld de,D_SAVE
        ld bc,3
        ldir
        call read_pos
        ld c,e                  ; the first byte
        ld b,10
.ahead:
        push bc
        call read_pos
        call inc_pos
        pop bc
        ld a,e
        cp c
        jr nz,.back
        djnz .ahead
.back:
        ld hl,D_SAVE
        ld de,D_POS
        push bc
        ld bc,3
        ldir
        pop bc
        ld a,b
        or a
        ld hl,1920              ; the short tone's 1 bits at 1200 baud
        jr nz,.speed
        ld a,c
        cp 0D0h                 ; a binary file
        jr z,.long
        cp 0D3h                 ; a BASIC program
        jr z,.long
        cp 0EAh                 ; an ASCII program
        jr nz,.speed
.long:
        ld hl,7680
.speed:
        ld a,(D_SPEED)
        dec a
        jr z,.counted
        add hl,hl               ; as many seconds at 2400 baud
.counted:
        ex de,hl                ; the tone's 1 bits
        ld hl,(nq)
.tone:
        scf
        call bit
        dec de
        ld a,e
        or a
        jr nz,.more
        push hl
        call keys
        pop hl
        ret c                   ; CTRL+STOP
.more:
        ld a,d
        or e
        jr nz,.tone
        ret

; At a tape speed, starts the motor through the motor relay, PPI port C bit 4,
; as the BIOS's TAPION does.
motor_on:
        ld a,(D_SPEED)
        or a
        ret z
        in a,(0AAh)
        and 0EFh
        out (0AAh),a
        ret

; T0's STMOTR and TAPIOF, with B as STMOTR's A: 1 starts the motor, and any
; other value stops the manual tape (INTERNALS.md, The manual tape). At a tape
; speed, 0 also stops the motor and FFh switches it, as the BIOS's do, so the
; relay clicks.
c_motor:
        ld a,b
        cp 1
        jr z,motor_on
        ld a,1
        ld (D_STOP),a
        ld a,(D_SPEED)
        or a
        ret z
        in a,(0AAh)
        inc b
        jr z,.switch
        or 10h
        out (0AAh),a
        ret
.switch:
        xor 10h
        out (0AAh),a
        ret
        endif
