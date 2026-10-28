# snapcas build and tests (docs/PLAN.md).
#
#   make        build bin/SNAPCAS.COM
#   make test   run the tests in openMSX
#
# The tests read the CAS files from CAS_DIR, by default tapes/, a folder that git
# ignores because snapcas cannot ship CAS files. The tests that need them are
# skipped when the folder does not exist.
#
# The Makefile downloads its tools into out/, each pinned by version and SHA-256:
# the sjasmplus assembler's source, which it builds, and Nextor's NEXTOR.SYS and
# COMMAND2.COM for the test disks. The tests run openMSX 22.0 from the path, in
# a home of their own, out/openmsx-home, with a link to the system ROMs, so that
# they leave the user's openMSX settings alone.

SJASMPLUS_VERSION := 1.24.0
SYSTEMROMS ?= $(HOME)/.openMSX/share/systemroms
CAS_DIR ?= tapes

OUT       := out
DL        := $(OUT)/dl
SJASMPLUS := $(OUT)/tools/sjasmplus
NEXTOR    := $(DL)/nextor
EMU_HOME  := $(OUT)/openmsx-home

all: bin/SNAPCAS.COM

bin/SNAPCAS.COM: src/snapcas.asm $(SJASMPLUS)
	mkdir -p bin
	$(SJASMPLUS) --nologo --raw=$@ $<

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

test: bin/SNAPCAS.COM $(NEXTOR)/NEXTOR.SYS $(NEXTOR)/COMMAND2.COM $(EMU_HOME)/share/systemroms
	OPENMSX_HOME=$(abspath $(EMU_HOME)) NEXTOR_DIR=$(abspath $(NEXTOR)) CAS_DIR=$(abspath $(CAS_DIR)) \
	  python3 -I -m unittest discover -s tests -v

clean:
	rm -rf bin $(OUT)/test

.PHONY: all test clean
