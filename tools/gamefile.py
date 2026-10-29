"""Game files (docs/DESIGN.md, Game file).

A game file holds one setting per line: a key, a space and a value. A line that
starts with # is a comment, and blank lines are ignored.
"""
import os
import re
import shlex

from msx import KEYS


class GameFileError(Exception):
    """A game file that cannot be read."""


class Game:
    def __init__(self, folder):
        self.folder = folder
        self.cas = None
        self.side2 = None
        self.sha1 = []
        self.name = default_name(os.path.basename(os.path.normpath(folder)))
        self.keys = []        # [(time, kind, value)], kind "key" or "text"
        self.continue_key = None
        self.snapshot_at = None
        self.service_no = False  # service no: the game never reads the rest
        self.capture = None      # the machine file for the capture, if not the user's
        self.rom_keep = False    # rom keep: page 0 keeps the ROM, and T0 does not replace it
        self.patches = []     # [Patch]


class Patch:
    """A patch line: its place, as the page, 0 to 3, whose selected RAM page
    it patches, or as "side1" or "side2", and the offset, the old bytes and the
    new bytes."""

    def __init__(self, where, page, offset, old, new):
        self.where = where
        self.page = page
        self.offset = offset
        self.old = old
        self.new = new


def default_name(folder_name):
    """<GAME>: the folder name in upper case, cut to 8 letters and digits."""
    return re.sub(r"[^A-Z0-9]", "", folder_name.upper())[:8]


def read_patch(args, where):
    """A patch line's values: a place, the old bytes, >, the new bytes."""
    usage = f"{where}: patch takes a place, the old bytes, > and as many new bytes"
    if ">" not in args:
        raise GameFileError(usage)
    split = args.index(">")
    place, old, new = args[0], args[1:split], args[split + 1:]
    if not old or len(old) != len(new) or not all(re.fullmatch(r"[0-9A-Fa-f]{2}", b) for b in old + new):
        raise GameFileError(usage)
    ram = re.fullmatch(r"page([0-3]):([0-9A-Fa-f]{1,4})", place)
    tape = re.fullmatch(r"(side[12]):([0-9A-Fa-f]{1,6})", place)
    if ram:
        page, offset = int(ram.group(1)), ram.group(2)
        if int(offset, 16) + len(old) > 0x4000:
            raise GameFileError(f"{where}: the patch goes past the page's end")
    elif tape:
        page, offset = tape.groups()
    else:
        raise GameFileError(f"{where}: {place} is not a place: page<n>:<offset>, side1:<offset> or side2:<offset>")
    return Patch(where, page, int(offset, 16), bytes.fromhex("".join(old)), bytes.fromhex("".join(new)))


def number(text, where):
    try:
        value = float(text)
    except ValueError:
        raise GameFileError(f"{where}: {text} is not a time in seconds")
    if value < 0:
        raise GameFileError(f"{where}: the time {text} is negative")
    return value


def read_game(folder):
    path = os.path.join(folder, "game.txt")
    game = Game(folder)
    with open(path) as f:
        lines = f.read().splitlines()
    for number_, line in enumerate(lines, 1):
        where = f"{path}:{number_}"
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            words = shlex.split(line)
        except ValueError as e:
            raise GameFileError(f"{where}: {e}")
        key, args = words[0], words[1:]
        if key in ("cas", "side2", "name", "continue", "service", "capture", "rom") and len(args) != 1:
            raise GameFileError(f"{where}: {key} takes one value")
        if key == "cas":
            game.cas = args[0]
        elif key == "side2":
            game.side2 = args[0]
        elif key == "sha1":
            if not 1 <= len(args) <= 2 or not all(re.fullmatch(r"[0-9a-f]{40}", a) for a in args):
                raise GameFileError(f"{where}: sha1 takes one or two 40-digit SHA-1s")
            game.sha1 = args
        elif key == "name":
            if not re.fullmatch(r"[A-Z0-9]{1,8}", args[0]):
                raise GameFileError(f"{where}: name takes up to 8 capital letters and digits")
            game.name = args[0]
        elif key == "keys":
            if len(args) != 2:
                raise GameFileError(f"{where}: keys takes a time and a key name or a text")
            quoted = '"' in line.split(None, 2)[2]
            if not quoted and args[1] not in KEYS:
                raise GameFileError(f"{where}: {args[1]} is not a key name")
            game.keys.append((number(args[0], where), "text" if quoted else "key", args[1]))
        elif key == "continue":
            if args[0] not in KEYS:
                raise GameFileError(f"{where}: {args[0]} is not a key name")
            game.continue_key = args[0]
        elif key == "snapshot":
            if len(args) != 2 or args[0] != "at":
                raise GameFileError(f"{where}: snapshot takes at and a time")
            game.snapshot_at = number(args[1], where)
        elif key == "service":
            if args[0] != "no":
                raise GameFileError(f"{where}: service takes no")
            game.service_no = True
        elif key == "capture":
            game.capture = args[0]
        elif key == "rom":
            if args[0] != "keep":
                raise GameFileError(f"{where}: rom takes keep")
            game.rom_keep = True
        elif key == "patch":
            game.patches.append(read_patch(args, where))
        else:
            raise GameFileError(f"{where}: unknown key {key}")
    if game.cas is None:
        raise GameFileError(f"{path}: needs a cas line")
    return game
