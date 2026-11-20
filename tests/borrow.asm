; Test game for T0-mode tape service borrowing non-mapper page 2 without using
; the stack (tests/test_service.py). Waits ~60 s for capture, then reads and
; verifies a 256-byte block into page 2 and halts at passed or failed.

TAPION  equ 00E1h       ; MSX Red Book, chapter 4: the BIOS's tape entries
TAPIN   equ 00E4h
TAPIOF  equ 00E7h
JIFFY   equ 0FC9Eh      ; MSX Red Book, chapter 6: counts the VDP's interrupts

        org 0C000h
start:
        in a,(0A8h)
        and 0CFh
        or 10h                  ; page 2: slot 1, the RAM cartridge
        out (0A8h),a
        ld sp,0C000h            ; the stack in page 2
        ei
        ld hl,0
        ld (JIFFY),hl
.wait:
        ld hl,(JIFFY)
        ld de,3600              ; 60 seconds at 60 frames a second
        or a
        sbc hl,de
        jr c,.wait
        in a,(0A8h)
        and 0FCh
rom:
        or 00h                  ; page 0: slot 0, the main ROM
        out (0A8h),a
        call TAPION
        jr c,failed
        ld hl,8000h
        ld b,0                  ; 256 bytes
.read:
        push hl
        push bc
        call TAPIN
        pop bc
        pop hl
        jr c,failed
        ld (hl),a
        inc hl
        djnz .read
        call TAPIOF
        ld hl,8000h
.check:
        ld a,(hl)
        cp l
        jr nz,failed
        inc l
        jr nz,.check
passed:
        jr passed
failed:
        jr failed
code_end:
