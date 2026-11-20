# Downloaded Tapes

This directory caches `.CAS` files downloaded on demand from [File-Hunter](https://download.file-hunter.com) by `./snapcas.py snap`. Git ignores everything here except this file.

- Each tape is downloaded once and verified against the SHA-1 in its `game.txt`.
- Existing files with matching SHA-1 are reused automatically; a mismatch aborts without overwriting your file.
- `make games` reads only from this cache and never accesses the network.
- Override this path with the `SNAPCAS_DOWNLOADS` environment variable.
