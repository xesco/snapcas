; SNAPCAS.COM: MSX-DOS 1/2/Nextor snapshot restorer (docs/internals/restorer-and-check.md).
; Code and data stay below 4000h so pages 1-2 remain free for buffers/worker;
; uses DOS's FCB calls and stack (switching to a page-0 stack when paging slot 3).

BDOS    equ 0005h       ; DOS function call
_TERM0  equ 00h         ; end the program
_CONOUT equ 02h         ; print the character in E
_STROUT equ 09h         ; print the string at DE, ended by "$"
_FOPEN  equ 0Fh         ; open the file of the FCB at DE
_SETDTA equ 1Ah         ; read at DE
_RDBLK  equ 27h         ; read HL records of the FCB at DE
_OPEN   equ 43h         ; MSX-DOS 2 only: open the file whose path is at DE
_READ   equ 48h         ; MSX-DOS 2 only: read HL bytes of handle B into DE
_SEEK   equ 4Ah         ; MSX-DOS 2 only: move handle B to DE:HL
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
        include "version.inc"

; The offsets of a record's data in the image come from these sizes by shifts,
; and the tables are walked by these sizes.
        assert H_SIZE = 1000h && DATA_SIZE = 4000h
        assert REC_SIZE = 4 && WRITE_SIZE = 2 && PLACE_SIZE = 3

        org 0100h

start:
        ; The banner, as DOS's own: the version, the year and the author.
        ; tests/support.py's restorer_run jumps from banner to banner_end.
banner:
        ld de,t_banner
        call print
banner_end:
        ; /M in the command line, its length at 0080h and its text after it,
        ; asks for the manual tape (docs/internals/service-and-resident.md, The manual tape). It is read
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
        call get_path
        ld de,t_usage
        jp z,stop_message
        ; MSX-DOS 2 and Nextor open the argument by its path, so that it can
        ; name a folder. MSX-DOS 1 has no folders, and its FCB holds a drive
        ; and a name only. MSX-DOS 1 has no function 6Fh and leaves B as it is.
        ld b,0
        ld c,_DOSVER
        call BDOS
        ld a,b
        cp 2
        jr c,.fcb
        ld a,1
        ld (by_path),a
        ld de,path
        ld a,1                  ; open mode: no writes
        ld c,_OPEN
        call BDOS
        or a
        ld de,t_notfound
        jp nz,stop_name
        ld a,b
        ld (handle),a
        ; The file's size goes where _FOPEN puts it, for check_size: a move
        ; to the file's end returns it. read_bytes moves from the start.
        ld a,2                  ; from the file's end
        ld de,0
        ld hl,0
        ld c,_SEEK
        call BDOS
        ld (fcb+FCB_FILESIZE),hl
        ld (fcb+FCB_FILESIZE+2),de
        jr .opened
.fcb:
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
.opened:
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

        include "plan.inc"
        include "segments.inc"
        include "records.inc"

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

        include "messages.inc"

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
