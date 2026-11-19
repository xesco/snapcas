# Supported machines

`snapcas` supports these MSX configurations. Each is an MSX model with its
cartridges. The first column is the name that the commands take.

| Machine | Computer | RAM | Cartridges | Games that work |
|---|---|---|---|---|
| `fsa1-mfrsd` | Panasonic FS-A1 (MSX2) | 64 KB | MegaFlashROM SCC+ SD | 1,544 |
| `hb75p-carnivore2` | Sony HB-75P (MSX1) | 64 KB | Carnivore2 | 1,545 |
| `hb75p-mfrsd` | Sony HB-75P (MSX1) | 64 KB | MegaFlashROM SCC+ SD | 1,544 |
| `hbf700p-ram512k-msxdos2` | Sony HB-F700P (MSX2) | 256 KB | 512 KB RAM, MSX-DOS 2 | 1,544 |
| `nms8245-ram512k-sunriseide` | Philips NMS 8245 (MSX2) | 128 KB | 512 KB RAM, Sunrise IDE | 1,544 |
| `nms8250-carnivore2` | Philips NMS 8250 (MSX2) | 128 KB | Carnivore2 | 1,545 |
| `phc28s-ram64k-carnivore2` | Sanyo PHC-28S (MSX1) | 16 KB | 64 KB RAM, Carnivore2 | 1,545 |
| `sx2` | SX-2 (MSX2+, FPGA) | 2048 KB | None | 1,545 |
| `sx2-extramapper-mcp` | SX-2 (MSX2+, FPGA), Extra-Mapper on, SX2RES | 6144 KB | None | 1,167 |
| `sx2-noexp0` | SX-2 (MSX2+, FPGA), slot 0 not expanded | 2048 KB | None | 1,545 |
| `vg8020-carnivore2` | Philips VG-8020 (MSX1) | 64 KB | Carnivore2 | 1,545 |
| `vg8020-sdmapper` | Philips VG-8020 (MSX1) | 64 KB | SD Mapper v1 | 1,544 |
| `xp800-sdmapper` | Gradiente Expert XP-800 (MSX1) | 64 KB | SD Mapper v1 | 1,544 |

The three SX-2 machines differ in slot 0 and in the Extra-Mapper. All three need
this setting in `OCMINFO`'s F4 screen: CPU clock Standard, cartridge slots 1 and 2
External, RAM mapper 2048KB, internal MegaSD ON.

- `sx2` is the SX-2 as it starts: slot 0 expanded, with the main ROM in 0-0,
  MSX-MUSIC in 0-2 and the Wi-Fi's BIOS in 0-3, and the Extra-Mapper off, the
  default. A cold reset, with the RESET button or the power, turns the Extra-Mapper
  off. In BASIC, `PRINT HEX$(PEEK(&HFCC1))` prints 80.
- `sx2-extramapper-mcp` is the SX-2 as the sx2-mcp project's resident program
  SX2RES, 2.8 or later, leaves it. SX2RES turns the Extra-Mapper of 4096 KB on in
  slot 0-1, so the BIOS and DOS keep their RAM there, and keeps itself in the
  2048 KB of slot 3-0. In BASIC, `PRINT HEX$(PEEK(&HF341))` prints 84. Each image
  calls SX2RES at each interrupt, from T0, from H.KEYI or from a wrapper for the
  game's own routine, so SX2RES answers while the game runs. A game that installs a
  routine of its own later ends the calls, unless its game file has a `rescall`
  line, as Gauntlet's has for its main game. Without SX2RES the game runs the same,
  without the calls.
- `sx2-noexp0` is the SX-2 with slot 0 not expanded. For that, type
  `SETSMART -F9FD` at the DOS prompt. `F9` reserves the setting and `FD` makes the
  warm reset that applies it, so the SX-2 restarts by itself. The RESET button does
  not apply it. The `-` keeps both codes out of the flash, so the setting lasts
  until the power goes off. In BASIC, `PRINT HEX$(PEEK(&HFCC1))` then prints a
  value below 80. The setting turns off the internal MSX-MUSIC and the Wi-Fi, whose
  BIOS is in slot 0-3, until the power goes off. Do not store it in the Smart
  Profile with `SETSMART #...F9`: the IPL applies the profile at each reset, and the
  Wi-Fi stays off. `SETSMART #00` and a power cycle clear such a profile.

`make firmware` needs the SX-2's `OCM-BIOS.DAT` from its SD card
([CLI.md](CLI.md)).

`RELICS` is the only game that does not work on the machines with 1,544 games,
because it needs more memory than they have.

Your MSX is not in the list? [Open an issue](https://github.com/xesco/snapcas/issues)
and tell me your MSX model, its RAM, and what is in each cartridge slot, for example
"Toshiba HX-10, 64 KB, Carnivore2 in slot 1". I will add support for your machine and
patch all the needed games for you.
