# snapcas build and tests (docs/PLAN.md).
#
#   make        print this help
#   make all    build bin/SNAPCAS.COM and bin/SERVICE.BIN
#   make test   run the tests in openMSX
#   make games  make and check every shipped game file's image on MACHINE=
#
# The tests read their tape files from tests/tapes/, and MSX-DOS's system files
# from DOS_DIR, by default dos/, with msxdos1/ and msxdos2/: git ignores dos/,
# because snapcas cannot ship MSX-DOS. The tests that need it are skipped when
# the folders do not exist.
#
# The Makefile downloads Nextor's NEXTOR.SYS and COMMAND2.COM into dos/nextor/,
# and its tools into out/cache/, each pinned by version and SHA-256: the sjasmplus
# assembler's source, which it builds, and two cartridges' firmware: the SD
# Mapper's SDMAPPER.ROM and Nextor's ROM for the MegaFlashROM SCC+ SD. The tests
# run openMSX 22.0 from the path, in a home of their own, out/cache/openmsx-home,
# whose system ROMs are a link to the user's and that firmware, so that they
# leave the user's openMSX settings alone.

SJASMPLUS_VERSION := 1.24.0
SYSTEMROMS ?= $(HOME)/.openMSX/share/systemroms
# openMSX's own share folder: in its app beside the program on macOS, as
# Homebrew installs it, or in /usr/share.
OPENMSX_BIN := $(dir $(realpath $(shell command -v openmsx)))
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
	@echo "make all    build bin/SNAPCAS.COM and bin/SERVICE.BIN"
	@echo "make test   run the tests"
	@echo "make games  check every game in downloads"
	@echo "make clean  remove the built files and the test output"

all: bin/SNAPCAS.COM bin/SERVICE.BIN

bin/SNAPCAS.COM: src/snapcas.asm src/service.inc $(SJASMPLUS)
	mkdir -p bin
	$(SJASMPLUS) --nologo --raw=$@ $<

# out/service.sym gives the tests the service's addresses. The second
# assembly, with the page 3 part one page lower, shows which bytes move with it.
bin/SERVICE.BIN: src/service.asm src/service.inc src/tape.inc tools/relocs.py $(SJASMPLUS)
	mkdir -p bin $(OUT)
	$(SJASMPLUS) --nologo --raw=$(OUT)/service-fc.bin --sym=$(OUT)/service.sym $<
	$(SJASMPLUS) --nologo -DP3_PAGE=0FBh --raw=$(OUT)/service-fb.bin $<
	python3 -I tools/relocs.py $(OUT)/service-fc.bin $(OUT)/service-fb.bin $@

# A test game for the tape service through a borrowed page outside a mapper.
$(OUT)/borrow.bin: tests/borrow.asm $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --raw=$@ --sym=$(OUT)/borrow.sym $<

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

# vg8020-picoverse: a 192 KB memory mapper cartridge, the PicoVerse's mapper.
RAM192K := $(EMU_HOME)/share/extensions/ram192k.xml
$(RAM192K):
	mkdir -p $(dir $@)
	sed 's|<size>512</size>|<size>192</size>|; s|512 kB|192 kB|g; s|512k|192k|g' $(OPENMSX_SHARE)/extensions/ram512k.xml > $@.tmp
	grep -q '<size>192</size>' $@.tmp
	mv $@.tmp $@

test: bin/SNAPCAS.COM bin/SERVICE.BIN $(OUT)/borrow.bin $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(NMS8250_512K) $(RAM192K)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) NEXTOR_DIR=$(abspath $(NEXTOR)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  python3 -I tests/run.py

MACHINE ?= phc28s-ram64k-carnivore2
DOS ?= $(NEXTOR)
FULL ?=

# The run over every shipped game file on a machine (docs/INTERNALS.md, The games
# run), apart from make test because it takes hours.
games: bin/SNAPCAS.COM bin/SERVICE.BIN $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(FIRMWARE) $(RAM192K)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) python3 -I tools/games.py $(MACHINE) --dos $(DOS) $(if $(FULL),--full)

clean:
	rm -rf bin $(OUT)/test

.PHONY: help all test games clean
