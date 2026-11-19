"""Resident-program call planning and code emission for build.py (docs/INTERNALS.md,
The resident program's call).

Builds the image's calls to a machine's resident program (such as SX2RES on
sx2-extramapper-mcp): from T0 (t_res), from H.KEYI (resb/resbg or res3/res3g),
or from wrappers for a game's own interrupt routine (res3 or resc).
"""
import struct

TAIL_SIZE = 26

SLTTBL = 0xFCC5  # the BIOS's copy of each slot's subslot register
H_KEYI = 0xFD9A  # the hook that the BIOS's interrupt routine calls first at each interrupt
EMPTY_HOOK = bytes([0xC9] * 5)
WRAPPER_SIZE = 17  # the wrapper of a game's vector with the tape service: place_wrapper
# Where the call routine goes without the tape service: SLTWRK's entries for
# slots 1 and 2, FD29h to FD68h, the work area of the ROMs in the cartridge
# slots, which nothing writes when the slots are empty. SLTATR at FCC9h, the
# other place, is where a ROM image's loader marks its slot, as the ROM loader
# of Aackosoft's tapes does, so it comes second.
CALL_AT = 0xFD29
CALL_ROOM = 0x40
SLTWRK = 0xFD09  # start of SLTWRK (FD09h-FD88h), above SLTATR (FCC9h-FD08h)
# MSX BIOS hooks (H.KEYI at FD9Ah through FFC8h): initialized to RET (C9h).
# Explicit rescode / resstack in this range may reuse unused C9h hooks directly
# without needing manual C9 -> 00 patch lines.
BIOS_HOOKS = (H_KEYI, 0xFFC8)
# The BIOS's slot routines in page 3, RDPRIM, WRPRIM and CLPRIM, as the BIOS
# writes them at F380h: resb's RDSLT and CALSLT run them. A game that clears
# them, as Super Cobra clears F380h to F7DBh, gets res3, which needs no BIOS
# routine.
BIOS_SLOT_CODE_AT = 0xF380
# The bytes on each side of a game file's patch of page 3 that the call
# routine's stack keeps clear of, for the patch's data (ResidentMixin.place_stack).
PATCH_MARGIN = 16
BIOS_SLOT_CODE = bytes.fromhex("D3 A8 5E 18 03 D3 A8 73 7A D3 A8 C9 D3 A8 08 CD 98 F3 08 F1 D3 A8 08 C9 DD E9")


class BuildError(Exception):
    """A snapshot or a file that cannot become an image."""


def patched_range(name, offset, length):
    """A patched range of a ram/ file as the check reads it: its page as
    build.txt names it, the first and the last offset."""
    return f"{name.cpu_page} {offset} {offset + length - 1}"


def ram_ranges(snapshot, ram_page, offset, length):
    """The patched ranges of a patch in a RAM page: one under each page that
    selects the page, because a game can select one mapper segment in two
    pages, and the check compares each page's file (Double Dragon maps segment
    0 of 0-1 in pages 2 and 3, so its vector at E2FFh is also A2FFh)."""
    return [patched_range(name, offset, length) for name in snapshot.names_of(ram_page)]


def rescall_kind(snapshot, game, mode, resident):
    """How the image calls a machine's resident program (FILES.md, Machine
    file, resident), from the snapshot: "t0" when T0's jump at 0038h can,
    because the game runs on the BIOS's interrupt routine in mode 1 with T0 in
    page 0; "hook" when there is no tape service and so no T0, and the game
    runs on the BIOS's routine in mode 1 with the main ROM in page 0, which
    calls H.KEYI. Otherwise the reason why not: "im2" or "im0"; "page0" when
    page 0 is not the main ROM at the snapshot, or with the tape service the
    snapshot keeps RAM for page 0, so that T0 does not replace the ROM;
    "romkeep"; "t0mode" in the mode without a part in page 3, whose T0 has no
    room; "slotbusy" when the game itself selects the program's slot in the
    entry's page, with another subslot there."""
    im = snapshot.num("im")
    if im != 1:
        return f"im{im}"
    if mode.service and mode.t0:
        return "t0mode"
    if mode.service and game.rom_keep:
        return "romkeep"
    ps, ss = snapshot.selected_slot(0)
    # With the tape service, T0 replaces the main ROM, so page 0 must select
    # it, and a RAM page kept for page 0 also keeps T0 from replacing it.
    # Without it, the BIOS's interrupt routine calls H.KEYI whenever page 0
    # is a ROM: a snapshot can catch the BIOS in a call of the sub-ROM, with
    # page 0 in its slot. Only RAM in page 0 has the game's own routine there.
    if mode.service:
        if not (ps == 0 and ss in (None, 0)) or any(r.name.page == 0 for r in snapshot.ram_pages):
            return "page0"
    elif snapshot.selected_ram(0) is not None:
        return "page0"
    if resident.slot_id & 0x80:
        page = resident.address >> 14
        if snapshot.selected_slot(page) not in ((resident.slot_id & 3, (resident.slot_id >> 2) & 3),) \
                and snapshot.selected_slot(page)[0] == resident.slot_id & 3:
            return "slotbusy"
    return "t0" if mode.service else "hook"


def check_resident_slot(snapshot, resident):
    """Stops when the snapshot keeps a RAM page in the slot of the machine's
    resident program, which the restore would write over."""
    for ram_page in snapshot.ram_pages:
        if ram_page.name.slot_id == resident.slot_id:
            raise BuildError(f"the snapshot keeps the RAM page {ram_page.name.file} in slot "
                             f"{ram_page.name.cpu_page.rsplit('-', 1)[0]}, which the machine's resident program "
                             "holds: the game needs RAM in another slot")


class ResidentMixin:
    """Resident-program call methods mixed into build.Image."""

    def use_resb(self):
        """Whether the H.KEYI call is resb, through the BIOS's RDSLT and
        CALSLT, and not res3: for H.KEYI, while the snapshot's page 3 holds
        the BIOS's slot routines at F380h as the BIOS writes them."""
        first = BIOS_SLOT_CODE_AT & 0x3FFF
        return self.hook is not None and bytes(self.p3.data[first:first + len(BIOS_SLOT_CODE)]) == BIOS_SLOT_CODE

    def routine_size(self):
        """The length of the call routine without the tape service: resb's
        for H.KEYI (use_resb), and res3's otherwise. The routines on the game's
        stack, res3g and resbg, have the same lengths."""
        service = self.service
        return service["res3g"] - service["resb"] if self.use_resb() else service["resb"] - service["res3"]

    def call_size(self):
        """The bytes that the image's code for the call takes in page 3,
        outside the tape service's part, for the plan that call_resident has
        made: with the tape service, the wrapper of a game's vector; without
        it, the call routine, with the wrapper of a vector and the chain of a
        hook in use. The routine's stack is apart (place_stack)."""
        if self.mode.service:
            return WRAPPER_SIZE * len(self.vectors)
        size = self.routine_size() + 6 * len(self.vectors)
        if self.hook == "chain":
            size += 3 + len(EMPTY_HOOK)
        return size

    def call_places(self):
        """The places for the call's code in page 3, in the order that
        call_resident tries them: the game file's rescode, or P3_FREE before
        the tape service's part, or, without the tape service, CALL_AT and
        then P3_FREE."""
        if self.game.rescode is not None:
            return [self.game.rescode]
        return [self.service["P3_FREE"]] if self.mode.service else [CALL_AT, self.service["P3_FREE"]]

    def room(self, length, at):
        """Whether the snapshot's page 3 holds zeros (or unused C9h BIOS hooks
        for an explicit rescode) for length bytes at at, clear of the tail and,
        with the tape service, of its part."""
        service = self.service
        if length == 0:
            return True
        if at + length > 0x10000:
            return False
        if self.mode.service:
            if at == self.game.rescode:
                if any(first < at + length and at <= first + len(data) - 1 for first, data in service.blocks()):
                    return False
            elif service.moved or at + length > service["E_ENTRY"]:
                return False
        if at == CALL_AT and length > CALL_ROOM:
            return False
        first = at & 0x3FFF
        allowed = (0, 0xC9) if (at == self.game.rescode and BIOS_HOOKS[0] <= at
                                and at + length - 1 <= BIOS_HOOKS[1]) else (0,)
        if any(b not in allowed for b in self.p3.data[first:first + length]):
            return False
        return not (self.tail.address < at + length and self.tail.address + TAIL_SIZE > at)

    def call_resident(self, resident):
        """Plans and makes the image's calls of the resident program, which
        rescall_kind allows: from T0 (t_res, build_t0) or, without the tape
        service, from H.KEYI (place_code). A game that has its own interrupt
        routine gets a wrapper in place of the game's vector (find_vector,
        patch_vector), and a game file's rescall names the routine when the
        game installs it later. Returns the kind for build.txt's rescall line
        and the patched ranges for the check."""
        game, kind, ranges = self.game, rescall_kind(self.snapshot, self.game, self.mode, resident), []
        self.program = resident
        if game.rescall == "no":
            return "off", []
        if game.rescall is not None and self.mode.service and self.mode.t0:
            raise BuildError("the game file's rescall cannot go with the tape service without a part in page 3")
        if isinstance(game.resstack, int) and self.mode.service:
            raise BuildError("the game file's resstack goes only with an image without the tape service, whose "
                             "call has its stack in page 3")
        self.vectors, self.hook = list(game.rescall or []), None
        found = None
        if not self.vectors and kind in ("page0", "im2"):
            found = self.find_vector()
            self.vectors = [found[0]] if found else []
        # Without the tape service, a rescode line places the routine alone,
        # for the calls that the game file's patches add to the game's code.
        alone = game.rescode is not None and not self.mode.service and kind in ("page0", "im0", "im2")
        if not self.vectors and kind not in ("t0", "hook") and not alone:
            return kind, []
        if self.p3 is None:
            self.vectors = []
            return "nopage3", []
        if kind == "hook":
            self.hook = "free" if bytes(self.p3.data[H_KEYI & 0x3FFF:][:len(EMPTY_HOOK)]) == EMPTY_HOOK else "chain"
        self.call_at = next((at for at in self.call_places() if self.room(self.call_size(), at)), None)
        if self.call_at is None:
            if game.rescall is not None or game.rescode is not None:
                places = " or ".join(f"{at:04X}h" for at in self.call_places())
                raise BuildError(f"the game file's rescall needs {self.call_size()} bytes of zeros at "
                                 f"{places} in the snapshot's page 3, clear of the tail and "
                                 "the tape service's part, and the snapshot has not")
            self.vectors, self.hook = [], None
            return "p3busy", []
        if found:
            ranges += self.patch_vector(found)
        if kind == "t0":
            self.resident = resident
        ranges += self.set_subslot(resident)
        if not self.mode.service:
            ranges += self.place_code()
        return kind, ranges

    def set_subslot(self, resident):
        """The program's subslot in the entry's page bits of the header's
        subslot register of its slot and of the game's SLTTBL. Returns the
        patched ranges."""
        ranges = []
        if resident.slot_id & 0x80:
            ps, ss, shift = resident.slot_id & 3, (resident.slot_id >> 2) & 3, 2 * (resident.address >> 14)
            sub = self.snapshot.state[f"sub{ps}"]
            if sub != "-":
                self.subslots[ps] = int(sub, 16) & ~(3 << shift) | (ss << shift)
            at = (SLTTBL + ps) & 0x3FFF
            self.p3.data[at] = self.p3.data[at] & ~(3 << shift) | (ss << shift)
            ranges += ram_ranges(self.snapshot, self.p3, at, 1)
        return ranges

    def wrapper_entry(self, n=0):
        """The address that a game's interrupt vector goes to: the nth wrapper,
        one for each routine in vectors, at the call's place, after the call
        routine without the tape service, res3 or resb (place_code)."""
        if self.mode.service:
            return self.call_at + WRAPPER_SIZE * n
        return self.call_at + self.routine_size() + 6 * n

    def place_code(self):
        """Without the tape service, writes the call routine at the call's
        place in the game's page 3, with its fields, then the wrapper of the
        game's vector, CALL the routine / JP the game's routine, and the chain
        of a hook in use, CALL the routine / the hook's old five bytes."""
        service, at = self.service, self.call_at
        name = "resb" if self.use_resb() else "res3"
        size = self.routine_size()
        self.code_span = (at, at + self.call_size() - 1)
        stack_size = service["RESB_STACK" if name == "resb" else "RES3_STACK"]
        first = service[name + "e"]
        end = bytearray(service.parts["call"][first:service["resbe" if name == "res3" else "sub0"]])
        stack = self.place_stack(stack_size + len(end))
        ranges = []
        if stack is None:
            name += "g"
        base = service[name]
        core = bytearray(service.parts["call"][base:base + size])
        if name.startswith("resb"):
            self.write_resb(core, name, self.program)
        else:
            self.write_call(core, name, self.program, base)
        if stack is not None:
            last = stack + stack_size
            def field(routine, label, value, offset=1):
                struct.pack_into("<H", core if routine == name else end,
                                 service[f"{routine}.{label}"] - service[routine] + offset, value)
            field(name, "pe", at + service[f"{name}.on"] - base)
            field(name, "save", last + service[f"{name}e.back"] - service[name + "e"] + 1, 2)
            field(name, "stack", last)
            for label in ("fail", "tail"):
                if f"{name}.{label}" in service.symbols:
                    field(name, label, last)
            field(name + "e", "po", last + service[f"{name}e.off"] - service[name + "e"])
            self.p3.data[last & 0x3FFF:(last & 0x3FFF) + len(end)] = end
            ranges = ram_ranges(self.snapshot, self.p3, last & 0x3FFF, len(end))
        code = bytes(core)
        for vector in self.vectors:
            code += b"\xCD" + struct.pack("<H", at) + b"\xC3" + struct.pack("<H", vector)
        keyi = bytes([0xCD]) + struct.pack("<H", at) + b"\xC9\xC9"
        if self.hook == "chain":
            first = H_KEYI & 0x3FFF
            old = bytes(self.p3.data[first:first + len(EMPTY_HOOK)])
            keyi = bytes([0xC3]) + struct.pack("<H", at + len(code)) + b"\xC9\xC9"
            code += b"\xCD" + struct.pack("<H", at) + old
        first = at & 0x3FFF
        self.p3.data[first:first + len(code)] = code
        assert self.code_span == (at, at + len(code) - 1)
        ranges += ram_ranges(self.snapshot, self.p3, first, len(code))
        if self.hook is not None:
            at_keyi = H_KEYI & 0x3FFF
            self.p3.data[at_keyi:at_keyi + len(keyi)] = keyi
            ranges += ram_ranges(self.snapshot, self.p3, at_keyi, len(keyi))
        return ranges

    def place_stack(self, size):
        """The first address of size bytes for the call routine's stack, or
        None: zeros of the snapshot's page 3, clear of the call's code and of
        the tail (or unused C9h BIOS hooks for an explicit resstack)."""
        service, game, (code_first, code_last) = self.service, self.game, self.code_span
        taken = [self.code_span, (self.tail.address, self.tail.address + TAIL_SIZE - 1)]

        def free(first, low=0xC000, high=0xFFFF, allow_ret=False):
            last = first + size - 1
            allowed = (0, 0xC9) if (allow_ret and BIOS_HOOKS[0] <= first and last <= BIOS_HOOKS[1]) else (0,)
            return (low <= first and last <= high
                    and all(b in allowed for b in self.p3.data[(first & 0x3FFF):(last & 0x3FFF) + 1])
                    and not any(a <= last and b >= first for a, b in taken))

        if game.resstack == "no":
            return None
        if game.resstack is not None:
            if not free(game.resstack, allow_ret=True):
                raise BuildError(f"the game file's resstack needs {size} bytes of zeros at {game.resstack:04X}h in "
                                 "the snapshot's page 3, clear of the tail and the call's code, and the snapshot "
                                 "has not")
            places = [game.resstack]
        else:
            low, high = service["P3_FREE"], service["P3_FREE_END"]
            sp = self.snapshot.num("sp")
            taken.append((sp - 0x100, sp))
            # A game file's code in page 3 keeps its data in zeros beside it,
            # as Pentagram's keeps its stack pointer and a count at FCE8h.
            taken += [(0xC000 + patch.offset - PATCH_MARGIN, 0xC000 + patch.offset + len(patch.old) - 1 + PATCH_MARGIN)
                      for patch in game.patches if patch.page == 3]
            # Prefer SLTWRK (FD09h-FD88h) over SLTATR (FCC9h-FD08h), where the
            # BIOS's ROM search and some games write.
            beside = [code_first - size, code_last + 1]
            places = ([first for first in beside if first >= SLTWRK and free(first, low, high)]
                      + [first for first in beside if first < SLTWRK and free(first, low, high)]
                      + [first for first in range(high - size + 1, low - 1, -1) if free(first, low, high)])
        if not places:
            return None
        self.stack_span = (places[0], places[0] + size - 1)
        return places[0]

    def find_vector(self):
        """For a game that has its own interrupt routine at the snapshot, where
        its vector is: in mode 1, the jump at 0038h of the game's RAM in page
        0, and in mode 2 the word at the address that I and FFh make."""
        snapshot = self.snapshot
        if snapshot.num("im") == 2:
            places = [((snapshot.num("i") << 8 | 0xFF) + n) & 0xFFFF for n in range(2)]
        else:
            page0 = snapshot.selected_ram(0)
            if page0 is None or page0.data[0x38] != 0xC3:
                return None
            places = [0x39, 0x3A]
        pages = [snapshot.selected_ram(at >> 14) for at in places]
        if None in pages:
            return None
        old = bytes(page.data[at & 0x3FFF] for page, at in zip(pages, places))
        return struct.unpack("<H", old)[0], places, pages

    def patch_vector(self, found):
        """Writes the wrapper's address into the game's vector that
        find_vector found, and returns the patched ranges for the check."""
        _, places, pages = found
        ranges = []
        for page, at, byte in zip(pages, places, struct.pack("<H", self.wrapper_entry())):
            page.data[at & 0x3FFF] = byte
            ranges += ram_ranges(self.snapshot, page, at & 0x3FFF, 1)
        return ranges

    def write_call(self, data, name, resident, base=0):
        """The fields of a call of the resident program in data, t_res in T0,
        resc in the code segment, or res3 or res3g from its start at base in
        the call part."""
        service = self.service
        page = resident.address >> 14
        if page not in (1, 2):
            raise BuildError(f"the resident program's entry {resident.address:04X}h is not in page 1 or 2")
        def at(field):
            return service[f"{name}.{field}"] - base
        if f"{name}.page" in service.symbols:
            data[at("page") + 1] = page << 6
        data[at("mask") + 1] = ~(3 << 2 * page) & 0xFF
        data[at("slot") + 1] = (resident.slot_id & 3) << 2 * page
        struct.pack_into("<H", data, at("at1") + 1, resident.address)
        data[at("is1") + 1] = resident.signature[0]
        struct.pack_into("<H", data, at("at2") + 1, resident.address + 1)
        data[at("is2") + 1] = resident.signature[1]
        struct.pack_into("<H", data, at("call") + 1, resident.address)

    def write_resb(self, data, name, resident):
        """The fields of resb or resbg in data, the routine from its start in
        the call part."""
        service = self.service
        page = resident.address >> 14
        if page not in (1, 2):
            raise BuildError(f"the resident program's entry {resident.address:04X}h is not in page 1 or 2")
        base = service[name]
        def at(field):
            return service[f"{name}.{field}"] - base
        if f"{name}.page" in service.symbols:
            data[at("page") + 1] = page << 6
        for n in (1, 2):
            data[at(f"id{n}") + 1] = resident.slot_id
            # resb reads the entry's second byte at HL plus 1, which RDSLT keeps.
            if f"{name}.at{n}" in service.symbols:
                struct.pack_into("<H", data, at(f"at{n}") + 1, resident.address + n - 1)
            data[at(f"is{n}") + 1] = resident.signature[n - 1]
        struct.pack_into("<H", data, at("iy") + 2, resident.slot_id << 8)
        struct.pack_into("<H", data, at("call") + 2, resident.address)

    def write_t_res(self, t0):
        """T0's jump at 0038h to t_res, with t_res's fields and the BIOS's
        interrupt routine, where the jump went."""
        service = self.service
        if t0[0x38] != 0xC3:
            raise BuildError(f"{self.snapshot.folder}/rom.bin: no jump at 0038h")
        old = struct.unpack_from("<H", t0, 0x39)[0]
        struct.pack_into("<H", t0, 0x39, service["t_res"])
        self.write_call(t0, "t_res", self.resident)
        struct.pack_into("<H", t0, service["t_res.jump"] + 1, old)

    def place_wrapper(self):
        """With the tape service, writes the wrappers that the game's interrupt
        vectors go to, one for each routine, before the entries."""
        service, at = self.service, self.call_at
        code = b"".join(bytes([0xF5, 0xC5, 0xD5, 0xE5, 0x21]) + struct.pack("<H", service["resc"]) + b"\xCD"
                        + struct.pack("<H", service["e_run"]) + bytes([0xE1, 0xD1, 0xC1, 0xF1, 0xC3])
                        + struct.pack("<H", vector) for vector in self.vectors)
        assert len(code) == WRAPPER_SIZE * len(self.vectors)
        first = at & 0x3FFF
        self.p3.data[first:first + len(code)] = code
        self.code_span = (at, at + len(code) - 1)
        return ram_ranges(self.snapshot, self.p3, first, len(code))
