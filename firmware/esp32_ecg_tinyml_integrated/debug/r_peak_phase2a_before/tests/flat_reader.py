"""Read-only FlatBuffer arithmetic diagnostics, stdlib only."""
import struct
class Flat:
    """Read-only subset of TFLite schema, using bounds-checked scalar reads."""
    def __init__(self, data):
        self.data = data

    def read(self, fmt, pos):
        if pos < 0 or pos + struct.calcsize(fmt) > len(self.data):
            raise ValueError("FlatBuffer offset out of range")
        return struct.unpack_from(fmt, self.data, pos)[0]

    def field(self, table, slot):
        vt = table - self.read("<i", table)
        entry = vt + 4 + slot * 2
        off = self.read("<H", entry) if entry + 2 <= vt + self.read("<H", vt) else 0
        return table + off if off else None

    def scalar(self, table, slot, fmt="<I", default=0):
        pos = self.field(table, slot)
        return self.read(fmt, pos) if pos is not None else default

    def ref(self, table, slot):
        pos = self.field(table, slot)
        return pos + self.read("<I", pos) if pos is not None else None

    def vector(self, table, slot, fmt="<i", tables=False):
        pos = self.ref(table, slot)
        if pos is None:
            return []
        size = 4 if tables else struct.calcsize(fmt)
        count = self.read("<I", pos)
        if count > len(self.data) // size:
            raise ValueError("Invalid vector length")
        start = pos + 4
        return [start + i * 4 + self.read("<I", start + i * 4) if tables
                else self.read(fmt, start + i * size) for i in range(count)]

    def string(self, table, slot):
        pos = self.ref(table, slot)
        if pos is None:
            return ""
        size = self.read("<I", pos)
        if pos + 4 + size > len(self.data):
            raise ValueError("Invalid string")
        return self.data[pos + 4:pos + 4 + size].decode("utf-8")
