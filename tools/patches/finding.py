"""A finding of an automatic patch kind (docs/DESIGN.md, The tools' code)."""


class Finding:
    """Code found at an offset: what it is, its bytes, and the patched bytes,
    or None when it is only listed."""

    def __init__(self, what, offset, old, new):
        self.what = what
        self.offset = offset
        self.old = old
        self.new = new

    def line(self, place):
        """The finding in a patch line's form, after its place."""
        text = f"{place}:{self.offset:04X} {self.old.hex(' ').upper()}"
        if self.new is not None:
            text += f" > {self.new.hex(' ').upper()}"
        return f"{text}  {self.what}"
