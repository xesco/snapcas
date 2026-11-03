# Downloaded tapes

`snapcas.py snap` downloads each game's tape files from File-Hunter into this
folder, once, and checks each one against its game file's SHA-1. `make games` reads
the tapes from here and never downloads any. Git ignores everything here except this
file.
