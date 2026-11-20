"""The trampoline patch (docs/internals/patches.md, The trampoline patch): the tape
loader of Opera Soft's, Topo Soft's, Dinamic's and other Spanish tapes, which
builds a trampoline on the stack at FC9Ah that reaches the BIOS's TAPION by the
slot register alone. Where the main ROM and the game's RAM share a primary slot,
as on the SX-2 with its Extra-Mapper on, the slot register cannot select the
ROM, and the trampoline calls the game's RAM. patches/tramp.tcl patches the
builder at step 3 on such a machine only. With the tape service, the build
makes each patched builder, in the snapshot's RAM pages and in the tape
service's tapes, and a patched trampoline at FC9Ah, call the service instead
(serve). The kind works only in the capture and in that step of the build, so
its find() finds nothing."""
import re

import msx

# The builder: LD DE,0C961h / PUSH DE / LD DE,0EDD9h / PUSH DE / LD DE,00E1h /
# PUSH DE / LD DE,0CDD9h / PUSH DE / LD DE,069EDh / PUSH DE / PUSH HL / EXX /
# LD C,0A8h / IN H,(C) / AND H / LD L,A, with A = FCh. The pushes leave at
# FC9Ah the trampoline OUT (C),L / EXX / CALL 00E1h / EXX / OUT (C),H / RET,
# and L is the slot register with slot 0 in page 0. CALL 0FC9Ah follows, and
# the loader changes the call's low byte at FC9Eh for TAPIN and STMOTR.
BUILDER = bytes.fromhex("11 61 C9 D5 11 D9 ED D5 11 E1 00 D5 11 D9 CD D5 11 ED 69 D5 E5 D9 0E A8 ED 60 A4 6F")
CALL = bytes.fromhex("CD 9A FC")
FORM = re.compile(re.escape(BUILDER + CALL))

# Patched trampoline: LD (HL),n / EXX / CALL 00E1h / EXX / LD (HL),C / RET
# (HL=FFFFh, C=saved subslot from NEW_CALLER). The unused trailing byte at
# FCA3h preserves the builder block's XOR checksum.
CALLER = 22        # LD C,0A8h / IN H,(C) / AND H / LD L,A
NEW_CALLER = bytes.fromhex("21 FF FF 7E 2F 4F")


def xor(data):
    value = 0
    for b in data:
        value ^= b
    return value


def patched(rom_sub, ram_sub):
    """The patched builder for a main ROM in subslot rom_sub and the RAM in
    subslot ram_sub of the same primary slot."""
    new = bytearray(BUILDER)
    # LD DE,nnC9h: RET at FCA2h and the free byte at FCA3h.
    new[1:3] = bytes([0xC9, 0])
    # LD DE,71D9h: EXX / LD (HL),C at FCA0h.
    new[6] = 0x71
    # LD DE,nn36h: LD (HL),n at FC9Ah.
    new[17:19] = bytes([0x36, ram_sub * 0x54 + rom_sub])
    new[CALLER:CALLER + 6] = NEW_CALLER
    new[2] = xor(BUILDER) ^ xor(new)
    return bytes(new)


def places(data):
    """The offsets in data of the builders."""
    return [m.start() for m in FORM.finditer(data)]


# A patched builder, whatever its subslots: the bytes that the patch leaves and
# the bytes that it writes.
PATCHED = re.compile(re.escape(BUILDER[:1]) + rb"\xC9." + re.escape(BUILDER[3:6]) + rb"\x71"
                     + re.escape(BUILDER[7:17]) + rb"\x36." + re.escape(BUILDER[19:CALLER])
                     + re.escape(NEW_CALLER), re.S)
# The offsets in the builder of LD (HL),n's n and of the call's high byte.
VALUE, CALL_HIGH = 18, 10

# The patched trampoline as the builder leaves it at FC9Ah, with any call:
# LD (HL),n / EXX / CALL nn / EXX / LD (HL),C / RET.
TRAMPOLINE = 0xFC9A
LIVE = re.compile(rb"\x36.\xD9\xCD..\xD9\x71\xC9", re.S)


def served_value(value):
    """n for the tape service: the RAM's subslot, from n's page 3 field, in
    every page. DOS's mapper, which holds T0 and the code segment, is that RAM,
    and the service's entry selects only its primary slot in page 0."""
    return ((value >> 6) & 3) * 0x55


def serve(data, entry_page):
    """Makes each patched builder in data, a bytearray of a RAM page or of a
    tape, the builder for the tape service: n selects the RAM's subslot in
    every page, and with an entry page, the image's default mode, the call
    goes to the entry at E1h of that page, FCE1h unless the part moved. With
    None, the mode without a part in page 3, the call stays. The free byte
    keeps the XOR. Returns the builders' offsets."""
    found = [m.start() for m in PATCHED.finditer(data)
             if data[m.end():m.end() + len(CALL)] == CALL]
    for at in found:
        new = bytearray(data[at:at + len(BUILDER)])
        new[VALUE] = served_value(new[VALUE])
        if entry_page is not None:
            new[CALL_HIGH] = entry_page
        new[2] = 0
        new[2] = xor(BUILDER) ^ xor(new)
        data[at:at + len(BUILDER)] = new
    return found


def serve_live(page3, entry_page):
    """Makes the patched trampoline at FC9Ah in page3, the bytes of the
    snapshot's RAM page in page 3, the trampoline for the tape service, as
    serve makes the builder: a snapshot within a load goes on with it, and
    with the registers that the patched builder set. Returns its offset in
    page3, or None."""
    at = TRAMPOLINE & 0x3FFF
    if not LIVE.match(bytes(page3), at):
        return None
    page3[at + 1] = served_value(page3[at + 1])
    if entry_page is not None:
        page3[at + 5] = entry_page
    return at


def find(data, context):
    """Nothing: the build makes the builders call the tape service before the
    scan (serve)."""
    return []


def tcl(side1, side2):
    """The kind's Tcl for the capture: each builder in the tape files, as
    {side offset}, the builder's bytes, and for each pair of the ROM's and
    the RAM's subslots, the patched bytes, as tramp.tcl's settings, and
    tramp.tcl."""
    found = [f"{{{side} {offset}}}" for side, data in ((1, side1), (2, side2)) for offset in places(data)]
    forms = [f"{rom},{ram} {msx.tcl_bytes(patched(rom, ram))}" for rom in range(4) for ram in range(4)
             if rom != ram]
    return (f"set ::tramp {{{' '.join(found)}}}\n"
            f"set ::tramp_old {msx.tcl_bytes(BUILDER)}\n"
            f"array set ::tramp_new {{{' '.join(forms)}}}\n"
            + msx.tcl("patches/tramp.tcl"))
