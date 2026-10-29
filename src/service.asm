; SERVICE.BIN: the code that tools/build.py writes into images (docs/DESIGN.md,
; SERVICE.BIN). It is never run as it is: build.py and the restorer fill in
; the operands that are 0 here.
;
; The file starts with its version and a table of its parts. build.py refuses
; a SERVICE.BIN whose version is not the one it expects.

VERSION equ 2

        org 0

        db VERSION
        db 1                    ; number of parts
        dw tail, tail_end-tail  ; part 0: the tail

; The tail (DESIGN.md, Tail): the restore's last code, written below the game's
; stack pointer. It selects the game's memory in the worker's page and the slot
; register, writes the subslot register of DOS's mapper's slot when the worker
; could not, loads AF and SP, and jumps to the game.
tail:
        ld a,0                  ; restorer: the worker's page's mapper register
        out (0),a               ; restorer: FDh or FEh
        ld a,0                  ; restorer: the slot register
        out (0A8h),a
        ld a,0                  ; restorer: the subslot register of DOS's mapper
        nop                     ; restorer: LD (0FFFFh),A, when it is needed
        nop
        nop
        ld sp,0                 ; build.py: the tail's address plus 24
        pop af
        ld sp,0                 ; build.py: the snapshot's SP
        nop                     ; build.py: EI when IFF1 is set
        jp 0                    ; build.py: the snapshot's PC
        dw 0                    ; build.py: AF
tail_end:
