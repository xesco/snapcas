; A test game for T0's calls of the sub-ROM (docs/internals/service-and-resident.md, T0 and the
; sub-ROM in one slot). tests/test_service.py writes this binary to a CAS file,
; with a block of 32 bytes after it on side 1.
;
; The game waits about 40 seconds, so that the capture takes its snapshot
; first, and what the game does next comes within the check's 60 seconds. Then
; it calls the sub-ROM twice through the BIOS in page 0, which is T0 after the
; restore: once inside CHGMOD, which an MSX2's BIOS sends to the sub-ROM, and
; once through EXTROM. Last it reads 8 bytes of the block through T0's jump
; table, and compares them with the bytes 1 to 8. It reaches the tape's entries
; through a computed address, so that the scan finds no call to patch
; (docs/internals/service-and-resident.md, Scan). The byte at result is 1 when the bytes are right, 2
; when a tape routine returns carry or a byte differs, and 0 until then.

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
