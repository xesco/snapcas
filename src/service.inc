; The tape service's fixed places (docs/DESIGN.md, Tape service), for
; service.asm and the restorer.

; The service's part of page 3, by default from FCE1h in SLTATR to the end of
; SLTWRK at FD88h. The Makefile also assembles it with P3_PAGE at FBh, so that
; build.py can move it to another page for a game that uses that area.
        ifndef P3_PAGE
P3_PAGE   equ 0FCh
        endif
E_ENTRY   equ P3_PAGE*256+0E1h  ; the entries: TAPION, TAPIN, TAPIOF, TAPOON,
                                ; TAPOUT, TAPOOF, STMOTR
E_SLOT    equ P3_PAGE*256+0F6h  ; restorer: DOS's mapper's slot ID
E_T0      equ P3_PAGE*256+0F7h  ; restorer: T0's segment
E_CODE    equ P3_PAGE*256+0F8h  ; restorer: the code segment
E_FC      equ P3_PAGE*256+0F9h  ; build.py: the game's mapper register FCh;
                                ; restorer: T0's segment when T0 replaces the ROM
E_INSIDE  equ P3_PAGE*256+0FAh  ; 1 while the entry code runs
E_STOP    equ P3_PAGE*256+0FBh  ; 1 while the manual tape is stopped; build.py:
                                ; 1 when the motor is off at the snapshot
E_STACK   equ P3_PAGE*256+189h  ; the entry code's stack top

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
C_SPEED   equ 0062h     ; the tape speed (DESIGN.md, Tape speed and sound), 0
C_TWO     equ 0063h     ; build.py: 1 when the tape has a side 2
C_SAVE    equ 0064h     ; TAPIN's position while it looks for a header, 3 bytes
C_S1REAL  equ 0067h     ; build.py: side 1's end before its padding to a
                        ; multiple of 8, with a side 2, otherwise C_S1END's
C_MODE    equ 006Ah     ; restorer: 1 for the manual tape of /M, 0 for the
                        ; automatic tape (DESIGN.md, The manual tape)

; T0 in the mode without a part in page 3 (DESIGN.md, Without a part in page 3):
; its data, then its routines, from 19DDh to 1B44h.
T_POS     equ 19DDh     ; build.py: the tape position at the snapshot, 3 bytes
T_S1END   equ 19E0h     ; build.py: side 1's end, 3 bytes
T_TOTAL   equ 19E3h     ; build.py: side 2's end, 3 bytes
T_START   equ 19E6h     ; side 1's start, 0, 3 bytes
T_HEADER  equ 19E9h     ; the CAS header, 8 bytes
T_SEGS    equ 19F1h     ; restorer: the tape's segments
T_SEGS_MAX equ 16       ; so the tape holds up to 256 KB
T_PAGE    equ 1A01h     ; the game's slot register while TAPIN borrows a page,
                        ; build.py: the slot register's mask for that page,
                        ; the restorer: DOS's mapper's slot in its bits,
                        ; build.py: its mapper register's port, its first
                        ; address's high byte, the game's segment there
T_BORDER  equ 1A07h     ; build.py: the flash's data, the tape speed and the
                        ; side 2 byte, as from C_BORDER to C_TWO
