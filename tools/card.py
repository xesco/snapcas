"""The copy of a machine's images to a card (docs/CLI.md, Sync a card).

The card holds SNAPCAS.COM in BIN/, and the images in SNAPCAS/, in a folder per
first letter, so that a folder never holds too many files for DOS: a game's
image in SNAPCAS/<letter>/<GAME>.SNP, and a compilation's program, or a custom
game, in SNAPCAS/<letter>/<COLLECTION>/<GAME>.SNP, with the letter of the
collection's name. A name that starts with a digit has the letter 0-9.
"""
import os

# The files of a game that go to the card: its image.
SUFFIXES = (".SNP",)


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


def sync(files, destination, log=print):
    """Copies each file that the destination lacks or holds with other bytes,
    reads each copy back and compares it, and returns the numbers of copied and
    unchanged files. It deletes nothing on the card."""
    copied = unchanged = 0
    for path, source in files.items():
        data = read(source)
        target = os.path.join(destination, path)
        if os.path.isfile(target) and read(target) == data:
            unchanged += 1
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
        if read(target) != data:
            raise CardError(f"{target}: the copy differs from {source} when read back")
        log(f"copy      {target}, compared ok")
        copied += 1
    return copied, unchanged
