# Built Images

This directory holds finished `.SNP` images built by `./snapcas.py snap`. Git ignores everything here except this file.

- **Layout:** `images/<machine>/<game>/<GAME>.SNP` (custom games go under `images/<machine>/custom/<GAME>/`).
- **Sync to MSX:** Run `./snapcas.py sync <machine> <destination>` to copy `bin/SNAPCAS.COM` and all images for that machine.
- **Test in `openMSX`:** Run `./snapcas.py try <game> <machine>`.
