; ---- Step 2: the segments ----

; Marks each free segment of DOS's mapper in freemap, and counts them.
FREE    equ 1                   ; freemap: a free segment
OWN     equ 2                   ; a free segment that a record takes as its own
find_free:
        ld a,(dos2)
        or a
        jr z,.dos1
.dos2:
        xor a
        ld b,a                  ; a user segment of the primary mapper
        call all_seg
        ret c
        call .free
        jr .dos2
.dos1:
        ; MSX-DOS 1 uses segments 0 to 3 and no other.
        ld a,(map_size)
        ld b,a
        ld a,4
.mark:
        cp b
        ret z
        call .free
        inc a
        jr nz,.mark
        ret
.free:
        ld l,a
        ld h,high freemap
        ld (hl),FREE
        ld hl,free_count
        inc (hl)
        ret

; Counts the free segments that the image needs: one for each record of DOS's
; mapper that does not go into DOS's segment in page 1 or 2, one for each
; service segment, and one for the worker. Stops, naming the segments needed
; and free, when there are too few.
count_needs:
        ld c,1
        call first_record
.record:
        jr z,.compare
        ld a,(ix)
        cp REC_SERVICE
        jr z,.need
        call dos_record
        jr nz,.next
        call in_dos_page
        jr z,.next
.need:
        inc c
.next:
        call next_record
        jr .record
.compare:
        ld a,(free_count)
        cp c
        ret nc
        ld a,c
        ld (needed),a
        call name
        ld de,t_needs
        call print
        ld a,(needed)
        call print_dec
        ld de,t_free
        call print
        ld a,(free_count)
        call print_dec
        ld de,t_crlf
        jp stop_message

; When T0 takes mapper register FCh for good, a RAM page for page 0 in another
; mapper follows the same register, so T0 must be that page's segment of DOS's
; mapper. Sets t0_fixed and t0_fix to that segment, and takes it now when it is
; free, before the holding segments can. Stops when the pages for page 0 of
; other mappers have different segments, when the segment is beyond DOS's
; mapper, or when a RAM page of DOS's mapper has it.
t0_segment:
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        ld hl,t0_rom
        or (hl)
        ret z
        call first_record
.record:
        jr z,.found
        ld a,(ix)
        cp REC_MAPPER
        jr nz,.next
        ld a,(ix+2)
        or a
        jr nz,.next
        ld a,(dos_slot)
        cp (ix+1)
        jr z,.next
        ld a,(t0_fixed)
        or a
        ld a,(ix+3)
        jr z,.set
        ld hl,t0_fix
        cp (hl)
        ld de,t_t0seg
        jp nz,stop_name
.set:
        ld (t0_fix),a
        ld a,1
        ld (t0_fixed),a
.next:
        call next_record
        jr .record
.found:
        ld a,(t0_fixed)
        or a
        ret z
        ld a,(map_size)
        or a
        jr z,.own               ; 256 segments
        ld c,a
        ld a,(t0_fix)
        cp c
        ld de,t_t0seg
        jp nc,stop_name
.own:
        call first_record
.dos:
        jr z,.take
        call dos_record
        jr nz,.dnext
        ld a,(t0_fix)
        cp (ix+3)
        ld de,t_t0seg
        jp z,stop_name
.dnext:
        call next_record
        jr .dos
.take:
        ld a,(t0_fix)
        ld l,a
        ld h,high freemap
        ld a,(hl)
        or a
        ret z
        ld (hl),0
        ld a,1
        ld (t0_direct),a
        ret

; Gives each record of DOS's mapper and each service segment the segment that
; it is read into, in dest, and takes a segment for the worker.
assign:
        ; A record whose own segment is free takes it, before a holding
        ; segment can.
        call first_record
.own:
        jr z,.segments
        call dos_record
        jr nz,.onext
        ld l,(ix+3)
        ld h,high freemap
        ld a,(hl)
        cp FREE
        jr nz,.onext
        ld (hl),OWN
.onext:
        call next_record
        jr .own
.segments:
        call first_record
.record:
        jr z,.worker
        ld a,(ix)
        cp REC_SERVICE
        jr nz,.ram
        call service_seg
        jr .set
.ram:
        call dos_record
        jr nz,.next
        ; A record goes straight into its own segment when it took it above,
        ; or when it is DOS's segment in page 1 or 2. Each other record gets a
        ; holding segment, which the worker copies into its own.
        call in_dos_page
        jr z,.straight
        ld l,(ix+3)
        ld h,high freemap
        ld a,(hl)
        cp OWN
        jr z,.straight
        call take_free
        ld e,(ix+3)
        call add_hold
        jr .set
.straight:
        ld a,(ix+3)
.set:
        ld c,a
        call dest_hl
        ld (hl),c
.next:
        call next_record
        jr .record
.worker:
        call take_free
        ld (worker_seg),a
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        ld hl,t0_rom
        or (hl)
        ret z
        ld a,(svc_segs)
        ld (HDR+H_MAP),a        ; T0 in page 0
        ret

; Returns in A the segment that the next service record is read into, and
; writes its segment in the restored game to svc_segs. Both are a free
; segment, except for T0, the first, with t0_fixed: its segment is t0_fix,
; which T0 is read into when t0_segment took it, or else the worker copies T0
; there from a holding segment.
service_seg:
        ld hl,(svc_next)
        inc hl
        ld (svc_next),hl
        dec hl
        ld de,svc_segs
        or a
        sbc hl,de
        add hl,de
        jr nz,.free             ; not T0
        ld a,(t0_fixed)
        or a
        jr z,.free
        ld a,(t0_fix)
        ld (hl),a
        ld e,a
        ld a,(t0_direct)
        or a
        ld a,e
        ret nz
        call take_free
        jr add_hold
.free:
        call take_free
        ld (hl),a
        ret

; Adds to the worker's list the holding segment A, which the worker copies
; into segment E, or stops when the list is full. Keeps A and HL.
add_hold:
        push hl
        push af
        ld hl,hold_count
        ld a,(hl)
        cp HOLD_MAX
        jr nc,.full
        inc (hl)
        pop af
        ld hl,(hold_next)
        ld (hl),a
        inc hl
        ld (hl),e
        inc hl
        ld (hold_next),hl
        pop hl
        ret
.full:
        ld de,t_holds
        jp stop_name

; Returns in A a free segment, taken from freemap. count_needs has checked that
; there are enough. Keeps BC, DE and HL.
take_free:
        push bc
        push hl
        ld hl,freemap
        ld b,0
.find:
        ld a,(hl)
        cp FREE
        jr z,.take
        inc l
        djnz .find
        ld de,t_segments
        jp stop_name
.take:
        ld (hl),0
        ld a,l
        pop hl
        pop bc
        ret

