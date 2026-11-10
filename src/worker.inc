; The worker (docs/INTERNALS.md, Restorer): the part of the restorer that runs in
; page 1 or 2 while it changes the other pages. snapcas.asm assembles it twice,
; for WBASE 4000h and 8000h, and copies the copy it needs to that page. The
; worker keeps its stack in its own page.

; Entry points, at fixed offsets from WBASE.
        jp crc_roms             ; +0
        jp copy_page0           ; +3
        jp final                ; +6

; ---- The ROMs' CRC-16 (step 1), run in page 2 ----

; Returns in HL the CRC-16 of the main ROM's 32 KB, and in DE that of the
; sub-ROM's 16 KB, or 0 without a sub-ROM.
crc_roms:
        di
        ld (w_sp),sp
        ld sp,w_stack
        call make_table
        ld hl,0FFFFh
        ld (crc),hl
        ld a,(EXPTBL)           ; the main ROM's slot ID
        ld (rom_id),a
        ld a,(EXBRSA)           ; the sub-ROM's slot ID, 0 on an MSX1
        ld (subrom_id),a
        ld b,0
        call crc_page
        ld b,1
        call crc_page
        ld hl,(crc)
        ld (rom_crc),hl
        ld hl,0
        ld a,(subrom_id)
        or a
        jr z,.done
        ld (rom_id),a
        ld hl,0FFFFh
        ld (crc),hl
        ld b,0
        call crc_page
        ld hl,(crc)
.done:
        ex de,hl
        ld hl,(rom_crc)
        ld sp,(w_sp)
        ei
        ret

; Adds page B of the slot rom_id to crc.
crc_page:
        ld a,(rom_id)
        ld c,a
        push bc
        call select_slot
        pop bc
        ld a,b
        rrca
        rrca
        ld h,a
        ld l,0
        ld bc,4000h
        ld de,(crc)
.byte:
        ; CRC-16/CCITT-FALSE, by table: crc = (crc << 8) ^ T[(crc >> 8) ^ byte].
        ld a,(hl)
        xor d
        push hl
        ld h,high crc_hi
        ld l,a
        ld a,(hl)
        xor e
        ld d,a
        inc h
        ld e,(hl)
        pop hl
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,.byte
        ld (crc),de
        jp restore_slot

; Builds the table of CRC-16/CCITT-FALSE, polynomial 1021h.
make_table:
        ld b,0
.entry:
        ld h,b
        ld l,0
        ld c,8
.bit:
        add hl,hl
        jr nc,.next
        ld a,h
        xor 10h
        ld h,a
        ld a,l
        xor 21h
        ld l,a
.next:
        dec c
        jr nz,.bit
        ld d,high crc_hi
        ld e,b
        ld a,h
        ld (de),a
        inc d
        ld a,l
        ld (de),a
        inc b
        jr nz,.entry
        ret

; ---- A copy into page 0 (step 3), run in page 1 ----

; Copies the 16 KB at 8000h into page 0 of slot ID C, then reads the page
; back. D is 1 for a page in a mapper, with its segment in E, and 0 for a page
; outside a mapper. Returns with carry set on a mismatch, and with dos_fc in
; mapper register FCh again.
copy_page0:
        di
        ld (w_sp),sp
        ld sp,w_stack
        ld b,0
        push de
        call select_slot
        pop de
        dec d
        jr nz,.copy             ; outside a mapper
        ld a,e
        out (0FCh),a
.copy:
        ld hl,8000h
        ld de,0
        ld bc,4000h
        ldir
        ld hl,8000h
        ld de,0
        ld bc,4000h
.check:
        ld a,(de)
        cp (hl)
        jr nz,.bad
        inc hl
        inc de
        dec bc
        ld a,b
        or c
        jr nz,.check
        or a
        jr .out
.bad:
        scf
.out:
        push af
        ld a,(dos_fc)
        out (0FCh),a
        call restore_slot
        pop af
        ld sp,(w_sp)
        ei
        ret

; ---- The switch to the game (step 6), run in the worker's own segment ----

final:
        ld sp,w_stack
        ; Copy each holding segment into its own segment: the source through
        ; the other page below page 3, the target through page 0.
        ld a,(f_holdn)
        or a
        jr z,.subslots
        ld b,a
        ld hl,f_hold
.hold:
        push bc
        ld a,(hl)
        inc hl
        out (SRC_PORT),a
        ld a,(hl)
        inc hl
        out (0FCh),a
        push hl
        ld hl,SRC_ADDR
        ld de,0
        ld bc,4000h
        ldir
        pop hl
        pop bc
        djnz .hold
.subslots:
        ; The subslot register of each expanded slot, written while page 3
        ; selects that slot, the snapshot's page 3 slot last.
        in a,(0A8h)
        ld (f_dos_a8),a
        ld c,0
.slot:
        ld a,(f_p3)
        cp c
        call nz,write_subslot
        inc c
        ld a,c
        cp 4
        jr nz,.slot
        ld a,(f_p3)
        ld c,a
        call write_subslot
        ; The mapper registers of the three other pages.
        ld hl,f_map
        ld c,0FCh
        ld b,4
.map:
        ld a,c
        cp 0FCh + WPAGE
        jr z,.skip
        ld a,(hl)
        out (c),a
.skip:
        inc hl
        inc c
        djnz .map
        ; The slot register, with this page still selecting DOS's mapper.
        ld a,(f_a8)
        out (0A8h),a
        ; The registers, except AF and SP, which the tail loads.
        ld hl,(f_af2)
        push hl
        pop af
        ex af,af'
        ld bc,(f_bc2)
        ld de,(f_de2)
        ld hl,(f_hl2)
        exx
        ld ix,(f_ix)
        ld iy,(f_iy)
        ld a,(f_i)
        ld i,a
        ld a,(f_im)
        cp 2
        jr z,.im2
        cp 1
        jr z,.im1
        im 0
        jr .regs
.im1:
        im 1
        jr .regs
.im2:
        im 2
.regs:
        ld bc,(f_bc)
        ld de,(f_de)
        ld hl,(f_hl)
f_jump: jp 0                    ; the tail's address

; Writes slot C's subslot register, when the slot is expanded.
write_subslot:
        ld hl,f_exp
        ld b,0
        add hl,bc
        ld a,(hl)
        or a
        ret z
        ld a,c
        rrca
        rrca
        ld e,a
        ld a,(f_dos_a8)
        and 3Fh
        or e
        out (0A8h),a
        ld hl,f_sub
        add hl,bc
        ld a,(hl)
        ld (0FFFFh),a
        ret

        include "slots.inc"

; ---- Data that snapcas.asm fills in ----
; f_holdn to f_im are read through IX from f_holdn, so they stay within 127
; bytes of it, and f_hold comes last.

dos_fc:     db 0                ; mapper register FCh's value under DOS: DOS's
                                ; segment in page 0
rom_crc:    dw 0
crc:        dw 0
rom_id:     db 0
subrom_id:  db 0
w_sp:       dw 0
f_holdn:    db 0                ; the number of holding segments
f_exp:      ds 4                ; per slot: nonzero when expanded
f_sub:      ds 4                ; per slot: the snapshot's subslot register
f_p3:       db 0                ; the snapshot's page 3 primary slot
f_map:      ds 4                ; the snapshot's mapper registers FCh to FFh
f_a8:       db 0                ; the slot register, this page on DOS's mapper
f_dos_a8:   db 0
f_bc:       dw 0
f_de:       dw 0
f_hl:       dw 0
f_af2:      dw 0                ; then BC', DE', HL', IX, IY
f_bc2:      dw 0
f_de2:      dw 0
f_hl2:      dw 0
f_ix:       dw 0
f_iy:       dw 0
f_i:        db 0
f_im:       db 0
f_hold:     ds 2*HOLD_MAX       ; each: the holding segment, its own segment
            ds 64
w_stack:
            align 256
crc_hi:     ds 256
crc_lo:     ds 256
