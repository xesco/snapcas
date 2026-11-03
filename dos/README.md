# DOS system files

The checks boot DOS from a disk, so they need DOS's system files. This folder holds
one folder per DOS:

| Folder | Files | From |
|---|---|---|
| `nextor/` | `NEXTOR.SYS`, `COMMAND2.COM` | The Makefile downloads them |
| `msxdos2/` | `MSXDOS2.SYS`, `COMMAND2.COM` | Your own copy, which `snapcas` cannot ship |
| `msxdos1/` | `MSXDOS.SYS`, `COMMAND.COM` | Your own copy, which `snapcas` cannot ship |

A machine under Nextor needs only `nextor/`. Git ignores everything here except this
file.
