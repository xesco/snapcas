; Test game for check point 2's page 3 write guard (tests/test_service.py).
; Optionally reads `loads` bytes before capture, waits ~40 s, reads `reads`
; bytes via tape service, writes to `target` if `writes != 0`, and halts.

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
        ld hl,(target)
        ld a,(hl)
        ld (hl),a               ; the same value, so the part stays whole
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
target: dw PART
        ds 64,0
stack:
code_end:
