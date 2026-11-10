"""The copy of a machine's images to a card (docs/CLI.md, Sync a card).

The card holds SNAPCAS.COM in BIN/, and the images in SNAPCAS/, in a folder per
first letter, so that a folder never holds too many files for DOS: a game's
image in SNAPCAS/<letter>/<GAME>.SNP, and a compilation's program, or a custom
game, in SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP, with the letter of the
collection's name. A name that starts with a digit has the letter 0-9.
"""
import os

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

# The files of a game that go to the card: its image.
SUFFIXES = (".SNP",)

# The first bytes of an AppleDouble file. macOS keeps a file's extended
# attributes on a FAT card in such a file beside it, named ._ and the file's
# name, and DOS lists it as one more file.
APPLEDOUBLE = b"\x00\x05\x16\x07"


class CardError(Exception):
    """A destination or a set of images that cannot be synced."""


def letter(name):
    return "0-9" if name[0].isdigit() else name[0].upper()


def card_path(key, name):
    """The path on the card of a game's file, from its name below
    images/<machine>/, such as GAUNTLET, SUPERMSX/GOLF or custom/MYGAME, and the
    file's name."""
    parts = key.split("/")
    if len(parts) > 1:
        return os.path.join("SNAPCAS", letter(parts[0]), parts[0].upper(), name)
    return os.path.join("SNAPCAS", letter(name), name)


def card_files(images, snapcas_com):
    """The files to put on the card, as {path on the card: source}: SNAPCAS.COM
    and each game's files below images, the machine's folder of images/."""
    files = {os.path.join("BIN", "SNAPCAS.COM"): snapcas_com}
    for folder, dirs, names in sorted(os.walk(images)):
        dirs.sort()
        key = os.path.relpath(folder, images).replace(os.sep, "/")
        for name in sorted(names):
            if key == "." or not name.upper().endswith(SUFFIXES):
                continue
            path = card_path(key, name.upper())
            if path in files:
                raise CardError(f"{files[path]} and {os.path.join(folder, name)} both go to {path}")
            files[path] = os.path.join(folder, name)
    return files


def check_destination(destination):
    """Stops for a destination that is not a folder, or that is the card's
    SNAPCAS or BIN folder in place of the card's top folder."""
    if not os.path.isdir(destination):
        raise CardError(f"{destination}: no such folder")
    if os.path.basename(os.path.normpath(destination)).upper() in ("SNAPCAS", "BIN"):
        raise CardError(f"{destination}: give the card's top folder, which holds SNAPCAS and BIN")


def read(path):
    with open(path, "rb") as f:
        return f.read()


def remove_sidecar(path):
    """Removes the AppleDouble file that macOS wrote beside the file path, if
    there is one. A file of that name with other bytes stays."""
    sidecar = os.path.join(os.path.dirname(path), "._" + os.path.basename(path))
    try:
        with open(sidecar, "rb") as f:
            if f.read(len(APPLEDOUBLE)) != APPLEDOUBLE:
                return
        os.remove(sidecar)
    except OSError:
        pass


def write(target, data):
    """Writes data as the file target. The bytes go to a temporary file beside
    it, whose name fits a FAT card's 8.3 names, and the OS writes them out
    before the file takes target's name: fsync, and on macOS F_FULLFSYNC, which
    also empties the drive's own buffer. So a card that is full or pulled out
    leaves no cut file under target's name. The AppleDouble file that macOS
    wrote beside either name goes."""
    temp = os.path.splitext(target)[0] + ".$$$"
    try:
        with open(temp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            if hasattr(fcntl, "F_FULLFSYNC"):
                try:
                    fcntl.fcntl(f.fileno(), fcntl.F_FULLFSYNC)
                except OSError:
                    pass  # not every file system has it, and fsync is done
        os.replace(temp, target)
        remove_sidecar(temp)
        remove_sidecar(target)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        remove_sidecar(temp)
        raise


def sync(files, destination, log=print):
    """Copies each file that the destination lacks or holds with other bytes,
    reads each copy back and compares it, and returns the numbers of copied and
    unchanged files. It deletes nothing on the card but the AppleDouble file
    of a copy that it makes."""
    copied = unchanged = 0
    for path, source in files.items():
        data = read(source)
        target = os.path.join(destination, path)
        if os.path.isfile(target) and read(target) == data:
            unchanged += 1
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write(target, data)
        if read(target) != data:
            raise CardError(f"{target}: the copy differs from {source} when read back")
        log(f"copy      {target}, compared ok")
        copied += 1
    return copied, unchanged
