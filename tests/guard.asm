; A test game for the check's guard of the tape service's part of page 3
; (INTERNALS.md, Check, point 2). tests/test_service.py writes this binary to a
; CAS file, after it has filled in what the game does, with a block of 32 bytes
; after it on side 1, or as side 2.
;
; The game first reads the number of bytes at loads from the tape, unless that
; number is 0: that is its own load, which the capture sees. Then it waits
; about 40 seconds, so that the capture takes its snapshot first, and what the
; game does next comes within the check's 60 seconds. It reads the number of
; bytes at reads from the tape, through the tape service, unless that number
; is 0. Then it writes the first byte of the service's part of page 3, unless
; the byte at writes is 0. It ends at passed, or at failed when a tape routine
; returns carry.

TAPION  equ 00E1h       ; MSX Red Book, chapter 4: the BIOS's tape entries
TAPIN   equ 00E4h
TAPIOF  equ 00E7h
JIFFY   equ 0FC9Eh      ; MSX Red Book, chapter 6: counts the VDP's interrupts
PART    equ 0FCE1h      ; the first byte of the service's part of page 3
WAIT    equ 2400        ; 40 seconds at 60 frames a second, 48 at 50

        org 0C000h
start:
        di
        ld sp,stack
        ei
        ld a,(loads)
        or a
        call nz,read
        ld hl,0
        ld (JIFFY),hl
.wait:
        ld hl,(JIFFY)
        ld de,WAIT
        or a
        sbc hl,de
        jr c,.wait
        ld a,(reads)
        or a
        call nz,read
        ld a,(writes)
        or a
        jr z,passed
        ld a,(PART)
        ld (PART),a             ; the same value, so the entry stays whole
passed:
        jr passed
failed:
        jr failed

; Reads A bytes from the tape.
read:
        ld b,a
        push bc
        call TAPION
        pop bc
        jr c,failed
.byte:
        push bc
        call TAPIN
        pop bc
        jr c,failed
        djnz .byte
        jp TAPIOF

; test: the bytes that the game reads from the tape before its wait and after
; it, and 1 for a game that writes the part.
loads:  db 0
reads:  db 0
writes: db 0
        ds 64,0
stack:
code_end:
