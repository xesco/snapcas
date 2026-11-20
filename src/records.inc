; ---- Step 3: the records ----

; Reads and places the records in four passes. The VRAM blocks come last: the
; first one blanks the screen and writes over DOS's text.
PASS_OTHER   equ 1              ; RAM pages of other slots than DOS's mapper
PASS_SERVICE equ 2              ; service segments
PASS_DOS     equ 3              ; RAM pages of DOS's mapper
PASS_VRAM    equ 4              ; VRAM blocks
read_records:
        ld a,PASS_OTHER
.pass:
        ld (pass),a
        call first_record
.record:
        jr z,.passed
        call record_pass
        ld hl,pass
        cp (hl)
        call z,place
        call next_record
        jr .record
.passed:
        ld a,(pass)
        inc a
        cp PASS_VRAM+1
        jr nz,.pass
        ret

; Returns in A the pass of the record at IX.
record_pass:
        ld a,(ix)
        cp REC_SERVICE
        ld a,PASS_SERVICE
        ret z
        ld a,PASS_VRAM
        ret nc
        call dos_record
        ld a,PASS_DOS
        ret z
        ld a,PASS_OTHER
        ret

; Reads the record at IX and places it, in the pass in A. Keeps IX.
place:
        cp PASS_OTHER
        jr z,other_page
        cp PASS_VRAM
        jp z,vram_block
        jp dos_page

; A RAM page of another slot than DOS's mapper: read into page 2, or page 1
; for a target in page 2, and copied to its slot by the restorer, or by the
; worker in page 1 for a target in page 0.
other_page:
        ld a,(ix+2)
        cp 2
        ld hl,8000h
        jr nz,.buffer
        ld hl,4000h
.buffer:
        ld (buffer),hl
        call read_this
        ld hl,(buffer)
        call fill
        ld a,(ix+2)
        or a
        jr nz,.restorer
        ld hl,worker1
        ld de,4000h
        ld bc,WORKER_SIZE
        ldir
        ld a,(dos_seg0)
        ld (w1.dos_fc),a
        ld c,(ix+1)
        call segment_de
        call w1.copy_page0
        ret nc
        jr not_ram
.restorer:
        ld hl,(buffer)
        call copy_page
        ret nc
not_ram:
        ld a,(ix+2)
        add a,"0"
        ld (t_page_n),a
        ld hl,t_notram
; Prints the image's name, then the message at HL with the primary slot of the
; record at IX at SLOT_AT in it, and ends the program.
SLOT_AT equ 7                   ; after ": slot "
stop_slot:
        push hl
        ld de,SLOT_AT
        add hl,de
        ld a,(ix+1)
        and 3
        add a,"0"
        ld (hl),a
        pop de
        jp stop_name

; Returns D = 1 and the segment in E for the record at IX of a RAM page in a
; mapper, and D = 0 for one of a page outside a mapper.
segment_de:
        ld d,0
        ld a,(ix)
        cp REC_MAPPER
        ret nz
        inc d
        ld e,(ix+3)
        ret

; Copies the 16 KB at HL to page (IX+2), 1 to 3, of slot (IX+1), reads it
; back, and returns with carry set on a mismatch. In an expanded slot, the copy
; of page 3 stops at FFFEh, because FFFFh is the subslot register.
copy_page:
        di
        ld (dos_sp),sp
        ld sp,STACK
        push hl
        ld b,(ix+2)
        ld c,(ix+1)
        call select_slot
        call segment_de
        dec d
        jr nz,.copy             ; outside a mapper
        ld a,(ix+2)
        add a,0FCh
        ld c,a
        out (c),e
.copy:
        pop hl
        ld a,(ix+2)
        rrca
        rrca
        ld d,a
        ld e,0
        ld bc,4000h
        cp 0C0h
        jr nz,.length
        bit 7,(ix+1)
        jr z,.length
        dec bc
.length:
        push hl
        push de
        push bc
        ldir
        pop bc
        pop de
        pop hl
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
        ld a,(ix+2)
        ld e,a
        ld d,0
        ld hl,dos_seg0
        add hl,de
        ld a,(ix+2)
        add a,0FCh
        ld c,a
        ld a,(hl)
        out (c),a
        call restore_slot
        pop af
        ld sp,(dos_sp)
        ei
        ret

; A RAM page of DOS's mapper or a service segment, read into its segment
; through page 2. T0, in the mode without a part in page 3, or else the code
; segment, gets the table of the tape's segments.
dos_page:
        call dest_hl
        ld a,(hl)
        call select_p2
        ld hl,8000h
        call read_this
        ld a,(ix)
        cp REC_SERVICE
        jr z,.service
        ld hl,8000h
        call fill
        jr .back
.service:
        ld hl,svc_i
        ld a,(hl)
        inc (hl)
        ld c,a                  ; this service segment's number: 0 for T0
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        jr z,.code
        ld a,c
        or a
        jr nz,.back
        ; DOS's mapper's slot in the borrowed page's bits of the slot
        ; register, for TAPIN.
        ld a,(HDR+H_BORROW)
        ld b,a
        ld a,(m_ps)
        call page_bits
        ld (8000h+(T_PAGE & 3FFFh)+2),a
        ld de,8000h+(T_SEGS & 3FFFh)
        ld bc,T_SEGS_MAX
        jr .table
.code:
        dec c
        jr nz,.back
        ld a,(manual)
        ld (8000h+C_MODE),a
        ld de,8000h+C_SEGS
        ld bc,SEGS_MAX
.table:
        ld hl,svc_segs+1
        ldir
.back:
        ld a,(dos_seg2)
select_p2:
        push ix
        push iy
        call put_p2
        pop iy
        pop ix
        ret

; A VRAM block, written with the display blanked. Its buffer is the worker's
; segment in page 2, which is free until step 6: by now DOS's own segment in
; page 2 can hold a page of the game. DOS's text mode has no planar layout, so
; the bytes go to VRAM as stored. On an MSX2, register 14 selects the 16 KB
; block.
vram_block:
        ld a,(worker_seg)
        call select_p2
        ld a,(ix)
        cp REC_ZEROS
        jr z,.zeros
        ld hl,8000h
        call read_this
        jr .write
.zeros:
        ld hl,8000h
        ld de,8001h
        ld bc,3FFFh
        ld (hl),0
        ldir
.write:
        ld a,1
        ld (vram_written),a
        di
        ; DOS's register 1 with bit 7 from the snapshot's, so that the VDP maps
        ; VRAM as the game does: bit 7 chooses a TMS9918's 4 KB or 16 KB
        ; mapping (TMS9918A data book, register 1). DOS's bit 5 keeps the
        ; VDP's interrupt, which DOS needs between the blocks.
        ld a,(HDR+H_VDP1)
        and 80h
        ld b,a
        ld a,(RG1SAV)
        and 3Fh                 ; bit 6 clear: the display blanked
        or b
        out (99h),a
        ld a,81h
        out (99h),a
        ld a,(EXBRSA)
        or a
        jr z,.pointer
        ld a,(ix+1)
        out (99h),a
        ld a,8Eh                ; register 14: VRAM bits 14 to 16
        out (99h),a
.pointer:
        xor a
        out (99h),a
        ld a,40h                ; a write setup at 0000h
        out (99h),a
        ld hl,8000h
        ld c,98h
        ld d,64                 ; 64 times 256 bytes
.otir:
        ld b,0
        otir
        dec d
        jr nz,.otir
        ei
        ld a,(dos_seg2)
        jr select_p2

; Reads the record at IX into HL, or stops. The only stop after a VRAM block
; is this one, at a later block that cannot be read, so it first makes the
; screen DOS's text screen again.
read_this:
        call read_record
        ret z
        call text_screen
        ld de,t_read
        jp stop_name

; Reads the 16 KB of the record at IX into HL, from its place in the image:
; after the header and tables and the data of each record before it that holds
; data. Returns Z when all of it was read.
read_record:
        call data_offset
        ld e,0
        ld b,0
        push hl
        ld hl,DATA_SIZE
        ld (count),hl
        pop hl
; Reads (count) bytes into HL from the image's offset BC:DE. Returns Z when all
; of them were read.
read_bytes:
        push ix
        push iy
        ld a,(by_path)
        or a
        jr z,.fcb
        push hl                 ; the buffer
        ex de,hl                ; the offset's low word
        ld d,b                  ; and its high word
        ld e,c
        ld a,(handle)
        ld b,a
        xor a                   ; from the file's start
        ld c,_SEEK
        call BDOS
        pop de
        or a
        jr nz,.done
        ld a,(handle)
        ld b,a
        ld hl,(count)
        ld c,_READ
        call BDOS
        or a
        jr z,.compare
        jr .done
.fcb:
        ld (fcb+FCB_RANDOM),de
        ld (fcb+FCB_RANDOM+2),bc
        ex de,hl
        ld c,_SETDTA
        call BDOS
        ld hl,(count)
        ld de,fcb
        ld c,_RDBLK
        call BDOS
.compare:
        ld de,(count)
        or a
        sbc hl,de
.done:
        pop iy
        pop ix
        ret

; After a VRAM block, the display is blanked and VRAM holds the game's, so a
; message would not show. This sets up DOS's text screen again, of 40 or 32
; columns by SCRMOD, with the BIOS's INITXT or INIT32 in the main ROM's slot,
; whose ID is at EXPTBL. On an MSX2 it first selects VRAM's first 16 KB block
; again in register 14. Before a VRAM block it does nothing.
text_screen:
        ld a,(vram_written)
        or a
        ret z
        ld a,(dos_seg2)
        call select_p2
        ld a,(EXBRSA)
        or a
        jr z,.init
        di
        xor a
        out (99h),a
        ld a,8Eh
        out (99h),a
.init:
        ld ix,INITXT
        ld a,(SCRMOD)
        or a
        jr z,.call
        ld ix,INIT32
.call:
        ld iy,(EXPTBL-1)
        call CALSLT
        ei
        ret

; Fills in the values that depend on this machine in the data at HL of the
; record at IX: the tail, in the record that holds it, the tape service's
; values in the game's page 3, in the record that holds that page, and each
; place of the record. The header names both records by their numbers, because
; a record of a segment that the game selects in two pages has one page field.
fill:
        ld a,(rec_n)
        ld c,a
        ld a,(HDR+H_TAILREC)
        cp c
        call z,fill_tail
        ld a,(service)
        or a
        jr z,.places
        ld a,(HDR+H_P3REC)
        cp c
        call z,fill_page3
.places:
        ; A place gets the slot register value that selects DOS's mapper in
        ; page 0 (FORMATS.md, Image).
        ld a,(HDR+H_PLACES)
        or a
        ret z
        ld b,a
        ld iy,(places_at)
.place:
        ld a,(iy)
        cp c
        jr nz,.next
        ld e,(iy+1)
        ld d,(iy+2)
        push hl
        add hl,de
        ld a,(t0_a8)
        ld (hl),a
        pop hl
.next:
        ld de,PLACE_SIZE
        add iy,de
        djnz .place
        ret

; Fills in the tail in the record's data at HL (FORMATS.md, Tail): the worker's
; page's mapper register and its value, the slot register, and the write of
; DOS's mapper's slot's subslot register when the tail makes it. Keeps BC and
; HL.
fill_tail:
        push hl
        ld de,(HDR+H_TAIL)
        ld a,d
        and 3Fh
        ld d,a
        add hl,de
        push hl
        pop iy
        ld a,(worker_page)
        ld e,a
        ld d,0
        ld hl,HDR+H_MAP
        add hl,de
        ld a,(hl)
        ld (iy+TAIL_MAP),a      ; the snapshot's mapper register
        ld a,e
        add a,0FCh
        ld (iy+TAIL_PORT),a     ; FDh or FEh
        ld a,(HDR+H_A8)
        ld (iy+TAIL_A8),a
        ld a,(worker_mode)
        cp 1
        jr nz,.done
        ld a,(m_sub)
        ld (iy+TAIL_SUB),a
        ld (iy+TAIL_LD),32h     ; LD (0FFFFh),A
        ld (iy+TAIL_LD+1),0FFh
        ld (iy+TAIL_LD+2),0FFh
.done:
        pop hl
        ret

; With the tape service, fills in the game's page 3 in the record's data at HL:
; DOS's mapper's slot ID, T0's segment and the code segment, T0's segment for
; mapper register FCh when T0 replaces the ROM, and DOS's mapper's subslot in
; the page 0 bits of SLTTBL, unless sub0 selects that subslot itself. Without
; a part in page 3, only SLTTBL. Keeps BC and HL.
fill_page3:
        push bc
        push hl
        ld a,(HDR+H_FLAGS)
        and FLAG_T0
        jr nz,.slttbl
        push hl
        ld a,(HDR+H_P3)         ; the page of the service's page 3 part
        sub 0C0h
        ld d,a
        ld e,E_SLOT & 0FFh
        add hl,de
        ld a,(dos_slot)
        ld (hl),a
        inc hl
        ex de,hl
        ld hl,svc_segs
        ldi                     ; E_T0
        ldi                     ; E_CODE
        ld a,(t0_rom)
        or a
        jr z,.part
        dec hl
        dec hl
        ldi                     ; E_FC
.part:
        pop hl
.slttbl:
        ld a,(p0_live)
        or a
        jr nz,.done             ; sub0 selects the subslot itself
        ld a,(dos_slot)
        bit 7,a
        jr z,.done
        ld a,(m_ps)
        ld de,SLTTBL-0C000h
        add a,e
        ld e,a
        add hl,de
        call subslot_bits
        ld (hl),a
.done:
        pop hl
        pop bc
        ret

