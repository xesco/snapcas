"""A finding of an automatic patch kind (docs/INTERNALS.md, The tools' code)."""


class Finding:
    """Code found at an offset: what it is, its bytes, and the patched bytes,
    or None when it is only listed. place is the offset in the patched bytes
    of the one that the restorer fills in, because its value depends on the
    machine that restores the image (docs/FORMATS.md, Image), or None."""

    def __init__(self, what, offset, old, new, place=None):
        self.what = what
        self.offset = offset
        self.old = old
        self.new = new
        self.place = place

    def line(self, place):
        """The finding in a patch line's form, after its place. The byte that
        the restorer fills in shows as nn."""
        text = f"{place}:{self.offset:04X} {self.old.hex(' ').upper()}"
        if self.new is not None:
            new = self.new.hex(" ").upper().split()
            if self.place is not None:
                new[self.place] = "nn"
            text += f" > {' '.join(new)}"
        return f"{text}  {self.what}"
