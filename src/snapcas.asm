; SNAPCAS.COM, the snapcas restorer (docs/INTERNALS.md, Restorer).
;
; SNAPCAS <GAME> restores <GAME>.SNP, the snapshot of a cassette game, and
; starts the game.
;
; It runs under MSX-DOS 1, MSX-DOS 2 and Nextor. Its code and its data stay
; below 4000h, in page 0, so that pages 1 and 2 are free for its buffers and its
; worker. It keeps DOS's stack, in page 3, because MSX-DOS 2's mapper routines
; page the DOS kernel into page 0, and switches to a stack in page 0 only while
; it selects other slots in page 3. It reads the image with the FCB functions, which
; MSX-DOS 1 has and MSX-DOS 2 and Nextor keep (MSX-DOS 2 Function Codes
; Specification).

BDOS    equ 0005h       ; DOS function call
_TERM0  equ 00h         ; end the program
_CONOUT equ 02h         ; print the character in E
_STROUT equ 09h         ; print the string at DE, ended by "$"
_FOPEN  equ 0Fh         ; open the file of the FCB at DE
_SETDTA equ 1Ah         ; read at DE
_RDBLK  equ 27h         ; read HL records of the FCB at DE
_DOSVER equ 6Fh         ; MSX-DOS 2 only: the version in B

DOSFCB  equ 005Ch       ; DOS parses the first argument into this FCB
FCB_RECSIZE equ 14      ; FCB offsets: record size, 2 bytes
FCB_RANDOM  equ 33      ; random record, 4 bytes
FCB_SIZE    equ 37

; System variables (MSX Red Book, chapter 6; map.grauw.nl).
RAMAD0  equ 0F341h      ; DOS's RAM slots of pages 0 to 3
RG1SAV  equ 0F3E0h      ; the last value written to VDP register 1
EXBRSA  equ 0FAF8h      ; the sub-ROM's slot ID, 0 on an MSX1
JIFFY   equ 0FC9Eh      ; counts the VDP's interrupts
EXPTBL  equ 0FCC1h      ; the main ROM's slot ID, then one byte per slot
SLTTBL  equ 0FCC5h      ; the subslot register of each slot
EXTBIO  equ 0FFCAh      ; MSX-DOS 2's extended BIOS

; The image (FORMATS.md, Image).
HDR     equ 2800h       ; the image's first 4,096 bytes
H_ROM   equ HDR+8
H_SUBROM equ HDR+10
H_RECS  equ HDR+12
H_WRITES equ HDR+13
H_FLAGS equ HDR+14      ; bit 0: T0 does not replace the ROM, bit 1: T0 mode
H_P3    equ HDR+15      ; the page of the service's page 3 part, as xxE1h
H_REGS  equ HDR+16      ; AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC
H_I     equ HDR+40
H_IM    equ HDR+41
H_A8    equ HDR+43
H_SUB   equ HDR+44
H_MAP   equ HDR+48
H_TAIL  equ HDR+52
H_VDP1  equ HDR+54      ; the snapshot's VDP register 1
H_BORROW equ HDR+55     ; the page that TAPIN borrows without a part in page 3
H_NOEXP equ HDR+56      ; bit n: the capture's slot n was not expanded
H_TABLE equ HDR+64
T_MAPPER equ 1          ; record types
T_RAM    equ 2
T_SERVICE equ 3
T_VRAM   equ 4
T_ZEROS  equ 5

STACK   equ 4000h

        include "service.inc"

        org 0100h

start:
        ld a,(DOSFCB+1)
        cp " "
        ld de,t_usage
        jp z,stop_message
        ; /M in the command line, its length at 0080h and its text after it,
        ; asks for the manual tape (INTERNALS.md, The manual tape). It is read
        ; first, before a DOS call can use 0080h.
        ld hl,0080h
        ld b,(hl)
.option:
        ld a,b
        or a
        jr z,.options
        inc hl
        dec b
        ld a,(hl)
        cp "/"
        jr nz,.option
        ld a,b
        or a
        jr z,.options
        inc hl
        dec b
        ld a,(hl)
        and 0DFh                ; upper case
        cp "M"
        jr nz,.option
        ld a,1
        ld (manual),a
        jr .option
.options:
        ; Copy the drive and the name into our own FCB, which already holds
        ; the extension SNP. The FCB at 005Ch cannot be used as it is: its
        ; random record field overlaps the command line at 0080h.
        ld hl,DOSFCB
        ld de,fcb
        ld bc,9
        ldir
        ld de,fcb
        ld c,_FOPEN
        call BDOS
        or a
        ld de,t_notfound
        jp nz,stop_name
        ld hl,1
        ld (fcb+FCB_RECSIZE),hl ; records of 1 byte
        ld hl,4096
        ld (count),hl
        ld hl,HDR
        ld bc,0
        ld de,0
        call read_bytes         ; the first 4,096 bytes, from offset 0
        ld de,t_notimage
        jp nz,stop_name
        ld hl,HDR
        ld de,t_mark
        ld b,7
.mark:
        ld a,(de)
        cp (hl)
        jr nz,.notimage
        inc hl
        inc de
        djnz .mark
        ; The mark's last character is the format's number: another number
        ; means an image for another version of SNAPCAS.COM.
        ld a,(de)
        cp (hl)
        ld de,t_version
        jp nz,stop_name

        call find_dos
        call check_roms
        call check_records
        call manual_note
        call find_worker_page
        call allocate
        call read_records
        call wait_motor
        di
        call port_writes
        jp switch
.notimage:
        ld de,t_notimage
        jp stop_name

; ---- Step 1: DOS, its mapper and its segments ----

; Sets dos2, dos_slot (DOS's mapper's slot ID), map_size and dos_seg0 to
; dos_seg3, and the mapper calls put_p2 and all_seg.
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
.extbio:
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
        ; MSX-DOS 1 runs in segments 3, 2, 1 and 0, as the MSX2 BIOS and
        ; Nextor set them, and gives no count of the mapper's segments.
        ld hl,0203h             ; dos_seg0 3, dos_seg1 2
        ld (dos_seg0),hl
        ld hl,0001h             ; dos_seg2 1, dos_seg3 0
        ld (dos_seg2),hl
        ld hl,dos1_put_p2
        ld (put_p2+1),hl
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
        ld de,(H_ROM)
        or a
        sbc hl,de
        pop hl
        ld de,t_roms
        jp nz,stop_name
        ld de,(H_SUBROM)
        or a
        sbc hl,de
        ld de,t_roms
        jp nz,stop_name
        ret

; ---- Step 1: the worker's page at the end ----

; The worker runs at the end in page 1 or 2, a page other than the tail's,
; selecting DOS's mapper. When that mapper is in an expanded slot, the worker
; must keep the mapper's subslot in its page while it writes the slot's
; subslot register. It takes, in this order:
; 1. a page whose bits in the snapshot's subslot register of that slot already
;    select DOS's mapper's subslot;
; 2. when the snapshot's page 3 selects DOS's mapper's slot, any page: the tail
;    writes the slot's true subslot register at FFFFh;
; 3. a page that does not select DOS's mapper's slot at the snapshot: only that
;    page's bits of the slot's subslot register differ from the snapshot's, and
;    the BIOS writes them again from SLTTBL when it next selects a subslot of
;    the slot.
find_worker_page:
        ld a,(H_TAIL+1)
        rlca
        rlca
        and 3
        ld (tail_page),a
        ld a,(dos_slot)
        and 3
        ld (m_ps),a
        ld e,a
        ld d,0
        ld hl,H_SUB
        add hl,de
        ld a,(hl)
        ld (m_sub),a            ; the snapshot's subslot register of the slot
        ld a,(dos_slot)
        rrca
        rrca
        and 3
        ld (m_ss),a
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
        ld a,(H_A8)
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
        ld a,(H_A8)
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

; Returns in A page B's 2 bits of the register value in A.
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

; ---- Step 1: the records ----

; Each record's segment must be within DOS's mapper's size. With the tape
; service, no RAM page for page 0 may be in another subslot of DOS's mapper's
; slot, and the snapshot changes so that the game finds T0 in page 0.
check_records:
        ld a,(H_RECS)
        or a
        ret z
        ld b,a
        ld ix,H_TABLE
.record:
        ld a,(ix)
        cp T_SERVICE
        jr nz,.ram
        ld (service),a
        jr .next
.ram:
        cp T_RAM+1
        jr nc,.next
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
        ld a,(ix)
        cp T_MAPPER
        jr nz,.next
        ld a,(dos_slot)
        cp (ix+1)
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
        ld de,4
        add ix,de
        djnz .record
        ld a,(service)
        or a
        ret z
        ld a,(p0)
        bit 1,a
        ld de,t_page0
        jp nz,stop_name
        ; Without a part in page 3, T0 takes mapper register FCh for good, so
        ; no RAM page for page 0 may be in DOS's mapper.
        ld a,(H_FLAGS)
        bit 1,a
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
        and 3
        ld e,a
        ld d,0
        ld hl,H_SUB
        add hl,de
        ; A slot that the capture did not have expanded: the game never wrote
        ; its subslot register, so the borrowed page gets the mapper's subslot.
        ld a,(H_NOEXP)
        ld b,e
        inc b
.noexp:
        rrca
        djnz .noexp
        jr nc,.check
        push hl
        ld a,(H_BORROW)
        ld b,a
        ld a,(dos_slot)
        rrca
        rrca
        and 3
        call page_bits
        pop hl
        ld e,a
        ld a,(hl)
        and d
        or e
        ld (hl),a
        jr .rom
.check:
        ld a,(H_BORROW)
        ld b,a
        ld a,(hl)
.borrowed:
        rrca
        rrca
        djnz .borrowed
        ld c,a
        ld a,(dos_slot)
        rrca
        rrca
        xor c
        and 3
        ld de,t_t0sub
        jp nz,stop_name
.rom:
        ld a,(p0)
        ; T0 replaces the ROM when page 0 selects it, no RAM page for page 0
        ; is in DOS's mapper, and the game file has no rom keep: page 0 then
        ; selects DOS's mapper. This holds in both modes.
        rrca
        jr c,.subslot
        ld a,(H_FLAGS)
        rrca
        jr c,.subslot
        ld b,0
        call selected_slot
        ld hl,EXPTBL
        cp (hl)
        jr nz,.subslot
        ld a,1
        ld (t0_rom),a
        ld a,(dos_slot)
        and 3
        ld c,a
        ld a,(H_A8)
        and 0FCh
        or c
        ld (H_A8),a
.subslot:
        ; DOS's mapper's subslot in page 0, so that the entry code finds T0
        ; by the slot register alone.
        ld a,(dos_slot)
        bit 7,a
        ret z
        and 3
        ld e,a
        ld d,0
        ld hl,H_SUB
        add hl,de
        call subslot_bits
        ld (hl),a
        ret

; Returns in A the value at HL with its page 0 bits set to DOS's mapper's
; subslot.
subslot_bits:
        ld a,(dos_slot)
        rrca
        rrca
        and 3
        ld c,a
        ld a,(hl)
        and 0FCh
        or c
        ret

; ---- Step 2: the segments ----

; Marks each free segment of DOS's mapper in freemap, assigns each record of
; DOS's mapper the segment that it is read into, and takes a segment for the
; worker. Each record's segment goes into dest, by record number.
allocate:
        ld a,(dos2)
        or a
        jr z,.dos1
.dos2:
        xor a
        ld b,a                  ; a user segment of the primary mapper
        call all_seg
        jr c,.assign
        ld l,a
        ld h,high freemap
        ld (hl),1
        ld hl,free_count
        inc (hl)
        jr .dos2
.dos1:
        ld a,(map_size)
        ld b,a
        ld a,4
.mark:
        cp b
        jr z,.assign
        ld l,a
        ld h,high freemap
        ld (hl),1
        ld hl,free_count
        inc (hl)
        inc a
        jr nz,.mark
.assign:
        call count_needs
        ; A record whose own segment is free, or is DOS's segment in page 1
        ; or 2, goes straight into it.
        ld a,(H_RECS)
        or a
        jr z,.holding
        ld b,a
        ld ix,H_TABLE
        ld iy,dest
.direct:
        ld (iy),0FFh
        call dos_record
        jr nz,.next
        ld a,(ix+3)
        ld l,a
        ld h,high freemap
        ld c,(hl)
        dec c
        jr z,.straight
        ld hl,dos_seg1
        cp (hl)
        jr z,.own
        inc hl
        cp (hl)
        jr z,.own
        jr .next
.straight:
        ld (hl),0
.own:
        ld (iy),a
.next:
        inc iy
        ld de,4
        add ix,de
        djnz .direct
.holding:
        ; Each other record of DOS's mapper gets a holding segment.
        ld a,(H_RECS)
        or a
        jr z,.worker
        ld b,a
        ld ix,H_TABLE
        ld iy,dest
.hold:
        call dos_record
        jr nz,.hnext
        ld a,(iy)
        cp 0FFh
        jr nz,.hnext
        call take_free
        ld (iy),a
        ld hl,(hold_next)
        ld (hl),a
        inc hl
        ld a,(ix+3)
        ld (hl),a
        inc hl
        ld (hold_next),hl
        ld hl,hold_count
        inc (hl)
.hnext:
        inc iy
        ld de,4
        add ix,de
        djnz .hold
        ; Each service segment, in order, gets one too.
        ld a,(H_RECS)
        ld b,a
        ld ix,H_TABLE
        ld iy,dest
        ld hl,svc_segs
.service:
        ld a,(ix)
        cp T_SERVICE
        jr nz,.snext
        call take_free
        ld (iy),a
        ld (hl),a
        inc hl
.snext:
        inc iy
        ld de,4
        add ix,de
        djnz .service
.worker:
        call take_free
        ld (worker_seg),a
        ld a,(H_FLAGS)          ; bit 1: without a part in page 3
        and 2
        ld hl,t0_rom
        or (hl)
        ret z
        ld a,(svc_segs)
        ld (H_MAP),a            ; T0 in page 0
        ret

; Counts the free segments that the image needs: one for each record of DOS's
; mapper that does not go into DOS's segment in page 1 or 2, one for each
; service segment, and one for the worker. Stops, naming the segments needed and free, when there are too few.
count_needs:
        ld c,1
        ld a,(H_RECS)
        or a
        jr z,.compare
        ld b,a
        ld ix,H_TABLE
.record:
        ld a,(ix)
        cp T_SERVICE
        jr z,.need
        call dos_record
        jr nz,.next
        ld a,(ix+3)
        ld hl,dos_seg1
        cp (hl)
        jr z,.next
        inc hl
        cp (hl)
        jr z,.next
.need:
        inc c
.next:
        ld de,4
        add ix,de
        djnz .record
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

print:
        ld c,_STROUT
        push ix
        push iy
        call BDOS
        pop iy
        pop ix
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
        ld a,(H_FLAGS)
        and 2                   ; bit 1: without a part in page 3
        ret z
.note:
        call name
        ld de,t_manual
        jp print

; Prints A in decimal, without leading zeros.
print_dec:
        ld hl,digits
        ld (hl),0
        ld b,100
        call .digit
        ld b,10
        call .digit
        ld hl,digits
        ld (hl),1
        ld b,1
.digit:
        ld d,"0"-1
.sub:
        inc d
        sub b
        jr nc,.sub
        add a,b
        push af
        ld a,d
        cp "0"
        jr nz,.show
        ld a,(digits)
        or a
        jr z,.skip
.show:
        ld a,1
        ld (digits),a
        ld e,d
        ld c,_CONOUT
        push ix
        push iy
        call BDOS
        pop iy
        pop ix
.skip:
        pop af
        ret

; Returns Z when the record at IX is a RAM page of DOS's mapper.
dos_record:
        ld a,(ix)
        cp T_MAPPER
        ret nz
        ld a,(dos_slot)
        cp (ix+1)
        ret

; Returns in A a free segment, taken from freemap. count_needs has checked that
; there are enough.
take_free:
        push bc
        push hl
        ld hl,freemap
        ld b,0
.find:
        ld a,(hl)
        or a
        jr nz,.take
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

; ---- Step 3: the records ----

; Reads the records in this order: RAM pages of other slots than DOS's
; mapper, VRAM blocks, service segments, then RAM pages of DOS's mapper.
read_records:
        ld a,1
.pass:
        push af
        call each_record
        pop af
        inc a
        cp 5
        jr nz,.pass
        ret

; Places each record of pass A: 1, other slots; 2, VRAM; 3, service segments;
; 4, DOS's mapper.
each_record:
        ld (pass),a
        ld a,(H_RECS)
        or a
        ret z
        ld b,a
        ld ix,H_TABLE
        ld iy,dest
        ld hl,0
        ld (data_before),hl
.record:
        push bc
        ld a,(pass)
        cp 2
        jr z,.vram
        jr c,.one
        cp 3
        jr nz,.dos
        ld a,(ix)
        cp T_SERVICE
        call z,dos_page
        jr .next
.one:
        ld a,(ix)
        cp T_RAM
        jr z,.other
        cp T_MAPPER
        jr nz,.next
        call dos_record
        jr z,.next
.other:
        call other_page
        jr .next
.vram:
        ld a,(ix)
        cp T_VRAM
        jr z,.block
        cp T_ZEROS
        jr nz,.next
.block:
        call vram_block
        jr .next
.dos:
        call dos_record
        call z,dos_page
.next:
        ld a,(ix)
        cp T_ZEROS
        jr z,.nodata
        ld hl,(data_before)
        inc hl
        ld (data_before),hl
.nodata:
        inc iy
        ld de,4
        add ix,de
        pop bc
        djnz .record
        ret

; Reads the 16 KB of the record at IX into HL, from its place in the image:
; after 4,096 bytes of header and 16,384 bytes for each record before it that
; holds data. Returns Z when all of it was read.
read_record:
        ld a,(data_before)      ; at most 255 records
        ld c,a
        srl c
        srl c                   ; C: offset bits 16 to 23
        and 3
        rrca
        rrca
        or 10h                  ; D: offset bits 8 to 15, with 4,096
        ld d,a
        ld e,0
        ld b,0
        push hl
        ld hl,16384
        ld (count),hl
        pop hl
; Reads (count) bytes into HL from the image's offset BC:DE. Returns Z when all
; of them were read.
read_bytes:
        push ix
        push iy
        ld (fcb+FCB_RANDOM),de
        ld (fcb+FCB_RANDOM+2),bc
        ex de,hl
        ld c,_SETDTA
        call BDOS
        ld hl,(count)
        ld de,fcb
        ld c,_RDBLK
        call BDOS
        ld de,(count)
        or a
        sbc hl,de
        pop iy
        pop ix
        ret

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
        ld (w1.dos_seg0),a
        ld c,(ix+1)
        call segment_e
        call w1.copy_page0
        ret nc
        jp not_ram
.restorer:
        ld hl,(buffer)
        call copy_page
        ret nc
not_ram:
        ld a,(ix+1)
        and 3
        add a,"0"
        ld (t_slot_n),a
        ld a,(ix+2)
        add a,"0"
        ld (t_page_n),a
        ld de,t_notram
        jp stop_name

; E = the record's segment, or FFh outside a mapper.
segment_e:
        ld e,0FFh
        ld a,(ix)
        cp T_MAPPER
        ret nz
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
        call segment_e
        ld a,e
        cp 0FFh
        jr z,.copy
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

; A VRAM block, written with the display blanked. DOS's text mode has no
; planar layout, so the bytes go to VRAM as stored. On an MSX2, register 14
; selects the 16 KB block.
vram_block:
        ld a,(ix)
        cp T_ZEROS
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
        di
        ; DOS's register 1 with bit 7 from the snapshot's, so that the VDP maps
        ; VRAM as the game does: bit 7 chooses a TMS9918's 4 KB or 16 KB
        ; mapping (TMS9918A data book, register 1). DOS's bit 5 keeps the
        ; VDP's interrupt, which DOS needs between the blocks.
        ld a,(H_VDP1)
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
        ret

; A RAM page of DOS's mapper or a service segment, read into its segment
; through page 2. The code segment gets the table of its own and the tape's
; segments.
dos_page:
        ld a,(iy)
        call select_p2
        ld hl,8000h
        call read_this
        ld hl,8000h
        ld a,(ix)
        cp T_SERVICE
        jr z,.service
        call fill
        jr .back
.service:
        ld a,(H_FLAGS)          ; bit 1: the table is in T0, not the code segment
        and 2
        jr z,.code
        ld a,(svc_segs)
        cp (iy)
        jr nz,.back
        ; DOS's mapper's slot in the borrowed page's bits of the slot
        ; register, for TAPIN.
        ld a,(H_BORROW)
        ld b,a
        ld a,(dos_slot)
        and 3
.slot:
        add a,a
        add a,a
        djnz .slot
        ld (8000h+(T_PAGE & 3FFFh)+2),a
        ld de,8000h+(T_SEGS & 3FFFh)
        ld bc,T_SEGS_MAX
        jr .table
.code:
        ld a,(svc_segs+1)
        cp (iy)
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

; Reads the record at IX into HL, or stops.
read_this:
        call read_record
        ret z
        ld de,t_read
        jp stop_name

; Fills in the values that depend on this machine in the record at IX, which
; is at HL.
fill:
        push hl
        call fill_tail
        pop hl
; With the tape service, when the record at IX is the game's page 3: DOS's
; mapper's slot ID, T0's segment and the code segment, T0's segment for
; mapper register FCh when T0 replaces the ROM, and DOS's mapper's subslot in
; the page 0 bits of SLTTBL.
        ld a,(service)
        or a
        ret z
        ld a,(ix+2)
        cp 3
        ret nz
        ld b,a
        push hl
        call selected_slot
        pop hl
        cp (ix+1)
        ret nz
        push hl
        ld a,(H_FLAGS)          ; bit 1: no part in page 3, only SLTTBL
        and 2
        jr nz,.slttbl
        ld a,(H_P3)             ; the page of the service's page 3 part
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
        jr z,.slttbl
        dec hl
        dec hl
        ldi                     ; E_FC
.slttbl:
        pop hl
        ld a,(dos_slot)
        bit 7,a
        ret z
        and 3
        ld de,SLTTBL-0C000h
        add a,e
        ld e,a
        add hl,de
        call subslot_bits
        ld (hl),a
        ret

; When the record at IX holds the tail, fills in the values that depend on
; this machine (FORMATS.md, Tail): the worker's page's mapper register and its
; value, and the slot register. HL is where the record is.
fill_tail:
        ld a,(tail_page)
        cp (ix+2)
        ret nz
        ld b,a
        push hl
        call selected_slot
        pop hl
        cp (ix+1)
        ret nz
        ld de,(H_TAIL)
        ld a,d
        and 3Fh
        ld d,a
        add hl,de
        inc hl
        ld a,(worker_page)
        ld e,a
        ld d,0
        push hl
        ld hl,H_MAP
        add hl,de
        ld a,(hl)
        pop hl
        ld (hl),a               ; offset 1: the snapshot's mapper register
        inc hl
        inc hl
        ld a,(worker_page)
        add a,0FCh
        ld (hl),a               ; offset 3: FDh or FEh
        inc hl
        inc hl
        ld a,(H_A8)
        ld (hl),a               ; offset 5: the slot register
        ld a,(worker_mode)
        cp 1
        ret nz
        inc hl
        inc hl
        inc hl
        inc hl
        ld a,(m_sub)
        ld (hl),a               ; offset 9: the subslot register of DOS's mapper
        inc hl
        ld (hl),32h             ; offset 10: LD (0FFFFh),A
        inc hl
        ld (hl),0FFh
        inc hl
        ld (hl),0FFh
        ret

; Returns in A the slot ID that the snapshot selects in page B.
selected_slot:
        ld a,(H_A8)
        ld c,b
        inc c
.shift:
        dec c
        jr z,.got
        rrca
        rrca
        jr .shift
.got:
        and 3
        ld e,a
        ld d,0
        ld hl,EXPTBL
        add hl,de
        bit 7,(hl)
        ret z
        ld hl,H_SUB
        add hl,de
        ld a,(hl)
        ld c,b
        inc c
.shift2:
        dec c
        jr z,.got2
        rrca
        rrca
        jr .shift2
.got2:
        and 3
        rlca
        rlca
        or e
        or 80h
        ret

; ---- Step 4: the floppy drive's motor ----

; Waits until JIFFY has advanced by 180, so that a floppy drive's motor
; stops, with interrupts on.
wait_motor:
        ei
        ld hl,(JIFFY)
        ld (jiffy0),hl
.wait:
        halt
        ld hl,(JIFFY)
        ld de,(jiffy0)
        or a
        sbc hl,de
        ld de,180
        sbc hl,de
        jr c,.wait
        ret

; ---- Step 5: the port writes ----

port_writes:
        ld a,(H_WRITES)
        or a
        ret z
        ld b,a
        ld a,(H_RECS)
        ld l,a
        ld h,0
        add hl,hl
        add hl,hl
        ld de,H_TABLE
        add hl,de
.write:
        ld c,(hl)
        inc hl
        ld a,(hl)
        inc hl
        out (c),a
        djnz .write
        ret

; ---- Step 6: the worker's switch to the game ----

; Fills in the worker's data, copies the worker into its own segment through
; page 2, selects that segment in its page and jumps to it.
switch:
        ld a,(worker_seg)
        out (0FEh),a
        ld a,(worker_page)
        cp 1
        jr nz,.page2
        ld hl,worker1
        ld ix,w1.f_holdn-4000h+8000h
        ld de,w1.f_jump+1-4000h+8000h
        jr .copy
.page2:
        ld hl,worker2
        ld ix,w2.f_holdn
        ld de,w2.f_jump+1
.copy:
        push de
        ld de,8000h
        ld bc,WORKER_SIZE
        ldir
        pop de
        ld hl,(H_TAIL)
        ex de,hl
        ld (hl),e
        inc hl
        ld (hl),d
        ; The holding segments.
        ld a,(hold_count)
        ld (ix+F_HOLDN),a
        push ix
        pop hl
        ld de,F_HOLD
        add hl,de
        ex de,hl
        ld hl,holds
        ld bc,2*64
        ldir
        ; Per slot: expanded, and the snapshot's subslot register.
        ld b,4
        ld hl,EXPTBL
        ld iy,H_SUB
        push ix
.slots:
        ld a,(hl)
        and 80h
        ld (ix+F_EXP),a
        ld a,(iy)
        ld (ix+F_SUB),a
        inc hl
        inc ix
        inc iy
        djnz .slots
        pop ix
        ; Unless page 1 of find_worker_page holds, the worker writes DOS's
        ; mapper's slot's subslot register with the mapper's subslot in its
        ; own page.
        ld a,(worker_mode)
        or a
        jr z,.subslot
        ld a,(worker_page)
        ld b,a
        ld a,(m_ss)
        call page_bits
        ld e,a
        ld a,(m_sub)
        and d
        or e
        push af
        push ix
        pop hl
        ld de,F_SUB
        add hl,de
        ld a,(m_ps)
        ld e,a
        ld d,0
        add hl,de
        pop af
        ld (hl),a
.subslot:
        ld a,(H_A8)
        rlca
        rlca
        and 3
        ld (ix+F_P3),a
        ld b,4
        ld hl,H_MAP
        push ix
.map:
        ld a,(hl)
        ld (ix+F_MAP),a
        inc hl
        inc ix
        djnz .map
        pop ix
        ; The slot register, with the worker's page on DOS's mapper.
        ld a,(worker_page)
        ld b,a
        ld a,(dos_slot)
        and 3
        call page_bits
        ld e,a
        ld a,(H_A8)
        and d
        or e
        ld (ix+F_A8),a
        ; The registers BC, DE, HL, AF', BC', DE', HL', IX and IY: 18 bytes
        ; in the same order in the header and in the worker.
        push ix
        pop hl
        ld de,F_BC
        add hl,de
        ex de,hl
        ld hl,H_REGS+2
        ld bc,18
        ldir
        ld a,(H_I)
        ld (ix+F_I),a
        ld a,(H_IM)
        ld (ix+F_IM),a
        ; Select the worker's segment in its page, and jump.
        ld a,(worker_page)
        add a,0FCh
        ld c,a
        ld a,(worker_seg)
        out (c),a
        ld a,(worker_page)
        cp 1
        jp z,4006h              ; the worker's final, at +6
        jp 8006h

; ---- Messages ----

; Prints the image's name, then the message at DE, and ends the program.
stop_name:
        push de
        call name
        pop de
stop_message:
        call print
        ld a,(dos_seg2)
        call select_p2
        ei
        ld c,_TERM0
        jp BDOS

; Prints the image's name: the FCB's name without its trailing spaces, then
; ".SNP".
name:
        ld hl,fcb+1
        ld b,8
.char:
        ld a,(hl)
        cp " "
        jr z,.ext
        push hl
        push bc
        ld e,a
        ld c,_CONOUT
        call BDOS
        pop bc
        pop hl
        inc hl
        djnz .char
.ext:
        ld de,t_ext
        ld c,_STROUT
        jp BDOS

        include "slots.inc"

t_usage:    db "Usage: SNAPCAS <game> [/M]",13,10
            db "Restores <game>.SNP, a snapcas image.",13,10
            db "/M: the tape moves only with RETURN,",13,10
            db "GRAPH or CODE.",13,10,"$"
t_manual:   db ": /M does not work with this image,",13,10
            db "so the tape stays automatic",13,10,"$"
t_ext:      db ".SNP$"
t_notfound: db " not found",13,10,"$"
t_notimage: db " is not a snapcas image",13,10,"$"
t_version:  db ": made for another version of SNAPCAS.COM",13,10,"$"
t_onemapper: db ": DOS's pages are not in one memory mapper",13,10,"$"
t_roms:     db ": made for another machine: its ROMs differ from this one's",13,10,"$"
t_noworker: db ": no page 1 or 2 can hold the restorer's worker at the end",13,10,"$"
t_mapsize:  db ": a page's segment is beyond this machine's mapper",13,10,"$"
t_segments: db ": DOS has too few free mapper segments",13,10,"$"
t_needs:    db ": needs $"
t_free:     db " free mapper segments, and DOS has $"
t_crlf:     db 13,10,"$"
t_page0:    db ": a page 0 is in another subslot of DOS's mapper's slot",13,10,"$"
t_t0page0:  db ": service t0 needs page 0 outside DOS's mapper",13,10,"$"
t_t0sub:    db ": service t0 needs DOS's mapper's subslot in the borrowed page",13,10,"$"
t_read:     db ": cannot be read",13,10,"$"
t_notram:   db ": slot "
t_slot_n:   db "0 page "
t_page_n:   db "0 is not RAM: the machine file does not describe this machine",13,10,"$"
t_mark:     db "SNAPCAS4"

fcb:        db 0                ; drive, from the argument
            ds 8," "            ; name, from the argument
            db "SNP"
            ds FCB_SIZE-12,0

dos2:       db 0
dos_slot:   db 0
map_slot:   db 0
map_size:   db 0
dos_seg0:   db 0
dos_seg1:   db 0
dos_seg2:   db 0
dos_seg3:   db 0
saved4:     ds 4
tail_page:  db 0
worker_page: db 0
worker_mode: db 0               ; 0, 1 or 2: the rule of find_worker_page
m_ps:       db 0                ; DOS's mapper's primary slot
m_ss:       db 0                ; and subslot
m_sub:      db 0                ; the snapshot's subslot register of that slot
worker_seg: db 0
service:    db 0                ; nonzero with the tape service
p0:         db 0                ; the RAM pages for page 0, as in check_records
t0_rom:     db 0                ; 1 when T0 replaces the ROM
manual:     db 0                ; 1 with /M
svc_segs:   ds SEGS_MAX+1       ; T0's segment, the code segment, the tape's
free_count: db 0
hold_count: db 0
hold_next:  dw holds
holds:      ds 2*64
pass:       db 0
dos_sp:     dw 0
buffer:     dw 0
count:      dw 0
needed:     db 0
digits:     db 0
data_before: dw 0
jiffy0:     dw 0
dest:       ds 256
            align 256
freemap:    ds 256

; The worker, assembled for page 1 and for page 2.
worker1:
        module w1
WBASE   equ 4000h
WPAGE   equ 1
SRC_PORT equ 0FEh
SRC_ADDR equ 8000h
        disp WBASE
        include "worker.inc"
        ent
        endmodule
worker2:
        module w2
WBASE   equ 8000h
WPAGE   equ 2
SRC_PORT equ 0FDh
SRC_ADDR equ 4000h
        disp WBASE
        include "worker.inc"
        ent
        endmodule
WORKER_SIZE equ worker2-worker1

; Offsets of the worker's data, from f_holdn.
F_HOLDN equ 0
F_HOLD  equ w1.f_hold-w1.f_holdn
F_EXP   equ w1.f_exp-w1.f_holdn
F_SUB   equ w1.f_sub-w1.f_holdn
F_P3    equ w1.f_p3-w1.f_holdn
F_MAP   equ w1.f_map-w1.f_holdn
F_A8    equ w1.f_a8-w1.f_holdn
F_BC    equ w1.f_bc-w1.f_holdn
F_DE    equ w1.f_de-w1.f_holdn
F_HL    equ w1.f_hl-w1.f_holdn
F_AF2   equ w1.f_af2-w1.f_holdn
F_I     equ w1.f_i-w1.f_holdn
F_IM    equ w1.f_im-w1.f_holdn

        assert $ < HDR
