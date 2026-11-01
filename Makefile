# snapcas build and tests (docs/PLAN.md).
#
#   make        print this help
#   make all    build bin/SNAPCAS.COM and bin/SERVICE.BIN
#   make test   run the tests in openMSX
#   make try    start openMSX as advanced/phc28s, with SNAPCAS.COM and the images
#               in out/try/ on its disk: MACHINE= and FILES= change them
#
# The tests read the tape files from CAS_DIR, by default tapes/, and MSX-DOS's
# system files from DOS_DIR, by default dos/, with msxdos1/ and msxdos2/: git
# ignores both, because snapcas cannot ship them. The tests that need them are
# skipped when the folders do not exist.
#
# The Makefile downloads its tools into out/, each pinned by version and SHA-256:
# the sjasmplus assembler's source, which it builds, and Nextor's NEXTOR.SYS and
# COMMAND2.COM for the test disks. The tests run openMSX 22.0 from the path, in
# a home of their own, out/openmsx-home, with a link to the system ROMs, so that
# they leave the user's openMSX settings alone.

SJASMPLUS_VERSION := 1.24.0
SYSTEMROMS ?= $(HOME)/.openMSX/share/systemroms
# openMSX's own share folder: in its app beside the program on macOS, as
# Homebrew installs it, or in /usr/share.
OPENMSX_BIN := $(dir $(realpath $(shell command -v openmsx)))
OPENMSX_SHARE ?= $(firstword $(wildcard $(OPENMSX_BIN)../openMSX.app/Contents/Resources/share \
                   $(OPENMSX_BIN)../Resources/share /usr/share/openmsx /usr/local/share/openmsx))
CAS_DIR ?= tapes
COLLECTION_DIR ?= $(CAS_DIR)/collection
COLLECTION_MACHINES ?= advanced/phc28s basic/vg8020
COLLECTION_WORKERS ?= 11
COLLECTION_FULL ?=
DOS_DIR ?= dos

OUT       := out
DL        := $(OUT)/dl
SJASMPLUS := $(OUT)/tools/sjasmplus
NEXTOR    := $(DL)/nextor
EMU_HOME  := $(OUT)/openmsx-home

help:
	@echo "make all    build bin/SNAPCAS.COM and bin/SERVICE.BIN"
	@echo "make test   run the tests in openMSX: CAS_DIR=, by default tapes/, holds the"
	@echo "            tape files, the TSX files in tsx/, and DOS_DIR=, by default dos/,"
	@echo "            MSX-DOS's system files"
	@echo "make collection  capture, build and check every game file of games/ on"
	@echo "            COLLECTION_MACHINES, by default advanced/phc28s and basic/vg8020,"
	@echo "            with the CAS files of COLLECTION_DIR, by default CAS_DIR/collection,"
	@echo "            into out/test/step9/collection/<machine>.txt: takes hours. A game"
	@echo "            file whose inputs and the code are unchanged keeps its last result,"
	@echo "            unless COLLECTION_FULL=1. COLLECTION_WORKERS=, by default 11, runs"
	@echo "            that many at once"
	@echo "make try    start openMSX as advanced/phc28s with SNAPCAS.COM and the images"
	@echo "            in out/try/ on its disk: MACHINE= and FILES= change them"
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
	rm -rf $(OUT)/tools/src
	mkdir -p $(OUT)/tools/src
	tar -xJf $< -C $(OUT)/tools/src
	$(MAKE) -C $(OUT)/tools/src/sjasmplus-$(SJASMPLUS_VERSION)
	cp $(OUT)/tools/src/sjasmplus-$(SJASMPLUS_VERSION)/sjasmplus $@

$(DL)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz:
	python3 -I tools/fetch.py https://github.com/z00m128/sjasmplus/releases/download/v$(SJASMPLUS_VERSION)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz 0b5013f07e8d8505f9e296529655668b6fdf0268625c19e883b0fff484e209f1 $@

# Nextor 2.1.0's tools.zip holds NEXTOR.SYS 2.11 and COMMAND2.COM 2.44.
$(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM &:
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.0/tools.zip 5792ff3fe7ab684b8afd405cdd898e25f6efdb84ca1f2cb9ac1428cc848d924e $(NEXTOR) NEXTOR.SYS COMMAND2.COM

$(EMU_HOME)/share/systemroms:
	mkdir -p $(EMU_HOME)/share
	ln -sfn $(SYSTEMROMS) $@

# test/nms8250-512k: openMSX's NMS 8250 with its mapper at 512 KB, which
# Moonwalker's 236 KB tape needs.
NMS8250_512K := $(EMU_HOME)/share/machines/Philips_NMS_8250_512k.xml
$(NMS8250_512K):
	mkdir -p $(dir $@)
	sed 's|<size>128</size>|<size>512</size>|' $(OPENMSX_SHARE)/machines/Philips_NMS_8250.xml > $@.tmp
	grep -q '<size>512</size>' $@.tmp
	mv $@.tmp $@

# basic/picoverse: a 192 KB memory mapper cartridge, the PicoVerse's mapper.
RAM192K := $(EMU_HOME)/share/extensions/ram192k.xml
$(RAM192K):
	mkdir -p $(dir $@)
	sed 's|<size>512</size>|<size>192</size>|; s|512 kB|192 kB|g; s|512k|192k|g' $(OPENMSX_SHARE)/extensions/ram512k.xml > $@.tmp
	grep -q '<size>192</size>' $@.tmp
	mv $@.tmp $@

test: bin/SNAPCAS.COM bin/SERVICE.BIN $(OUT)/borrow.bin $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(EMU_HOME)/share/systemroms $(NMS8250_512K) $(RAM192K)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) NEXTOR_DIR=$(abspath $(NEXTOR)) CAS_DIR=$(abspath $(CAS_DIR)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  python3 -I tests/run.py

# The run over every shipped game file (docs/PLAN.md, step 9), apart from make
# test because it takes hours.
collection: bin/SNAPCAS.COM bin/SERVICE.BIN $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(EMU_HOME)/share/systemroms $(RAM192K)
	OPENMSX_HOME=$(abspath $(EMU_HOME)) NEXTOR_DIR=$(abspath $(NEXTOR)) CAS_DIR=$(abspath $(CAS_DIR)) DOS_DIR=$(abspath $(DOS_DIR)) \
	  COLLECTION_DIR=$(abspath $(COLLECTION_DIR)) COLLECTION_MACHINES="$(COLLECTION_MACHINES)" \
	  COLLECTION_WORKERS=$(COLLECTION_WORKERS) COLLECTION_FULL=$(COLLECTION_FULL) \
	  python3 -I -m unittest discover -s tests -p test_step9.py -k Collection -v

MACHINE ?= advanced/phc28s
FILES ?= bin/SNAPCAS.COM $(wildcard $(OUT)/try/*.SNP)

try: bin/SNAPCAS.COM $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(EMU_HOME)/share/systemroms
	OPENMSX_HOME=$(abspath $(EMU_HOME)) python3 -I tools/run.py $(MACHINE) --dos $(NEXTOR) $(FILES)

clean:
	rm -rf bin $(OUT)/test

.PHONY: help all test collection try clean
