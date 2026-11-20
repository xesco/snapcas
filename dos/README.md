# DOS System Files

This directory holds the DOS system files that `snap --check`, `try`, and `make test` boot inside `openMSX`. Git ignores everything here except this file.

| Folder | Required files | Source |
|---|---|---|
| `nextor/` | `NEXTOR.SYS`, `COMMAND2.COM` | Downloaded automatically by `snapcas.py` and `make` (Nextor 2.1.0). |
| `msxdos2/` | `MSXDOS2.SYS`, `COMMAND2.COM` | Supply your own copy (`snapcas` cannot redistribute MSX-DOS). |
| `msxdos1/` | `MSXDOS.SYS`, `COMMAND.COM` | Supply your own copy (`snapcas` cannot redistribute MSX-DOS). |

Nextor-based machines only need `nextor/`. Override this directory with `--dos <dir>` or the `DOS_DIR` environment variable ([CLI.md](../docs/CLI.md#environment-variables)).
