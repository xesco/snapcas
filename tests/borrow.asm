; A test game for the tape service without a part in page 3 (DESIGN.md,
; Without a part in page 3), on the Sanyo PHC-28S with its RAM cartridge in
; slot 1: page 2 holds that cartridge's RAM, which is not in a mapper, and
; the stack, so TAPIN must borrow page 2 through the slot register, without
; the stack. test_step6.py writes
; this binary to a CAS file, followed by a block of the bytes 0 to 255.
;
; The game waits about 60 seconds, so that the capture takes its snapshot
; first, then reads the block into page 2 and checks it. It ends at passed
; or at failed, which the test counts. Before it reads, it selects the main
; ROM in page 0, as a loader can, and the test's game file patches the slot
; at rom to DOS's mapper, where T0 is.

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
