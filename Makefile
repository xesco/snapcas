# snapcas build, firmware, and test entry point (see docs/BUILD.md).

SYSTEMROMS    ?= $(HOME)/.openMSX/share/systemroms
OPENMSX       ?= openmsx
OPENMSX_BIN   := $(dir $(realpath $(shell command -v $(OPENMSX))))
OPENMSX_SHARE ?= $(firstword $(wildcard $(OPENMSX_BIN)../openMSX.app/Contents/Resources/share \
                   $(OPENMSX_BIN)../Resources/share /usr/share/openmsx /usr/local/share/openmsx))
DOS_DIR       ?= dos

OUT      := out
CACHE    := $(OUT)/cache
DL       := $(CACHE)/dl
EMU_HOME := $(CACHE)/openmsx-home

help:
	@echo "make all       build bin/SNAPCAS.COM and bin/SERVICE.BIN"
	@echo "make firmware  download firmware and build openMSX machine XMLs"
	@echo "make unit      run pure Python unit tests (no openMSX)"
	@echo "make test      run full unit + openMSX test suite"
	@echo "make games     build and check all games for MACHINE="
	@echo "make clean     remove intermediate build and test files in out/"

include mk/build.mk
include mk/firmware.mk
include mk/test.mk

# Keep bin/ (tracked in git) and out/cache/.
clean:
	rm -rf $(OUT)/test $(SYMBOLS) $(OUT)/service-fc.bin $(OUT)/service-fb.bin $(OUT)/service-cm.bin \
	  $(OUT)/service-fc.exp $(OUT)/service-fb.exp $(OUT)/service-cm.exp $(OUT)/service.exp $(TEST_GAMES)

.PHONY: help all unit test games firmware clean
.DELETE_ON_ERROR:
