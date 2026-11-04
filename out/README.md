# Work files

The tools write here what they make along the way:

| Name | Holds |
|---|---|
| `work/` | Each game's snapshot, its image until `snap` moves it to `images/`, its check and the build's reports |
| `games/` | The results of `make games`, one file per machine |
| `test/` | The output of `make test` |
| `cache/` | The tools that the Makefile downloads and builds, and the test home of `openMSX` |
| `service.sym`, `service-fb.bin`, `service-fc.bin`, `borrow.bin`, `borrow.sym` | The build's files beside `bin/`, which the tests read |

Nothing here needs your attention. Git ignores everything here except this file.
