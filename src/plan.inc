; ---- Steps 1 and 2: the plan ----

; Decides everything that the restore depends on: DOS's mapper and segments,
; the worker's page, and the segment of each record. It stops with a message
; for an image that this machine cannot restore. Every such stop comes here,
; before step 3 writes the game's memory and VRAM, so its message shows on
; DOS's screen.
plan:
        ; The port writes follow the records, and the places follow them.
        ld a,(HDR+H_RECS)
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        ld de,HDR+H_TABLE
        add hl,de
        ld (writes_at),hl
        ld a,(HDR+H_WRITES)
        ld e,a
        ld d,0
        add hl,de
        add hl,de
        ld (places_at),hl
        call find_dos
        call check_roms
        call check_size
        call check_records
        call manual_note
        call find_worker_page
        call find_free
        call count_needs
        call t0_segment
        jp assign

; ---- The walk over the records ----

; first_record starts a walk over the record table, and next_record goes on to
; the next record. Each returns Z after the last record, and otherwise the
; record at IX, its number in rec_n, and in data_n the number of records
; before it that hold data. They keep BC.
first_record:
        ld ix,HDR+H_TABLE
        xor a
        ld (rec_n),a
        ld (data_n),a
        jr next_record.last
next_record:
        ld a,(ix)
        cp REC_ZEROS
        jr z,.nodata
        ld hl,data_n
        inc (hl)
.nodata:
        ld de,REC_SIZE
        add ix,de
        ld hl,rec_n
        inc (hl)
.last:
        ld a,(rec_n)
        ld hl,HDR+H_RECS
        cp (hl)
        ret

; Returns Z when the record at IX is a RAM page of DOS's mapper.
dos_record:
        ld a,(ix)
        cp REC_MAPPER
        ret nz
        ld a,(dos_slot)
        cp (ix+1)
        ret

; Returns Z when the segment of the record at IX is DOS's segment in page 1 or
; 2, which the record is read straight into.
in_dos_page:
        ld a,(ix+3)
        ld hl,dos_seg1
        cp (hl)
        ret z
        inc hl
        cp (hl)
        ret

; Returns HL at the byte of dest for the record at IX: the segment of DOS's
; mapper that the record is read into.
dest_hl:
        ld a,(rec_n)
        ld l,a
        ld h,high dest
        ret

; ---- Step 1: DOS, its mapper and its segments ----

; Sets dos2, dos_slot (DOS's mapper's slot ID), m_ps and m_ss (its primary slot
; and its subslot), map_size and dos_seg0 to dos_seg3, and the mapper calls
; put_p2 and all_seg.
find_dos:
        ; RAMAD0 to RAMAD3 name one slot, DOS's mapper.
        ld hl,RAMAD0
        ld a,(hl)
        ld (dos_slot),a
        ld b,3
.ramad:
        inc hl
        cp (hl)
        ld de,t_onemapper
        jp nz,stop_name
        djnz .ramad
        and 3
        ld (m_ps),a
        ld a,(dos_slot)
        rrca
        rrca
        and 3
        ld (m_ss),a
        ; MSX-DOS 1 has no function 6Fh and leaves B as it is.
        ld b,0
        ld c,_DOSVER
        call BDOS
        ld a,b
        cp 2
        jr c,.dos1
        ld a,1
        ld (dos2),a
        ; MSX-DOS 2's mapper support: EXTBIO with D=4, E=2 returns the
        ; jump table in HL, the primary mapper's size in A and its slot in B
        ; (MSX-DOS 2 Program Interface Specification, section 5.2).
        xor a
        ld de,0402h
        call EXTBIO
        ld (map_size),a
        ld a,b
        ld (map_slot),a
        ld de,00h               ; ALL_SEG
        ld ix,all_seg
        call patch_jump
        ld de,24h               ; PUT_P2
        ld ix,put_p2
        call patch_jump
        ld de,1Bh               ; GET_P0, then GET_P1 to GET_P3, 6 bytes apart
        add hl,de
        ld iy,dos_seg0
        ld b,4
.getp:
        ld (get_p+1),hl
        push bc
        push hl
        push iy
        call get_p
        pop iy
        ld (iy),a
        inc iy
        pop hl
        ld de,6
        add hl,de
        pop bc
        djnz .getp
        ld a,(map_slot)
        ld b,a
        ld a,(dos_slot)
        cp b
        ld de,t_onemapper
        jp nz,stop_name
        ret
.dos1:
        ; MSX-DOS 1 has no mapper calls. The restorer takes DOS's segments
        ; for 3, 2, 1 and 0, as the MSX2 BIOS sets them (MSX2 Technical
        ; Handbook, chapter 5, section 7) and Nextor does, checks them, and
        ; counts the mapper's segments itself.
        ld hl,0203h             ; dos_seg0 3, dos_seg1 2
        ld (dos_seg0),hl
        ld hl,0001h             ; dos_seg2 1, dos_seg3 0
        ld (dos_seg2),hl
        ld hl,dos1_put_p2
        ld (put_p2+1),hl
        call check_dos1
        jp count_dos1

; Points the jump at IX+0 to the mapper table at HL plus DE.
patch_jump:
        push hl
        add hl,de
        ld (ix+1),l
        ld (ix+2),h
        pop hl
        ret

; The mapper calls, pointed at MSX-DOS 2's routines or at dos1_put_p2. Until
; then they return.
all_seg: jp no_call
put_p2:  jp no_call
get_p:   jp no_call
no_call: scf
        ret

dos1_put_p2:
        out (0FEh),a
        ret

; Checks under MSX-DOS 1 that pages 0 to 3 show segments dos_seg0 to dos_seg3
; of a mapper, with interrupts off. A mapper register cannot be read back on
; every machine, so the check looks through page 2. For page 2 itself, a mark
; that it writes at 8000h must still be there with dos_seg2 selected: when it
; is not, page 2's segment is lost, and the restorer stops. For each other
; page, with the page's segment selected in page 2, a byte that it changes at
; the page's first address through page 2 must change in the page too.
DOS1_MARK equ 0A55Ah
check_dos1:
        di
        ld hl,(8000h)
        push hl
        ld hl,DOS1_MARK
        ld (8000h),hl
        ld a,(dos_seg2)
        out (0FEh),a
        ld de,(8000h)
        or a
        sbc hl,de
        pop hl
        jr nz,.differ
        ld (8000h),hl
        ld de,8000h
        ld h,00h
        ld a,(dos_seg0)
        call .same
        ld h,40h
        ld a,(dos_seg1)
        call .same
        ld h,0C0h
        ld a,(dos_seg3)
        call .same
        ld a,(dos_seg2)
        out (0FEh),a
        ei
        ret
; Stops unless the page at H*256 shows segment A.
.same:
        out (0FEh),a
        ld l,e
        ld a,(de)
        cpl
        ld (de),a
        cp (hl)
        cpl                     ; CPL and LD keep the Z flag
        ld (de),a
        jr nz,.other
        cp (hl)
        ret z
.other:
        pop hl
.differ:
        ld a,(dos_seg2)
        out (0FEh),a
        ei
        ld de,t_dos1
        jp stop_name

; Counts DOS's mapper under MSX-DOS 1: with interrupts off and through page 2,
; saves the first byte of segments 0 to 3, writes each segment's number into
; its first byte from 255 down to 0, reads them back from 4 up to the first
; mismatch, and restores the saved bytes.
count_dos1:
        di
        ld hl,saved4
        ld b,0
.save:
        ld a,b
        out (0FEh),a
        ld a,(8000h)
        ld (hl),a
        inc hl
        inc b
        ld a,b
        cp 4
        jr nz,.save
        ld b,255
.write:
        ld a,b
        out (0FEh),a
        ld (8000h),a
        dec b
        ld a,b
        cp 255
        jr nz,.write
        ld b,4
.read:
        ld a,b
        out (0FEh),a
        ld a,(8000h)
        cp b
        jr nz,.size
        inc b
        jr nz,.read
.size:
        ld a,b
        ld (map_size),a         ; 0 for 256 segments
        ld hl,saved4
        ld b,0
.restore:
        ld a,b
        out (0FEh),a
        ld a,(hl)
        ld (8000h),a
        inc hl
        inc b
        ld a,b
        cp 4
        jr nz,.restore
        ld a,(dos_seg2)
        out (0FEh),a
        ei
        ret

; ---- Step 1: the ROMs ----

check_roms:
        ld hl,worker2
        ld de,8000h
        ld bc,WORKER_SIZE
        ldir
        call w2.crc_roms
        push de
        ld de,(HDR+H_ROM)
        or a
        sbc hl,de
        pop hl
        ld de,t_roms
        jp nz,stop_name
        ld de,(HDR+H_SUBROM)
        or a
        sbc hl,de
        ld de,t_roms
        jp nz,stop_name
        ret

; ---- Step 1: the file's size ----

; The file must hold the header and the tables, and the data of each record
; that has data. A file that is cut would otherwise stop the restore at a read,
; after the game's memory is written.
check_size:
        call first_record
.record:
        jr z,.size
        call next_record
        jr .record
.size:
        call data_offset        ; the size, bits 16 to 23 in C and 8 to 15 in D
        ld a,(fcb+FCB_FILESIZE+3)
        or a
        ret nz                  ; 16 MB or more
        ld hl,(fcb+FCB_FILESIZE+1)
        ld e,d
        ld d,c
        or a
        sbc hl,de
        ret nc
        ld de,t_cut
        jp stop_name

; Returns in C and D bits 16 to 23 and bits 8 to 15 of the image's offset after
; the header and tables and the data of data_n records. Bits 0 to 7 are zero.
data_offset:
        ld a,(data_n)           ; at most 255 records
        ld c,a
        srl c
        srl c
        and 3
        rrca
        rrca
        or high H_SIZE
        ld d,a
        ret

; ---- Step 1: the worker's page at the end ----

; Choose worker page (1 or 2, distinct from tail's page) so the worker stays
; mapped when writing DOS's expanded subslot register: prefer (1) a page whose
; snapshot subslot already matches DOS's mapper, (2) any page if page 3 is DOS's
; slot (tail writes FFFFh), or (3) a page not selecting DOS's slot at snapshot.
find_worker_page:
        ld a,(HDR+H_TAIL+1)
        rlca
        rlca
        and 3
        ld (tail_page),a
        call dos_sub
        ld a,(hl)
        ld (m_sub),a            ; the snapshot's subslot register of the slot
        xor a
        ld (worker_mode),a
        ld b,1
.exact:
        call other_than_tail
        jr z,.exact_next
        ld a,(dos_slot)
        bit 7,a
        jr z,.found
        ld a,(m_sub)
        call bits_of_page
        ld c,a
        ld a,(m_ss)
        cp c
        jr z,.found
.exact_next:
        inc b
        ld a,b
        cp 3
        jr nz,.exact
        ld a,(HDR+H_A8)
        rlca
        rlca
        and 3
        ld c,a
        ld a,(m_ps)
        cp c
        jr nz,.latent
        ld a,1                  ; 2: the tail writes the subslot register
        ld (worker_mode),a
        ld b,1
        call other_than_tail
        jr nz,.found
        inc b
        jr .found
.latent:
        ld a,2                  ; 3: a page outside DOS's mapper's slot
        ld (worker_mode),a
        ld b,1
.page:
        call other_than_tail
        jr z,.page_next
        ld a,(HDR+H_A8)
        call bits_of_page
        ld c,a
        ld a,(m_ps)
        cp c
        jr nz,.found
.page_next:
        inc b
        ld a,b
        cp 3
        jr nz,.page
        ld de,t_noworker
        jp stop_name
.found:
        ld a,b
        ld (worker_page),a
        ret

; Returns NZ when page B is not the tail's.
other_than_tail:
        ld a,(tail_page)
        cp b
        ret

; Returns in A page B's 2 bits of the register value in A. Keeps B, DE and HL.
bits_of_page:
        ld c,b
        inc c
.shift:
        dec c
        jr z,.done
        rrca
        rrca
        jr .shift
.done:
        and 3
        ret

; Returns HL at the header's subslot register of DOS's mapper's slot, and that
; slot in E.
dos_sub:
        ld a,(m_ps)
        ld e,a
        ld d,0
        ld hl,HDR+H_SUB
        add hl,de
        ret

; ---- Step 1: the records ----

; Each RAM page's slot must be on this machine what it was at the capture:
; expanded or not, and not DOS's mapper for a page outside a mapper, whose copy
; would go over DOS's own memory. Each record's segment must be within DOS's
; mapper's size. With the tape service, no page 0 may be in another subslot of
; DOS's mapper's slot, and the snapshot changes so that the game finds T0 in
; page 0.
check_records:
        ; The slot register value that selects DOS's mapper in page 0, for the
        ; places.
        ld a,(HDR+H_A8)
        and 0FCh
        ld hl,m_ps
        or (hl)
        ld (t0_a8),a
        call first_record
.record:
        jr z,.checked
        ld a,(ix)
        cp REC_SERVICE
        jr nz,.ram
        ld (service),a
        jr .next
.ram:
        jr nc,.next             ; a VRAM block
        ld a,(ix+1)
        and 3
        ld e,a
        ld d,0
        ld hl,EXPTBL
        add hl,de
        ld a,(hl)
        xor (ix+1)
        rlca                    ; bit 7: expanded
        ld hl,t_expanded
        jp c,stop_slot
        ld a,(ix)
        cp REC_RAM
        jr nz,.page0
        ld a,(dos_slot)
        cp (ix+1)
        ld hl,t_plain
        jp z,stop_slot
.page0:
        ld a,(ix+2)
        or a
        jr nz,.size
        ; A page 0 in DOS's mapper sets bit 0 of p0, in another subslot of its
        ; slot bit 1.
        ld a,(dos_slot)
        cp (ix+1)
        ld c,1
        jr z,.p0
        xor (ix+1)
        and 3
        jr nz,.size
        ld c,2
.p0:
        ld a,(p0)
        or c
        ld (p0),a
.size:
        call dos_record
        jr nz,.next
        ld a,(map_size)
        or a
        jr z,.next              ; 256 segments
        ld c,a
        ld a,(ix+3)
        cp c
        ld de,t_mapsize
        jp nc,stop_name
.next:
        call next_record
        jr .record
.checked:
        ld a,(service)
        or a
        ret z
        ld a,(p0)
        bit 1,a
        ld de,t_page0
        jp nz,stop_name
        ; Without a part in page 3, T0 takes mapper register FCh for good, so
        ; no RAM page for page 0 may be in DOS's mapper.
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        jr z,.rom
        ld a,(p0)
        rrca
        ld de,t_t0page0
        jp c,stop_name
        ; TAPIN selects DOS's mapper in the borrowed page by the slot register
        ; alone, so the subslot register of DOS's mapper's slot must select
        ; the mapper there.
        ld a,(dos_slot)
        bit 7,a
        jr z,.rom
        call dos_sub
        ; A slot that the capture did not have expanded: the game never wrote
        ; its subslot register, so the borrowed page gets the mapper's subslot.
        ld a,(HDR+H_NOEXP)
        ld b,e
        inc b
.noexp:
        rrca
        djnz .noexp
        jr nc,.check
        push hl
        ld a,(HDR+H_BORROW)
        ld b,a
        ld a,(m_ss)
        call page_bits
        pop hl
        ld e,a
        ld a,(hl)
        and d
        or e
        ld (hl),a
        jr .rom
.check:
        ld a,(HDR+H_BORROW)
        ld b,a
        ld a,(hl)
        call bits_of_page
        ld hl,m_ss
        cp (hl)
        ld de,t_t0sub
        jp nz,stop_name
.rom:
        ; T0 replaces the ROM when page 0 selects it, no RAM page for page 0
        ; is in DOS's mapper, and the game file has no rom keep: page 0 then
        ; selects DOS's mapper. This holds in both modes.
        ld b,0
        call selected_slot
        ld hl,EXPTBL
        cp (hl)
        ld de,t_page0
        jr nz,.kept
        ld a,(p0)
        rrca
        jr c,.kept
        ld a,(HDR+H_FLAGS)
        and FLAG_ROM_KEEP
        ld de,t_romkeep
        jr nz,.kept
        ld a,1
        ld (t0_rom),a
        ld a,(t0_a8)
        ld (HDR+H_A8),a
        jr .subslot
.kept:
        ; Page 0 keeps the snapshot's slot. The entry code finds T0 by the
        ; slot register alone, so page 0's bits of the subslot register of
        ; DOS's mapper's slot become the mapper's subslot below. When the
        ; snapshot's page 0 is in another subslot of that slot, as the ROM of
        ; a game file with rom keep can be, it would become the mapper's RAM,
        ; so the restorer stops with the message at DE. With sub0, the entry
        ; code selects the mapper's subslot in page 0 itself, while it runs,
        ; so page 0's bits stay the snapshot's here and in SLTTBL.
        ld a,(dos_slot)
        bit 7,a
        ret z
        push de
        call sub0_on
        pop de
        jr nz,.static
        ld a,1
        ld (p0_live),a
        ret
.static:
        ld a,(HDR+H_A8)
        and 3
        ld hl,m_ps
        cp (hl)
        jr nz,.subslot
        push de
        call dos_sub
        pop de
        ld a,(hl)
        and 3
        ld hl,m_ss
        cp (hl)
        jp nz,stop_name
.subslot:
        ; DOS's mapper's subslot in page 0, so that the entry code finds T0
        ; by the slot register alone.
        ld a,(dos_slot)
        bit 7,a
        ret z
        call dos_sub
        call subslot_bits
        ld (hl),a
        ret

; Returns Z when the image's entry code has sub0 (FLAG_P0, with the part in
; page 3) and the snapshot's page 3 is in DOS's mapper, whose slot's subslot
; register sub0 then writes at FFFFh (docs/internals/service-and-resident.md, Page 0 in another subslot
; of DOS's mapper's slot).
sub0_on:
        ld a,(HDR+H_FLAGS)
        and FLAG_P0|FLAG_T0
        cp FLAG_P0
        ret nz
        ld b,3
        call selected_slot
        ld hl,dos_slot
        cp (hl)
        ret

; Returns in A the value at HL with its page 0 bits set to DOS's mapper's
; subslot.
subslot_bits:
        ld a,(m_ss)
        ld c,a
        ld a,(hl)
        and 0FCh
        or c
        ret

; Returns in A the slot ID that the snapshot selects in page B.
selected_slot:
        ld a,(HDR+H_A8)
        call bits_of_page
        ld e,a
        ld d,0
        ld hl,EXPTBL
        add hl,de
        bit 7,(hl)
        ret z
        ld hl,HDR+H_SUB
        add hl,de
        ld a,(hl)
        call bits_of_page
        rlca
        rlca
        or e
        or 80h
        ret

; The manual tape needs the tape service with its part in page 3, because T0
; has no room for its code. Otherwise /M says that the tape stays automatic,
; and the restore goes on.
manual_note:
        ld a,(manual)
        or a
        ret z
        ld a,(service)
        or a
        jr z,.note
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        ret z
.note:
        call name
        ld de,t_manual
        jp print

