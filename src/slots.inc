; Slot selection in one page, shared by the restorer and its worker
; (docs/INTERNALS.md, Restorer). The slot register is port A8h, with 2 bits per
; page. An expanded slot's subslot register is at FFFFh of that slot, readable
; only while page 3 selects the slot, and it reads back inverted (MSX Red Book,
; chapter 1).
;
; The caller keeps interrupts off, and runs and keeps its stack in a page other
; than the target page and, for an expanded slot, other than page 3.

; Shifts the 2-bit value in A to page B's bits, and returns in D the mask that
; clears page B's bits.
page_bits:
        ld d,0FCh
        ld e,b
        inc e
.next:
        dec e
        ret z
        rlca
        rlca
        rlc d
        rlc d
        jr .next

; Selects slot ID C (bit 7 set when expanded, bits 3 and 2 the subslot, bits 1
; and 0 the primary slot) in page B, with only page B's bits of the subslot
; register changed. restore_slot puts both registers back.
select_slot:
        in a,(0A8h)
        ld (sv_a8),a
        ld a,c
        ld (sv_id),a
        bit 7,c
        jr z,.primary
        ; Page 3 selects the primary slot, so that FFFFh is its subslot
        ; register.
        ld a,c
        and 3
        rrca
        rrca
        ld e,a
        ld a,(sv_a8)
        and 3Fh
        or e
        out (0A8h),a
        ld a,(0FFFFh)
        cpl
        ld (sv_sub),a
        ld a,c
        rrca
        rrca
        and 3
        call page_bits
        ld e,a
        ld a,(sv_sub)
        and d
        or e
        ld (0FFFFh),a
.primary:
        ld a,c
        and 3
        call page_bits
        ld e,a
        ld a,(sv_a8)
        and d
        or e
        out (0A8h),a
        ret

restore_slot:
        ld a,(sv_id)
        bit 7,a
        jr z,.primary
        and 3
        rrca
        rrca
        ld e,a
        ld a,(sv_a8)
        and 3Fh
        or e
        out (0A8h),a
        ld a,(sv_sub)
        ld (0FFFFh),a
.primary:
        ld a,(sv_a8)
        out (0A8h),a
        ret

sv_a8:  db 0
sv_id:  db 0
sv_sub: db 0
