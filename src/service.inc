; The places that service.asm, the restorer and build.py share: the tape
; service's fixed places (docs/internals/service-and-resident.md, Tape service), the tail's fields and
; the image's layout (docs/FORMATS.md, Image). This file is their one source.
; service.asm exports them, and build.py reads them by name from SERVICE.BIN
; (docs/FORMATS.md, SERVICE.BIN), as it reads the service's other places, which
; are labels of service.asm and tape.inc.

; The service's part of page 3, by default from FCE1h in SLTATR. The Makefile
; also assembles it with P3_PAGE at FBh, so that build.py can move it to
; another page for a game that uses that area.
        ifndef P3_PAGE
P3_PAGE   equ 0FCh
        endif
E_PAGE    equ P3_PAGE           ; the part's page, under a name that -D leaves a symbol
E_ENTRY   equ E_PAGE*256+0E1h   ; the entries, with the low bytes of the BIOS's
                                ; tape jump table from 00E1h: TAPION, TAPIN,
                                ; TAPIOF, TAPOON, TAPOUT, TAPOOF, STMOTR
E_SLOT    equ E_ENTRY+7*3       ; restorer: DOS's mapper's slot ID
E_T0      equ E_SLOT+1          ; restorer: T0's segment
E_CODE    equ E_SLOT+2          ; restorer: the code segment
E_FC      equ E_SLOT+3          ; build.py: the game's mapper register FCh;
                                ; restorer: T0's segment when T0 replaces the ROM
E_STOP    equ E_SLOT+4          ; 1 while the manual tape is stopped; build.py:
                                ; 1 when the motor is off at the snapshot
; The code block of the part, which follows the entries unless the Makefile's
; third assembly gives it another address, for the list of the addresses that
; move with it.
        ifdef CODE_MOVED
P3_CODE   equ CODE_MOVED
        else
P3_CODE   equ E_STOP+1
        endif
; The restorer writes E_SLOT, E_T0, E_CODE and E_FC one after the other.
        assert E_T0 = E_SLOT+1 && E_CODE = E_T0+1 && E_FC = E_CODE+1

; The area of page 3 that build.py wants at zero before it leaves the part at
; FCE1h: SLTATR and SLTWRK, which no cassette game's BIOS uses.
P3_FREE     equ 0FCC9h          ; its first byte
P3_FREE_END equ 0FD88h          ; its last byte

; The stacks of the calls of a machine's resident program (docs/internals/service-and-resident.md, The
; resident program's call), in bytes. The program switches to a stack of its
; own at entry (SX2RES 2.8+ uses 6 bytes below SP before switching), staying
; within 8 bytes below SP at its entry, and the call's return address takes 2
; more, RES_STACK. res3 keeps the slot register and the interrupts' state on its
; stack too, 2 bytes, RES3_STACK (12 + 12 for res3e = 24 bytes). resb reaches
; the entry through the BIOS's CALSLT, which takes 14 bytes on the SX-2 down to
; the entry (RDSLT takes 12), plus 2 for the interrupts' state, 8 for the entry
; and 4 to spare for another BIOS's CALSLT: RESB_STACK (28 + 12 for resbe = 40
; bytes, which fits in SLTWRK after resb without touching SLTATR). resc and
; t_res, whose stacks cost the game nothing, have RES_SPARE bytes to spare too.
RES_STACK  equ 2+8
RES3_STACK equ 2+RES_STACK
RESB_STACK equ 2+14+8+4
RES_SPARE  equ 8

; T0: the BIOS's tape code, which the service replaces (MSX Red Book, chapter
; 4). OUTDO's code follows it.
T0_CODE   equ 19DDh             ; its first byte, TAPOOF
T0_END    equ 1B45h             ; the first byte after it

; The service's data, which tape.inc declares, starts each copy of the
; service: at 0000h of the code segment, and at T0_CODE in the mode without a
; part in page 3 (docs/internals/service-and-resident.md, Without a part in page 3). The restorer writes
; these fields, and service.asm checks their places against tape.inc's.
SEGS_AT   equ 14h               ; the table of segments in the data
C_SEGS    equ SEGS_AT           ; restorer: the code segment, then the next tape segments
SEGS_MAX  equ 64                ; so the tape service holds up to 1 MB
C_MODE    equ C_SEGS+SEGS_MAX   ; restorer: 1 for the manual tape of /M, 0 for the
                                ; automatic tape (docs/internals/service-and-resident.md, The manual tape)
T_SEGS    equ T0_CODE+SEGS_AT   ; restorer: the tape's segments
T_SEGS_MAX equ 16               ; so the tape holds up to 256 KB
T_PAGE    equ T_SEGS+T_SEGS_MAX ; the borrowed page's data, 6 bytes. Restorer:
                                ; DOS's mapper's slot in the page's bits of the
                                ; slot register, at T_PAGE+2

; The tail (FORMATS.md, Tail): its length, and the offsets in it of the bytes
; that the restorer and build.py fill in. service.asm checks them against its
; code.
TAIL_SIZE equ 26
TAIL_MAP  equ 1                 ; restorer: the snapshot's value of the worker's
                                ; page's mapper register
TAIL_PORT equ 3                 ; restorer: that register's port, FDh or FEh
TAIL_A8   equ 5                 ; restorer: the slot register
TAIL_SUB  equ 9                 ; restorer: the subslot register of DOS's mapper's
                                ; slot, when the tail writes it
TAIL_LD   equ 10                ; restorer: LD (0FFFFh),A, 3 bytes, when the tail
                                ; writes that register
TAIL_STACK equ 14               ; build.py: the address of the tail's AF
TAIL_SP   equ 18                ; build.py: the snapshot's SP
TAIL_EI   equ 20                ; build.py: EI when IFF1 is set
TAIL_JP   equ 21                ; the tail's last instruction, the jump to the game
TAIL_PC   equ 22                ; build.py: the snapshot's PC
TAIL_AF   equ 24                ; build.py: the snapshot's AF

; The image (FORMATS.md, Image). Its mark is "SNAPCAS" and the format's number,
; one character.
IMAGE_FORMAT equ "6"
H_SIZE    equ 4096              ; the header and the tables, in bytes
DATA_SIZE equ 16384             ; a record's data, in bytes
; The header's fields, as offsets in the image.
H_ROM     equ 8                 ; the CRC-16 of the main ROM
H_SUBROM  equ 10                ; the CRC-16 of the sub-ROM
H_RECS    equ 12                ; the number of records
H_WRITES  equ 13                ; the number of port writes
H_FLAGS   equ 14                ; FLAG_ROM_KEEP and FLAG_T0
H_P3      equ 15                ; the page of the service's part of page 3
H_REGS    equ 16                ; AF, BC, DE, HL, AF', BC', DE', HL', IX, IY, SP, PC
H_I       equ 40
H_IM      equ 41
H_IFF     equ 42
H_A8      equ 43                ; the slot register
H_SUB     equ 44                ; the subslot registers of slots 0 to 3
H_MAP     equ 48                ; the mapper registers FCh to FFh
H_TAIL    equ 52                ; the tail's address
H_VDP1    equ 54                ; the snapshot's VDP register 1
H_BORROW  equ 55                ; the page that TAPIN borrows without a part in page 3
H_NOEXP   equ 56                ; bit n: the capture's slot n was not expanded
H_TAILREC equ 57                ; the number of the record that holds the tail
H_P3REC   equ 58                ; with the tape service, the number of the record
                                ; that holds the game's page 3
H_PLACES  equ 59                ; the number of places
H_TABLE   equ 64                ; the records, then the port writes, then the places
REC_SIZE  equ 4                 ; a record: its type, then 3 bytes by type
WRITE_SIZE equ 2                ; a port write: the port, the value
PLACE_SIZE equ 3                ; a place: its record's number, its offset in the
                                ; record's data, 2 bytes
; H_FLAGS.
FLAG_ROM_KEEP equ 1             ; bit 0: the game file's rom keep, so T0 does not
                                ; replace the ROM
FLAG_T0   equ 2                 ; bit 1: the tape service without a part in page 3
FLAG_P0   equ 4                 ; bit 2: sub0 sets page 0's bits of page 3's
                                ; subslot register around each call of the
                                ; code segment (docs/internals/service-and-resident.md, Page 0 in another
                                ; subslot of DOS's mapper's slot)
; A record's type.
REC_MAPPER  equ 1               ; a RAM page in a mapper: slot ID, page, segment
REC_RAM     equ 2               ; a RAM page outside a mapper: slot ID, page, 0
REC_SERVICE equ 3               ; a service segment: T0 first, then the tape in order
REC_VRAM    equ 4               ; a VRAM block: its number, 0 to 7
REC_ZEROS   equ 5               ; a VRAM block of zeros, which holds no data
