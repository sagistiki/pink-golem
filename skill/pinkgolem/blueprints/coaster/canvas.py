"""canvas.py — a tiny RGBA image for the coaster tools (no dependencies): pixels, straight lines, rectangles, a 3×5
digit font for plot labels, and PNG output. It draws exactly like PIL's putpixel / ImageDraw.line (1 px) /
ImageDraw.rectangle(outline=…), so textures come out the same as they would with Pillow.
"""
import struct
import zlib

FONT = {  # 3×5 glyphs, rows top → bottom, bit 2 = left column
    "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 7, 1, 7), "4": (5, 5, 7, 1, 1),
    "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 1, 1), "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
    "-": (0, 0, 7, 0, 0), ".": (0, 0, 0, 0, 2), " ": (0, 0, 0, 0, 0),
}


class Canvas:
    def __init__(self, w, h, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(_rgba(bg)) * (w * h))

    def put(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i:i + 4] = bytes(_rgba(c))

    def get(self, x, y):
        i = (y * self.w + x) * 4
        return tuple(self.px[i:i + 4])

    def line(self, x0, y0, x1, y1, c, width=1):
        """Bresenham line between two points (both ends drawn); width > 1 stamps a square brush."""
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err, r = dx + dy, (width - 1) // 2
        while True:
            for ox in range(-r, width - r):
                for oy in range(-r, width - r):
                    self.put(x0 + ox, y0 + oy, c)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x0, y0, x1, y1, outline=None, fill=None):
        """Inclusive corners, like ImageDraw.rectangle."""
        if fill is not None:
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    self.put(x, y, fill)
        if outline is not None:
            for x in range(x0, x1 + 1):
                self.put(x, y0, outline)
                self.put(x, y1, outline)
            for y in range(y0, y1 + 1):
                self.put(x0, y, outline)
                self.put(x1, y, outline)

    def text(self, x, y, s, c, scale=1):
        """Digits, '-', '.' and spaces in a 3×5 font (enough for axis labels)."""
        for ch in str(s):
            rows = FONT.get(ch, FONT[" "])
            for j, bits in enumerate(rows):
                for i in range(3):
                    if bits & (4 >> i):
                        for a in range(scale):
                            for b in range(scale):
                                self.put(x + i * scale + a, y + j * scale + b, c)
            x += 4 * scale

    def save(self, path):
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 4:(y + 1) * self.w * 4]) for y in range(self.h))

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
        return path


def _rgba(c):
    c = tuple(int(v) for v in c)
    return c if len(c) == 4 else c + (255,)
