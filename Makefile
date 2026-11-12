# snapcas build and tests (docs/PLAN.md).
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
SNAPCAS_SRC := src/snapcas.asm src/service.inc src/slots.inc src/worker.inc
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
# move with it. Each assembly also writes the symbols that service.asm exports,
# which tools/relocs.py appends for build.py.
bin/SERVICE.BIN: $(SERVICE_SRC) tools/relocs.py $(SJASMPLUS)
	mkdir -p bin $(OUT)
	$(SJASMPLUS) --nologo --raw=$(OUT)/service-fc.bin --exp=$(OUT)/service-fc.exp $<
	$(SJASMPLUS) --nologo -DP3_PAGE=0FBh --raw=$(OUT)/service-fb.bin --exp=$(OUT)/service-fb.exp $<
	python3 -I tools/relocs.py $(OUT)/service-fc.bin $(OUT)/service-fc.exp $(OUT)/service-fb.bin $(OUT)/service-fb.exp $@

# service.asm exports symbols, so each of its assemblies names a file for them.
$(OUT)/service.sym: $(SERVICE_SRC) $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ --exp=$(OUT)/service.exp $<

# Three test games, each with the symbol file that its tests read, by a rule of
# its own: borrow, for the tape service through a borrowed page outside a
# mapper, contract, which calls each entry of the tape service and keeps what
# it returns, and guard, which writes the service's part of page 3, for the
# check's point 2.
TEST_GAME_NAMES := borrow contract guard
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

# The MegaFlashROM SCC+ SD with only Nextor in its flash, for fsa1-mfrsd and
# hbf1xd-mfrsd: openMSX's stock flash also holds a ROM disk, whose AUTOEXEC.BAT
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
  PICOPICO.TSX ROCKYA.CAS SIR-FRED.CAS SOOTLANB.CAS SOOTLAND.CAS SUPER-09.CAS \
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

test: bin/SNAPCAS.COM bin/SERVICE.BIN $(SYMBOLS) $(TEST_GAMES) $(TEST_TAPES) $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(NMS8250_512K) $(NMS8250_4M) $(HBF700P_NOEXP0)
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

# The run over every shipped game file on a machine (docs/INTERNALS.md, The games
# run), apart from make test because it takes hours.
games: bin/SNAPCAS.COM bin/SERVICE.BIN $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(HBF700P_NOEXP0)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  python3 -I tools/games.py $(MACHINE) $(if $(DOS),--dos $(DOS)) $(if $(FULL),--full) $(if $(filter 0,$(FIX)),--no-fix)

# The openMSX home that snapcas.py uses, with the firmware of the machines that
# need it.
firmware: $(FIRMWARE) $(HBF700P_NOEXP0)

# bin/ stays, because git holds its files.
clean:
	rm -rf $(OUT)/test $(SYMBOLS) $(OUT)/service-fc.bin $(OUT)/service-fb.bin $(OUT)/service-fc.exp $(OUT)/service-fb.exp $(OUT)/service.exp \
	  $(TEST_GAMES)

.PHONY: help all unit test games firmware clean

# A recipe that fails leaves no cut file under its target's name.
.DELETE_ON_ERROR:
