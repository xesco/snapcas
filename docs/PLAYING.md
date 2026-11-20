# Playing on the MSX

This guide is for MSX users running `.SNP` images on real hardware. It covers starting games with `SNAPCAS.COM`, controlling multi-load tapes from the keyboard, manual `/M` mode, and troubleshooting hardware issues.

## Running an image

You need an MSX with a memory mapper and a disk or SD card interface running Nextor, MSX-DOS 2, or MSX-DOS 1.

Copy `bin/SNAPCAS.COM` and your `.SNP` images to your disk. If you used `./snapcas.py sync`, `SNAPCAS.COM` is in `\BIN` and images sit in alphabetical folders (`\SNAPCAS\A`–`Z`, `\SNAPCAS\0-9`, or `\SNAPCAS\CUSTOM`):

```text
CD \SNAPCAS\G
\BIN\SNAPCAS GAUNTLET
```

Under Nextor and MSX-DOS 2, you can pass the full path directly:

```text
\BIN\SNAPCAS \SNAPCAS\G\GAUNTLET
```

Use `\` (shown as `¥` on MSX keyboards) for folders—DOS interprets `/` as an option switch. MSX-DOS 1 has no subdirectories, so place `SNAPCAS.COM` and `.SNP` files in the root directory and run `SNAPCAS GAUNTLET`.

## Tape keys

Multi-load games embed the rest of their cassette inside the `.SNP` file. By default, `SNAPCAS.COM` runs the virtual tape automatically: it starts and stops the motor on demand and flips to Side B when Side A finishes.

When a game asks you to rewind or flip the cassette, hold one of these keys as the game starts reading:

| Key | Action | Screen flash |
|---|---|---|
| `GRAPH` | Rewind to the start of Side A | Green |
| `CODE` | Jump to the start of Side B | Red |
| `CTRL+STOP` | Stop the tape | — |

## Manual tape mode

Add `/M` to control the virtual cassette manually, like a physical tape deck:

```text
SNAPCAS GAUNTLET /M
```

In manual mode, the tape pauses whenever the game stops the motor or finishes a side. On the next tape read, `SNAPCAS` waits for a keypress:

| Key | Action | Screen flash |
|---|---|---|
| `RETURN` | Resume playing (advances to Side B at the end of Side A) | Yellow |
| `GRAPH` | Rewind to the start of Side A and play | Green |
| `CODE` | Jump to the start of Side B and play | Red |
| `CTRL+STOP` | Stop the tape | — |

If a game prompts *"rewind the tape and press a key"*, press the game's key first, then press `GRAPH` or `CODE` to start playback. A few images cannot use manual mode; for those, `SNAPCAS` prints a short notice and stays in automatic mode.

## Troubleshooting

If an image passed `--check` in `openMSX` but fails on your real MSX, check the table below:

| What you see | Cause | What to do |
|---|---|---|
| `made for another machine: its ROMs differ` | Image was built for a different MSX model or BIOS ROM. | Rebuild using the machine matching your exact model and ROMs. |
| `slot X page Y is not RAM` or `slot 0 is not expanded as at the capture` | Cartridge slot order or SX-2 slot-0 setting differs from the image's target machine. | Match your exact cartridge slots (for SX-2, see [SX-2 configurations](MACHINES.md#sx-2-configurations)). |
| `needs N free mapper segments, and DOS has M` | The game needs more free mapper RAM than your hardware has. | This game cannot fit in your current mapper; a larger mapper is required. |
| `made for another version of SNAPCAS.COM` | `SNAPCAS.COM` on your card is older than the `.SNP` image. | Run `./snapcas.py sync` or copy the current `bin/SNAPCAS.COM` to your card. |
| Game waits indefinitely during a level load | Game expects a rewind, side flip, or manual tape start. | Use the tape keys above or launch with `/M`. |
| Game hangs, corrupts graphics, or reboots | Hardware difference or gameplay path not exercised by the 60-second check. | Note what appears on screen and what you pressed, and use the on-MSX debugging workflow in [AGENTS.md](../AGENTS.md). |
