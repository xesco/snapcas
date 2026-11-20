# Supported Machines

This page lists the 13 MSX configurations shipped with `snapcas`, explains the three SX-2 setups, and shows how to request or add support for another MSX. Each machine represents one exact computer model together with its cartridges in slot order.

## Supported machines

Pass a machine name from the first column to `./snapcas.py snap`, `try`, or `sync`. Machines marked `*` require a one-time `make firmware` step ([CLI.md](CLI.md#firmware-and-roms)).

| Machine | Model | RAM | Cartridges / DOS | Capture variants | Working games |
|---|---|---|---|---|---|
| `fsa1-mfrsd` * | Panasonic FS-A1 (MSX2) | 64 KB | MegaFlashROM SCC+ SD (Nextor) | `fsa1` | 1,543 |
| `hb75p-carnivore2` | Sony HB-75P (MSX1) | 64 KB | Carnivore2 (Nextor) | `hb75p` | 1,544 |
| `hb75p-mfrsd` | Sony HB-75P (MSX1) | 64 KB | MegaFlashROM SCC+ SD (stock flash) | `hb75p` | 1,543 |
| `hbf700p-ram512k-msxdos2` * | Sony HB-F700P (MSX2) | 256 KB | 512 KB RAM, MSX-DOS 2 | `hbf700p-msxdos2`, `hbf700p-noexp0-ram512k-msxdos2`, `hbf700p-noexp0-msxdos2` | 1,543 |
| `nms8245-ram512k-sunriseide` | Philips NMS 8245 (MSX2) | 128 KB | 512 KB RAM, Sunrise IDE (Nextor) | `nms8245` | 1,543 |
| `nms8250-carnivore2` | Philips NMS 8250 (MSX2) | 128 KB | Carnivore2 (Nextor) | `nms8250` | 1,544 |
| `phc28s-ram64k-carnivore2` | Sanyo PHC-28S (MSX1) | 16 KB | 64 KB RAM, Carnivore2 (Nextor) | `phc28s-ram64k`, `phc28s-empty-carnivore2` | 1,544 |
| `sx2` * | SX-2 (MSX2+, FPGA) | 2048 KB | None (internal MegaSD, Nextor) | `sx2-noexp0` | 1,544 |
| `sx2-extramapper-mcp` * | SX-2 (MSX2+, FPGA), Extra-Mapper + SX2RES | 6144 KB | None (internal MegaSD, Nextor) | `sx2-extramapper-noram30` | 1,544 |
| `sx2-noexp0` * | SX-2 (MSX2+, FPGA), slot 0 unexpanded | 2048 KB | None (internal MegaSD, Nextor; inherits `sx2`) | — | 1,544 |
| `vg8020-carnivore2` | Philips VG-8020 (MSX1) | 64 KB | Carnivore2 (Nextor) | `vg8020` | 1,544 |
| `vg8020-sdmapper` * | Philips VG-8020 (MSX1) | 64 KB | SD Mapper v1 (Nextor) | `vg8020` | 1,543 |
| `xp800-sdmapper` * | Gradiente Expert XP-800 (MSX1) | 64 KB | SD Mapper v1 (Nextor) | `xp800` | 1,543 |

On 512 KB mapper setups (1,543 working games), only `RELICS` does not fit—it requires 33 free mapper segments.

## SX-2 configurations

All three SX-2 targets assume these `OCMINFO` (`F4`) settings: **CPU clock Standard**, **cartridge slots 1 and 2 External**, **RAM mapper 2048KB**, and **internal MegaSD ON**. Building SX-2 images requires `OCM-BIOS.DAT` from your SX-2 SD card and a one-time `make firmware` run.

- **`sx2`** — Default boot configuration: slot 0 expanded (main ROM in 0-0, MSX-MUSIC in 0-2, Wi-Fi BIOS in 0-3) and Extra-Mapper off. A power cycle or RESET button restores this state. In BASIC, `PRINT HEX$(PEEK(&HFCC1))` prints `80`.
- **`sx2-extramapper-mcp`** — For machines running `sx2-mcp`'s resident **SX2RES 2.8+**, which turns on the 4096 KB Extra-Mapper in slot 0-1 and stays resident in slot 3-0. In BASIC, `PRINT HEX$(PEEK(&HF341))` prints `84`. Images call SX2RES during interrupts so it remains reachable during play, and still run normally if SX2RES is not loaded.
- **`sx2-noexp0`** — Runs the SX-2 with slot 0 unexpanded so loaders that assume an unexpanded slot 0 work unmodified. At the DOS prompt, run:

  ```text
  SETSMART -F9FD
  ```

  `F9` requests unexpanded slot 0 and `FD` warm-resets to apply it (the hardware RESET button does not apply it). The leading `-` keeps the change temporary until power-off; internal MSX-MUSIC and Wi-Fi stay off until then. In BASIC, `PRINT HEX$(PEEK(&HFCC1))` prints a value below `80`.

  > [!WARNING]
  > Never save `F9` to flash with `SETSMART #...F9`, or Wi-Fi will stay disabled after every reboot. To recover if you saved it, run `SETSMART #00` and power-cycle the SX-2.

## Adding a machine

Because cartridge order and RAM slot placement affect how cassette loaders behave, adding or removing even one cartridge requires a distinct machine file.

- **Request a machine:** [Open an issue](https://github.com/xesco/snapcas/issues) listing your MSX model, internal RAM, and what is in each cartridge slot (e.g., *"Toshiba HX-10, 64 KB, Carnivore2 in slot 1"*).
- **Add it yourself (or with an AI agent):** Follow the machine-addition steps in [AGENTS.md](../AGENTS.md) and the machine-file schema in [FILES.md](FILES.md#machine-file).
