; A test game for the contracts of the tape service's entries (INTERNALS.md,
; Tape service): what each routine returns and keeps, as the BIOS's routine
; does. tests/test_service.py writes this binary to a CAS file, followed by
; blocks of known bytes, after it has filled in the cases and the entries that
; the game calls.
;
; The game waits about 60 seconds, so that the capture takes its snapshot
; first. Then it calls each case's entry with the case's AF and interrupt
; state, with BC = 1122h, DE = 3344h and HL = 5566h, and keeps what the routine
; returns. It runs the cases with the entries from first on, T0's jump table at
; 00E1h, and then with those from second on, the entries in page 3 at FCE1h,
; unless second is 0. It reaches every entry through a computed address, so
; that the scan finds no call to patch (INTERNALS.md, Scan).

JIFFY   equ 0FC9Eh      ; MSX Red Book, chapter 6: counts the VDP's interrupts
CASES   equ 32          ; the most cases
RESULT  equ 9           ; a result's bytes: IFF, F, A, C, B, E, D, L, H

        org 0C000h
start:
        di
        ld sp,stack
        ei
        ld hl,0
        ld (JIFFY),hl
.wait:
        ld hl,(JIFFY)
        ld de,3600              ; 60 seconds at 60 frames a second
        or a
        sbc hl,de
        jr c,.wait
        ld iy,results
        ld hl,(first)
        call run
        ld hl,(second)
        ld a,h
        or l
        call nz,run
        di
        ld a,1
        ld (done),a
passed:
        jr passed

; Runs the cases with the entries from HL on, and adds a result for each at IY.
run:
        ld ix,cases
.case:
        ld a,(ix+0)
        cp 0FFh
        ret z
        push hl
        add a,l                 ; the entry's low byte, E1h to F3h
        ld l,a
        ld (.call+1),hl
        ld a,(ix+1)
        ld (.iff),a
        ld c,(ix+2)
        ld b,(ix+3)
        push bc
        pop af
        ld bc,1122h
        ld de,3344h
        ld hl,5566h
.iff:
        nop                     ; the case's DI or EI
.call:
        call 0                  ; the case's entry
        push hl
        push de
        push bc
        push af
        ; IFF2 is in the parity flag after LD A,I. An interrupt that the CPU
        ; accepts during that instruction clears the flag, so two reads count.
        ld a,i
        push af
        ld a,i
        push af
        di
        pop bc
        pop de
        ld a,c
        or e
        rrca
        rrca
        and 1
        ld (iy+0),a             ; 1 when interrupts are on
        ld b,4                  ; AF, BC, DE, HL, each low byte first
.word:
        pop de
        inc iy
        ld (iy+0),e
        inc iy
        ld (iy+0),d
        djnz .word
        inc iy
        ld bc,4
        add ix,bc
        pop hl
        jr .case

        db 0
; test: TAPION's entry of each run, and 0 for no second run.
first:  dw 00E1h                ; T0's jump table
second: dw 0FCE1h               ; the entries in page 3
done:   db 0                    ; 1 when every case has run
; test: each case as the entry's offset from TAPION's, the opcode of DI or EI,
; and AF, and FFh after the last.
cases:  ds 4*CASES+1,0FFh
results: ds 2*RESULT*CASES,0
        ds 64,0
stack:
code_end:
