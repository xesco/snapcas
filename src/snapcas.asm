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
FCB_FILESIZE equ 16     ; the file's size, 4 bytes, which _FOPEN sets
FCB_RANDOM  equ 33      ; random record, 4 bytes
FCB_SIZE    equ 37

; BIOS entries (MSX Red Book, chapter 4). DOS keeps the inter-slot call at the
; BIOS's address in its own page 0 (MSX2 Technical Handbook, chapter 5,
; section 2), and the restorer calls the other two through it.
CALSLT  equ 001Ch       ; calls IX in the slot whose ID is in IY's high byte
INITXT  equ 006Ch       ; sets up the 40-column text screen
INIT32  equ 006Fh       ; sets up the 32-column text screen

; System variables (MSX Red Book, chapter 6; map.grauw.nl).
RAMAD0  equ 0F341h      ; DOS's RAM slots of pages 0 to 3
RG1SAV  equ 0F3E0h      ; the last value written to VDP register 1
EXBRSA  equ 0FAF8h      ; the sub-ROM's slot ID, 0 on an MSX1
JIFFY   equ 0FC9Eh      ; counts the VDP's interrupts
SCRMOD  equ 0FCAFh      ; the screen mode: 0 with 40 columns, 1 with 32
EXPTBL  equ 0FCC1h      ; the main ROM's slot ID, then one byte per slot
SLTTBL  equ 0FCC5h      ; the subslot register of each slot
EXTBIO  equ 0FFCAh      ; MSX-DOS 2's extended BIOS

HDR     equ 2800h       ; the image's header and tables are read here. Their
                        ; fields are service.inc's H_ names (FORMATS.md, Image)
STACK   equ 4000h
HOLD_MAX equ 64         ; the most holding segments that the worker copies

        include "service.inc"

; The offsets of a record's data in the image come from these sizes by shifts,
; and the tables are walked by these sizes.
        assert H_SIZE = 1000h && DATA_SIZE = 4000h
        assert REC_SIZE = 4 && WRITE_SIZE = 2 && PLACE_SIZE = 3

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
        ld hl,H_SIZE
        ld (count),hl
        ld hl,HDR
        ld bc,0
        ld de,0
        call read_bytes         ; the header and the tables, from offset 0
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

        call plan
        call read_records
        call wait_motor
        di
        call port_writes
        jp switch
.notimage:
        ld de,t_notimage
        jp stop_name

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
        ; so the restorer stops with the message at DE.
        ld a,(dos_slot)
        bit 7,a
        ret z
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
; the page 0 bits of SLTTBL. Without a part in page 3, only SLTTBL. Keeps BC
; and HL.
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
        ld a,(HDR+H_WRITES)
        or a
        ret z
        ld b,a
        ld hl,(writes_at)
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
        ld hl,(HDR+H_TAIL)
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
        ld bc,2*HOLD_MAX
        ldir
        ; Per slot: expanded, and the snapshot's subslot register.
        ld b,4
        ld hl,EXPTBL
        ld iy,HDR+H_SUB
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
        ; Unless rule 1 of find_worker_page holds, the worker writes DOS's
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
        ld a,(HDR+H_A8)
        rlca
        rlca
        and 3
        ld (ix+F_P3),a
        ld b,4
        ld hl,HDR+H_MAP
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
        ld a,(m_ps)
        call page_bits
        ld e,a
        ld a,(HDR+H_A8)
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
        ld hl,HDR+H_REGS+2
        ld bc,18
        ldir
        ld a,(HDR+H_I)
        ld (ix+F_I),a
        ld a,(HDR+H_IM)
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
; tools/check.py finds this label and print in out/snapcas.sym, and takes the
; call of print as the restorer's first instruction of a stop.
stop_message:
        call print
        ld a,(dos_seg2)
        call select_p2
        ei
        ld c,_TERM0
        jp BDOS

print:
        ld c,_STROUT
        push ix
        push iy
        call BDOS
        pop iy
        pop ix
        ret

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
t_cut:      db ": the file is cut short: it lacks data of its records",13,10,"$"
t_onemapper: db ": DOS's pages are not in one memory mapper",13,10,"$"
t_dos1:     db ": MSX-DOS 1 needs a memory mapper with DOS in segments 3, 2, 1 and 0",13,10,"$"
t_roms:     db ": made for another machine: its ROMs differ from this one's",13,10,"$"
t_noworker: db ": no page 1 or 2 can hold the restorer's worker at the end",13,10,"$"
t_mapsize:  db ": a page's segment is beyond this machine's mapper",13,10,"$"
t_segments: db ": DOS has too few free mapper segments",13,10,"$"
t_holds:    db ": more than 64 pages need a segment that DOS uses",13,10,"$"
            assert HOLD_MAX = 64
t_needs:    db ": needs $"
t_free:     db " free mapper segments, and DOS has $"
t_crlf:     db 13,10,"$"
t_page0:    db ": a page 0 is in another subslot of DOS's mapper's slot",13,10,"$"
t_romkeep:  db ": rom keep needs the main ROM outside DOS's mapper's slot",13,10,"$"
t_t0page0:  db ": service t0 needs page 0 outside DOS's mapper",13,10,"$"
t_t0seg:    db ": T0 cannot take the segment of page 0's RAM,",13,10
            db "which shares mapper register FCh with it",13,10,"$"
t_t0sub:    db ": service t0 needs DOS's mapper's subslot in the borrowed page",13,10,"$"
t_read:     db ": cannot be read",13,10,"$"
; stop_slot writes the slot's number at SLOT_AT of these three.
t_notram:   db ": slot 0 page "
t_page_n:   db "0 is not RAM: the machine file does not describe this machine",13,10,"$"
t_plain:    db ": slot 0 is DOS's mapper, and the image has RAM without a mapper there",13,10,"$"
t_expanded: db ": slot 0 is not expanded as at the capture:",13,10
            db "the machine file does not describe this machine",13,10,"$"
; The image's mark (FORMATS.md, Image).
t_mark:     db "SNAPCAS",IMAGE_FORMAT

fcb:        db 0                ; drive, from the argument
            ds 8," "            ; name, from the argument
            db "SNP"
            ds FCB_SIZE-12,0

dos2:       db 0
dos_slot:   db 0                ; DOS's mapper's slot ID
m_ps:       db 0                ; its primary slot
m_ss:       db 0                ; and its subslot
m_sub:      db 0                ; the snapshot's subslot register of that slot
map_slot:   db 0
map_size:   db 0                ; DOS's mapper's segments, 0 for 256
dos_seg0:   db 0                ; DOS's segments in pages 0 to 3
dos_seg1:   db 0
dos_seg2:   db 0
dos_seg3:   db 0
saved4:     ds 4
tail_page:  db 0
worker_page: db 0
worker_mode: db 0               ; 0, 1 or 2: the rule of find_worker_page
worker_seg: db 0
service:    db 0                ; nonzero with the tape service
p0:         db 0                ; the RAM pages for page 0, as in check_records
t0_a8:      db 0                ; the slot register with DOS's mapper in page 0
t0_rom:     db 0                ; 1 when T0 replaces the ROM
t0_fixed:   db 0                ; 1 when T0 must be segment t0_fix
t0_fix:     db 0
t0_direct:  db 0                ; 1 when T0 is read straight into t0_fix
manual:     db 0                ; 1 with /M
svc_segs:   ds SEGS_MAX+1       ; T0's segment, the code segment, the tape's
svc_next:   dw svc_segs         ; where service_seg writes next
svc_i:      db 0                ; the number of the next service segment read
free_count: db 0
hold_count: db 0
hold_next:  dw holds
holds:      ds 2*HOLD_MAX       ; each: the holding segment, its own segment
rec_n:      db 0                ; the walk: the record's number
data_n:     db 0                ; and the records with data before it
writes_at:  dw 0                ; the port writes, after the records
places_at:  dw 0                ; the places, after the port writes
pass:       db 0
vram_written: db 0              ; 1 once a VRAM block is written
dos_sp:     dw 0
buffer:     dw 0
count:      dw 0
needed:     db 0
digits:     db 0
jiffy0:     dw 0
            align 256
dest:       ds 256              ; by record: the segment that it is read into
freemap:    ds 256              ; by segment of DOS's mapper: 0, FREE or OWN

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
F_I     equ w1.f_i-w1.f_holdn
F_IM    equ w1.f_im-w1.f_holdn

        assert $ < HDR
