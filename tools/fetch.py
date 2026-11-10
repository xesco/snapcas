#!/usr/bin/env python3
"""Download a file and check it against its SHA-256.

Usage: fetch.py URL SHA256 OUT [MEMBER...]

Without MEMBER arguments, the download is saved as OUT. With them, the download
is a zip file, and each MEMBER is extracted into the folder OUT. The download is
checked before anything is written, so a changed or broken file never lands in
OUT, and each file is written under a temporary name and then renamed, so a
run that stops leaves no cut file under its name.

Exit status: 0 on success, 1 with a line on standard error for a download that
fails or differs.
"""
import hashlib
import http.client
import io
import os
import sys
import urllib.error
import urllib.request
import zipfile

# Real seconds that the server may take to answer or to send more bytes.
TIMEOUT = 120


def save(path, data):
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__.strip())
    url, sha, out, members = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as reply:
            data = reply.read()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        sys.exit(f"fetch.py: {url}: {getattr(e, 'reason', e)}")
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        sys.exit(f"fetch.py: {url}: SHA-256 is {got}, expected {sha}")
    if not members:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        save(out, data)
        return
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            files = [(name, z.read(name)) for name in members]
    except (zipfile.BadZipFile, KeyError) as e:
        sys.exit(f"fetch.py: {url}: {e}")
    os.makedirs(out, exist_ok=True)
    for name, content in files:
        save(os.path.join(out, name), content)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
