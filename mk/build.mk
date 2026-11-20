# Z80 binaries (bin/SNAPCAS.COM, bin/SERVICE.BIN), symbols, test games, and sjasmplus.

SJASMPLUS_VERSION := 1.24.0
SJASMPLUS_URL     := https://github.com/z00m128/sjasmplus/releases/download/v$(SJASMPLUS_VERSION)/sjasmplus-$(SJASMPLUS_VERSION)-src.tar.xz
SJASMPLUS_SHA256  := 0b5013f07e8d8505f9e296529655668b6fdf0268625c19e883b0fff484e209f1
SJASMPLUS         := $(CACHE)/tools/sjasmplus

SNAPCAS_SRC := src/snapcas.asm src/plan.inc src/segments.inc src/records.inc src/messages.inc src/service.inc src/slots.inc src/worker.inc src/version.inc
SERVICE_SRC := src/service.asm src/service.inc src/tape.inc
SYMBOLS     := $(OUT)/snapcas.sym $(OUT)/service.sym

TEST_GAME_NAMES := borrow contract guard subrom
TEST_GAMES      := $(foreach g,$(TEST_GAME_NAMES),$(OUT)/$(g).bin $(OUT)/$(g).sym)

all: bin/SNAPCAS.COM bin/SERVICE.BIN $(SYMBOLS)

bin/SNAPCAS.COM: $(SNAPCAS_SRC) $(SJASMPLUS)
	mkdir -p bin
	$(SJASMPLUS) --nologo --raw=$@ $<

# Symbol files are built separately from bin/ so a fresh clone gets symbols without dirtying git.
$(OUT)/snapcas.sym: $(SNAPCAS_SRC) $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ $<

# Assemble at FCE1h, FBE1h (page 3 relocs), and +0111h (code-block relocs) for tools/relocs.py.
bin/SERVICE.BIN: $(SERVICE_SRC) tools/relocs.py $(SJASMPLUS)
	mkdir -p bin $(OUT)
	$(SJASMPLUS) --nologo --raw=$(OUT)/service-fc.bin --exp=$(OUT)/service-fc.exp $<
	$(SJASMPLUS) --nologo -DP3_PAGE=0FBh --raw=$(OUT)/service-fb.bin --exp=$(OUT)/service-fb.exp $<
	$(SJASMPLUS) --nologo -DCODE_MOVED=0FE0Ch --raw=$(OUT)/service-cm.bin --exp=$(OUT)/service-cm.exp $<
	python3 -I tools/relocs.py $(OUT)/service-fc.bin $(OUT)/service-fc.exp $(OUT)/service-fb.bin $(OUT)/service-fb.exp \
	  $(OUT)/service-cm.bin $(OUT)/service-cm.exp $@

$(OUT)/service.sym: $(SERVICE_SRC) $(SJASMPLUS)
	mkdir -p $(OUT)
	$(SJASMPLUS) --nologo --sym=$@ --exp=$(OUT)/service.exp $<

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
	python3 -I tools/fetch.py $(SJASMPLUS_URL) $(SJASMPLUS_SHA256) $@
