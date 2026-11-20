; ---- Messages ----

; Prints the image's name, then the message at DE, and ends the program.
stop_name:
        push de
        call name
        pop de
; tools/check.py finds this label and print in out/snapcas.sym, and takes the
; call of print as the restorer's first instruction of a stop.
stop_message:
        call print
        ld a,(dos_seg2)
        call select_p2
        ei
        ld c,_TERM0
        jp BDOS

print:
        ld c,_STROUT
        push ix
        push iy
        call BDOS
        pop iy
        pop ix
        ret

; Prints the image's name: its path, or under MSX-DOS 1 the FCB's name without
; its trailing spaces, then ".SNP".
name:
        ld a,(by_path)
        or a
        jr z,.fcb
        ld hl,path
.path:
        ld a,(hl)
        or a
        ret z
        push hl
        ld e,a
        ld c,_CONOUT
        call BDOS
        pop hl
        inc hl
        jr .path
.fcb:
        ld hl,fcb+1
        ld b,8
.char:
        ld a,(hl)
        cp " "
        jr z,.ext
        push hl
        push bc
        ld e,a
        ld c,_CONOUT
        call BDOS
        pop bc
        pop hl
        inc hl
        djnz .char
.ext:
        ld de,t_ext
        ld c,_STROUT
        jp BDOS

; Copies the image's argument from the command line at 0080h into path, ended by
; 0, and adds ".SNP" when the path's last item has no extension. The argument is
; the first word that is not an option, and it ends at a space, a "/" or the
; line's end. Returns Z when there is no argument.
get_path:
        ld hl,0080h
        ld b,(hl)
        inc hl
        ld de,path
.skip:
        ld a,b
        or a
        jr z,.end
        ld a,(hl)
        cp "/"
        jr z,.option
        cp " "+1
        jr nc,.copy
        inc hl
        dec b
        jr .skip
.option:
        inc hl
        dec b
        ld a,b
        or a
        jr z,.end
        ld a,(hl)
        cp " "+1
        jr nc,.option
        jr .skip
.copy:
        ld c,0                  ; 1 after a "." in the last item
.char:
        ld a,b
        or a
        jr z,.end
        ld a,(hl)
        cp " "+1
        jr c,.end
        cp "/"
        jr z,.end
        cp "."
        jr nz,.sep
        ld c,1
.sep:
        cp 5Ch                  ; "\", which the MSX shows as its yen sign
        jr z,.item
        cp ":"
        jr nz,.store
.item:
        ld c,0
.store:
        ld (de),a
        inc de
        inc hl
        dec b
        jr .char
.end:
        ld a,e
        cp low path
        jr nz,.ext
        ld a,d
        cp high path
        jr z,.done              ; no argument
.ext:
        ld a,c
        or a
        jr nz,.done
        ld hl,t_ext
        ld bc,4
        ldir
.done:
        xor a
        ld (de),a
        ld a,(path)
        or a
        ret

; Prints A in decimal, without leading zeros.
print_dec:
        ld hl,digits
        ld (hl),0
        ld b,100
        call .digit
        ld b,10
        call .digit
        ld hl,digits
        ld (hl),1
        ld b,1
.digit:
        ld d,"0"-1
.sub:
        inc d
        sub b
        jr nc,.sub
        add a,b
        push af
        ld a,d
        cp "0"
        jr nz,.show
        ld a,(digits)
        or a
        jr z,.skip
.show:
        ld a,1
        ld (digits),a
        ld e,d
        ld c,_CONOUT
        push ix
        push iy
        call BDOS
        pop iy
        pop ix
.skip:
        pop af
        ret

        include "slots.inc"

t_banner:   db "SNAPCAS.COM version ",VERSION,13,10
            db "Copyright (",YEAR,") ",AUTHOR,13,10,13,10,"$"
t_usage:    db "Usage: SNAPCAS <game> [/M]",13,10
            db "Restores <game>.SNP, a snapcas image.",13,10
            db "/M: the tape moves only with RETURN,",13,10
            db "GRAPH or CODE.",13,10,"$"
t_manual:   db ": /M does not work with this image,",13,10
            db "so the tape stays automatic",13,10,"$"
t_ext:      db ".SNP$"
t_notfound: db " not found",13,10,"$"
t_notimage: db " is not a snapcas image",13,10,"$"
t_version:  db ": made for another version of SNAPCAS.COM",13,10,"$"
t_cut:      db ": the file is cut short: it lacks data of its records",13,10,"$"
t_onemapper: db ": DOS's pages are not in one memory mapper",13,10,"$"
t_dos1:     db ": MSX-DOS 1 needs a memory mapper with DOS in segments 3, 2, 1 and 0",13,10,"$"
t_roms:     db ": made for another machine: its ROMs differ from this one's",13,10,"$"
t_noworker: db ": no page 1 or 2 can hold the restorer's worker at the end",13,10,"$"
t_mapsize:  db ": a page's segment is beyond this machine's mapper",13,10,"$"
t_segments: db ": DOS has too few free mapper segments",13,10,"$"
t_holds:    db ": more than 64 pages need a segment that DOS uses",13,10,"$"
            assert HOLD_MAX = 64
t_needs:    db ": needs $"
t_free:     db " free mapper segments, and DOS has $"
t_crlf:     db 13,10,"$"
t_page0:    db ": a page 0 is in another subslot of DOS's mapper's slot",13,10,"$"
t_romkeep:  db ": rom keep needs the main ROM outside DOS's mapper's slot",13,10,"$"
t_t0page0:  db ": service t0 needs page 0 outside DOS's mapper",13,10,"$"
t_t0seg:    db ": T0 cannot take the segment of page 0's RAM,",13,10
            db "which shares mapper register FCh with it",13,10,"$"
t_t0sub:    db ": service t0 needs DOS's mapper's subslot in the borrowed page",13,10,"$"
t_read:     db ": cannot be read",13,10,"$"
; stop_slot writes the slot's number at SLOT_AT of these three.
t_notram:   db ": slot 0 page "
t_page_n:   db "0 is not RAM: the machine file does not describe this machine",13,10,"$"
t_plain:    db ": slot 0 is DOS's mapper, and the image has RAM without a mapper there",13,10,"$"
t_expanded: db ": slot 0 is not expanded as at the capture:",13,10
            db "the machine file does not describe this machine",13,10,"$"
; The image's mark (FORMATS.md, Image).
t_mark:     db "SNAPCAS",IMAGE_FORMAT

fcb:        db 0                ; drive, from the argument
            ds 8," "            ; name, from the argument
            db "SNP"
            ds FCB_SIZE-12,0

by_path:    db 0                ; 1 when the image is open by its path, under MSX-DOS 2
handle:     db 0                ; then its handle
path:       ds 128+5            ; the argument, with ".SNP" and a 0
dos2:       db 0
dos_slot:   db 0                ; DOS's mapper's slot ID
m_ps:       db 0                ; its primary slot
m_ss:       db 0                ; and its subslot
m_sub:      db 0                ; the snapshot's subslot register of that slot
map_slot:   db 0
map_size:   db 0                ; DOS's mapper's segments, 0 for 256
dos_seg0:   db 0                ; DOS's segments in pages 0 to 3
dos_seg1:   db 0
dos_seg2:   db 0
dos_seg3:   db 0
saved4:     ds 4
tail_page:  db 0
worker_page: db 0
worker_mode: db 0               ; 0, 1 or 2: the rule of find_worker_page
worker_seg: db 0
service:    db 0                ; nonzero with the tape service
p0:         db 0                ; the RAM pages for page 0, as in check_records
t0_a8:      db 0                ; the slot register with DOS's mapper in page 0
t0_rom:     db 0                ; 1 when T0 replaces the ROM
p0_live:    db 0                ; 1 when sub0 gives page 0 the mapper's subslot
t0_fixed:   db 0                ; 1 when T0 must be segment t0_fix
t0_fix:     db 0
t0_direct:  db 0                ; 1 when T0 is read straight into t0_fix
manual:     db 0                ; 1 with /M
svc_segs:   ds SEGS_MAX+1       ; T0's segment, the code segment, the tape's
svc_next:   dw svc_segs         ; where service_seg writes next
svc_i:      db 0                ; the number of the next service segment read
free_count: db 0
hold_count: db 0
hold_next:  dw holds
holds:      ds 2*HOLD_MAX       ; each: the holding segment, its own segment
rec_n:      db 0                ; the walk: the record's number
data_n:     db 0                ; and the records with data before it
writes_at:  dw 0                ; the port writes, after the records
places_at:  dw 0                ; the places, after the port writes
pass:       db 0
vram_written: db 0              ; 1 once a VRAM block is written
dos_sp:     dw 0
buffer:     dw 0
count:      dw 0
needed:     db 0
digits:     db 0
jiffy0:     dw 0
            align 256
dest:       ds 256              ; by record: the segment that it is read into
freemap:    ds 256              ; by segment of DOS's mapper: 0, FREE or OWN

