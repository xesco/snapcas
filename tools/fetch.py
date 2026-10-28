#!/usr/bin/env python3
"""Download a file and check it against its SHA-256.

Usage: fetch.py URL SHA256 OUT [MEMBER...]

Without MEMBER arguments, the download is saved as OUT. With them, the download
is a zip file, and each MEMBER is extracted into the folder OUT. The download is
checked before anything is written, so a changed or broken file never lands in
OUT.
"""
import hashlib
import io
import os
import sys
import urllib.request
import zipfile


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__.strip())
    url, sha, out, members = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    with urllib.request.urlopen(url) as reply:
        data = reply.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        sys.exit(f"fetch.py: {url}: SHA-256 is {got}, expected {sha}")
    if not members:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        return
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in members:
            with open(os.path.join(out, name), "wb") as f:
                f.write(z.read(name))


if __name__ == "__main__":
    main()
