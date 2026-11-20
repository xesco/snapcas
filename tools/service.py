"""Reader and relocator for bin/SERVICE.BIN (docs/FORMATS.md, SERVICE.BIN)."""
import os
import struct

import paths
from resident import BuildError, TAIL_SIZE

SERVICE = os.path.join(paths.BIN, "SERVICE.BIN")
SERVICE_VERSION = 20
# The image's mark without its last character, the format's number, which is
# SERVICE.BIN's symbol IMAGE_FORMAT (src/service.inc).
MARK = b"SNAPCAS"

# SERVICE.BIN's parts, in the order of its table (docs/FORMATS.md, SERVICE.BIN).
PARTS = ("tail", "stubs", "page3", "code", "t0", "call", "symbols", "relocs", "coderelocs")


class Service:
    """SERVICE.BIN: its parts' bytes and assembly symbols, relocated to an
    entry page and optional split code block address."""

    def __init__(self, data, entry_page=None, code_at=None):
        self.source = bytes(data)
        data = bytearray(data)
        table = dict(zip(PARTS, struct.iter_unpack("<HH", bytes(data[2:2 + 4 * len(PARTS)]))))
        self.assembled = self.read_symbols(data, *table["symbols"])["E_PAGE"]
        offset, length = table["relocs"]
        for (n,) in struct.iter_unpack("<H", bytes(data[offset:offset + length])):
            data[n] = (data[n] + (self.assembled if entry_page is None else entry_page) - self.assembled) & 0xFF
        self.code_follows = self.read_symbols(data, *table["symbols"])["P3_CODE"]
        if code_at is not None:
            offset, length = table["coderelocs"]
            for (n,) in struct.iter_unpack("<H", bytes(data[offset:offset + length])):
                value = struct.unpack_from("<H", data, n)[0]
                struct.pack_into("<H", data, n, (value + code_at - self.code_follows) & 0xFFFF)
        self.parts = {name: bytes(data[offset:offset + length]) for name, (offset, length) in table.items()}
        self.symbols = self.read_symbols(data, *table["symbols"])
        self.entry_page = self.symbols["E_PAGE"]

    @staticmethod
    def read_symbols(data, offset, length):
        """The symbols' part as {name: value}: 2-byte value, 1-byte length, ASCII name."""
        symbols, at = {}, offset
        while at < offset + length:
            value, size = struct.unpack_from("<HB", data, at)
            symbols[bytes(data[at + 3:at + 3 + size]).decode("ascii")] = value
            at += 3 + size
        return symbols

    def __getitem__(self, name):
        """A symbol's value."""
        if name not in self.symbols:
            raise BuildError(f"SERVICE.BIN has no symbol {name}: build it from this snapcas")
        return self.symbols[name]

    def field(self, name, t0_mode):
        """Address of a service data field (src/tape.inc) in code segment or T0."""
        return self[("t0m." if t0_mode else "") + name]

    def at(self, entry_page, code_at=None):
        """This SERVICE.BIN relocated to entry_page and optional split code_at."""
        return Service(self.source, entry_page, code_at)

    @property
    def split(self):
        """Whether the page-3 code block is separated from its entries."""
        return self["P3_CODE"] != self.code_follows

    def blocks(self):
        """The page-3 part's two blocks as [(first_address, bytes)]."""
        part = self.parts["page3"]
        cut = self.code_follows - self["E_ENTRY"]
        return [(self["E_ENTRY"], part[:cut]), (self["P3_CODE"], part[cut:])]

    @property
    def mark(self):
        """The image's 8-byte mark: MARK plus IMAGE_FORMAT."""
        return MARK + bytes([self["IMAGE_FORMAT"]])

    @property
    def moved(self):
        """Whether the page-3 part was relocated from its assembled layout."""
        return self.entry_page != self.assembled or self.split


def read_service(path):
    """Loads SERVICE.BIN and checks its version byte, part count, and tail size."""
    with open(path, "rb") as f:
        data = f.read()
    if not data or data[0] != SERVICE_VERSION:
        raise BuildError(f"{path}: version {data[0] if data else 'none'}, "
                         f"expected {SERVICE_VERSION}: build it from this snapcas")
    if data[1] != len(PARTS):
        raise BuildError(f"{path}: {data[1]} parts, expected {len(PARTS)}: build it from this snapcas")
    service = Service(data)
    if len(service.parts["tail"]) != TAIL_SIZE:
        raise BuildError(f"{path}: a tail of {len(service.parts['tail'])} bytes, expected {TAIL_SIZE}: "
                         "build it from this snapcas")
    return service
