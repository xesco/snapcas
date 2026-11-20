#!/usr/bin/env python3
"""Build cartridge flash images and openMSX machine XMLs for make firmware."""
import argparse
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET

MFR_FLASH_SIZE = 0x800000
MFR_NEXTOR_OFFSET = 0x700000
BLOCK = 0x4000

SX2_PARTS = {
    "main": (8, 2, b"\xf3\xc3"),
    "xbasic": (10, 1, b"AB"),
    "music": (11, 1, b"AB"),
    "sub": (12, 1, b"CD"),
    "kanji": (13, 2, b"AB"),
    "slot03": (15, 1, b""),
    "kanjifont": (16, 16, b""),
}


def atomic_write(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(tmp, mode) as f:
        f.write(data)
    os.replace(tmp, path)


def build_mfr_flash(args):
    """Build an 8 MB MegaFlashROM SCC+ SD flash with Nextor at 700000h."""
    with open(args.rom, "rb") as f:
        rom = f.read()
    flash = bytearray(b"\xff" * MFR_FLASH_SIZE)
    flash[MFR_NEXTOR_OFFSET:MFR_NEXTOR_OFFSET + len(rom)] = rom
    got = hashlib.sha1(flash).hexdigest()
    if got != args.sha1:
        sys.exit(f"SHA-1 mismatch for {args.out}: got {got}, expected {args.sha1}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    atomic_write(args.out, flash)


def build_sx2(args):
    """Extract SX-2 ROMs from OCM-BIOS.DAT and generate an openMSX machine XML."""
    with open(args.bios, "rb") as f:
        data = f.read()
    if len(data) != 32 * BLOCK:
        sys.exit(f"{args.bios} is not an SX-2 OCM-BIOS.DAT of 512 KB")

    os.makedirs(args.roms, exist_ok=True)
    rom = {}
    for name, (block, count, head) in SX2_PARTS.items():
        part = data[block * BLOCK:(block + count) * BLOCK]
        if not part.startswith(head):
            sys.exit(f"{args.bios}: block {block} is not the {name} ROM of an MSX2+ OCM-BIOS.DAT")
        rom_path = os.path.join(args.roms, f"sx2-{name}.rom")
        atomic_write(rom_path, part)
        sha1 = hashlib.sha1(part).hexdigest()
        rom[name] = f"<rom><filename>sx2-{name}.rom</filename><sha1>{sha1}</sha1></rom>"

    with open(args.fsa1wsx) as f:
        model = f.read()
    font = re.compile(r'(?s)(<Kanji id="Kanji ROM">\s*)<rom>.*?</rom>')
    if len(font.findall(model)) != 1:
        sys.exit(f"{args.fsa1wsx} does not have exactly one Kanji ROM")
    model = font.sub(lambda m: m.group(1) + rom["kanjifont"], model)

    with open(args.ide) as f:
        sunrise = re.search(r"(?s)<SunriseIDE .*?</SunriseIDE>", f.read()).group(0)

    first = model.index('<primary slot="0">')
    last = model.rindex("</primary>") + len("</primary>")
    main = f'<ROM id="MSX BIOS with BASIC ROM">{rom["main"]}<mem base="0x0000" size="0x8000"/></ROM>'

    if args.mode.startswith("extramapper"):
        extra = (
            '<secondary slot="1">\n'
            '        <MemoryMapper id="Extra-Mapper"><size>4096</size><mem base="0x0000" size="0x10000"/></MemoryMapper>\n'
            '      </secondary>'
        )
    else:
        extra = '<secondary slot="1"/>'

    if args.mode == "expanded" or args.mode.startswith("extramapper"):
        main = (
            f'<secondary slot="0">\n        {main}\n      </secondary>\n'
            f'      {extra}\n'
            f'      <secondary slot="2">\n'
            f'        <MSX-MUSIC id="MSX Music">{rom["music"]}<sound><volume>9000</volume></sound>'
            f'<ym2413-core>NukeYKT</ym2413-core><io base="0x7C" num="2" type="O"/><mem base="0x4000" size="0x4000"/></MSX-MUSIC>\n'
            f'      </secondary>\n'
            f'      <secondary slot="3">\n'
            f'        <ROM id="Slot 0-3 ROM">{rom["slot03"]}<mem base="0x4000" size="0x4000"/></ROM>\n'
            f'      </secondary>'
        )

    main_ram = (
        "" if args.mode == "extramapper-noram30"
        else '<MemoryMapper id="Main RAM"><size>2048</size><mem base="0x0000" size="0x10000"/></MemoryMapper>'
    )
    slots = (
        f'<primary slot="0">\n      {main}\n    </primary>\n'
        f'    <primary external="true" slot="1"/>\n'
        f'    <primary external="true" slot="2"/>\n'
        f'    <primary slot="3">\n'
        f'      <secondary slot="0">\n        {main_ram}\n      </secondary>\n'
        f'      <secondary slot="1">\n'
        f'        <ROM id="MSX Sub ROM">{rom["sub"]}<mem base="0x0000" size="0x4000"/></ROM>\n'
        f'        <ROM id="MSX Kanji Driver with BASIC">{rom["kanji"]}<mem base="0x4000" size="0x8000"/></ROM>\n'
        f'      </secondary>\n'
        f'      <secondary slot="2">\n        {sunrise}\n      </secondary>\n'
        f'      <secondary slot="3">\n'
        f'        <ROM id="BASIC\'n">{rom["xbasic"]}<mem base="0x4000" size="0x4000"/></ROM>\n'
        f'      </secondary>\n'
        f'    </primary>'
    )

    text = model[:first] + slots + model[last:]
    ET.fromstring(text)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    atomic_write(args.out, text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    mfr = sub.add_parser("mfr-flash")
    mfr.add_argument("rom")
    mfr.add_argument("sha1")
    mfr.add_argument("out")
    mfr.set_defaults(fn=build_mfr_flash)

    sx2 = sub.add_parser("sx2")
    sx2.add_argument("fsa1wsx")
    sx2.add_argument("ide")
    sx2.add_argument("bios")
    sx2.add_argument("roms")
    sx2.add_argument("mode", choices=("expanded", "noexp0", "extramapper", "extramapper-noram30"))
    sx2.add_argument("out")
    sx2.set_defaults(fn=build_sx2)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
