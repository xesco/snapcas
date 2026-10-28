; SNAPCAS.COM, the snapcas restorer (docs/DESIGN.md, Restorer).
;
; This first version opens <GAME>.IMG and checks that it starts with the
; image's mark, SNAPCAS1. It prints its usage when it gets no name, and an error
; naming the file when the file is missing or is not an image.
;
; It uses only the FCB functions that MSX-DOS 1 has and that MSX-DOS 2 and
; Nextor keep (MSX-DOS 2 Function Codes Specification).

BDOS    equ 0005h       ; DOS function call
_CONOUT equ 02h         ; print the character in E
_STROUT equ 09h         ; print the string at DE, ended by "$"
_FOPEN  equ 0Fh         ; open the file of the FCB at DE
_SETDTA equ 1Ah         ; read and write at DE
_RDBLK  equ 27h         ; read HL records of the FCB at DE
DOSFCB  equ 005Ch       ; DOS parses the first argument into this FCB

FCB_RECSIZE equ 14      ; FCB offsets: record size, 2 bytes
FCB_SIZE    equ 37      ; an FCB with its random record field

        org 0100h

start:
        ld a,(DOSFCB+1)
        cp " "
        jr z,usage
        ; Copy the drive and the name into our own FCB, which already holds
        ; the extension IMG. The FCB at 005Ch cannot be used as it is: its
        ; random record field overlaps the command line at 0080h.
        ld hl,DOSFCB
        ld de,fcb
        ld bc,9
        ldir
        ld de,fcb
        ld c,_FOPEN
        call BDOS
        or a
        jr nz,notfound
        ld de,mark
        ld c,_SETDTA
        call BDOS
        ld hl,1
        ld (fcb+FCB_RECSIZE),hl ; records of 1 byte, from random record 0
        ld de,fcb
        ld hl,8
        ld c,_RDBLK
        call BDOS
        ld a,l                  ; HL = the bytes read
        cp 8
        jr nz,notimage
        ld hl,mark
        ld de,t_mark
        ld b,8
.compare:
        ld a,(de)
        cp (hl)
        jr nz,notimage
        inc hl
        inc de
        djnz .compare
        ret                     ; the restore comes in step 4 (docs/PLAN.md)

usage:
        ld de,t_usage
        jr print

notfound:
        call name
        ld de,t_notfound
        jr print

notimage:
        call name
        ld de,t_notimage
print:
        ld c,_STROUT
        jp BDOS

; Prints the image's name: the FCB's name without its trailing spaces, then
; ".IMG".
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
        jr print

t_usage:    db "Usage: SNAPCAS <game>",13,10
            db "Restores <game>.IMG, a snapcas image.",13,10,"$"
t_ext:      db ".IMG$"
t_notfound: db " not found",13,10,"$"
t_notimage: db " is not a snapcas image",13,10,"$"
t_mark:     db "SNAPCAS1"

fcb:        db 0                ; drive, from the argument
            ds 8," "            ; name, from the argument
            db "IMG"
            ds FCB_SIZE-12,0
mark:       ds 8
