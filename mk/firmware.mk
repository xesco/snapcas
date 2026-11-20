# Cartridge firmware and generated openMSX machine XMLs in out/cache/openmsx-home/.

SYSTEMROMS_LINK := $(EMU_HOME)/share/systemroms/user
$(SYSTEMROMS_LINK):
	if [ -L $(EMU_HOME)/share/systemroms ]; then rm $(EMU_HOME)/share/systemroms; fi
	mkdir -p $(dir $@)
	ln -sfn $(SYSTEMROMS) $@

# SD Mapper v1 Nextor firmware (driver 1.0.7).
SDMAPPER_ROM := $(EMU_HOME)/share/systemroms/snapcas/SDMAPPER.ROM
$(SDMAPPER_ROM): | $(SYSTEMROMS_LINK)
	python3 -I tools/fetch.py https://github.com/fbelavenuto/msxsdmapper/releases/download/v1.0.7/SDMAPPER.ROM 4371c4094756672f78b295dbfb753cb6a3011e7fdb11348249be1bc36fbd061b $@

# Nextor-only MegaFlashROM SCC+ SD flash (for fsa1-mfrsd).
MFR_NEXTOR     := $(DL)/Nextor-2.1.4.MegaFlashSDSCC.1-slot.ROM
MFR_FLASH      := $(EMU_HOME)/share/systemroms/snapcas/MFRSD-Nextor-2.1.4.ROM
MFR_FLASH_SHA1 := ea48fb3d4f73a9046bfe82a3c94d738b6a903b4e
MFR_NEXTOR_EXT := $(EMU_HOME)/share/extensions/MegaFlashROM_SCC+_SD_Nextor.xml

$(MFR_NEXTOR):
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.4/Nextor-2.1.4.MegaFlashSDSCC.1-slot.ROM 5e1ab82af74b84e46636a14c592ac9d97a1515feb1104fb38d46152b16e57cb1 $@

$(MFR_FLASH): $(MFR_NEXTOR) tools/firmware.py | $(SYSTEMROMS_LINK)
	python3 -I tools/firmware.py mfr-flash $< $(MFR_FLASH_SHA1) $@

$(MFR_NEXTOR_EXT): $(MFR_FLASH)
	mkdir -p $(dir $@)
	sed 's|<sha1>1621f623b834dc57cb2983f30b36bcc3ac56cafd</sha1>|<sha1>$(MFR_FLASH_SHA1)</sha1>|; s|<sramname>megaflashromsccplussd.sram</sramname>|<sramname>megaflashromsccplussd-nextor.sram</sramname>|; s|<name>MegaFlashROM SCC+ SD</name>|<name>MegaFlashROM SCC+ SD with Nextor only</name>|' $(OPENMSX_SHARE)/extensions/MegaFlashROM_SCC+_SD.xml > $@.tmp
	grep -q '$(MFR_FLASH_SHA1)' $@.tmp
	grep -q 'megaflashromsccplussd-nextor.sram' $@.tmp
	mv $@.tmp $@

FIRMWARE := $(SYSTEMROMS_LINK) $(SDMAPPER_ROM) $(MFR_NEXTOR_EXT)

# Test-only NMS 8250 mapper variants (512 KB and 4 MB).
NMS8250_512K := $(EMU_HOME)/share/machines/Philips_NMS_8250_512k.xml
$(NMS8250_512K):
	mkdir -p $(dir $@)
	sed 's|<size>128</size>|<size>512</size>|' $(OPENMSX_SHARE)/machines/Philips_NMS_8250.xml > $@.tmp
	grep -q '<size>512</size>' $@.tmp
	mv $@.tmp $@

NMS8250_4M := $(EMU_HOME)/share/machines/Philips_NMS_8250_4m.xml
$(NMS8250_4M):
	mkdir -p $(dir $@)
	sed 's|<size>128</size>|<size>4096</size>|' $(OPENMSX_SHARE)/machines/Philips_NMS_8250.xml > $@.tmp
	grep -q '<size>4096</size>' $@.tmp
	mv $@.tmp $@

# HB-F700P with unexpanded slot 0 (keeps slot 3's two subslots).
HBF700P_NOEXP0 := $(EMU_HOME)/share/machines/Sony_HB-F700P_noexp0.xml
$(HBF700P_NOEXP0):
	mkdir -p $(dir $@)
	sed -e '/<primary slot="0">/,/<\/primary>/{' -e '/<secondary slot="0">/d' -e '/<\/secondary>/d' -e '}' $(OPENMSX_SHARE)/machines/Sony_HB-F700P.xml > $@.tmp
	test "$$(grep -c '<secondary slot' $@.tmp)" = 2
	test "$$(grep -c '</secondary>' $@.tmp)" = 2
	mv $@.tmp $@

# SX-2 MSX2+ models built from the user's OCM-BIOS.DAT and FS-A1WSX's XML.
SX2_BIOS        ?= $(SYSTEMROMS)/OCM-BIOS.DAT
SX2_ROMS        := $(EMU_HOME)/share/systemroms/snapcas/sx2
SX2             := $(EMU_HOME)/share/machines/OCM_SX-2.xml
SX2_NOEXP0      := $(EMU_HOME)/share/machines/OCM_SX-2_noexp0.xml
SX2_EXTRAMAPPER := $(EMU_HOME)/share/machines/OCM_SX-2_extramapper.xml
SX2_NORAM30     := $(EMU_HOME)/share/machines/OCM_SX-2_extramapper_noram30.xml
SX2_BASE_XML    := $(OPENMSX_SHARE)/machines/Panasonic_FS-A1WSX.xml $(OPENMSX_SHARE)/extensions/SunriseIDE_Nextor.xml

$(SX2): $(SX2_BIOS) tools/firmware.py
	python3 -I tools/firmware.py sx2 $(SX2_BASE_XML) $< $(SX2_ROMS) expanded $@

$(SX2_EXTRAMAPPER): $(SX2_BIOS) tools/firmware.py
	python3 -I tools/firmware.py sx2 $(SX2_BASE_XML) $< $(SX2_ROMS) extramapper $@

$(SX2_NORAM30): $(SX2_BIOS) tools/firmware.py
	python3 -I tools/firmware.py sx2 $(SX2_BASE_XML) $< $(SX2_ROMS) extramapper-noram30 $@

$(SX2_NOEXP0): $(SX2_BIOS) tools/firmware.py
	python3 -I tools/firmware.py sx2 $(SX2_BASE_XML) $< $(SX2_ROMS) noexp0 $@

SUNRISE_NEXTOR := $(EMU_HOME)/share/systemroms/snapcas/Nextor-2.1.1.SunriseIDE.ROM
$(SUNRISE_NEXTOR): | $(SYSTEMROMS_LINK)
	python3 -I tools/fetch.py https://github.com/Konamiman/Nextor/releases/download/v2.1.1/Nextor-2.1.1.SunriseIDE.ROM 205af7f7893aa0328be23f66b3afe3132c7dee59cf4bbc493408475a201c7ad6 $@

SX2_FIRMWARE := $(if $(wildcard $(SX2_BIOS)),$(SX2) $(SX2_NOEXP0) $(SX2_EXTRAMAPPER) $(SX2_NORAM30) $(SUNRISE_NEXTOR))
SX2_MISSING  := $(if $(SX2_FIRMWARE),,SX-2 machines need OCM-BIOS.DAT at $(SX2_BIOS) or SX2_BIOS=<path>)

firmware: $(FIRMWARE) $(HBF700P_NOEXP0) $(SX2_FIRMWARE)
	$(if $(SX2_MISSING),@echo "$(SX2_MISSING)" >&2)
