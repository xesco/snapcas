# Supported machines

`snapcas` supports these MSX configurations. Each is an MSX model with its
cartridges. The first column is the name that the commands take.

| Machine | Computer | RAM | Cartridges | Games that work |
|---|---|---|---|---|
| `fsa1-mfrsd` | Panasonic FS-A1 (MSX2) | 64 KB | MegaFlashROM SCC+ SD | 1,544 |
| `hb75p-carnivore2` | Sony HB-75P (MSX1) | 64 KB | Carnivore2 | pending |
| `hb75p-mfrsd` | Sony HB-75P (MSX1) | 64 KB | MegaFlashROM SCC+ SD | 1,544 |
| `hbf700p-ram512k-msxdos2` | Sony HB-F700P (MSX2) | 256 KB | 512 KB RAM, MSX-DOS 2 | pending |
| `nms8245-ram512k-sunriseide` | Philips NMS 8245 (MSX2) | 128 KB | 512 KB RAM, Sunrise IDE | 1,544 |
| `nms8250-carnivore2` | Philips NMS 8250 (MSX2) | 128 KB | Carnivore2 | pending |
| `phc28s-ram64k-carnivore2` | Sanyo PHC-28S (MSX1) | 16 KB | 64 KB RAM, Carnivore2 | 1,545 |
| `vg8020-carnivore2` | Philips VG-8020 (MSX1) | 64 KB | Carnivore2 | 1,545 |
| `vg8020-sdmapper` | Philips VG-8020 (MSX1) | 64 KB | SD Mapper v1 | 1,544 |
| `xp800-sdmapper` | Gradiente Expert XP-800 (MSX1) | 64 KB | SD Mapper v1 | 1,544 |

Of the 1,545 games, `RELICS` needs more memory than the machines with 1,544 have.

Your MSX is not in the list? [Open an issue](https://github.com/xesco/snapcas/issues)
and tell me your MSX model, its RAM, and what is in each cartridge slot, for example
"Toshiba HX-10, 64 KB, Carnivore2 in slot 1". I will add support for your machine and
patch all the needed games for you.
