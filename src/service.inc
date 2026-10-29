; The tape service's fixed places (docs/DESIGN.md, Tape service), for
; service.asm and the restorer.

; Page 3, from FCE1h in SLTATR to the end of SLTWRK at FD88h.
E_ENTRY   equ 0FCE1h    ; JPs to the entry code: TAPION, TAPIN, TAPIOF
E_SLOT    equ 0FCEAh    ; restorer: DOS's mapper's slot ID
E_T0      equ 0FCEBh    ; restorer: T0's segment
E_CODE    equ 0FCECh    ; restorer: the code segment
E_FC      equ 0FCEDh    ; build.py: the game's mapper register FCh; restorer:
                        ; T0's segment when T0 replaces the ROM
E_INSIDE  equ 0FCEEh    ; 1 while the entry code runs
E_STACK   equ 0FD89h    ; the entry code's stack top, the end of SLTWRK

; The code segment, which runs in page 0. The tape follows its code.
C_POS     equ 0006h     ; build.py: the tape position at the snapshot, 3 bytes
C_S1END   equ 0009h     ; build.py: side 1's end, 3 bytes
C_TOTAL   equ 000Ch     ; build.py: side 2's end, 3 bytes
C_START   equ 000Fh     ; build.py: side 1's start, 3 bytes
C_SEGS    equ 001Ah     ; restorer: the code segment, then the next tape segments
SEGS_MAX  equ 64        ; so the tape service holds up to 1 MB
C_BORDER  equ 005Ah     ; build.py: where the game's VDP register 7 is, 2 bytes
C_FRAMES  equ 005Ch     ; build.py: the frames in 0.1 second
C_VDP7    equ 005Dh     ; build.py: the snapshot's VDP register 7
C_SIDE    equ 005Eh     ; build.py: 0 while the position is on side 1, 1 on side 2
C_SCREEN  equ 005Fh     ; build.py: where the game's VDP register 1 is, 2 bytes
C_VDP1    equ 0061h     ; build.py: the snapshot's VDP register 1
