; Test game for T0 sub-ROM calls when T0 and sub-ROM share a slot
; (tests/test_service.py). Waits ~40 s for capture, calls CHGMOD and EXTROM,
; then reads and verifies 8 tape bytes via T0 (result: 1=ok, 2=fail).

CHGMOD  equ 005Fh       ; MSX Red Book, chapter 4: sets the screen mode in A
EXTROM  equ 015Fh       ; MSX2 Technical Handbook, chapter 5: calls IX in the sub-ROM
REDCLK  equ 01F5h       ; the sub-ROM's read of the clock chip's register in C
JIFFY   equ 0FC9Eh      ; MSX Red Book, chapter 6: counts the VDP's interrupts
WAIT    equ 2400        ; 40 seconds at 60 frames a second, 48 at 50
BYTES   equ 8

        org 0C000h
start:
        di
        ld sp,stack
        ei
        ld hl,0
        ld (JIFFY),hl
.wait:
        ld hl,(JIFFY)
        ld de,WAIT
        or a
        sbc hl,de
        jr c,.wait
        ld a,1
        call CHGMOD
        ld c,0
        ld ix,REDCLK
        call EXTROM
        ld hl,(entries)         ; TAPION
        call entry
        jr c,failed
        ld b,BYTES
        ld c,1
.byte:
        push bc
        ld hl,(entries)
        inc hl
        inc hl
        inc hl                  ; TAPIN
        call entry
        pop bc
        jr c,failed
        cp c
        jr nz,failed
        inc c
        djnz .byte
        ld a,1
        ld (result),a
passed:
        jr passed
failed:
        ld a,2
        ld (result),a
.stay:
        jr .stay
entry:
        jp (hl)

; The address of TAPION's entry in the BIOS's jump table. TAPIN's follows it.
entries: dw 00E1h
; test: 0, then 1 or 2.
result: db 0
; The BIOS's CHGMOD takes more than 64 bytes of the stack on an MSX2, with its
; calls of the sub-ROM and the sub-ROM's calls of the main ROM.
        ds 256,0
stack:
code_end:
