"""The download of a game's tape files from the links of its url line
(docs/CLI.md, Download).

Each side's zip holds the side's CAS or TSX file under a name of its own, and a
compilation's zip holds many, so the file is the zip's member whose SHA-1 is the
game file's for that side. It is saved in the tapes folder under the game file's
name for the side, where the tools look for it.
"""
import hashlib
import io
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# Real seconds that one download may take.
TIMEOUT = 120


class DownloadError(Exception):
    """A tape file that cannot be downloaded."""


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def fetch(url):
    """The bytes of the file at url."""
    request = urllib.request.Request(url, headers={"User-Agent": "snapcas"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            return reply.read()
    except (urllib.error.URLError, OSError) as e:
        raise DownloadError(f"{url}: {getattr(e, 'reason', e)}")


def member(data, want, url):
    """The name and the bytes of the zip's member whose SHA-1 is want."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                content = z.read(name)
                if sha1(content) == want:
                    return name, content
    except zipfile.BadZipFile:
        raise DownloadError(f"{url}: not a zip file")
    raise DownloadError(f"{url}: the zip holds no file whose SHA-1 is {want}")


def shown(path):
    """The path to print: relative to the current folder when the file is below
    it, else whole."""
    try:
        relative = os.path.relpath(path)
    except ValueError:
        return path
    return path if relative.startswith("..") else relative


def say(text):
    """Prints a line at once, before the output of the tools that follow."""
    print(text, flush=True)


def tapes(game, folder, log=say):
    """Downloads each side of the game whose file is not in the folder, and
    checks the SHA-1 of each side that is."""
    sides = [game.tape] + ([game.side2] if game.side2 else [])
    for i, name in enumerate(sides):
        path = os.path.join(folder, name)
        want = game.sha1[i] if i < len(game.sha1) else None
        if os.path.exists(path):
            with open(path, "rb") as f:
                got = sha1(f.read())
            if want and got != want:
                raise DownloadError(f"{path} has the SHA-1 {got}, and the game file's is {want}. Move it "
                                    "away, and snapcas.py snap downloads the game file's tape")
            continue
        if not game.urls or not want:
            raise DownloadError(f"{os.path.join(game.folder, 'game.txt')} has no url line. Put the file "
                                f"whose SHA-1 is {want} in {shown(folder)} as {name}" if want else
                                f"{os.path.join(game.folder, 'game.txt')} has no url and sha1 lines. Put the "
                                f"tape file in {shown(folder)} as {name}")
        url = game.urls[i]
        log(f"download  {urllib.parse.unquote(url.rsplit('/', 1)[1])} from {url.split('/')[2]}")
        source, content = member(fetch(url), want, url)
        os.makedirs(folder, exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(content)
        os.replace(path + ".tmp", path)
        log(f"copy      {source} to {shown(path)}, sha1 ok")
