; SERVICE.BIN: the code that tools/build.py writes into images (docs/FORMATS.md,
; SERVICE.BIN). It is never run as it is: build.py and the restorer fill in
; the operands and the data that are 0 here.
;
; The file starts with its version and a table of its parts. build.py refuses
; a SERVICE.BIN whose version is not the one it expects.

        include "service.inc"

VERSION equ 20

        org 0

        db VERSION
        db 9                    ; number of parts
        dw tail, tail_end-tail          ; part 0: the tail
        dw t0_start, t0_end-t0_start    ; part 1: T0's stubs, for T0_CODE
        dw p3_start, p3_end-p3_start    ; part 2: page 3, for E_ENTRY
        dw code_start, code_end-code_start  ; part 3: the code segment
        dw t0m_start, t0m_end-t0m_start ; part 4: T0 without a part in page 3
        dw call_start, call_end-call_start ; part 5: the call of a resident program, and sub0
        dw file_end, 0                  ; part 6: the symbols that this file exports
        dw file_end, 0                  ; part 7: the bytes that move with page 3
        dw file_end, 0                  ; part 8: the addresses that move with the
                                        ; code block. tools/relocs.py appends
                                        ; parts 6 to 8

; Fills with zeros up to an address, which the code before it must not pass.
        macro fill_to address
        assert $ <= address
        ds address-$,0
        endm

; The tail (FORMATS.md, Tail): the restore's last code, written below the game's
; stack pointer. It selects the game's memory in the worker's page and the slot
; register, writes the subslot register of DOS's mapper's slot when the worker
; could not, loads AF and SP, and jumps to the game.
tail:
.map:   ld a,0                  ; restorer: the worker's page's mapper register
.port:  out (0),a               ; restorer: FDh or FEh
.a8:    ld a,0                  ; restorer: the slot register
        out (0A8h),a
.sub:   ld a,0                  ; restorer: the subslot register of DOS's mapper
.ld:    nop                     ; restorer: LD (0FFFFh),A, when it is needed
        nop
        nop
.stack: ld sp,0                 ; build.py: the address of .af
        pop af
.sp:    ld sp,0                 ; build.py: the snapshot's SP
.ei:    nop                     ; build.py: EI when IFF1 is set
.pc:    jp 0                    ; build.py: the snapshot's PC
.af:    dw 0                    ; build.py: AF
tail_end:
; The restorer's fill_tail and build.py's place_tail write these bytes by
; service.inc's offsets.
        assert tail_end-tail = TAIL_SIZE
        assert tail.map+1-tail = TAIL_MAP && tail.port+1-tail = TAIL_PORT
        assert tail.a8+1-tail = TAIL_A8 && tail.sub+1-tail = TAIL_SUB
        assert tail.ld-tail = TAIL_LD && tail.stack-tail = TAIL_LD+3
        assert tail.stack+1-tail = TAIL_STACK && tail.sp+1-tail = TAIL_SP
        assert tail.ei-tail = TAIL_EI && tail.pc-tail = TAIL_JP
        assert tail.pc+1-tail = TAIL_PC && tail.af-tail = TAIL_AF

; ---- T0's stubs, over the BIOS's tape code from 19DDh to 1B44h ----
;
; They keep the BIOS's entry addresses, which the jump table at 00E1h to 00F0h
; jumps to (MSX Red Book, chapter 4), and each returns as the BIOS's routine
; does. TAPION and TAPIN run in the code segment, through tramp in page 3,
; because page 0 changes under it. TAPIOF and STMOTR run in page 3 too, where
; the entries share them. After TAPIN's stub comes T0's own call of a routine
; in its slot (INTERNALS.md, T0 and the sub-ROM in one slot). The rest of the
; range is free.

t0_start:
        disp T0_CODE

t_tapoof:                       ; 19DDh, TAPOOF: every register kept
        ei
        ret
t_stmotr:                       ; STMOTR, through the jump at 00F3h
        jp stmotr
        fill_to 19E9h
t_tapiof:                       ; 19E9h, TAPIOF
        jp tapiof
        fill_to 19F1h
t_tapoon:                       ; 19F1h, TAPOON: the tape cannot be written, so
        di                      ; it returns as the BIOS's does for CTRL+STOP,
        scf                     ; with carry and interrupts off
        ret
        fill_to 1A19h
t_tapout:                       ; 1A19h, TAPOUT: the same. The BIOS's leaves
        scf                     ; the interrupts as they are
        ret
; t_res's stack, below t_tapion, in bytes of the BIOS's TAPOUT that nothing
; runs: AF and HL, then the program's call.
t_stack_end:
        fill_to 1A63h
T_STACK:
        assert T_STACK-t_stack_end >= 4+RES_STACK+RES_SPARE
t_tapion:                       ; 1A63h, TAPION
        di
        ld hl,tapion
        jp tramp
        fill_to 1ABCh
t_tapin:                        ; 1ABCh, TAPIN
        di
        ld hl,tapin
        jp tramp

; T0's call of a routine in page 0 of its own slot, which is the sub-ROM on a
; machine that has it in the slot of DOS's mapper. The BIOS's CALSLT writes
; the routine's subslot to the slot's subslot register while its own code
; runs in page 0, and for that slot the write would take T0 from under it. So
; build.py sends two places of CALSLT here.
;
; t_s takes the place of CALSLT's call of the BIOS's routine that writes the
; subslot register, with the slot ID in A, the routine's address in HL and
; interrupts off. For a routine in page 0 of the slot that pages 0 and 3 are
; in, it leaves the register as it is, keeps the subslot at t_pend, and
; returns what the BIOS's routine returns: the slot in A, the slot register in
; B, the slot in page 3's bits in C, the subslot in D, the other pages' bits
; in H and the register in L. Any other call goes to the BIOS's routine.
t_s:
        push af
        ld a,h
        and 0C0h
        jr nz,.bios             ; a routine in another page
        in a,(0A8h)
        ld b,a
        rlca
        rlca
        xor b
        and 3
        jr nz,.bios             ; page 3 is in another slot than T0
        pop af
        push af
        xor b
        and 3
        jr nz,.bios             ; the routine is in another slot than T0
        pop af
        rrca
        rrca
        and 3
        ld d,a
        ld (t_pend),a
        ld h,0FCh
        ld a,(0FFFFh)
        cpl
        ld l,a
        ld a,b
        and 0C0h
        ld c,a
        ld a,b
        and 3
        ret
.bios:
        pop af
.jump:  jp 0                    ; build.py: the BIOS's routine

; t_c takes the place of CALSLT's jump to CLPRIM at F38Ch, with the slot
; register's value for the call in A and the one before it on the stack.
; Without a subslot at t_pend it goes to CLPRIM. With one, the slot register
; stays, and sub in page 3 makes the call with that subslot in page 0. It gets
; the subslot register's value for the call in A, and the value now on the
; stack, in the high byte.
t_c:
        push hl
        ld hl,t_pend
        bit 7,(hl)
        jr z,.sub
        pop hl
        jp 0F38Ch
.sub:
        ld a,(hl)
        ld (hl),0FFh
        ld l,a
        ld a,(0FFFFh)
        cpl
        ld h,a
        and 0FCh
        or l
        ld l,a
        ex (sp),hl
        jp sub
t_pend: db 0FFh                 ; the subslot that waits for t_c, or FFh

; t_res takes the place of the BIOS's jump at 0038h on a machine with a
; resident program (FILES.md, Machine file, resident): at each interrupt it
; calls the program's entry, in a page of another slot, and goes on to the
; BIOS's interrupt routine. It needs no BIOS routine, and the game cannot write
; over it as over a hook. It runs on a stack of its own in T0, so that the
; game's stack keeps only the interrupt's return address, and the call runs
; when that stack is in the entry's page too, which the call takes from the
; game. The interrupts stay off. It leaves the call out when the entry does
; not start with the program's two bytes: the program is not there, or its
; slot shows another subslot. build.py fills in the fields. The entry keeps
; every register, H among them.
t_res:
        di
        ld (.back+1),sp
        ld sp,T_STACK
        push af
        push hl
        in a,(0A8h)
        ld h,a                  ; the game's slot register
.mask:  and 0                   ; build.py: without the page's bits
.slot:  or 0                    ; build.py: the program's primary slot there
        out (0A8h),a
.at1:   ld a,(0)                ; build.py: the entry
.is1:   cp 0                    ; build.py: its first byte
        jr nz,.out
.at2:   ld a,(0)                ; build.py: the entry plus 1
.is2:   cp 0                    ; build.py: its second byte
        jr nz,.out
.call:  call 0                  ; build.py: the entry
.out:
        ld a,h
        out (0A8h),a
        pop hl
        pop af
.back:  ld sp,0                 ; the game's stack pointer
.jump:  jp 0                    ; build.py: the BIOS's interrupt routine
        fill_to T0_END
        ent
t0_end:

; ---- Page 3, from E_ENTRY to E_STACK, by default FCE1h to FD7Eh ----
;
; Two blocks: the entries and their data, from E_ENTRY to E_STOP, and the code
; block, from P3_CODE to E_STACK. By default the code block follows the
; entries. A game file's service at can put it at another address in page 3,
; and build.py moves its addresses with the list that tools/relocs.py makes
; (INTERNALS.md, Build).

p3_start:
        disp E_ENTRY
; The entries, one for each entry of the BIOS's tape jump table from 00E1h to
; 00F3h, with the same low bytes (MSX Red Book, chapter 4). Each is 3 bytes,
; so a game that changes the low byte of a call reaches the matching entry.
        jp e_tapion             ; xxE1h, TAPION
        jp e_tapin              ; xxE4h, TAPIN
        jp tapiof               ; xxE7h, TAPIOF
        assert $ = E_ENTRY+3*3
        di                      ; xxEAh, TAPOON, as t_tapoon
        scf
        ret
        scf                     ; xxEDh, TAPOUT, as t_tapout
        ret
        nop
        assert $ = E_ENTRY+5*3
        ei                      ; xxF0h, TAPOOF, as t_tapoof
        ret
        nop
        jp stmotr               ; xxF3h, STMOTR
        assert $ = E_SLOT
        db 0,0,0,0              ; E_SLOT, E_T0, E_CODE, E_FC
        assert $ = E_STOP
        db 0
        ent
p3_code:
        disp P3_CODE

; STMOTR and TAPIOF stop the manual tape, which waits for the player's key at
; the next read (INTERNALS.md, The manual tape). STMOTR with A = 1 starts the
; motor and leaves the tape as it is. The automatic tape ignores E_STOP. They
; run here for the entries and for T0's stubs, with the caller's registers,
; stack and interrupts, as the BIOS's do: STMOTR changes only AF, and TAPIOF
; keeps every register and enables interrupts.
stmotr:
        cp 1
        ret z
        ld a,1
        ld (E_STOP),a
        ret
tapiof:
        push af
        ld a,1
        ld (E_STOP),a
        pop af
        ei
        ret

; From the entries of TAPION and TAPIN, which return with interrupts off, as
; the BIOS's TAPION does: selects DOS's mapper in page 0, calls the code
; segment's routine at HL on the stack below E_STACK, and selects the game's
; page 0 again, with mapper register FCh at E_FC, and the game's stack. It
; returns what tramp returns, so that an entry and T0's stub of the same
; routine leave the same registers: a game can count on the B = 0 that the
; BIOS's TAPIN leaves (tape.inc, next_byte).
e_tapin:
        ld hl,tapin
        jr e_run
e_tapion:
        ld hl,tapion
e_run:
        di
        ld (e_sp),sp
        ld sp,E_STACK
        in a,(0A8h)
        ld (e_a8),a             ; the game's slot register
        and 0FCh
        ld b,a
        ld a,(E_SLOT)
        and 3
        or b
        out (0A8h),a
.call:  call tramp              ; A is also in D. build.py: sub0 for FLAG_P0
        ld a,(E_FC)
        out (0FCh),a
        ld a,(e_a8)
        out (0A8h),a
        ld a,d
        ld sp,(e_sp)
        ret

; From T0's stubs and from e_run, with HL a routine of the code segment and
; interrupts off: selects the code segment in page 0, calls the routine, and
; selects T0 again. It returns the routine's A, flags, BC and HL, with A also
; in D, where the BIOS's TAPIN leaves the byte too.
tramp:
        ld a,(E_CODE)
        out (0FCh),a
        call .routine
        ld d,a
        ld a,(E_T0)
        out (0FCh),a
        ld a,d
        ret
.routine:
        jp (hl)
; With C = FCh, D the byte's tape segment and B the code segment: selects the
; tape segment in page 0, reads the byte at HL into E, and selects the code
; segment again.
reader:
        out (c),d
        ld e,(hl)
        out (c),b
        ret
; From T0's t_c, with interrupts off, the subslot register's value for the call
; in A, its value now in the high byte on the stack, and under it what CLPRIM
; finds: the slot register's value before the call. Selects the routine's
; subslot in page 0, where T0 was, calls the routine at IX through the BIOS's
; JP (IX) at F398h, as CLPRIM does, and selects T0 again. It returns to T0's
; CALSLT what the routine returns. The slot register did not change.
sub:
        ld (0FFFFh),a
        ex af,af'
        call 0F398h
        ex af,af'
        pop af
        ld (0FFFFh),a
        pop af
        ex af,af'
        ret

; e_run's scratch bytes and stack. Its deepest path takes 20 bytes of the
; stack, or 22 with sub0 between e_run and tramp: 4 for the calls of tramp
; and of the routine, 2 for the call of sub0, and 16 in the code
; segment, where a read under the header's compare of TAPION or TAPIN, which
; keeps BC and HL, 4, calls next_byte, 2, which keeps DE, 2, and calls wrap,
; 2, whose flash keeps two values, 4, and calls vdp, 2. The manual tape's
; wait takes as much.
e_sp:   dw 0                    ; the game's stack pointer
e_a8:   db 0                    ; the game's slot register
        ds 22,0
E_STACK:
        ent
p3_end:
; At FCE1h, the part is inside the area that build.py wants at zero.
        assert P3_CODE-E_ENTRY != E_STOP+1-E_ENTRY || E_STACK-E_ENTRY = p3_end-p3_start
        assert p3_code-p3_start = E_STOP+1-E_ENTRY && p3_end-p3_code = E_STACK-P3_CODE
        assert E_PAGE != 0FCh || P3_CODE != E_STOP+1 || (E_ENTRY >= P3_FREE && E_STACK-1 <= P3_FREE_END)

; ---- The code segment, which runs in page 0 with interrupts off ----
;
; Its data, then TAPION and TAPIN. The tape follows it: side 1, padded to a
; multiple of 8 bytes, then side 2. The position is the offset of the next
; byte, counted from the start of this segment.

code_start:
        disp 0
T0MODE  equ 0
        include "tape.inc"

; resc is the call of a machine's resident program (INTERNALS.md, The resident
; program's call) for a game that takes the interrupt for a routine of its own.
; The game's vector goes to a wrapper in page 3, which build.py writes: it
; runs resc through e_run and jumps to the game's routine. resc runs on a
; stack of its own in the code segment, resc_stack, because the program needs
; more than e_run's, and the game's can be in the entry's page. As t_res, it
; selects the program's primary slot in the entry's page for the call, and
; leaves the call out when the entry does not start with the program's two
; bytes. build.py fills in the fields. The entry keeps every register, H among
; them. e_run has turned the interrupts off.
resc:
        ld (resc_sp),sp
        ld sp,resc_stack
        in a,(0A8h)
        ld h,a                  ; the slot register, with DOS's mapper in page 0
.mask:  and 0                   ; build.py: without the page's bits
.slot:  or 0                    ; build.py: the program's primary slot there
        out (0A8h),a
.at1:   ld a,(0)                ; build.py: the entry
.is1:   cp 0                    ; build.py: its first byte
        jr nz,.back
.at2:   ld a,(0)                ; build.py: the entry plus 1
.is2:   cp 0                    ; build.py: its second byte
        jr nz,.back
.call:  call 0                  ; build.py: the entry
.back:
        ld a,h
        out (0A8h),a
        ld sp,(resc_sp)
        ret
resc_sp: dw 0                   ; e_run's stack pointer during the call
        ds RES_STACK+RES_SPARE,0
resc_stack:
        align 8,0               ; the tape starts at a multiple of 8
        ent
code_end:
; The restorer writes these by service.inc's places.
        assert D_SEGS = C_SEGS && D_MODE = C_MODE

; ---- T0 without a part in page 3, from 19DDh to 1B44h ----
;
; T0's data and routines, for a game whose page 3 has no room for the service
; (INTERNALS.md, Without a part in page 3). The game reaches T0 through DOS's
; mapper in page 0, where mapper register FCh holds T0, and build.py points the
; jump table's entries from 00E1h to 00F3h at the routines here.

t0m_start:
        module t0m
        disp T0_CODE
T0MODE  equ 1
        include "tape.inc"
; T0 has no room for the manual tape, so the tape is automatic in this mode
; (INTERNALS.md, The manual tape), and TAPIOF and STMOTR have nothing to stop.
; Each returns as the BIOS's routine does, as T0's stubs above.
tapiof:                         ; TAPIOF and TAPOOF
tapoof:
        ei
stmotr:                         ; STMOTR
        ret
tapoon:                         ; TAPOON: the tape cannot be written
        di
tapout:                         ; TAPOUT
        scf
        ret
        fill_to T0_END          ; within the BIOS's tape code
        ent
        endmodule
t0m_end:
; The restorer writes these by service.inc's places.
        assert t0m.D_SEGS = T_SEGS && t0m.D_PAGE = T_PAGE && t0m.D_PAGE_SLOT = T_PAGE+2

; ---- The call of a resident program, for an image without the tape service,
; ---- and sub0, for the tape service's entry code ----
;
; res3 is t_res's call (above), for an image that has no T0 to hold it: build.py
; writes it into zeros of the game's page 3, at FD29h, with the fields that it
; fills in, and a call of it into H.KEYI or the game's interrupt vector. Its
; stack is RES3_STACK other zeros of page 3, which build.py finds, and res3e,
; its end, follows the stack there. So the game's stack keeps only AF and the
; return address, and the call runs when the game's stack is in the entry's
; page too. It keeps every register. It turns the interrupts off for the call
; and on again at its end when they were on, for a call from a game's main
; loop: LD A,I gives IFF2 in P/V, and a second LD A,I when the first gives 0,
; because a Z80 that takes an interrupt at the end of LD A,I gives 0 there.
; The flags stay with the slot register on res3's stack. An interrupt can come
; before the DI, and its call of the routine runs to its end before this one
; goes on, so the stack is never in use twice.
call_start:
        disp 0
res3:
        push af
        ld a,i                  ; P/V: IFF2
.pe:    jp pe,0                 ; build.py: .on
        ld a,i
.on:    di
.save:  ld (0),sp               ; build.py: res3e.back+1
.stack: ld sp,0                 ; build.py: the stack's end, res3e
        in a,(0A8h)             ; the game's slot register; IN keeps the flags
        push af
.mask:  and 0                   ; build.py: without the page's bits
.slot:  or 0                    ; build.py: the program's primary slot there
        out (0A8h),a
.at1:   ld a,(0)                ; build.py: the entry
.is1:   cp 0                    ; build.py: its first byte
.fail:  jp nz,0                 ; build.py: res3e
.at2:   ld a,(0)                ; build.py: the entry plus 1
.is2:   cp 0                    ; build.py: its second byte
.call:  call z,0                ; build.py: the entry
.tail:  jp 0                    ; build.py: res3e
        fill_to res3+45
; From H.KEYI, where the BIOS's interrupt routine runs with the main ROM in
; page 0: the same call through the BIOS's RDSLT and CALSLT, which select the
; program's subslot in the entry's page and give the slot's subslot register
; back, whatever another ROM of that slot left there. build.py writes only this
; routine for the H.KEYI call, and only res3 for a wrapper. Its stack is
; RESB_STACK zeros of page 3, for CALSLT's bytes too, and resbe follows it. It
; keeps the main registers, on the game's stack, and the interrupts as res3
; does, which RDSLT turns off. RDSLT keeps HL. CALSLT changes IX, IY and the
; alternate registers, which the BIOS's interrupt routine keeps around H.KEYI,
; and a game's hook after the call does not take them from the interrupt
; routine.
resb:
        push af
        push hl
        push bc
        push de
        ld a,i
.pe:    jp pe,0                 ; build.py: .on
        ld a,i
.on:    di
.save:  ld (0),sp               ; build.py: resbe.back+1
.stack: ld sp,0                 ; build.py: the stack's end, resbe
        push af                 ; IFF2 in P/V
.id1:   ld a,0                  ; build.py: the program's slot ID
.at1:   ld hl,0                 ; build.py: the entry
        call 000Ch              ; RDSLT
.is1:   cp 0                    ; build.py: its first byte
        jr nz,.out
.id2:   ld a,0                  ; build.py: the program's slot ID
        inc hl
        call 000Ch
.is2:   cp 0                    ; build.py: its second byte
.iy:    ld iy,0                 ; build.py: the slot ID in IYH
.call:  ld ix,0                 ; build.py: the entry
        call z,001Ch            ; CALSLT
.out:   pop af
.tail:  jp 0                    ; build.py: resbe
        assert $ = resb+55
; res3g and resbg are res3 and resb on the game's stack, for an image whose page
; 3 has no zeros for the stack. Each has its routine's length, so that the
; wrappers after it keep their places. They use no address of their own. They
; leave the call out when the game's stack is in the entry's page, which the
; call takes from the game, and keep the interrupts as they are until RDSLT.
res3g:
        push af
        push hl
        ld hl,0
        add hl,sp
        ld a,h
        and 0C0h
.page:  cp 0                    ; build.py: the entry's page, in bits 7 and 6
        jr z,.skip
        in a,(0A8h)
        ld h,a                  ; the game's slot register
.mask:  and 0                   ; build.py: without the page's bits
.slot:  or 0                    ; build.py: the program's primary slot there
        out (0A8h),a
.at1:   ld a,(0)                ; build.py: the entry
.is1:   cp 0                    ; build.py: its first byte
        jr nz,.back
.at2:   ld a,(0)                ; build.py: the entry plus 1
.is2:   cp 0                    ; build.py: its second byte
        jr nz,.back
.call:  call 0                  ; build.py: the entry
.back:
        ld a,h
        out (0A8h),a
.skip:
        pop hl
        pop af
        ret
resbg:
        push af
        push hl
        ld hl,0
        add hl,sp
        ld a,h
        and 0C0h
.page:  cp 0                    ; build.py: the entry's page, in bits 7 and 6
        jr z,.skip
        push bc
        push de
.id1:   ld a,0                  ; build.py: the program's slot ID
.at1:   ld hl,0                 ; build.py: the entry
        call 000Ch              ; RDSLT
.is1:   cp 0                    ; build.py: its first byte
        jr nz,.back
.id2:   ld a,0                  ; build.py: the program's slot ID
.at2:   ld hl,0                 ; build.py: the entry plus 1
        call 000Ch
.is2:   cp 0                    ; build.py: its second byte
        jr nz,.back
.iy:    ld iy,0                 ; build.py: the slot ID in IYH
.call:  ld ix,0                 ; build.py: the entry
        call 001Ch              ; CALSLT
.back:
        pop de
        pop bc
.skip:
        pop hl
        pop af
        ret
; res3e and resbe end res3 and resb: build.py writes each just after the
; routine's stack, where its stack begins. Each gives the game its slot register
; and its stack back, and turns the interrupts on when they were on at the call,
; by P/V.
res3e:
        pop af                  ; the slot register, and IFF2 in P/V
        out (0A8h),a
.back:  ld sp,0                 ; the game's stack pointer
.po:    jp po,0                 ; build.py: .off
        ei
.off:   pop af
        ret
resbe:
.back:  ld sp,0                 ; the game's stack pointer
        pop de
        pop bc
        pop hl
.po:    jp po,0                 ; build.py: .off
        ei
.off:   pop af
        ret
; Game files call resb at FD29h and jump to the wrapper after res3 at FD56h, so
; each routine keeps the length that it had before it took a stack.
        assert resb-res3 = 45 && res3g-resb = 55
        assert resbg-res3g = resb-res3 && res3e-resbg = res3g-resb
        assert resbe-res3e = sub0-resbe

; sub0 is e_run's call of tramp for an image whose page 0 can be in another
; subslot of the slot of page 3, which is DOS's mapper's (INTERNALS.md, Page 0
; in another subslot of DOS's mapper's slot). There the slot register alone
; selects the game's subslot in page 0, the main ROM or other RAM, and not the
; mapper. build.py writes sub0 into zeros of the game's page 3, points e_run's
; call at it and sets FLAG_P0. It writes page 3's subslot into page 0's bits
; of the subslot register at FFFFh, calls tramp, and writes the register's
; value back. The value is the one when the entry ran, because the game
; switches its page 0 at any time. Interrupts are off, and pages 1 to 3 keep
; their bits. It takes 2 bytes of e_run's stack, so the deepest path takes all
; 22. It returns tramp's flags, BC, DE and HL, and e_run takes A from D.
sub0:
        ld a,(0FFFFh)
        cpl
.save:  ld (0),a                ; build.py: .back+1
        and 0FCh
.ss:    or 0                    ; build.py: page 3's subslot
        ld (0FFFFh),a
.tramp: call 0                  ; build.py: tramp
.back:  ld a,0                  ; the subslot register before the call
        ld (0FFFFh),a
        ret
        ent
call_end:

; tools/relocs.py appends the symbols and the offsets of the bytes that differ
; when P3_PAGE is FBh: the high bytes of the addresses in the page 3 part.
file_end:

; ---- The symbols that build.py reads by name (FORMATS.md, SERVICE.BIN) ----

; The tail's fields and the image's layout, from service.inc.
        export TAIL_PORT
        export TAIL_STACK
        export TAIL_SP
        export TAIL_EI
        export TAIL_JP
        export TAIL_PC
        export TAIL_AF
        export IMAGE_FORMAT
        export H_SIZE
        export DATA_SIZE
        export H_ROM
        export H_SUBROM
        export H_RECS
        export H_WRITES
        export H_FLAGS
        export H_P3
        export H_REGS
        export H_I
        export H_IM
        export H_IFF
        export H_A8
        export H_SUB
        export H_MAP
        export H_TAIL
        export H_VDP1
        export H_BORROW
        export H_NOEXP
        export H_TAILREC
        export H_P3REC
        export H_PLACES
        export H_TABLE
        export REC_SIZE
        export WRITE_SIZE
        export PLACE_SIZE
        export FLAG_ROM_KEEP
        export FLAG_T0
        export FLAG_P0
        export REC_MAPPER
        export REC_RAM
        export REC_SERVICE
        export REC_VRAM
        export REC_ZEROS

; The part of page 3 and the area that it takes by default.
        export E_PAGE
        export P3_FREE
        export P3_FREE_END
        export E_ENTRY
        export E_CODE
        export E_FC
        export E_STOP
        export P3_CODE
        export e_sp
        export e_run
        export e_run.call
        export tramp
        export resc
        export resc_stack
        export resc.mask
        export resc.slot
        export resc.at1
        export resc.is1
        export resc.at2
        export resc.is2
        export resc.call
; T0: the BIOS's tape code and the stubs at its routines' addresses.
        export T0_CODE
        export T0_END
        export t_tapion
        export t_tapin
        export t_tapiof
        export t_tapoon
        export t_tapout
        export t_tapoof
        export t_stmotr
; T0's call of a routine in its own slot: the two routines that build.py sends
; CALSLT to, and the jump to the BIOS's routine, whose address it fills in.
        export t_s
        export t_s.jump
        export t_c
        export t_res
        export T_STACK
        export RES_STACK
        export RESB_STACK
        export res3
        export res3.pe
        export res3.on
        export res3.save
        export res3.stack
        export res3.mask
        export res3.slot
        export res3.at1
        export res3.is1
        export res3.fail
        export res3.at2
        export res3.is2
        export res3.call
        export res3.tail
        export resb
        export resb.pe
        export resb.on
        export resb.save
        export resb.stack
        export resb.id1
        export resb.at1
        export resb.is1
        export resb.id2
        export resb.is2
        export resb.iy
        export resb.call
        export resb.tail
        export res3g
        export res3g.page
        export res3g.mask
        export res3g.slot
        export res3g.at1
        export res3g.is1
        export res3g.at2
        export res3g.is2
        export res3g.call
        export resbg
        export resbg.page
        export resbg.id1
        export resbg.at1
        export resbg.is1
        export resbg.id2
        export resbg.at2
        export resbg.is2
        export resbg.iy
        export resbg.call
        export res3e
        export res3e.back
        export res3e.po
        export res3e.off
        export resbe
        export resbe.back
        export resbe.po
        export resbe.off
        export RES3_STACK
        export sub0
        export sub0.save
        export sub0.ss
        export sub0.tramp
        export sub0.back
        export t_res.back
        export t_res.mask
        export t_res.slot
        export t_res.at1
        export t_res.is1
        export t_res.at2
        export t_res.is2
        export t_res.call
        export t_res.jump
; The code segment's data.
        export SEGS_MAX
        export D_POS
        export D_S1END
        export D_TOTAL
        export D_START
        export D_BORDER
        export D_FRAMES
        export D_VDP7
        export D_SIDE
        export D_SCREEN
        export D_VDP1
        export D_TWO
        export D_S1REAL
; The code segment's two jumps of a tape at its last side's end, for the check.
        export wrap.one
        export wrap.two
; T0 without a part in page 3: its routines for the jump table, and its data.
        export t0m.tapion
        export t0m.tapin
        export t0m.tapiof
        export t0m.tapoon
        export t0m.tapout
        export t0m.tapoof
        export t0m.stmotr
        export T_SEGS_MAX
        export t0m.D_POS
        export t0m.D_S1END
        export t0m.D_TOTAL
        export t0m.D_START
        export t0m.D_PAGE_MASK
        export t0m.D_PAGE_PORT
        export t0m.D_PAGE_HIGH
        export t0m.D_PAGE_SEG
        export t0m.D_BORDER
        export t0m.D_FRAMES
        export t0m.D_VDP7
        export t0m.D_SIDE
        export t0m.D_SCREEN
        export t0m.D_VDP1
        export t0m.D_TWO
