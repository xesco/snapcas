"""Game files (docs/FILES.md, Game file).

A game file holds one setting per line: a key, a space and a value. A line that
starts with # is a comment, and blank lines are ignored. A machine's game file beside
game.txt, named after the machine file, adds the lines that fit only that machine.
"""
import math
import os
import re
import shlex
import urllib.parse

from msx import KEYS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The tape files that snapcas.py snap downloads, and the images that it moves
# there from the work folders.
# The tests set SNAPCAS_DOWNLOADS to their own tapes, so that make finds them
# there and downloads nothing.
DOWNLOADS = os.environ.get("SNAPCAS_DOWNLOADS", os.path.join(ROOT, "downloads"))
IMAGES = os.path.join(ROOT, "images")
# The user's own game files, each with its tape files, which git ignores.
CUSTOM = os.path.join(ROOT, "custom")


class GameFileError(Exception):
    """A game file that cannot be read, or a patch line whose old bytes are
    not where it puts them."""


class Game:
    def __init__(self, folder):
        self.folder = folder
        self.tape = None      # side 1's tape file, from cas or tsx
        self.side2 = None
        self.load = None      # the load command, for a tape whose first block is not standard
        self.start = None     # the name of the file on side 1 where the load starts
        self.sha1 = []
        self.urls = []        # the links to side 1's zip and side 2's, to download them
        self.name = default_name(os.path.basename(os.path.normpath(folder)))
        self.keys = []        # [(time, kind, value)], kind "key" or "text"
        self.continue_key = None
        self.snapshot_at = None
        # The service line's first word: None without the line, "no" when the
        # game never reads the rest of its tape, "t0" for the tape service
        # without a part in page 3, or "at".
        self.service = None
        # For service at xxE1, the entry page: the high byte, xx, of the
        # addresses of the service's part of page 3. Otherwise None.
        self.entry_page = None
        self.capture = None      # the machine file for the capture, if not the user's
        self.rom_keep = False    # rom keep: page 0 keeps the ROM, and T0 does not replace it
        self.patches = []     # [Patch]


class Patch:
    """A patch line: where the line is, its place, the old bytes and the new
    bytes. The place is an offset in a side of the tape, 1 or 2, or in the RAM
    page that the snapshot selects in a page, 0 to 3. The other of side and
    page is None."""

    def __init__(self, where, side, page, offset, old, new):
        self.where = where
        self.side = side
        self.page = page
        self.offset = offset
        self.old = old
        self.new = new

    @property
    def place(self):
        """The place as an error names it: side<n>:<offset> in the tape, or the
        address in memory."""
        if self.side is not None:
            return f"side{self.side}:{self.offset:X}"
        return f"{self.page * 0x4000 + self.offset:04X}"

    def apply(self, data):
        """Writes the new bytes over the old ones in data, the bytes of the
        patch's side or RAM page."""
        end = self.offset + len(self.old)
        if bytes(data[self.offset:end]) != self.old:
            raise GameFileError(f"{self.where}: the bytes at {self.place} are not the patch's old bytes")
        data[self.offset:end] = self.new


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
    tape = re.fullmatch(r"side([12]):([0-9A-Fa-f]{1,6})", place)
    side = page = None
    if ram:
        page, offset = int(ram.group(1)), ram.group(2)
        if int(offset, 16) + len(old) > 0x4000:
            raise GameFileError(f"{where}: the patch goes past the page's end")
    elif tape:
        side, offset = int(tape.group(1)), tape.group(2)
    else:
        raise GameFileError(f"{where}: {place} is not a place: page<n>:<offset>, side1:<offset> or side2:<offset>")
    return Patch(where, side, page, int(offset, 16), bytes.fromhex("".join(old)), bytes.fromhex("".join(new)))


def number(text, where):
    try:
        value = float(text)
    except ValueError:
        raise GameFileError(f"{where}: {text} is not a time in seconds")
    if not math.isfinite(value):
        raise GameFileError(f"{where}: {text} is not a time in seconds")
    if value < 0:
        raise GameFileError(f"{where}: the time {text} is negative")
    return value


def game_names():
    """The game files' folders below games/, in order: a game's, or a
    compilation's program's in its collection's folder, such as SUPERMSX/GOLF,
    for a folder without a game.txt (INTERNALS.md, A game later on the tape)."""
    games = os.path.join(ROOT, "games")
    names = []
    for name in sorted(os.listdir(games)):
        if os.path.isfile(os.path.join(games, name, "game.txt")):
            names.append(name)
        elif os.path.isdir(os.path.join(games, name)):
            names += [f"{name}/{n}" for n in sorted(os.listdir(os.path.join(games, name)))
                      if os.path.isfile(os.path.join(games, name, n, "game.txt"))]
    return names


def custom_names():
    """The custom games' names, custom/<game>, for each folder of custom/ that
    holds a game.txt, in order."""
    if not os.path.isdir(CUSTOM):
        return []
    return [f"custom/{name}" for name in sorted(os.listdir(CUSTOM))
            if os.path.isfile(os.path.join(CUSTOM, name, "game.txt"))]


def title(folder):
    """A game's title, which names the File-Hunter file that it comes from
    (FILES.md, Shipped files): a game's first comment line, its File-Hunter
    name, which is its zip's name or the zip's name, / and the CAS file in it.
    A compilation's program's first comment names the program before its first
    comma, as in "Africa Film, the fourth game on the tape Super MSX n.23", so
    its title is its zip's name, from its url line, / and that name. A CAS
    file whose name starts with its zip's name, as the zip's name with
    [LOADERFIX] added, is named by the zip alone. Or "" for a game file that
    starts with no comment."""
    with open(os.path.join(folder, "game.txt"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    comments = []
    for line in lines:
        if not line.startswith("#"):
            break
        comments.append(line[1:].strip())
    zips = next((line.split()[1:] for line in lines if line.startswith("url ")), [])
    if not comments:
        return ""
    # A compilation's program's folder is two levels below games/.
    below = os.path.relpath(os.path.abspath(folder), os.path.join(ROOT, "games"))
    if not below.startswith("..") and os.sep in below:
        program = " ".join(comments).split(",", 1)[0]
        if zips:
            return zip_name(zips[0]) + " / " + program
        return program
    zip_part, _, cas = comments[0].partition(" / ")
    if cas and os.path.splitext(cas)[0].startswith(zip_part):
        return zip_part
    return comments[0]


def zip_name(url):
    """The name of the zip file that a url links, without .zip."""
    return urllib.parse.unquote(url.rsplit("/", 1)[1]).rsplit(".", 1)[0]


def game_folder(game):
    """The folder of a game: a custom game's name, such as custom/MYGAME, or a
    folder below games/, such as ABADIA or a compilation's program,
    SUPERMSX/GOLF. A name that is neither is the path of a folder that holds a
    game.txt, as the tests give, so that a folder of the game's name below the
    current folder, as images/<machine>/ has, is not taken for the game."""
    if game.lower().startswith("custom/"):
        folder = os.path.join(CUSTOM, game.split("/", 1)[1])
    else:
        folder = os.path.join(ROOT, "games", game)
    if not os.path.isfile(os.path.join(folder, "game.txt")) and os.path.isfile(os.path.join(game, "game.txt")):
        return os.path.abspath(game)
    return folder


def game_key(folder):
    """The game's name below images/<machine>/ and out/work/<machine>/: a
    shipped game's path below games/, such as GAUNTLET or SUPERMSX/GOLF, a
    custom game's custom/<game>, or None for a folder elsewhere."""
    folder = os.path.abspath(folder)
    games = os.path.join(ROOT, "games")
    if os.path.commonpath([folder, games]) == games:
        return os.path.relpath(folder, games)
    if os.path.commonpath([folder, CUSTOM]) == CUSTOM:
        return "custom/" + os.path.relpath(folder, CUSTOM)
    return None


def is_custom(folder):
    """Whether the game in folder is a custom game, whose tapes are beside its
    game.txt."""
    return (game_key(folder) or "").startswith("custom/")


def out_folder(machine, folder):
    """The work folder of the game in folder: its snapshot, its image, its check
    and the build's reports. A shipped or custom game's is
    out/work/<machine>/<game>/, where <game> is its game_key, so that two
    collections' programs of the same name stay apart. A game folder elsewhere,
    as the tests make, holds its own, <folder>/<machine>/."""
    key = game_key(folder)
    if key is None:
        return os.path.join(os.path.abspath(folder), machine)
    return os.path.join(ROOT, "out", "work", machine, key)


def image_path(machine, folder, name):
    """The image that build.py writes, <name>.SNP in the game's work folder."""
    return os.path.join(out_folder(machine, folder), f"{name}.SNP")


def published_path(machine, folder, name):
    """A shipped or custom game's image that snapcas.py snap moves to
    images/<machine>/<game>/<name>.SNP, or None for a game folder elsewhere."""
    key = game_key(folder)
    return None if key is None else os.path.join(IMAGES, machine, key, f"{name}.SNP")


def publish(machine, folder):
    """Moves a shipped or custom game's image from its work folder to
    images/<machine>/<game>/, where the user takes it, and returns its path, or
    None for a game folder elsewhere, whose image stays."""
    name = read_game(folder, machine).name
    target = published_path(machine, folder, name)
    if target is None:
        return None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(image_path(machine, folder, name), target)
    return target


def machine_file(folder, machine):
    """The path of a machine's file in a game's folder: phc28s-ram64k-carnivore2 has
    phc28s-ram64k-carnivore2.txt, and a test machine's path has - for /."""
    return os.path.join(folder, machine.replace("/", "-") + ".txt")


def read_game(folder, machine=None):
    """The game of folder's game.txt, then of the machine's file there, when
    machine is given and the file exists."""
    path = os.path.join(folder, "game.txt")
    game = Game(folder)
    with open(path, encoding="utf-8") as f:
        lines = [(path, n, line) for n, line in enumerate(f.read().splitlines(), 1)]
    if machine is not None and os.path.exists(machine_file(folder, machine)):
        with open(machine_file(folder, machine), encoding="utf-8") as f:
            lines += [(machine_file(folder, machine), n, line) for n, line in enumerate(f.read().splitlines(), 1)]
    service_files = set()
    for file, number_, line in lines:
        where = f"{file}:{number_}"
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            words = shlex.split(line)
        except ValueError as e:
            raise GameFileError(f"{where}: {e}")
        key, args = words[0], words[1:]
        if key in ("cas", "tsx", "side2", "load", "start", "name", "continue", "capture", "rom") and len(args) != 1:
            raise GameFileError(f"{where}: {key} takes one value")
        if key in ("cas", "tsx"):
            if game.tape is not None:
                raise GameFileError(f"{where}: a game file has one cas or tsx line")
            if os.path.splitext(args[0])[1].lower() != "." + key:
                raise GameFileError(f"{where}: {key} takes a .{key.upper()} file")
            game.tape = args[0]
        elif key == "load":
            game.load = args[0]
        elif key == "start":
            game.start = args[0]
        elif key == "side2":
            game.side2 = args[0]
        elif key == "sha1":
            if not 1 <= len(args) <= 2 or not all(re.fullmatch(r"[0-9a-f]{40}", a) for a in args):
                raise GameFileError(f"{where}: sha1 takes one or two 40-digit SHA-1s")
            game.sha1 = args
        elif key == "url":
            if not 1 <= len(args) <= 2 or not all(re.fullmatch(r"https://\S+\.(zip|ZIP)", a) for a in args):
                raise GameFileError(f"{where}: url takes one or two https links to zip files")
            game.urls = args
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
            try:
                args[1].encode("latin-1")
            except UnicodeEncodeError:
                raise GameFileError(f"{where}: the text holds a character that is not in Latin-1")
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
            # One line in each file, and the machine's file's replaces
            # game.txt's.
            if file in service_files:
                raise GameFileError(f"{where}: a file holds one service line")
            service_files.add(file)
            if args in (["no"], ["t0"]):
                game.service, game.entry_page = args[0], None
            elif len(args) == 2 and args[0] == "at" and re.fullmatch(r"[C-Fc-f][0-9A-Fa-f][Ee]1", args[1]):
                game.service, game.entry_page = "at", int(args[1][:2], 16)
                if game.entry_page == 0xFF:
                    raise GameFileError(f"{where}: a part of the tape service at FFE1h would pass FFFEh, "
                                        "the last byte that it can take")
            else:
                raise GameFileError(f"{where}: service takes no, at and an address xxE1 in page 3, or t0")
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
    if game.tape is None:
        raise GameFileError(f"{path}: needs a cas or tsx line")
    if not game.name:
        raise GameFileError(f"{path}: the folder's name has no letter or digit for the image's name, so the "
                            "game file needs a name line")
    if game.side2 and os.path.splitext(game.side2)[1].lower() != os.path.splitext(game.tape)[1].lower():
        raise GameFileError(f"{path}: side2 takes a file of side 1's format")
    if game.urls and len(game.urls) != (2 if game.side2 else 1):
        raise GameFileError(f"{path}: url takes a link for each side")
    # rom keep leaves the game only the entries in page 3, which service t0
    # removes (FILES.md, Game file).
    if game.rom_keep and game.service == "t0":
        raise GameFileError(f"{folder}: rom keep needs the tape service's part of page 3, so it cannot "
                            "go with service t0")
    return game
