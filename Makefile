# snapcas build and tests (docs/BUILD.md).
#
#   make        print this help
#   make all    build bin/SNAPCAS.COM and bin/SERVICE.BIN
#   make unit   run the tests that need no openMSX, in a few seconds
#   make test   run all the tests, most of them in openMSX
#   make games  make and check every shipped game file's image on MACHINE=
#
# The tests read their tape files from tests/tapes/, which git holds, and
# MSX-DOS's system files from DOS_DIR, by default dos/, with msxdos1/ and
# msxdos2/: git ignores dos/, because snapcas cannot ship MSX-DOS. The tests that
# need MSX-DOS are skipped when its folder does not exist, and the run names
# them. No other test is skipped: a tape or a built file that is missing stops
# make test.
#
# The Makefile downloads Nextor's NEXTOR.SYS and COMMAND2.COM into dos/nextor/,
# and its tools into out/cache/, each pinned by version and SHA-256: the sjasmplus
# assembler's source, which it builds, and two cartridges' firmware: the SD
# Mapper's SDMAPPER.ROM and Nextor's ROM for the MegaFlashROM SCC+ SD. The tests
# run openMSX 22.0 from the path, or the program that OPENMSX names, in a home of
# their own, out/cache/openmsx-home, whose system ROMs are a link to the user's
# and that firmware, so that they leave the user's openMSX settings alone.

SJASMPLUS_VERSION := 1.24.0
SYSTEMROMS ?= $(HOME)/.openMSX/share/systemroms
# openMSX's own share folder: in its app beside the program on macOS, as
# Homebrew installs it, or in /usr/share.
OPENMSX ?= openmsx
OPENMSX_BIN := $(dir $(realpath $(shell command -v $(OPENMSX))))
OPENMSX_SHARE ?= $(firstword $(wildcard $(OPENMSX_BIN)../openMSX.app/Contents/Resources/share \
                   $(OPENMSX_BIN)../Resources/share /usr/share/openmsx /usr/local/share/openmsx))
DOS_DIR ?= dos

OUT       := out
CACHE     := $(OUT)/cache
DL        := $(CACHE)/dl
SJASMPLUS := $(CACHE)/tools/sjasmplus
NEXTOR    := $(DOS_DIR)/nextor
EMU_HOME  := $(CACHE)/openmsx-home

help:
	@echo "make all       build bin/SNAPCAS.COM and bin/SERVICE.BIN"
	@echo "make firmware  download the firmware that some machines need"
	@echo "make unit      run the tests that need no openMSX"
	@echo "make test      run all the tests"
	@echo "make games     check every game in downloads"
	@echo "make clean     remove the test output and the build's files in out/"

# The symbol files give the addresses in the binaries: out/service.sym the
# service's, which the tests read, and out/snapcas.sym the restorer's. Each has
# a rule of its own, with its binary's sources, because git holds the binaries
# and not the symbol files: a clone gets them by an assembly that leaves the
# binaries alone.
SNAPCAS_SRC := src/snapcas.asm src/service.inc src/slots.inc src/worker.inc src/version.inc
SERVICE_SRC := src/service.asm src/service.inc src/tape.inc
SYMBOLS := $(OUT)/snapcas.sym $(OUT)/service.sym

all: bin/SNAPCAS.COM bin/SERVICE.BIN $(SYMBOLS)

bin/SNAPCAS.COM: $(SNAPCAS_SRC) $(SJASMPLUS)
	mkdir -p bin
	$(SJASMPLUS) --nologo --raw=$@ $<

$(OUT)/snapcas.sym: $(SNAPCAS_SRC) $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ $<

# The second assembly, with the page 3 part one page lower, shows which bytes
# move with it, and the third, with the part's code block 0111h bytes higher,
# which addresses move with that block. Each assembly also writes the symbols
# that service.asm exports, which tools/relocs.py appends for build.py.
bin/SERVICE.BIN: $(SERVICE_SRC) tools/relocs.py $(SJASMPLUS)
	mkdir -p bin $(OUT)
	$(SJASMPLUS) --nologo --raw=$(OUT)/service-fc.bin --exp=$(OUT)/service-fc.exp $<
	$(SJASMPLUS) --nologo -DP3_PAGE=0FBh --raw=$(OUT)/service-fb.bin --exp=$(OUT)/service-fb.exp $<
	$(SJASMPLUS) --nologo -DCODE_MOVED=0FE0Ch --raw=$(OUT)/service-cm.bin --exp=$(OUT)/service-cm.exp $<
	python3 -I tools/relocs.py $(OUT)/service-fc.bin $(OUT)/service-fc.exp $(OUT)/service-fb.bin $(OUT)/service-fb.exp \
	  $(OUT)/service-cm.bin $(OUT)/service-cm.exp $@

# service.asm exports symbols, so each of its assemblies names a file for them.
$(OUT)/service.sym: $(SERVICE_SRC) $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ --exp=$(OUT)/service.exp $<

# Four test games, each with the symbol file that its tests read, by a rule of
# its own: borrow, for the tape service through a borrowed page outside a
# mapper, contract, which calls each entry of the tape service and keeps what
# it returns, guard, which writes the service's part of page 3, for the
# check's point 2, and subrom, which calls the sub-ROM through T0 and then
# reads the tape.
TEST_GAME_NAMES := borrow contract guard subrom
TEST_GAMES := $(foreach game,$(TEST_GAME_NAMES),$(OUT)/$(game).bin $(OUT)/$(game).sym)

$(TEST_GAME_NAMES:%=$(OUT)/%.bin): $(OUT)/%.bin: tests/%.asm $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --raw=$@ $<

$(TEST_GAME_NAMES:%=$(OUT)/%.sym): $(OUT)/%.sym: tests/%.asm $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ $<

$(SJASMPLUS): $(DL)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz
	rm -rf $(CACHE)/tools/src
	mkdir -p $(CACHE)/tools/src
	tar -xJf $< -C $(CACHE)/tools/src
	$(MAKE) -C $(CACHE)/tools/src/sjasmplus-$(SJASMPLUS_VERSION)
	cp $(CACHE)/tools/src/sjasmplus-$(SJASMPLUS_VERSION)/sjasmplus $@

$(DL)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz:
	python3 -I tools/fetch.py https://github.com/z00m128/sjasmplus/releases/download/v$(SJASMPLUS_VERSION)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz 0b5013f07e8d8505f9e296529655668b6fdf0268625c19e883b0fff484e209f1 $@

# Nextor 2.1.0's tools.zip holds NEXTOR.SYS 2.11 and COMMAND2.COM 2.44.
$(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM &:
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.0/tools.zip 5792ff3fe7ab684b8afd405cdd898e25f6efdb84ca1f2cb9ac1428cc848d924e $(NEXTOR) NEXTOR.SYS COMMAND2.COM

# The test home's system ROMs: a link to the user's, and the firmware below in
# a folder of snapcas's own. openMSX finds a ROM by its SHA-1 in either. An
# older test home had the link in place of the folder.
SYSTEMROMS_LINK := $(EMU_HOME)/share/systemroms/user
$(SYSTEMROMS_LINK):
	if [ -L $(EMU_HOME)/share/systemroms ]; then rm $(EMU_HOME)/share/systemroms; fi
	mkdir -p $(dir $@)
	ln -sfn $(SYSTEMROMS) $@

# The SD Mapper v1's firmware, Nextor with its driver 1.0.7, which openMSX's
# SD_Mapper_v1 loads into its flash.
SDMAPPER_ROM := $(EMU_HOME)/share/systemroms/snapcas/SDMAPPER.ROM
$(SDMAPPER_ROM): | $(SYSTEMROMS_LINK)
	python3 -I tools/fetch.py https://github.com/fbelavenuto/msxsdmapper/releases/download/v1.0.7/SDMAPPER.ROM 4371c4094756672f78b295dbfb753cb6a3011e7fdb11348249be1bc36fbd061b $@

# The MegaFlashROM SCC+ SD with only Nextor in its flash, for fsa1-mfrsd:
# openMSX's stock flash also holds a ROM disk, whose AUTOEXEC.BAT
# starts a file manager on an MSX2. The flash is 8 MB of FFh with Nextor's ROM
# at 700000h, where the cartridge's subslot 3, its SD interface, reads it.
MFR_NEXTOR := $(DL)/Nextor-2.1.4.MegaFlashSDSCC.1-slot.ROM
$(MFR_NEXTOR):
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.4/Nextor-2.1.4.MegaFlashSDSCC.1-slot.ROM 5e1ab82af74b84e46636a14c592ac9d97a1515feb1104fb38d46152b16e57cb1 $@

MFR_FLASH := $(EMU_HOME)/share/systemroms/snapcas/MFRSD-Nextor-2.1.4.ROM
MFR_FLASH_SHA1 := ea48fb3d4f73a9046bfe82a3c94d738b6a903b4e
$(MFR_FLASH): $(MFR_NEXTOR) | $(SYSTEMROMS_LINK)
	mkdir -p $(dir $@)
	python3 -I -c "import sys; d = open(sys.argv[1], 'rb').read(); f = bytearray(b'\xff' * 0x800000); f[0x700000:0x700000 + len(d)] = d; open(sys.argv[2], 'wb').write(f)" $< $@.tmp
	python3 -I -c "import hashlib, sys; sys.exit(hashlib.sha1(open(sys.argv[1], 'rb').read()).hexdigest() != sys.argv[2])" $@.tmp $(MFR_FLASH_SHA1)
	mv $@.tmp $@

MFR_NEXTOR_EXT := $(EMU_HOME)/share/extensions/MegaFlashROM_SCC+_SD_Nextor.xml
$(MFR_NEXTOR_EXT): $(MFR_FLASH)
	mkdir -p $(dir $@)
	sed 's|<sha1>1621f623b834dc57cb2983f30b36bcc3ac56cafd</sha1>|<sha1>$(MFR_FLASH_SHA1)</sha1>|; s|<sramname>megaflashromsccplussd.sram</sramname>|<sramname>megaflashromsccplussd-nextor.sram</sramname>|; s|<name>MegaFlashROM SCC+ SD</name>|<name>MegaFlashROM SCC+ SD with Nextor only</name>|' $(OPENMSX_SHARE)/extensions/MegaFlashROM_SCC+_SD.xml > $@.tmp
	grep -q '$(MFR_FLASH_SHA1)' $@.tmp
	grep -q 'megaflashromsccplussd-nextor.sram' $@.tmp
	mv $@.tmp $@

FIRMWARE := $(SYSTEMROMS_LINK) $(SDMAPPER_ROM) $(MFR_NEXTOR_EXT)

# test/nms8250-512k: openMSX's NMS 8250 with its mapper at 512 KB, which
# Moonwalker's 236 KB tape needs.
NMS8250_512K := $(EMU_HOME)/share/machines/Philips_NMS_8250_512k.xml
$(NMS8250_512K):
	mkdir -p $(dir $@)
	sed 's|<size>128</size>|<size>512</size>|' $(OPENMSX_SHARE)/machines/Philips_NMS_8250.xml > $@.tmp
	grep -q '<size>512</size>' $@.tmp
	mv $@.tmp $@

# test/nms8250-4m-dos1 and test/nms8250-4m-ram4mb-dos1: the same with its
# mapper at 4 MB, whose last segment is segment 255.
NMS8250_4M := $(EMU_HOME)/share/machines/Philips_NMS_8250_4m.xml
$(NMS8250_4M):
	mkdir -p $(dir $@)
	sed 's|<size>128</size>|<size>4096</size>|' $(OPENMSX_SHARE)/machines/Philips_NMS_8250.xml > $@.tmp
	grep -q '<size>4096</size>' $@.tmp
	mv $@.tmp $@

# The capture variants hbf700p-noexp0-ram512k-msxdos2 and hbf700p-noexp0-msxdos2:
# openMSX's HB-F700P with its slot 0 not expanded. The real slot 0 holds only
# the main ROM, in subslot 0. So the two lines that start and end that subslot
# go, in slot 0 alone, and the file keeps the 2 subslots of slot 3.
HBF700P_NOEXP0 := $(EMU_HOME)/share/machines/Sony_HB-F700P_noexp0.xml
$(HBF700P_NOEXP0):
	mkdir -p $(dir $@)
	sed -e '/<primary slot="0">/,/<\/primary>/{' -e '/<secondary slot="0">/d' -e '/<\/secondary>/d' -e '}' $(OPENMSX_SHARE)/machines/Sony_HB-F700P.xml > $@.tmp
	test "$$(grep -c '<secondary slot' $@.tmp)" = 2
	test "$$(grep -c '</secondary>' $@.tmp)" = 2
	mv $@.tmp $@

# The machines sx2 and sx2-noexp0: the SX-2, an FPGA MSX2+ on KdL's OCM-PLD
# firmware, whose slots copy the Panasonic FS-A1WSX's. Its ROMs are KdL's own,
# in the SD card's OCM-BIOS.DAT, which snapcas cannot ship: SX2_BIOS names the
# user's copy, by default OCM-BIOS.DAT in the system ROMs. The file is the disk
# ROM's 128 KB, then 16 KB blocks: the main ROM in 8 and 9, BASIC'n in 10,
# MSX-MUSIC in 11, the sub-ROM in 12, Kanji BASIC in 13 and 14, the ROM of slot
# 0-3 in 15, on the SX-2 the ESP8266's Wi-Fi BIOS, and the Kanji font in 16 to
# 31. The models take the devices of openMSX's FS-A1WSX, and their slots are
# the SX-2's: 2048 KB of RAM in 3-0; the sub-ROM and Kanji BASIC in 3-1; a
# Sunrise IDE with Nextor in 3-2, in place of the MegaSD, which openMSX lacks;
# and BASIC'n in 3-3. OCM_SX-2.xml has slot 0 expanded, as the SX-2 starts: the
# main ROM in 0-0, MSX-MUSIC in 0-2 and the Wi-Fi BIOS in 0-3, with 0-1 empty
# while the extra mapper is off. openMSX has no ESP8266, so the Wi-Fi BIOS finds
# none. OCM_SX-2_noexp0.xml has slot 0 as SETSMART -F9FD leaves it: not
# expanded, with only the main ROM. OCM_SX-2_extramapper.xml has the
# Extra-Mapper of 4096 KB on in 0-1, and OCM_SX-2_extramapper_noram30.xml is
# that model without the 2048 KB mapper in 3-0, for the capture of a game whose
# loader finds that RAM before the Extra-Mapper (machines/capture/).
SX2_BIOS ?= $(SYSTEMROMS)/OCM-BIOS.DAT
SX2 := $(EMU_HOME)/share/machines/OCM_SX-2.xml
SX2_NOEXP0 := $(EMU_HOME)/share/machines/OCM_SX-2_noexp0.xml
SX2_EXTRAMAPPER := $(EMU_HOME)/share/machines/OCM_SX-2_extramapper.xml
SX2_NORAM30 := $(EMU_HOME)/share/machines/OCM_SX-2_extramapper_noram30.xml
SX2_ROMS := $(EMU_HOME)/share/systemroms/snapcas/sx2
define SX2_PY
import hashlib, os, re, sys
import xml.etree.ElementTree as ET
fsa1wsx, ide, bios, roms, slot0, out = sys.argv[1:]
data = open(bios, "rb").read()
K = 0x4000
if len(data) != 32 * K:
    sys.exit(bios + " is not an SX-2's OCM-BIOS.DAT of 512 KB")
parts = dict(main=(8, 2, b"\xf3\xc3"), xbasic=(10, 1, b"AB"), music=(11, 1, b"AB"), sub=(12, 1, b"CD"),
             kanji=(13, 2, b"AB"), slot03=(15, 1, b""), kanjifont=(16, 16, b""))
os.makedirs(roms, exist_ok=True)
rom = {}
for name, (block, count, head) in parts.items():
    part = data[block * K:(block + count) * K]
    if not part.startswith(head):
        sys.exit(bios + ": block " + str(block) + " is not the " + name + " ROM of an MSX2+ OCM-BIOS.DAT")
    rom_path = os.path.join(roms, "sx2-" + name + ".rom")
    tmp_path = f"{rom_path}.{os.getpid()}.tmp"
    open(tmp_path, "wb").write(part)
    os.replace(tmp_path, rom_path)
    rom[name] = "<rom><filename>sx2-" + name + ".rom</filename><sha1>" + hashlib.sha1(part).hexdigest() + "</sha1></rom>"
model = open(fsa1wsx).read()
font = re.compile(r"(?s)(<Kanji id=\"Kanji ROM\">\s*)<rom>.*?</rom>")
if len(font.findall(model)) != 1:
    sys.exit(fsa1wsx + " has not one Kanji ROM")
model = font.sub(lambda m: m.group(1) + rom["kanjifont"], model)
sunrise = re.search(r"(?s)<SunriseIDE .*?</SunriseIDE>", open(ide).read()).group(0)
first, last = model.index('<primary slot="0">'), model.rindex("</primary>") + len("</primary>")
main = f"""<ROM id="MSX BIOS with BASIC ROM">{rom["main"]}<mem base="0x0000" size="0x8000"/></ROM>"""
# The Extra-Mapper in 0-1, which SETSMART's code 57h turns on.
extra = """<secondary slot="1"/>"""
if slot0.startswith("extramapper"):
    extra = """<secondary slot="1">
        <MemoryMapper id="Extra-Mapper"><size>4096</size><mem base="0x0000" size="0x10000"/></MemoryMapper>
      </secondary>"""
if slot0 == "expanded" or slot0.startswith("extramapper"):
    main = f"""<secondary slot="0">
        {main}
      </secondary>
      {extra}
      <secondary slot="2">
        <MSX-MUSIC id="MSX Music">{rom["music"]}<sound><volume>9000</volume></sound><ym2413-core>NukeYKT</ym2413-core><io base="0x7C" num="2" type="O"/><mem base="0x4000" size="0x4000"/></MSX-MUSIC>
      </secondary>
      <secondary slot="3">
        <ROM id="Slot 0-3 ROM">{rom["slot03"]}<mem base="0x4000" size="0x4000"/></ROM>
      </secondary>"""
# Slot 3-0's mapper of 2048 KB, which extramapper-noram30 leaves out.
main_ram = """<MemoryMapper id="Main RAM"><size>2048</size><mem base="0x0000" size="0x10000"/></MemoryMapper>"""
if slot0 == "extramapper-noram30":
    main_ram = ""
slots = f"""<primary slot="0">
      {main}
    </primary>
    <primary external="true" slot="1"/>
    <primary external="true" slot="2"/>
    <primary slot="3">
      <secondary slot="0">
        {main_ram}
      </secondary>
      <secondary slot="1">
        <ROM id="MSX Sub ROM">{rom["sub"]}<mem base="0x0000" size="0x4000"/></ROM>
        <ROM id="MSX Kanji Driver with BASIC">{rom["kanji"]}<mem base="0x4000" size="0x8000"/></ROM>
      </secondary>
      <secondary slot="2">
        {sunrise}
      </secondary>
      <secondary slot="3">
        <ROM id="BASIC'n">{rom["xbasic"]}<mem base="0x4000" size="0x4000"/></ROM>
      </secondary>
    </primary>"""
text = model[:first] + slots + model[last:]
ET.fromstring(text)
open(out, "w").write(text)
endef
export SX2_PY
$(SX2): $(SX2_BIOS)
	mkdir -p $(dir $@)
	python3 -I -c "$$SX2_PY" $(OPENMSX_SHARE)/machines/Panasonic_FS-A1WSX.xml $(OPENMSX_SHARE)/extensions/SunriseIDE_Nextor.xml $< $(SX2_ROMS) expanded $@.tmp
	mv $@.tmp $@
$(SX2_EXTRAMAPPER): $(SX2_BIOS)
	mkdir -p $(dir $@)
	python3 -I -c "$$SX2_PY" $(OPENMSX_SHARE)/machines/Panasonic_FS-A1WSX.xml $(OPENMSX_SHARE)/extensions/SunriseIDE_Nextor.xml $< $(SX2_ROMS) extramapper $@.tmp
	mv $@.tmp $@
$(SX2_NORAM30): $(SX2_BIOS)
	mkdir -p $(dir $@)
	python3 -I -c "$$SX2_PY" $(OPENMSX_SHARE)/machines/Panasonic_FS-A1WSX.xml $(OPENMSX_SHARE)/extensions/SunriseIDE_Nextor.xml $< $(SX2_ROMS) extramapper-noram30 $@.tmp
	mv $@.tmp $@
$(SX2_NOEXP0): $(SX2_BIOS)
	mkdir -p $(dir $@)
	python3 -I -c "$$SX2_PY" $(OPENMSX_SHARE)/machines/Panasonic_FS-A1WSX.xml $(OPENMSX_SHARE)/extensions/SunriseIDE_Nextor.xml $< $(SX2_ROMS) noexp0 $@.tmp
	mv $@.tmp $@
# Without the user's OCM-BIOS.DAT, make leaves the SX-2's machines out, and make
# firmware says where the file goes.
# The Sunrise IDE's Nextor ROM, which the models' slot 3-2 loads, so that the
# SX-2's machines need no other file of the user's than OCM-BIOS.DAT.
SUNRISE_NEXTOR := $(EMU_HOME)/share/systemroms/snapcas/Nextor-2.1.1.SunriseIDE.ROM
$(SUNRISE_NEXTOR): | $(SYSTEMROMS_LINK)
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.1/Nextor-2.1.1.SunriseIDE.ROM 205af7f7893aa0328be23f66b3afe3132c7dee59cf4bbc493408475a201c7ad6 $@
SX2_FIRMWARE := $(if $(wildcard $(SX2_BIOS)),$(SX2) $(SX2_NOEXP0) $(SX2_EXTRAMAPPER) $(SX2_NORAM30) $(SUNRISE_NEXTOR))
SX2_MISSING := $(if $(SX2_FIRMWARE),,the SX-2's machines need its OCM-BIOS.DAT from its SD card at $(SX2_BIOS), or SX2_BIOS= naming it)

# The tests' tape files, which git holds. A test does not skip without its
# tape, so one that the folder lacks stops make test here.
TEST_TAPES := $(addprefix tests/tapes/, \
  001-ARIO.CAS 016-ROBE.CAS 022-MOON.CAS 035-EDGY.CAS 4X4OFFRO.TSX 7-CARD.CAS \
  ABADIA.CAS ABU-SIMB.CAS AMOTO-S.CAS BATMAN.CAS BESTIAL.CAS BUMPER.CAS \
  CALDERO.CAS CAMELOT.CAS CHASE-H.CAS CHASEB.CAS CHICAGO.CAS COBRA-S.CAS \
  COMPUTAD.CAS DESPERAD.CAS DOKI-DOK.CAS DUSTIN.CAS EMERALD.CAS ENCHANTE.CAS \
  ENGESO06.CAS ENGESO07.CAS FERNANDO.CAS FIELD-MA.CAS FINDERIN.CAS FREDDY.CAS \
  GAUNTLEB.CAS GAUNTLET.CAS GHOSTB85.CAS ITALIA.CAS JET-BOMB.CAS KNIGHTMA.CAS \
  KONAMI.CAS LAZERBYK.TSX LICENCE.TSX LIVINGST.CAS MAD-MIDE.CAS MAD-MIX.CAS \
  MADE-IN.CAS MOONWALK.CAS MORTADEL.CAS MOTB.CAS MOTORIST.CAS NONAMED.CAS \
  PICOPICO.TSX ROCKYA.CAS SIR-FRED.CAS SOOTLANB.CAS SOOTLAND.CAS SUPER-09.CAS SUPER-1.CAS \
  SUPERM18.CAS SUPERMOB.CAS TETRIS.CAS THING-BO.CAS TOUR-91.CAS TOUR-91B.CAS \
  TUAREG.CAS TURBO-GI.CAS UCHI87.CAS WORLD-CU.CAS YIE-AR.CAS YIE-ARII.CAS \
  ZANAC.CAS)

$(TEST_TAPES):
	@echo "$@ is missing: git holds the tests' tapes" >&2
	@false

# The pure tier (tests/support.py, PURE): the tests that start no openMSX and
# read no tape, so they need only the built files.
unit: bin/SNAPCAS.COM bin/SERVICE.BIN $(SYMBOLS)
	python3 -I tests/run.py --pure

test: bin/SNAPCAS.COM bin/SERVICE.BIN $(SYMBOLS) $(TEST_GAMES) $(TEST_TAPES) $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(NMS8250_512K) $(NMS8250_4M) $(HBF700P_NOEXP0) $(SX2_FIRMWARE)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) NEXTOR_DIR=$(abspath $(NEXTOR)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  python3 -I tests/run.py

MACHINE ?= phc28s-ram64k-carnivore2
# The folder of the check's DOS files, in place of the machine's own below
# DOS_DIR, which its machine file's dosfiles line names.
DOS ?=
FULL ?=
# The run tries each game file that fails on the machine's capture variants, and
# writes the capture line of one that passes into the machine's game file. FIX=0
# leaves that out.
FIX ?= 1

# The run over every shipped game file on a machine (docs/internals/capture.md, The games
# run), apart from make test because it takes hours.
games: bin/SNAPCAS.COM bin/SERVICE.BIN $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(HBF700P_NOEXP0) $(SX2_FIRMWARE)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  python3 -I tools/games.py $(MACHINE) $(if $(DOS),--dos $(DOS)) $(if $(FULL),--full) $(if $(filter 0,$(FIX)),--no-fix)

# The openMSX home that snapcas.py uses, with the firmware of the machines that
# need it.
firmware: $(FIRMWARE) $(HBF700P_NOEXP0) $(SX2_FIRMWARE)
	$(if $(SX2_MISSING),@echo "$(SX2_MISSING)" >&2)

# bin/ stays, because git holds its files.
clean:
	rm -rf $(OUT)/test $(SYMBOLS) $(OUT)/service-fc.bin $(OUT)/service-fb.bin $(OUT)/service-cm.bin $(OUT)/service-fc.exp $(OUT)/service-fb.exp $(OUT)/service-cm.exp $(OUT)/service.exp \
	  $(TEST_GAMES)

.PHONY: help all unit test games firmware clean

# A recipe that fails leaves no cut file under its target's name.
.DELETE_ON_ERROR:
