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
        self.patches = []     # [(place, old, new)]


def default_name(folder_name):
    """<GAME>: the folder name in upper case, cut to 8 letters and digits."""
    return re.sub(r"[^A-Z0-9]", "", folder_name.upper())[:8]


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
        if key in ("cas", "side2", "name", "continue", "service", "capture") and len(args) != 1:
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
        elif key == "patch":
            game.patches.append((where, line))
        else:
            raise GameFileError(f"{where}: unknown key {key}")
    if game.cas is None:
        raise GameFileError(f"{path}: needs a cas line")
    return game
